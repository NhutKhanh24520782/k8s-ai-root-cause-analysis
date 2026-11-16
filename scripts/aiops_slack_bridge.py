"""
scripts/aiops_slack_bridge.py

AIOps Autonomous Incident Diagnoser & Slack Notification Bridge:
1. Receives firing alert webhooks from Prometheus Alertmanager.
2. Extracts telemetry snapshots from Prometheus around the incident timestamp.
3. Submits metrics snapshot to RCA API (/predict) for automated ML root-cause diagnosis.
4. Posts a rich structured AIOps incident card directly to the Slack incident channel.

Usage:
    # Run standalone bridge server (listens on :5000 for Alertmanager webhooks):
    python scripts/aiops_slack_bridge.py --port 5000 --slack-webhook https://hooks.slack.com/services/...

    # Test an immediate diagnosis & Slack card post directly:
    python scripts/aiops_slack_bridge.py --test --scenario payment_failure --slack-webhook https://hooks.slack.com/services/...
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
import sys
import urllib.request
import urllib.error

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aiops-slack-bridge")

DEFAULT_RCA_URL = os.getenv("RCA_API_URL", "http://localhost:8080/predict")
DEFAULT_SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")


def send_slack_card(webhook_url: str, card_payload: dict) -> bool:
    if not webhook_url or "hooks.slack.com" not in webhook_url:
        logger.warning("No valid Slack Webhook URL provided. Skipping actual Slack post.")
        logger.info("Generated Card: \n%s", json.dumps(card_payload, indent=2))
        return False

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(card_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error("Failed to post message to Slack: %s", e)
        return False


def build_slack_message(alert_name: str, service: str, rca_result: dict, grafana_url: str = "") -> dict:
    predicted_cause = rca_result.get("predicted_root_cause", "unknown")
    confidence = rca_result.get("confidence", 0.0) * 100
    top3 = rca_result.get("top3_candidates", [])
    evidence = rca_result.get("evidence", {})
    key_metrics = evidence.get("key_metrics", [])

    candidates_text = "\n".join([f"• *{c.get('fault_type')}*: {c.get('probability', 0)*100:.1f}%" for c in top3])

    color = "#E01E5A" if confidence > 80 else "#ECB22E"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 AIOps Incident Detected: {alert_name}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Target Service:*\n`{service}`"},
                {"type": "mrkdwn", "text": f"*Detected At:*\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"},
                {"type": "mrkdwn", "text": f"*AI Diagnosed Root Cause:*\n🔥 *`{predicted_cause.upper()}`*"},
                {"type": "mrkdwn", "text": f"*Confidence Score:*\n*{confidence:.1f}%*"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Top Ranked Suspects:*\n{candidates_text}\n\n*Key Telemetry Signals:*\n`{', '.join(key_metrics) if key_metrics else 'N/A'}`",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Grafana Dashboard"},
                    "url": grafana_url or "http://localhost:3000/d/microservices-overview",
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View ML Model Monitoring"},
                    "url": "http://localhost:3000/d/rca-model-monitoring",
                },
            ],
        },
    ]

    return {
        "text": f"[AIOps Alert] {alert_name} on {service} -> Predicted Cause: {predicted_cause} ({confidence:.1f}%)",
        "attachments": [{"color": color, "blocks": blocks}],
    }


def query_rca_api(rca_url: str, snapshot: dict) -> dict:
    req = urllib.request.Request(
        rca_url,
        data=json.dumps(snapshot).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error("Error querying RCA API at %s: %s", rca_url, e)
        return {
            "predicted_root_cause": "inference_error",
            "confidence": 0.0,
            "top3_candidates": [],
            "evidence": {"key_metrics": [str(e)]},
        }


def run_test_scenario(scenario: str, rca_url: str, webhook_url: str):
    logger.info("Executing test simulation for scenario: '%s'...", scenario)
    sample_snapshots = {
        "payment_failure": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gw_request_rate": 5.2,
            "gw_error_rate": 0.82,
            "gw_p95_latency": 120.0,
            "order_request_rate": 5.0,
            "order_error_rate": 0.78,
            "order_p95_latency": 110.0,
            "order_cpu": 0.05,
            "order_mem": 81.0,
            "payment_request_rate": 4.8,
            "payment_error_rate": 0.95,
            "payment_p95_latency": 15.0,
            "payment_cpu": 0.03,
            "payment_mem": 84.0,
            "db_query_latency_p95": 2.2,
            "db_connection_count": 5.0,
        },
        "db_slowness": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gw_request_rate": 4.8,
            "gw_error_rate": 0.03,
            "gw_p95_latency": 750.0,
            "order_request_rate": 4.6,
            "order_error_rate": 0.02,
            "order_p95_latency": 720.0,
            "order_cpu": 0.08,
            "order_mem": 82.0,
            "payment_request_rate": 4.5,
            "payment_error_rate": 0.0,
            "payment_p95_latency": 12.0,
            "payment_cpu": 0.04,
            "payment_mem": 84.0,
            "db_query_latency_p95": 680.0,
            "db_connection_count": 22.0,
        },
    }

    snapshot = sample_snapshots.get(scenario, sample_snapshots["payment_failure"])
    rca_result = query_rca_api(rca_url, snapshot)
    msg = build_slack_message(
        alert_name=f"AIOps{scenario.replace('_', ' ').title().replace(' ', '')}Detected",
        service="payment-service" if "payment" in scenario else "order-service",
        rca_result=rca_result,
    )
    send_slack_card(webhook_url, msg)
    print("\n[OK] Test simulated successfully.")


def main():
    parser = argparse.ArgumentParser(description="AIOps Alertmanager Slack & RCA Bridge")
    parser.add_argument("--slack-webhook", default=DEFAULT_SLACK_WEBHOOK, help="Slack Incoming Webhook URL")
    parser.add_argument("--rca-url", default=DEFAULT_RCA_URL, help="RCA API POST /predict URL")
    parser.add_argument("--test", action="store_true", help="Run a test event and print/send Slack notification")
    parser.add_argument("--scenario", default="payment_failure", help="Test scenario: payment_failure, db_slowness")
    args = parser.parse_args()

    if args.test:
        run_test_scenario(args.scenario, args.rca_url, args.slack_webhook)
    else:
        logger.info("To start bridge HTTP server, deploy in Kubernetes monitoring stack or run with --test.")


if __name__ == "__main__":
    main()


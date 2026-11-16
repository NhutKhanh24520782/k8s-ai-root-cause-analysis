import argparse
import json
import os
import sys
import time
import urllib.request

def send_slack_card(webhook_url: str, alert_name: str, service: str, predicted_rca: str, confidence: float, candidates: list, evidence: dict):
    percentage = round(confidence * 100, 1)

    candidate_text = "\n".join([
        f"• *{c.get('fault_type')}*: {round(c.get('probability', 0) * 100, 1)}%"
        for c in candidates[:3]
    ])

    blocks = [
        {
            "text": {
                "text": f"🚨 [AIOps Incident] {alert_name}",
                "emoji": True,
            },
        },
        {
            "fields": [
            ],
        },
        {
            "text": {
                "text": f"*Top Ranked Root Causes:*\n{candidate_text}",
            },
        },
        {
            "elements": [
                {
                    "text": f"⏱ *Timestamp:* {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())} | *Project:* AIOps K8s Root Cause Analysis",
                }
            ],
        },
    ]

    payload = json.dumps({"blocks": blocks}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[OK] Slack notification sent (Status: {resp.status})")
            return True
    except Exception as exc:
        print(f"[ERR] Failed to send Slack message: {exc}", file=sys.stderr)
        return False

def test_mock_diagnosis(webhook_url: str):
    print("[*] Running sample incident diagnosis bridge test...")
    sample_candidates = [
    ]
    sample_evidence = {
        "key_metrics": ["db_query_latency_p95", "order_p95_latency"],
    }
    send_slack_card(
        webhook_url=webhook_url,
        alert_name="AIOpsDatabaseQuerySlow",
        service="order-service",
        predicted_rca="db_slowness",
        confidence=0.964,
        candidates=sample_candidates,
        evidence=sample_evidence,
    )

def main():
    parser = argparse.ArgumentParser(description="AIOps Alertmanager Slack Bridge.")
    parser.add_argument("--webhook", default=os.getenv("SLACK_WEBHOOK_URL", ""), help="Slack Webhook URL")
    parser.add_argument("--test", action="store_true", help="Send mock test notification to Slack")
    args = parser.parse_args()

    if not args.webhook:
        print("[WARN] No Slack Webhook URL provided. Specify --webhook or SLACK_WEBHOOK_URL env var.")
        return

    if args.test:
        test_mock_diagnosis(args.webhook)

if __name__ == "__main__":
    main()

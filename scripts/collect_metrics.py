"""
scripts/collect_metrics.py

Collects the 15 required observability metrics from Prometheus in real-time.
Supports:
1. Appending labeled snapshots to a dataset CSV for model training/evaluation.
2. Directly streaming snapshots to the RCA API (/predict) for live testing.

Usage:
    # 1. Collect 10 snapshots of baseline metrics into dataset CSV:
    python scripts/collect_metrics.py --count 10 --interval 15 --fault-type normal --run-id run_01 --output ml/data/dataset_live.csv

    # 2. Query Prometheus and immediately send to RCA API for live diagnosis:
    python scripts/collect_metrics.py --count 1 --send-to-api --rca-url http://localhost:8080/predict
"""

import argparse
from datetime import datetime, timezone
import json
import os
import sys
import time
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request
import pandas as pd


METRIC_PROMQL_QUERIES = {
    "gw_request_rate": 'sum(rate(http_requests_total{service="api-gateway"}[1m])) or vector(0)',
    "gw_error_rate": (
        'sum(rate(http_requests_total{service="api-gateway",status=~"5.."}[1m])) '
        '/ clamp_min(sum(rate(http_requests_total{service="api-gateway"}[1m])), 0.001) or vector(0)'
    ),
    "gw_p95_latency": (
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="api-gateway"}[1m]))) * 1000 or vector(0)'
    ),
    "order_request_rate": 'sum(rate(http_requests_total{service="order-service"}[1m])) or vector(0)',
    "order_error_rate": (
        'sum(rate(http_requests_total{service="order-service",status=~"5.."}[1m])) '
        '/ clamp_min(sum(rate(http_requests_total{service="order-service"}[1m])), 0.001) or vector(0)'
    ),
    "order_p95_latency": (
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="order-service"}[1m]))) * 1000 or vector(0)'
    ),
    "order_cpu": (
        'sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{container="order-service"}) '
        'or sum(rate(container_cpu_usage_seconds_total{container="order-service"}[1m])) or vector(0)'
    ),
    "order_mem": (
        'sum(container_memory_working_set_bytes{container="order-service"}) / 1048576 or vector(0)'
    ),
    "payment_request_rate": 'sum(rate(http_requests_total{service="payment-service"}[1m])) or vector(0)',
    "payment_error_rate": (
        'sum(rate(http_requests_total{service="payment-service",status=~"5.."}[1m])) '
        '/ clamp_min(sum(rate(http_requests_total{service="payment-service"}[1m])), 0.001) or vector(0)'
    ),
    "payment_p95_latency": (
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="payment-service"}[1m]))) * 1000 or vector(0)'
    ),
    "payment_cpu": (
        'sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{container="payment-service"}) '
        'or sum(rate(container_cpu_usage_seconds_total{container="payment-service"}[1m])) or vector(0)'
    ),
    "payment_mem": (
        'sum(container_memory_working_set_bytes{container="payment-service"}) / 1048576 or vector(0)'
    ),
    "db_query_latency_p95": (
        'histogram_quantile(0.95, sum by (le) (rate(db_query_duration_seconds_bucket[1m]))) * 1000 or vector(0)'
    ),
    "db_connection_count": (
        'sum(pg_stat_activity_count) or vector(0)'
    ),
}


def query_prometheus_scalar(prom_url: str, query: str) -> float:
    """Executes instant PromQL query and returns a single float scalar value."""
    encoded = urllib.parse.urlencode({"query": query})
    url = f"{prom_url.rstrip('/')}/api/v1/query?{encoded}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RCA-Metric-Collector"})
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") != "success":
                return 0.0

            result = payload.get("data", {}).get("result", [])
            if not result:
                return 0.0

            val = result[0].get("value", [0, 0])[1]
            return float(val) if val != "NaN" else 0.0
    except Exception as e:
        return 0.0


def collect_snapshot(prom_url: str) -> Dict[str, float]:
    """Queries Prometheus for all 15 metrics."""
    snapshot = {}
    for metric_name, query in METRIC_PROMQL_QUERIES.items():
        snapshot[metric_name] = round(query_prometheus_scalar(prom_url, query), 4)
    return snapshot


def send_to_rca_api(api_url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Posts telemetry snapshot to RCA API /predict."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "RCA-Collector"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[ERR] Failed to send snapshot to RCA API: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Collect Prometheus telemetry for RCA ML pipeline.")
    parser.add_argument("--prom-url", default="http://localhost:9090", help="Prometheus base URL")
    parser.add_argument("--interval", type=int, default=15, help="Collection interval in seconds")
    parser.add_argument("--count", type=int, default=1, help="Number of snapshots to collect (0 for infinite)")
    parser.add_argument("--fault-type", default="normal", help="Ground-truth fault label for dataset")
    parser.add_argument("--run-id", default=f"run_{int(time.time())}", help="Unique run identifier")
    parser.add_argument("--output", default="ml/data/dataset_live.csv", help="CSV path to append records")
    parser.add_argument("--send-to-api", action="store_true", help="Send snapshot to RCA API for live prediction")
    parser.add_argument("--rca-url", default="http://localhost:8080/predict", help="RCA API prediction URL")
    args = parser.parse_args()

    print(f"[*] Starting telemetry collection from {args.prom_url}...")
    print(f"[*] Target fault label: '{args.fault_type}' | Run ID: '{args.run_id}'")

    collected = 0
    while args.count == 0 or collected < args.count:
        iso_now = datetime.now(timezone.utc).isoformat()
        metrics = collect_snapshot(args.prom_url)

        record = {
            "timestamp": iso_now,
            "fault_type": args.fault_type,
            "run_id": args.run_id,
            **metrics,
        }

        # Save to CSV
        df = pd.DataFrame([record])
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        file_exists = os.path.exists(args.output)
        df.to_csv(args.output, mode="a", index=False, header=not file_exists)

        print(f"[{iso_now}] Snapshot #{collected + 1}: gw_rps={metrics['gw_request_rate']:.1f}, "
              f"gw_err={metrics['gw_error_rate']:.2f}, order_cpu={metrics['order_cpu']:.3f}, "
              f"db_p95={metrics['db_query_latency_p95']:.1f}ms")

        if args.send_to_api:
            res = send_to_rca_api(args.rca_url, record)
            if res:
                print(f"  --> [RCA PREDICTION]: Cause='{res.get('predicted_root_cause')}' "
                      f"(Confidence: {res.get('confidence', 0)*100:.1f}%) | Top: {res.get('top3_candidates')}")

        collected += 1
        if args.count == 0 or collected < args.count:
            time.sleep(args.interval)

    print(f"[OK] Completed collection of {collected} snapshots saved to {args.output}.")


if __name__ == "__main__":
    main()


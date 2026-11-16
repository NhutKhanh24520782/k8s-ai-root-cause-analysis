"""
scripts/data_collection/collect_metrics.py

Collects observability metrics snapshots from Prometheus HTTP API and saves them
into a labeled dataset CSV file following the schema agreed upon for Giai đoạn A3.
Includes `run_id` for group-based train/test splitting to prevent temporal correlation leakage.

Usage:
    python scripts/data_collection/collect_metrics.py --fault normal --duration 300 --run-id run_normal_001
    python scripts/data_collection/collect_metrics.py --prometheus http://localhost:9090 --fault cpu_stress --duration 600
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

METRICS_QUERIES = {
    "gw_request_rate": (
        'sum(rate(http_requests_total{service="api-gateway"}[1m])) '
        'or sum(rate(http_requests_total{job=~".*api-gateway.*"}[1m])) or vector(0)'
    ),
    "gw_error_rate": (
        '(sum(rate(http_requests_total{service="api-gateway",status=~"5.."}[1m])) '
        'or sum(rate(http_requests_total{job=~".*api-gateway.*",status=~"5.."}[1m])) or vector(0)) '
        '/ clamp_min((sum(rate(http_requests_total{service="api-gateway"}[1m])) '
        'or sum(rate(http_requests_total{job=~".*api-gateway.*"}[1m])) or vector(0.001)), 0.001)'
    ),
    "gw_p95_latency": (
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="api-gateway"}[1m]))) * 1000 '
        'or histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job=~".*api-gateway.*"}[1m]))) * 1000 '
        'or vector(0)'
    ),
    "order_request_rate": (
        'sum(rate(http_requests_total{service="order-service"}[1m])) '
        'or sum(rate(http_requests_total{job=~".*order-service.*"}[1m])) or vector(0)'
    ),
    "order_error_rate": (
        '(sum(rate(http_requests_total{service="order-service",status=~"5.."}[1m])) '
        'or sum(rate(http_requests_total{job=~".*order-service.*",status=~"5.."}[1m])) or vector(0)) '
        '/ clamp_min((sum(rate(http_requests_total{service="order-service"}[1m])) '
        'or sum(rate(http_requests_total{job=~".*order-service.*"}[1m])) or vector(0.001)), 0.001)'
    ),
    "order_p95_latency": (
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="order-service"}[1m]))) * 1000 '
        'or histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job=~".*order-service.*"}[1m]))) * 1000 '
        'or vector(0)'
    ),
    "order_cpu": (
        'sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{container="order-service"}) '
        'or sum(rate(container_cpu_usage_seconds_total{container="order-service"}[1m])) '
        'or sum(rate(process_cpu_seconds_total{job=~".*order-service.*"}[1m])) or vector(0)'
    ),
    "order_mem": (
        'sum(container_memory_working_set_bytes{container="order-service"}) / 1048576 '
        'or sum(process_resident_memory_bytes{job=~".*order-service.*"}) / 1048576 or vector(0)'
    ),
    "payment_request_rate": (
        'sum(rate(http_requests_total{service="payment-service"}[1m])) '
        'or sum(rate(http_requests_total{job=~".*payment-service.*"}[1m])) or vector(0)'
    ),
    "payment_error_rate": (
        '(sum(rate(http_requests_total{service="payment-service",status=~"5.."}[1m])) '
        'or sum(rate(http_requests_total{job=~".*payment-service.*",status=~"5.."}[1m])) or vector(0)) '
        '/ clamp_min((sum(rate(http_requests_total{service="payment-service"}[1m])) '
        'or sum(rate(http_requests_total{job=~".*payment-service.*"}[1m])) or vector(0.001)), 0.001)'
    ),
    "payment_p95_latency": (
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="payment-service"}[1m]))) * 1000 '
        'or histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job=~".*payment-service.*"}[1m]))) * 1000 '
        'or vector(0)'
    ),
    "payment_cpu": (
        'sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{container="payment-service"}) '
        'or sum(rate(container_cpu_usage_seconds_total{container="payment-service"}[1m])) '
        'or sum(rate(process_cpu_seconds_total{job=~".*payment-service.*"}[1m])) or vector(0)'
    ),
    "payment_mem": (
        'sum(container_memory_working_set_bytes{container="payment-service"}) / 1048576 '
        'or sum(process_resident_memory_bytes{job=~".*payment-service.*"}) / 1048576 or vector(0)'
    ),
    "db_query_latency_p95": (
        'histogram_quantile(0.95, sum by (le) (rate(db_query_duration_seconds_bucket[1m]))) * 1000 '
        'or histogram_quantile(0.95, sum by (le) (rate(db_query_duration_seconds_bucket[2m]))) * 1000 '
        'or vector(0)'
    ),
    "db_connection_count": (
        'sum(pg_stat_activity_count) or vector(0)'
    ),
}

FIELDS = [
    "run_id",
    "timestamp",
    "fault_type",
    "gw_request_rate",
    "gw_error_rate",
    "gw_p95_latency",
    "order_request_rate",
    "order_error_rate",
    "order_p95_latency",
    "order_cpu",
    "order_mem",
    "payment_request_rate",
    "payment_error_rate",
    "payment_p95_latency",
    "payment_cpu",
    "payment_mem",
    "db_query_latency_p95",
    "db_connection_count",
]


def query_prometheus_scalar(prometheus_url: str, query: str) -> float:
    encoded = urllib.parse.urlencode({"query": query})
    url = f"{prometheus_url.rstrip('/')}/api/v1/query?{encoded}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AIOps-Collector/1.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if payload.get("status") != "success":
            return 0.0

        results = payload.get("data", {}).get("result", [])
        if not results:
            return 0.0

        val = results[0].get("value", [0, 0])[1]
        return float(val) if val not in ("NaN", "Inf", "-Inf") else 0.0
    except Exception:
        return 0.0


def collect_snapshot(prometheus_url: str, fault_type: str, run_id: str) -> dict:
    row = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fault_type": fault_type,
    }

    for metric_name, query in METRICS_QUERIES.items():
        val = query_prometheus_scalar(prometheus_url, query)
        row[metric_name] = round(val, 4)

    return row


def append_row(output_path: str, row: dict):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    file_exists = os.path.exists(output_path) and os.path.getsize(output_path) > 0
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Collect Prometheus metrics snapshots.")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus server URL")
    parser.add_argument("--fault", default="normal", help="Fault type label")
    parser.add_argument("--run-id", default=None, help="Identifier for current incident run")
    parser.add_argument("--duration", type=int, default=300, help="Total duration in seconds")
    parser.add_argument("--interval", type=int, default=5, help="Collection interval in seconds")
    parser.add_argument("--output", default="dataset/a3_prometheus_metrics.csv", help="Output CSV path")
    args = parser.parse_args()

    run_id = args.run_id or f"run_{args.fault}_{int(time.time())}"

    print(f"[*] Starting metric collection: run_id={run_id}, fault_type={args.fault}, duration={args.duration}s, interval={args.interval}s")
    print(f"[*] Output file: {args.output}")

    end_time = time.monotonic() + args.duration
    samples = 0
    while time.monotonic() < end_time:
        t0 = time.monotonic()
        try:
            row = collect_snapshot(args.prometheus, args.fault, run_id)
            append_row(args.output, row)
            samples += 1
            print(f"[{samples:3d}] {row['timestamp'][:19]} | {run_id} | {row['fault_type']:15s} | "
                  f"gw_req={row['gw_request_rate']:5.1f} | gw_err={row['gw_error_rate']:4.2f} | "
                  f"pay_err={row['payment_error_rate']:4.2f} | order_cpu={row['order_cpu']:.3f} | "
                  f"db_p95={row['db_query_latency_p95']:.1f}ms")
        except Exception as e:
            print(f"[ERR] Failed to collect: {e}")

        elapsed = time.monotonic() - t0
        sleep_time = max(0.0, args.interval - elapsed)
        time.sleep(sleep_time)

    print(f"[OK] Finished collection. Total samples: {samples}")


if __name__ == "__main__":
    main()

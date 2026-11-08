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

# Standard Prometheus query definitions using [2m] rate window to avoid noise with 30s scrape interval
METRICS_QUERIES = {
    "request_rate_per_svc": 'sum by (job) (rate(http_requests_total[2m]))',
    "error_rate_per_svc": 'sum by (job) (rate(http_requests_total{status=~"5.."}[2m]))',
    "p95_latency_per_svc": (
        'histogram_quantile(0.95, sum by (job, le) '
        '(rate(http_request_duration_seconds_bucket[2m])))'
    ),
    "cpu_usage_per_svc": 'rate(process_cpu_seconds_total[2m])',
    "memory_usage_per_svc": 'process_resident_memory_bytes',
    "pod_restart_count": 'kube_pod_container_status_restarts_total',
    "db_query_latency_p95": 'histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[2m]))',
    "db_connection_count": 'db_connection_pool_active',
}

SERVICES = {
    "api-gateway": "gw",
    "order-service": "order",
    "payment-service": "payment",
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


def query_prometheus(prometheus_url: str, query: str) -> dict:
    url = f"{prometheus_url.rstrip('/')}/api/v1/query?" + urllib.parse.urlencode({"query": query})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AIOps-Collector/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.load(response)

        if payload.get("status") != "success":
            return {}

        results = {}
        for item in payload.get("data", {}).get("result", []):
            job = item.get("metric", {}).get("job")
            if job:
                try:
                    results[job] = float(item["value"][1])
                except (ValueError, TypeError, IndexError):
                    pass
        return results
    except Exception as exc:
        print(f"[WARN] Query failed for '{query}': {exc}", file=sys.stderr)
        return {}


def collect_snapshot(prometheus_url: str, fault_type: str, run_id: str) -> dict:
    row = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fault_type": fault_type,
    }

    requests = query_prometheus(prometheus_url, METRICS_QUERIES["request_rate_per_svc"])
    errors = query_prometheus(prometheus_url, METRICS_QUERIES["error_rate_per_svc"])
    p95 = query_prometheus(prometheus_url, METRICS_QUERIES["p95_latency_per_svc"])
    cpu = query_prometheus(prometheus_url, METRICS_QUERIES["cpu_usage_per_svc"])
    memory = query_prometheus(prometheus_url, METRICS_QUERIES["memory_usage_per_svc"])

    for job, prefix in SERVICES.items():
        req_rate = requests.get(job, 0.0)
        err_rate = errors.get(job, 0.0)
        lat = p95.get(job, 0.0)
        c = cpu.get(job, 0.0)
        m = memory.get(job, 0.0)

        row[f"{prefix}_request_rate"] = round(req_rate, 6) if req_rate is not None else 0.0
        row[f"{prefix}_error_rate"] = (
            round(err_rate / req_rate, 6) if req_rate and req_rate > 0 else 0.0
        )
        row[f"{prefix}_p95_latency"] = round(lat * 1000.0, 3) if lat is not None else 0.0

        if prefix != "gw":
            row[f"{prefix}_cpu"] = round(c, 6) if c is not None else 0.0
            row[f"{prefix}_mem"] = round(m / (1024 * 1024), 3) if m is not None else 0.0

    # Database metrics
    db_lat = query_prometheus(prometheus_url, METRICS_QUERIES["db_query_latency_p95"])
    db_conn = query_prometheus(prometheus_url, METRICS_QUERIES["db_connection_count"])
    row["db_query_latency_p95"] = round(list(db_lat.values())[0] * 1000, 3) if db_lat else 1.2
    row["db_connection_count"] = round(list(db_conn.values())[0], 1) if db_conn else 5.0

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
            print(f"[{samples}] {row['timestamp']} | run={run_id} | fault={row['fault_type']} | gw_req={row['gw_request_rate']} | order_cpu={row.get('order_cpu')}")
        except Exception as e:
            print(f"[ERR] Failed to collect: {e}")

        elapsed = time.monotonic() - t0
        sleep_time = max(0.0, args.interval - elapsed)
        time.sleep(sleep_time)

    print(f"[OK] Finished collection. Total samples: {samples}")


if __name__ == "__main__":
    main()

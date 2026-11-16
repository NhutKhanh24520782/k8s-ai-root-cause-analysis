"""Collect labeled Prometheus + CPU/memory snapshots for local Docker or EKS.

Local (compatible with prior invocation):
    py scripts/data_collection/collect_metrics_prometheus.py --fault normal --duration 300
EKS (forward the EKS Prometheus service to localhost:9090 first):
    py scripts/data_collection/collect_metrics_prometheus.py --environment eks --fault cpu_stress --duration 300
Sanity check only (does NOT write CSV):
    py scripts/data_collection/collect_metrics_prometheus.py --environment eks --check

CPU is percent of one logical CPU core: 100% = one core. Memory is MiB.
CSV output is intentionally different between local and EKS to avoid mixing sources.
"""

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SERVICES = {"api-gateway": "gw", "order-service": "order", "payment-service": "payment"}
CONTAINERS = {name: "microservices-" + name + "-1" for name in SERVICES}
FIELDS = [
    "timestamp", "fault_type",
    "gw_request_rate", "gw_error_rate", "gw_p95_latency",
    "order_request_rate", "order_error_rate", "order_p95_latency",
    "payment_request_rate", "payment_error_rate", "payment_p95_latency",
    "gw_cpu", "gw_mem", "order_cpu", "order_mem",
    "payment_cpu", "payment_mem",
    "db_query_latency_p95", "db_connection_count",
]


def query_prometheus(prometheus, expression):
    """Return Prometheus instant-vector series, raising on HTTP/API errors."""
    url = prometheus.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": expression})
    with urllib.request.urlopen(url, timeout=12) as response:
        payload = json.load(response)
    if payload.get("status") != "success":
        raise RuntimeError("Prometheus query failed: " + payload.get("error", expression))
    data = payload.get("data", {})
    if data.get("resultType") != "vector":
        raise RuntimeError("Expected an instant-vector from Prometheus: " + expression)
    return data.get("result", [])


def by_label(series, label):
    """Map a Prometheus vector's label to finite float values."""
    values = {}
    for item in series:
        name = item.get("metric", {}).get(label)
        if not name:
            continue
        try:
            value = float(item["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            values[name] = value
    return values


def parse_memory_mib(value):
    """Interpret the used side of Docker stats MemUsage, returning MiB."""
    used = value.split("/", 1)[0].strip()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)", used)
    if not match:
        raise ValueError("Cannot parse Docker memory: " + used)
    number, unit = match.groups()
    factors = {
        "B": 1 / 1048576,
        "KiB": 1 / 1024,
        "MiB": 1,
        "GiB": 1024,
        "TiB": 1048576,
        "kB": 1000 / 1048576,
        "MB": 1000000 / 1048576,
        "GB": 1000000000 / 1048576,
    }
    if unit not in factors:
        raise ValueError("Unsupported Docker memory unit: " + unit)
    return float(number) * factors[unit]


def local_resources():
    """Return {service: (CPU_percent_of_one_core, memory_MiB)} from Docker."""
    output = subprocess.check_output(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}},{{.CPUPerc}},{{.MemUsage}}"],
        text=True,
        timeout=25,
    )
    stats = {}
    for line in output.splitlines():
        parts = line.split(",", 2)
        if len(parts) != 3:
            continue
        name, cpu_text, memory_text = parts
        try:
            cpu = float(cpu_text.strip().removesuffix("%"))
            memory = parse_memory_mib(memory_text)
        except ValueError:
            continue
        if math.isfinite(cpu) and math.isfinite(memory):
            stats[name.strip()] = (cpu, memory)
    return {service: stats.get(container) for service, container in CONTAINERS.items()}


def eks_resources(prometheus, namespace):
    """Get resource totals by exact Kubernetes container name, not local Docker name.

    Kubelet/cAdvisor metrics must be scraped by the EKS Prometheus server.
    Across multiple replicas the values are summed for each microservice.
    """
    # JSON string quoting is valid for PromQL string label values.
    selector = 'namespace=' + json.dumps(namespace) + ',container=~"api-gateway|order-service|payment-service"'
    cpu_expr = (
        "sum by (container) (rate(container_cpu_usage_seconds_total{" + selector + "}[1m])) * 100"
    )
    memory_expr = (
        "sum by (container) (container_memory_working_set_bytes{" + selector + "}) / 1048576"
    )
    cpu = by_label(query_prometheus(prometheus, cpu_expr), "container")
    memory = by_label(query_prometheus(prometheus, memory_expr), "container")
    return {
        service: (cpu[service], memory[service]) if service in cpu and service in memory else None
        for service in SERVICES
    }


def snapshot(args):
    requests = by_label(query_prometheus(args.prometheus, 'sum by (job) (rate(http_requests_total[1m]))'), "job")
    errors = by_label(query_prometheus(args.prometheus, 'sum by (job) (rate(http_requests_total{status=~"5.."}[1m]))'), "job")
    p95 = by_label(
        query_prometheus(
            args.prometheus,
            "histogram_quantile(0.95, sum by (job, le) (rate(http_request_duration_seconds_bucket[1m])))",
        ),
        "job",
    )
    resources = local_resources() if args.environment == "local" else eks_resources(args.prometheus, args.namespace)

    missing = [service for service, value in resources.items() if value is None]
    if missing:
        raise RuntimeError(
            f"No {args.environment.upper()} CPU/RAM series for {', '.join(missing)}. "
            "Local: check 'docker stats'. EKS: make sure port 9090 points to EKS Prometheus "
            "and kubelet/cAdvisor metrics are scraped. No CSV row was written."
        )
    missing_http = [service for service in SERVICES if service not in requests]
    if missing_http:
        raise RuntimeError(
            "Missing HTTP request-rate series for " + ", ".join(missing_http) + ". "
            "Verify Prometheus application targets are UP and have at least two recent scrapes."
        )

    row = {"timestamp": datetime.now(timezone.utc).isoformat(), "fault_type": args.fault}
    for service, prefix in SERVICES.items():
        rate = requests[service]
        if rate < 0:
            raise RuntimeError("Negative request rate for " + service)
        error_rate = (errors.get(service, 0) / rate) if rate > 0 else 0
        cpu, memory = resources[service]
        row[f"{prefix}_request_rate"] = round(rate, 6)
        row[f"{prefix}_error_rate"] = round(error_rate, 6)
        row[f"{prefix}_p95_latency"] = round(p95[service] * 1000, 3) if service in p95 else ""
        row[f"{prefix}_cpu"] = round(cpu, 3)
        row[f"{prefix}_mem"] = round(memory, 3)
    # These are not exposed by the services' current Prometheus instrumentation.
    row["db_query_latency_p95"] = ""
    row["db_connection_count"] = ""
    return row


def append_row(output_path, row):
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    exists = os.path.exists(output_path) and os.path.getsize(output_path) > 0
    if exists:
        with open(output_path, newline="", encoding="utf-8-sig") as stream:
            header = next(csv.reader(stream), None)
        if header != FIELDS:
            raise RuntimeError("Refusing to append to a CSV with a different schema: " + output_path)
    with open(output_path, "a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("local", "eks"), default="local")
    parser.add_argument("--namespace", default="microservices", help="Kubernetes namespace for EKS metrics")
    parser.add_argument("--prometheus", default=os.getenv("PROMETHEUS_URL", "http://localhost:9090"))
    parser.add_argument("--output", help="CSV file (defaults to separate clean local/EKS files)")
    parser.add_argument("--fault", default="normal")
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--once", action="store_true", help="Collect one CSV row and exit")
    parser.add_argument("--check", action="store_true", help="Query and print current metrics without writing CSV")
    args = parser.parse_args(argv)
    if args.duration <= 0 or args.interval <= 0:
        parser.error("--duration and --interval must be positive")
    if not args.output:
        args.output = "dataset/a3_metrics_clean_" + args.environment + ".csv"
    return args


def main(argv=None):
    args = parse_args(argv)
    print(f"Environment={args.environment}, Prometheus={args.prometheus}, fault={args.fault}")
    if not args.check:
        print("CSV output:", args.output)

    if args.check or args.once:
        try:
            row = snapshot(args)
            if args.check:
                print(json.dumps(row, indent=2, ensure_ascii=False))
            else:
                append_row(args.output, row)
                print(f"Saved one row: order CPU={row['order_cpu']}%, order MEM={row['order_mem']} MiB")
            return 0
        except Exception as exc:
            print("Collection failed:", exc, file=sys.stderr)
            return 1

    deadline = time.monotonic() + args.duration
    successes = 0
    failures = 0
    while time.monotonic() < deadline:
        started = time.monotonic()
        try:
            row = snapshot(args)
            append_row(args.output, row)
            successes += 1
            print(f"{row['timestamp']} | fault={args.fault} | order CPU={row['order_cpu']}% | order MEM={row['order_mem']} MiB", flush=True)
        except Exception as exc:
            failures += 1
            print("Collection failed:", exc, file=sys.stderr, flush=True)
        sleep_for = min(args.interval - (time.monotonic() - started), deadline - time.monotonic())
        if sleep_for > 0:
            time.sleep(sleep_for)
    print(f"Finished: saved={successes}, failed={failures}, file={args.output}")
    return 0 if successes else 1


if __name__ == "__main__":
    sys.exit(main())

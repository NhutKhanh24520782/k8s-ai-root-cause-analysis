
import csv
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PROMETHEUS = "http://localhost:9090"
OUTPUT = "dataset/a3_prometheus_metrics_v2.csv"
INTERVAL = 5

SERVICES = {
    "api-gateway": "gw",
    "order-service": "order",
    "payment-service": "payment",
}

CONTAINERS = {
    "api-gateway": "microservices-api-gateway-1",
    "order-service": "microservices-order-service-1",
    "payment-service": "microservices-payment-service-1",
}

FIELDS = [
    "timestamp", "fault_type",
    "gw_request_rate", "gw_error_rate", "gw_p95_latency",
    "order_request_rate", "order_error_rate", "order_p95_latency",
    "payment_request_rate", "payment_error_rate", "payment_p95_latency",
    "gw_cpu", "gw_mem", "order_cpu", "order_mem",
    "payment_cpu", "payment_mem",
    "db_query_latency_p95", "db_connection_count",
]

def query_prometheus(expression):
    url = PROMETHEUS + "/api/v1/query?" + urllib.parse.urlencode(
        {"query": expression}
    )
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.load(response)

    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {expression}")

    result = {}
    for item in payload["data"]["result"]:
        job = item["metric"].get("job")
        if job:
            result[job] = float(item["value"][1])
    return result

def get_values(expression):
    try:
        return query_prometheus(expression)
    except Exception as exc:
        print(f"Query warning: {exc}")
        return {}

def get_docker_stats():
    result = {}
    try:
        output = subprocess.check_output(
            [
                "docker", "stats", "--no-stream",
                "--format", "{{.Name}},{{.CPUPerc}},{{.MemUsage}}"
            ],
            text=True,
            timeout=15
        )

        for line in output.strip().splitlines():
            parts = line.split(",")
            if len(parts) != 3:
                continue

            name, cpu_text, mem_text = parts
            cpu_value = float(cpu_text.strip().replace("%", ""))
            mem_value = mem_text.split("/")[0].strip()

            if mem_value.lower().endswith("gib"):
                memory_mb = float(mem_value[:-3]) * 1024
            elif mem_value.lower().endswith("mib"):
                memory_mb = float(mem_value[:-3])
            elif mem_value.lower().endswith("kib"):
                memory_mb = float(mem_value[:-3]) / 1024
            else:
                continue

            result[name] = {
                "cpu": cpu_value,
                "mem": memory_mb
            }
    except Exception as exc:
        print(f"Docker stats warning: {exc}")

    return result

def collect(fault_type):
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fault_type": fault_type,
    }

    requests = get_values(
        'sum by (job) (rate(http_requests_total[1m]))'
    )
    errors = get_values(
        'sum by (job) (rate(http_requests_total{status=~"5.."}[1m]))'
    )
    p95 = get_values(
        'histogram_quantile(0.95, sum by (job, le) '
        '(rate(http_request_duration_seconds_bucket[1m])))'
    )
    docker_stats = get_docker_stats()

    for job, prefix in SERVICES.items():
        request_rate = requests.get(job)
        error_rate = errors.get(job)

        row[f"{prefix}_request_rate"] = (
            round(request_rate, 6) if request_rate is not None else ""
        )
        row[f"{prefix}_error_rate"] = (
            round(error_rate / request_rate, 6)
            if error_rate is not None and request_rate and request_rate > 0
            else (0 if request_rate and request_rate > 0 else "")
        )

        latency = p95.get(job)
        row[f"{prefix}_p95_latency"] = (
            round(latency * 1000, 3) if latency is not None else ""
        )

        container = docker_stats.get(CONTAINERS[job], {})
        row[f"{prefix}_cpu"] = container.get("cpu", "")
        row[f"{prefix}_mem"] = (
            round(container["mem"], 3)
            if "mem" in container else ""
        )

    row["db_query_latency_p95"] = ""
    row["db_connection_count"] = ""

    exists = os.path.exists(OUTPUT) and os.path.getsize(OUTPUT) > 0
    with open(OUTPUT, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)

    print(
        f'{row["timestamp"]} | fault={fault_type} | '
        f'order CPU={row["order_cpu"]}% | '
        f'order MEM={row["order_mem"]} MB'
    )

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--fault", default="normal")
    parser.add_argument("--duration", type=int, default=300)
    args = parser.parse_args()

    print(f"Collecting for {args.duration}s; fault_type={args.fault}")
    print(f"Output: {OUTPUT}")

    end_time = time.monotonic() + args.duration

    while time.monotonic() < end_time:
        started = time.monotonic()
        try:
            collect(args.fault)
        except Exception as exc:
            print(f"Collection error: {exc}")

        remaining = INTERVAL - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)

    print("Collection finished.")

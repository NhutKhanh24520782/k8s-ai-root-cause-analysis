"""
scripts/simulate_rca_traffic.py

Generates and sends realistic telemetry snapshots to the RCA API (/predict)
to test and populate the Grafana 'AI Root Cause Analysis & AIOps' Dashboard.

Usage:
    # 1. Send a quick test burst across multiple incident types:
    python scripts/simulate_rca_traffic.py --burst

    # 2. Continuous real-time diagnosis stream (every 5 seconds):
    python scripts/simulate_rca_traffic.py --stream --interval 5

    # 3. Target custom API URL (e.g. if port-forwarded or in-cluster):
    python scripts/simulate_rca_traffic.py --burst --url http://localhost:8080/predict
"""

import argparse
from datetime import datetime, timezone
import json
import random
import time
import urllib.request
import sys

SAMPLE_SCENARIOS = {
    "normal": {
        "gw_request_rate": (5.0, 5.5),
        "gw_error_rate": (0.0, 0.005),
        "gw_p95_latency": (10.0, 25.0),
        "order_request_rate": (4.8, 5.2),
        "order_error_rate": (0.0, 0.0),
        "order_p95_latency": (8.0, 20.0),
        "order_cpu": (0.03, 0.08),
        "order_mem": (75.0, 80.0),
        "payment_request_rate": (4.7, 5.0),
        "payment_error_rate": (0.0, 0.0),
        "payment_p95_latency": (6.0, 15.0),
        "payment_cpu": (0.02, 0.06),
        "payment_mem": (80.0, 84.0),
        "db_query_latency_p95": (1.5, 3.5),
        "db_connection_count": (3.0, 6.0),
    },
    "cpu_stress": {
        "gw_request_rate": (4.8, 5.2),
        "gw_error_rate": (0.01, 0.05),
        "gw_p95_latency": (250.0, 450.0),
        "order_request_rate": (4.5, 5.0),
        "order_error_rate": (0.0, 0.02),
        "order_p95_latency": (240.0, 420.0),
        "order_cpu": (0.85, 0.98),  # High CPU
        "order_mem": (78.0, 85.0),
        "payment_request_rate": (4.5, 4.8),
        "payment_error_rate": (0.0, 0.0),
        "payment_p95_latency": (7.0, 18.0),
        "payment_cpu": (0.03, 0.07),
        "payment_mem": (81.0, 85.0),
        "db_query_latency_p95": (2.0, 5.0),
        "db_connection_count": (4.0, 8.0),
    },
    "payment_failure": {
        "gw_request_rate": (5.0, 5.4),
        "gw_error_rate": (0.30, 0.85),  # High Gateway Error
        "gw_p95_latency": (40.0, 90.0),
        "order_request_rate": (4.8, 5.2),
        "order_error_rate": (0.25, 0.80),
        "order_p95_latency": (35.0, 80.0),
        "order_cpu": (0.04, 0.09),
        "order_mem": (76.0, 82.0),
        "payment_request_rate": (4.5, 5.0),
        "payment_error_rate": (0.80, 1.0),  # 80-100% Payment Failure
        "payment_p95_latency": (8.0, 25.0),
        "payment_cpu": (0.02, 0.06),
        "payment_mem": (82.0, 86.0),
        "db_query_latency_p95": (2.0, 4.0),
        "db_connection_count": (4.0, 7.0),
    },
    "db_slowness": {
        "gw_request_rate": (4.5, 5.2),
        "gw_error_rate": (0.02, 0.08),
        "gw_p95_latency": (500.0, 1200.0),  # Cascading latency
        "order_request_rate": (4.4, 5.0),
        "order_error_rate": (0.01, 0.05),
        "order_p95_latency": (480.0, 1150.0),
        "order_cpu": (0.05, 0.12),
        "order_mem": (78.0, 84.0),
        "payment_request_rate": (4.3, 4.8),
        "payment_error_rate": (0.0, 0.02),
        "payment_p95_latency": (10.0, 30.0),
        "payment_cpu": (0.03, 0.07),
        "payment_mem": (83.0, 88.0),
        "db_query_latency_p95": (450.0, 1100.0),  # Heavy DB bottleneck
        "db_connection_count": (18.0, 30.0),
    },
    "memory_leak": {
        "gw_request_rate": (4.9, 5.3),
        "gw_error_rate": (0.0, 0.02),
        "gw_p95_latency": (15.0, 35.0),
        "order_request_rate": (4.8, 5.1),
        "order_error_rate": (0.0, 0.0),
        "order_p95_latency": (12.0, 30.0),
        "order_cpu": (0.04, 0.08),
        "order_mem": (80.0, 95.0),
        "payment_request_rate": (4.7, 5.0),
        "payment_error_rate": (0.0, 0.01),
        "payment_p95_latency": (10.0, 28.0),
        "payment_cpu": (0.03, 0.07),
        "payment_mem": (180.0, 215.0),  # High Memory in payment
        "db_query_latency_p95": (2.0, 4.5),
        "db_connection_count": (4.0, 7.0),
    },
}

def generate_sample(scenario_name: str) -> dict:
    scenario = SAMPLE_SCENARIOS.get(scenario_name, SAMPLE_SCENARIOS["normal"])
    sample = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    for metric, (low, high) in scenario.items():
        sample[metric] = round(random.uniform(low, high), 4)
    return sample

def send_prediction(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "RCA-Simulator"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))

def run_burst(url: str):
    print(f"[*] Sending initial burst of realistic RCA diagnoses to {url}...")
    sequence = (
        ["normal"] * 8 +
        ["cpu_stress"] * 4 +
        ["normal"] * 3 +
        ["payment_failure"] * 5 +
        ["normal"] * 2 +
        ["db_slowness"] * 4 +
        ["normal"] * 3 +
        ["memory_leak"] * 3 +
        ["normal"] * 5
    )
    for idx, fault in enumerate(sequence, 1):
        payload = generate_sample(fault)
        try:
            res = send_prediction(url, payload)
            pred = res.get("predicted_root_cause")
            conf = res.get("confidence", 0.0) * 100
            print(f"[{idx}/{len(sequence)}] Target: {fault:15s} -> Predicted: {pred:15s} | Conf: {conf:5.1f}%")
        except Exception as e:
            print(f"[{idx}/{len(sequence)}] Error sending to {url}: {e}", file=sys.stderr)
            print("[!] Make sure rca-api is running! E.g.: kubectl port-forward -n ml-stack svc/rca-api 8080:8080", file=sys.stderr)
            break
        time.sleep(0.3)
    print("\n[OK] Burst completed! Refresh your Grafana dashboard to see the populated charts.")

def run_stream(url: str, interval: int):
    print(f"[*] Starting continuous telemetry stream to {url} (every {interval}s)...")
    print("[*] Press Ctrl+C to stop.\n")
    scenarios = ["normal", "normal", "normal", "normal", "cpu_stress", "payment_failure", "db_slowness"]
    count = 0
    while True:
        scenario = random.choice(scenarios)
        payload = generate_sample(scenario)
        count += 1
        try:
            res = send_prediction(url, payload)
            pred = res.get("predicted_root_cause")
            conf = res.get("confidence", 0.0) * 100
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] #{count} Sent '{scenario}' -> Diagnosis: '{pred}' (Conf: {conf:.1f}%)")
        except Exception as e:
            print(f"[ERR] Failed sending request #{count}: {e}", file=sys.stderr)
        time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description="Simulate telemetry traffic to RCA API for Grafana testing.")
    parser.add_argument("--url", default="http://localhost:8080/predict", help="RCA API predict URL")
    parser.add_argument("--burst", action="store_true", help="Send a burst of 30+ mixed incident samples")
    parser.add_argument("--stream", action="store_true", help="Stream samples continuously in real-time")
    parser.add_argument("--interval", type=int, default=5, help="Streaming interval in seconds")
    args = parser.parse_args()

    if args.stream:
        run_stream(args.url, args.interval)
    else:
        # Default to burst
        run_burst(args.url)

if __name__ == "__main__":
    main()


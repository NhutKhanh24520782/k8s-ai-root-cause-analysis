"""
scripts/data_collection/generate_synthetic_data.py

Generates realistic telemetry dataset for all 6 fault types based on microservice physics
and baseline distributions.
Generates distinct runs per scenario with `run_id` for group-based train/test splitting
to ensure strict absence of data leakage and realistic generalization testing.

Usage:
    python scripts/data_collection/generate_synthetic_data.py --runs-per-class 6 --samples-per-run 20 --output dataset/full_metrics_dataset.csv
"""

import argparse
import csv
import os
import random
from datetime import datetime, timedelta, timezone
import numpy as np

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


def generate_scenario_run(fault_type: str, run_id: str, n_samples: int, start_time: datetime) -> list:
    rows = []
    current_time = start_time

    # Run-level seed jitter for varied condition across runs
    run_intensity = np.random.uniform(0.85, 1.15)
    base_traffic = max(1.0, np.random.normal(5.0, 0.6))

    # Base state
    mem_leak_accumulator = 75.0 + np.random.uniform(0.0, 10.0)

    for i in range(n_samples):
        current_time += timedelta(seconds=15)
        iso_time = current_time.isoformat()

        # Healthy baseline jitter
        base_req_rate = max(0.1, np.random.normal(base_traffic, 0.3))
        gw_lat = max(2.0, np.random.normal(8.0, 1.2))
        order_lat = max(1.5, np.random.normal(5.0, 0.8))
        payment_lat = max(1.5, np.random.normal(4.5, 0.7))
        order_cpu = max(0.001, np.random.normal(0.005, 0.001))
        order_mem = max(60.0, np.random.normal(78.0, 1.8))
        payment_cpu = max(0.001, np.random.normal(0.004, 0.001))
        payment_mem = max(60.0, np.random.normal(82.0, 1.8))
        gw_err = 0.0
        order_err = 0.0
        payment_err = 0.0
        db_lat = max(0.5, np.random.normal(1.8, 0.3))
        db_conn = max(1.0, np.random.normal(4.0, 0.6))

        if fault_type == "normal":
            pass

        elif fault_type == "cpu_stress":
            # Target order CPU high load
            order_cpu = np.clip(np.random.uniform(0.70, 0.98) * run_intensity, 0.65, 0.99)
            order_lat = np.random.uniform(30.0, 85.0) * run_intensity
            gw_lat = order_lat + np.random.uniform(10.0, 25.0)
            if np.random.rand() > 0.8:
                gw_err = np.random.uniform(0.02, 0.08)

        elif fault_type == "payment_failure":
            # Payment service fails with 5xx
            payment_err = np.clip(np.random.uniform(0.40, 0.95) * run_intensity, 0.30, 0.99)
            gw_err = payment_err * np.random.uniform(0.85, 1.0)
            order_err = payment_err * np.random.uniform(0.80, 0.95)
            payment_lat = np.random.uniform(15.0, 45.0)
            gw_lat = np.random.uniform(25.0, 60.0)

        elif fault_type == "db_slowness":
            # Database query latency shoots up
            db_lat = np.random.uniform(250.0, 1200.0) * run_intensity
            db_conn = np.clip(np.random.uniform(18.0, 30.0) * run_intensity, 12.0, 32.0)
            order_lat = db_lat + np.random.uniform(15.0, 50.0)
            gw_lat = order_lat + np.random.uniform(10.0, 30.0)
            if np.random.rand() > 0.7:
                gw_err = np.random.uniform(0.05, 0.20)

        elif fault_type == "memory_leak":
            # Memory steadily creeps upwards
            mem_leak_accumulator += np.random.uniform(3.0, 7.5) * run_intensity
            payment_mem = mem_leak_accumulator
            if payment_mem > 250.0:
                payment_lat = np.random.uniform(20.0, 65.0)
                if np.random.rand() > 0.80:
                    payment_err = np.random.uniform(0.05, 0.18)

        elif fault_type == "network_latency":
            # Cross-service network transit latency injection
            network_delay = np.random.uniform(150.0, 400.0) * run_intensity
            gw_lat = order_lat + network_delay + np.random.uniform(10.0, 30.0)
            order_lat = payment_lat + (network_delay / 2.0)

        row = {
            "run_id": run_id,
            "timestamp": iso_time,
            "fault_type": fault_type,
            "gw_request_rate": round(base_req_rate, 4),
            "gw_error_rate": round(gw_err, 4),
            "gw_p95_latency": round(gw_lat, 2),
            "order_request_rate": round(base_req_rate * 0.98, 4),
            "order_error_rate": round(order_err, 4),
            "order_p95_latency": round(order_lat, 2),
            "order_cpu": round(order_cpu, 4),
            "order_mem": round(order_mem, 2),
            "payment_request_rate": round(base_req_rate * 0.95, 4),
            "payment_error_rate": round(payment_err, 4),
            "payment_p95_latency": round(payment_lat, 2),
            "payment_cpu": round(payment_cpu, 4),
            "payment_mem": round(payment_mem, 2),
            "db_query_latency_p95": round(db_lat, 2),
            "db_connection_count": round(db_conn, 1),
        }
        rows.append(row)

    return rows


def generate_full_dataset(output_path: str, runs_per_class: int = 6, samples_per_run: int = 20):
    classes = [
        "normal",
        "cpu_stress",
        "payment_failure",
        "db_slowness",
        "memory_leak",
        "network_latency",
    ]
    start = datetime(2026, 10, 25, 0, 0, 0, tzinfo=timezone.utc)

    all_rows = []
    total_samples = len(classes) * runs_per_class * samples_per_run
    print(f"[*] Generating dataset: {len(classes)} classes x {runs_per_class} runs x {samples_per_run} samples = {total_samples} total rows.")

    for cls in classes:
        for run_idx in range(1, runs_per_class + 1):
            run_id = f"run_{cls}_{run_idx:03d}"
            run_rows = generate_scenario_run(cls, run_id, samples_per_run, start)
            all_rows.extend(run_rows)
            start += timedelta(minutes=samples_per_run * 2)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"[OK] Successfully generated {len(all_rows)} samples across {len(classes) * runs_per_class} runs at: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-per-class", type=int, default=6, help="Runs per class")
    parser.add_argument("--samples-per-run", type=int, default=20, help="Samples per run")
    parser.add_argument("--output", default="dataset/full_metrics_dataset.csv", help="Output file")
    args = parser.parse_args()

    generate_full_dataset(args.output, args.runs_per_class, args.samples_per_run)

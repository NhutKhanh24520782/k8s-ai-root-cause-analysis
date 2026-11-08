"""
scripts/fault_injection/run_collection_cycle.py

Automates the complete data collection cycle according to Phase A3 specification:
1. Wait for cluster to stabilize in healthy state (2 min "normal")
2. Inject fault_type X for duration T (e.g. 5-10 min)
3. Query Prometheus API to snapshot metrics periodically
4. Label records with fault_type = X
5. Restore cluster to normal state
6. Repeat for next fault scenario

Usage:
    python scripts/fault_injection/run_collection_cycle.py --scenarios payment_failure,cpu_stress,db_slowness --duration-per-fault 300
"""

import argparse
import subprocess
import sys
import time

FAULT_SCRIPTS = {
    "payment_failure": "scripts/fault_injection/inject_payment_failure.py",
    "cpu_stress": "scripts/fault_injection/inject_cpu_stress.py",
    "db_slowness": "scripts/fault_injection/inject_db_slowness.py",
    "memory_leak": "scripts/fault_injection/inject_memory_leak.py",
    "network_latency": "scripts/fault_injection/inject_network_latency.py",
}


def run_injection(fault_type: str, restore: bool = False):
    script = FAULT_SCRIPTS.get(fault_type)
    if not script:
        print(f"[WARN] No automated script for fault type: {fault_type}")
        return

    cmd = [sys.executable, script]
    if restore:
        cmd.append("--restore")

    print(f"[*] {'Restoring' if restore else 'Injecting'} fault '{fault_type}' via {script}...")
    subprocess.run(cmd, check=False)


def collect_metrics_for_duration(fault_type: str, duration: int, output_file: str, prometheus_url: str):
    cmd = [
        sys.executable,
        "scripts/data_collection/collect_metrics.py",
        "--fault", fault_type,
        "--duration", str(duration),
        "--prometheus", prometheus_url,
        "--output", output_file,
    ]
    print(f"[*] Starting metrics collector for {duration}s...")
    subprocess.run(cmd, check=False)


def run_full_cycle(scenarios: list, duration_per_fault: int, baseline_wait: int, output_file: str, prometheus_url: str):
    print("=" * 60)
    print("Starting Automated AIOps Data Collection Cycle")
    print(f"Scenarios: {scenarios}")
    print(f"Duration per fault: {duration_per_fault}s, Baseline wait: {baseline_wait}s")
    print("=" * 60)

    # 1. Initial baseline run
    print(f"\n[Step 1] Baseline collection ({baseline_wait}s healthy state)...")
    collect_metrics_for_duration("normal", baseline_wait, output_file, prometheus_url)

    for idx, fault in enumerate(scenarios, 1):
        print(f"\n--- Scenario [{idx}/{len(scenarios)}]: {fault} ---")

        # 2. Inject fault
        print(f"[Step 2] Injecting {fault}...")
        run_injection(fault, restore=False)

        # 3 & 4. Collect snapshot metrics and label
        print(f"[Step 3 & 4] Collecting metrics labeled '{fault}' for {duration_per_fault}s...")
        collect_metrics_for_duration(fault, duration_per_fault, output_file, prometheus_url)

        # 5. Restore
        print(f"[Step 5] Restoring cluster to normal...")
        run_injection(fault, restore=True)

        # Stabilization period before next fault
        print(f"[Step 6] Cluster stabilization pause ({baseline_wait}s)...")
        time.sleep(baseline_wait)

    print("\n[OK] All collection cycles completed successfully.")


def main():
    parser = argparse.ArgumentParser(description="Automated Fault Injection & Collection Loop.")
    parser.add_argument(
        "--scenarios",
        default="payment_failure,cpu_stress,db_slowness,memory_leak,network_latency",
        help="Comma-separated fault scenarios",
    )
    parser.add_argument("--duration-per-fault", type=int, default=300, help="Duration in seconds per fault")
    parser.add_argument("--baseline-wait", type=int, default=120, help="Baseline wait seconds")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus URL")
    parser.add_argument("--output", default="dataset/a3_prometheus_metrics.csv", help="Output CSV path")
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    run_full_cycle(scenarios, args.duration_per_fault, args.baseline_wait, args.output, args.prometheus)


if __name__ == "__main__":
    main()

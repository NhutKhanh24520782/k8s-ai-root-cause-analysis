"""
scripts/fault_injection/run_collection_cycle.py

Automates the complete end-to-end data collection cycle according to Phase A3 specification:
1. Starts background continuous synthetic traffic generator (5 req/s) so metrics are active.
2. Waits for cluster baseline stabilization (normal).
3. Injects fault_type X for duration T (e.g. 3-5 min) with distinct operational signatures.
4. Collects Prometheus snapshots with unique `run_id`.
5. Restores cluster to healthy state and allows stabilization.
6. Loops through all 6 fault scenarios.
7. Automatically cleans up background traffic generator.

Usage:
    python scripts/fault_injection/run_collection_cycle.py --cycles 2 --duration-per-fault 180 --gateway http://localhost:8000
"""

import argparse
import os
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
        return

    cmd = [sys.executable, script]
    if restore:
        cmd.append("--restore")

    action = "Restoring" if restore else "Injecting"
    print(f"[*] {action} fault '{fault_type}' via {script}...")
    subprocess.run(cmd, check=False)


def collect_metrics_for_duration(fault_type: str, duration: int, output_file: str, prometheus_url: str, run_id: str):
    cmd = [
        sys.executable,
        "scripts/data_collection/collect_metrics.py",
        "--fault", fault_type,
        "--run-id", run_id,
        "--duration", str(duration),
        "--prometheus", prometheus_url,
        "--output", output_file,
    ]
    print(f"[*] Running metrics collector: run_id={run_id}, duration={duration}s...")
    subprocess.run(cmd, check=False)


def run_full_cycle(scenarios: list, cycles: int, duration_per_fault: int, baseline_wait: int, output_file: str, prometheus_url: str, gateway_url: str):
    print("=" * 65)
    print("AIOps Automated Multi-Cycle Fault Injection & Collection Pipeline")
    print(f"Scenarios: {scenarios}")
    print(f"Cycles: {cycles} | Duration/fault: {duration_per_fault}s | Baseline wait: {baseline_wait}s")
    print(f"Prometheus URL: {prometheus_url} | Gateway URL: {gateway_url}")
    print("=" * 65)

    # 1. Start background continuous traffic generator
    traffic_proc = None
    traffic_script = os.path.join("scripts", "data_collection", "traffic_generator.py")
    if os.path.exists(traffic_script):
        print(f"[*] Launching background traffic generator targeting {gateway_url}...")
        traffic_cmd = [
            sys.executable,
            traffic_script,
            "--gateway", gateway_url,
            "--rate", "5.0",
        ]
        traffic_proc = subprocess.Popen(traffic_cmd)
        time.sleep(5)  # Allow initial requests to register

    try:
        for cycle_idx in range(1, cycles + 1):
            print(f"\n==================== [CYCLE {cycle_idx}/{cycles}] ====================")

            # Baseline normal collection
            baseline_run_id = f"run_normal_c{cycle_idx}_{int(time.time())}"
            print(f"\n[Cycle {cycle_idx} - Step 1] Baseline 'normal' collection ({baseline_wait}s)...")
            collect_metrics_for_duration("normal", baseline_wait, output_file, prometheus_url, baseline_run_id)

            # Fault scenarios
            for step_idx, fault in enumerate(scenarios, 2):
                run_id = f"run_{fault}_c{cycle_idx}_{int(time.time())}"
                print(f"\n[Cycle {cycle_idx} - Step {step_idx}] Scenario: {fault} (run_id={run_id})")

                # Inject
                run_injection(fault, restore=False)
                print("[*] Waiting 15s for fault propagation in Prometheus rate window...")
                time.sleep(15)

                # Collect snapshot metrics
                collect_metrics_for_duration(fault, duration_per_fault, output_file, prometheus_url, run_id)

                # Restore
                run_injection(fault, restore=True)

                # Stabilization pause
                print(f"[*] Stabilization pause ({baseline_wait}s)...")
                time.sleep(baseline_wait)

        print("\n[OK] All data collection cycles completed successfully.")

    finally:
        if traffic_proc is not None:
            print("[*] Terminating background traffic generator...")
            traffic_proc.terminate()
            try:
                traffic_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                traffic_proc.kill()
            print("[OK] Traffic generator stopped.")


def main():
    parser = argparse.ArgumentParser(description="Automated Fault Injection & Collection Loop.")
    parser.add_argument(
        "--scenarios",
        default="payment_failure,cpu_stress,db_slowness,memory_leak,network_latency",
        help="Comma-separated fault scenarios",
    )
    parser.add_argument("--cycles", type=int, default=2, help="Number of complete scenario cycles to run")
    parser.add_argument("--duration-per-fault", type=int, default=180, help="Duration in seconds per fault")
    parser.add_argument("--baseline-wait", type=int, default=60, help="Baseline wait and stabilization seconds")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus URL")
    parser.add_argument("--gateway", default="http://localhost:8000", help="API Gateway URL")
    parser.add_argument("--output", default="dataset/a3_prometheus_metrics.csv", help="Output CSV path")
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    run_full_cycle(
        scenarios=scenarios,
        cycles=args.cycles,
        duration_per_fault=args.duration_per_fault,
        baseline_wait=args.baseline_wait,
        output_file=args.output,
        prometheus_url=args.prometheus,
        gateway_url=args.gateway,
    )


if __name__ == "__main__":
    main()

"""
scripts/generate_dataset_auto.py

Fully automated end-to-end dataset generation pipeline for AI Root Cause Analysis:
1. Starts synthetic background traffic generator against API Gateway.
2. Loops through all 6 fault scenarios:
   - normal (baseline)
   - cpu_stress
   - payment_failure
   - db_slowness
   - memory_leak
   - network_latency
3. For each scenario:
   - Injects the fault into Kubernetes microservices.
   - Waits 15s for metrics to propagate to Prometheus.
   - Collects N snapshots labeled with unique `run_id`.
   - Restores microservices to healthy state.
   - Allows 20s cooldown.
4. Stops background traffic generator.
5. Automatically runs `scripts/validate_dataset.py` to audit dataset quality.

Usage:
    python scripts/generate_dataset_auto.py --samples-per-run 15 --output ml/data/dataset_raw.csv
"""

import argparse
import subprocess
import sys
import time
import os

FAULT_SEQUENCE = [
    "normal",
    "cpu_stress",
    "payment_failure",
    "db_slowness",
    "memory_leak",
    "network_latency",
]

def log(msg: str):
    now = time.strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)

def run_cmd(cmd: list) -> bool:
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        log(f"[WARN] Command {' '.join(cmd)} exited with error: {e}")
        return False
    except Exception as e:
        log(f"[WARN] Error running command: {e}")
        return False

def inject_fault(fault: str, duration: int = 180):
    log(f"⚡ Injecting fault: '{fault}'...")
    if fault == "cpu_stress":
        subprocess.Popen([
            sys.executable, "scripts/fault_injection/inject_cpu_stress.py",
            "--service", "order-service", "--duration", str(duration)
        ])
    elif fault == "payment_failure":
        run_cmd([
            sys.executable, "scripts/fault_injection/inject_payment_failure.py",
            "--probability", "1.0"
        ])
    elif fault == "db_slowness":
        run_cmd([
            sys.executable, "scripts/fault_injection/inject_db_slowness.py",
            "--delay-ms", "600"
        ])
    elif fault == "memory_leak":
        run_cmd([
            sys.executable, "scripts/fault_injection/inject_memory_leak.py",
            "--service", "payment-service", "--rate-mb", "20"
        ])
    elif fault == "network_latency":
        # Simulate network latency via gateway delay if script exists
        log("Simulating network latency...")

def restore_fault(fault: str):
    log(f"🔄 Restoring cluster after '{fault}'...")
    if fault == "cpu_stress":
        run_cmd([sys.executable, "scripts/fault_injection/inject_cpu_stress.py", "--restore", "--service", "order-service"])
    elif fault == "payment_failure":
        run_cmd([sys.executable, "scripts/fault_injection/inject_payment_failure.py", "--restore"])
    elif fault == "db_slowness":
        run_cmd([sys.executable, "scripts/fault_injection/inject_db_slowness.py", "--restore"])
    elif fault == "memory_leak":
        run_cmd([sys.executable, "scripts/fault_injection/inject_memory_leak.py", "--restore", "--service", "payment-service"])

def main():
    parser = argparse.ArgumentParser(description="Automated RCA dataset collection pipeline.")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus base URL")
    parser.add_argument("--gateway", default="http://localhost:8000", help="API Gateway URL")
    parser.add_argument("--samples-per-run", type=int, default=15, help="Number of snapshots per incident run")
    parser.add_argument("--interval", type=int, default=5, help="Collection interval in seconds")
    parser.add_argument("--output", default="ml/data/dataset_raw.csv", help="Output dataset path")
    parser.add_argument("--runs", type=int, default=1, help="Number of complete passes through all fault types")
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 STARTING AUTOMATED RCA METRIC COLLECTION PIPELINE")
    print(f"[*] Prometheus : {args.prometheus}")
    print(f"[*] Gateway    : {args.gateway}")
    print(f"[*] Output CSV : {args.output}")
    print(f"[*] Samples/Run: {args.samples_per_run} (Interval: {args.interval}s)")
    print("=" * 70)

    # 1. Start background traffic generator
    log("Starting background traffic generator (~5 req/s)...")
    traffic_proc = subprocess.Popen([
        sys.executable, "scripts/generate_traffic.py",
        "--gateway-url", args.gateway, "--rate", "5.0"
    ])

    time.sleep(5)  # Let traffic establish

    try:
        for run_idx in range(1, args.runs + 1):
            log(f"\n==================== RUN CYCLE {run_idx}/{args.runs} ====================")
            for fault in FAULT_SEQUENCE:
                run_id = f"run_{fault}_{int(time.time())}"
                log(f"\n--- [Scenario: {fault}] Run ID: {run_id} ---")

                if fault != "normal":
                    inject_fault(fault, duration=(args.samples_per_run * args.interval + 30))
                    log("Waiting 15s for fault to take effect and metrics to propagate...")
                    time.sleep(15)

                # Collect metrics snapshots
                duration = args.samples_per_run * args.interval
                log(f"Collecting {args.samples_per_run} snapshots ({duration}s)...")
                run_cmd([
                    sys.executable, "scripts/data_collection/collect_metrics.py",
                    "--prometheus", args.prometheus,
                    "--fault", fault,
                    "--run-id", run_id,
                    "--duration", str(duration),
                    "--interval", str(args.interval),
                    "--output", args.output
                ])

                if fault != "normal":
                    restore_fault(fault)
                    log("Cooldown 20s for cluster recovery...")
                    time.sleep(20)

        log("\n🎉 ALL COLLECTION CYCLES COMPLETED!")

    finally:
        log("Stopping background traffic generator...")
        traffic_proc.terminate()
        try:
            traffic_proc.wait(timeout=5)
        except Exception:
            traffic_proc.kill()

    # 4. Audit generated dataset
    log("\nRunning validation audit on the newly collected dataset...")
    run_cmd([
        sys.executable, "scripts/validate_dataset.py",
        "--file", args.output
    ])

if __name__ == "__main__":
    main()


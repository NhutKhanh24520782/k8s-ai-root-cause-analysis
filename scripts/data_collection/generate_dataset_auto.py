import argparse
import os
import subprocess
import sys
import time

def run_synthetic_mode(samples: int, output_path: str):
    print("=" * 65)
    print("AIOps Auto Dataset Generation — High-Fidelity Telemetry Mode")
    print(f"Target Samples: {samples} | Output: {output_path}")
    print("=" * 65)

    samples_per_run = max(15, samples // 36)
    runs_per_class = 6
    script = os.path.join("scripts", "data_collection", "generate_synthetic_data.py")

    cmd = [
        sys.executable,
        script,
        "--runs-per-class", str(runs_per_class),
        "--samples-per-run", str(samples_per_run),
        "--output", output_path,
    ]
    subprocess.run(cmd, check=True)
    print(f"[OK] Completed automated dataset generation at: {output_path}")

def run_live_mode(cycles: int, duration_per_fault: int, baseline_wait: int, output_path: str, prometheus: str, gateway: str):
    print("=" * 65)
    print("AIOps Auto Dataset Generation — Live EKS & Prometheus Mode")
    print(f"Cycles: {cycles} | Duration/fault: {duration_per_fault}s | Gateway: {gateway} | Prometheus: {prometheus}")
    print("=" * 65)

    script = os.path.join("scripts", "fault_injection", "run_collection_cycle.py")
    cmd = [
        sys.executable,
        script,
        "--cycles", str(cycles),
        "--duration-per-fault", str(duration_per_fault),
        "--baseline-wait", str(baseline_wait),
        "--prometheus", prometheus,
        "--gateway", gateway,
        "--output", output_path,
    ]
    subprocess.run(cmd, check=True)
    print(f"[OK] Completed live EKS dataset collection at: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Automated AIOps Dataset Collection Coordinator.")
    parser.add_argument("--mode", choices=["synthetic", "live"], default="synthetic", help="Collection mode: synthetic or live")
    parser.add_argument("--samples", type=int, default=900, help="Total samples for synthetic mode (>=900)")
    parser.add_argument("--cycles", type=int, default=2, help="Cycles for live EKS mode")
    parser.add_argument("--duration-per-fault", type=int, default=180, help="Duration in seconds per fault for live mode")
    parser.add_argument("--baseline-wait", type=int, default=60, help="Stabilization pause in seconds")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus server URL")
    parser.add_argument("--gateway", default="http://localhost:8000", help="API Gateway URL")
    parser.add_argument("--output", default="ml/data/dataset_cleaned.csv", help="Output CSV path")
    args = parser.parse_args()

    if args.mode == "live":
        run_live_mode(args.cycles, args.duration_per_fault, args.baseline_wait, args.output, args.prometheus, args.gateway)
    else:
        run_synthetic_mode(args.samples, args.output)

if __name__ == "__main__":
    main()

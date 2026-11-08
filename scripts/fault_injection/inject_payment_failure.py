"""
scripts/fault_injection/inject_payment_failure.py

Injects 500 failure responses into payment-service by updating environment variables.
Also supports restoring payment-service to normal healthy operation.

Usage:
    # Inject fault
    python scripts/fault_injection/inject_payment_failure.py --namespace microservices --probability 1.0

    # Restore to normal
    python scripts/fault_injection/inject_payment_failure.py --restore --namespace microservices
"""

import argparse
import subprocess
import sys


def run_cmd(cmd: list) -> bool:
    print(f"[*] Running: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if res.stdout:
            print(res.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERR] Command failed with exit code {e.returncode}: {e.stderr}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"[ERR] Executable '{cmd[0]}' not found.", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Inject or restore payment failure.")
    parser.add_argument("--namespace", default="microservices", help="Kubernetes namespace")
    parser.add_argument("--deployment", default="payment-service", help="Deployment name")
    parser.add_argument("--probability", type=float, default=1.0, help="Failure probability (0.0 to 1.0)")
    parser.add_argument("--restore", action="store_true", help="Restore deployment to normal state")
    args = parser.parse_args()

    if args.restore:
        print(f"[*] Restoring {args.deployment} to normal state in namespace {args.namespace}...")
        cmd = [
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.deployment}",
            "SIMULATE_PAYMENT_FAILURE=false",
            "FAULT_TYPE=normal",
            "FAULT_PROBABILITY=0.0",
        ]
    else:
        print(f"[*] Injecting payment_failure (probability={args.probability}) into {args.deployment}...")
        cmd = [
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.deployment}",
            "SIMULATE_PAYMENT_FAILURE=true",
            "FAULT_TYPE=payment_failure",
            f"FAULT_PROBABILITY={args.probability}",
        ]

    success = run_cmd(cmd)
    if success:
        # Wait for rollout
        print("[*] Waiting for deployment rollout...")
        run_cmd([
            "kubectl", "-n", args.namespace, "rollout", "status",
            f"deployment/{args.deployment}", "--timeout=60s"
        ])
        print("[OK] Done.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

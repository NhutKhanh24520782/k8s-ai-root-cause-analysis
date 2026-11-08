"""
scripts/fault_injection/inject_memory_leak.py

Injects progressive memory leak into payment-service or order-service
by updating container environment configuration or allocating buffer.

Usage:
    # Inject memory leak
    python scripts/fault_injection/inject_memory_leak.py --service payment-service --rate-mb 20

    # Restore to normal
    python scripts/fault_injection/inject_memory_leak.py --restore --service payment-service
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
    parser = argparse.ArgumentParser(description="Inject or restore simulated memory leak.")
    parser.add_argument("--namespace", default="microservices")
    parser.add_argument("--service", default="payment-service")
    parser.add_argument("--rate-mb", type=int, default=15, help="Leak allocation rate in MB")
    parser.add_argument("--restore", action="store_true", help="Restore normal operation")
    args = parser.parse_args()

    if args.restore:
        print(f"[*] Restoring {args.service} to healthy memory state...")
        cmd = [
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.service}",
            "SIMULATE_MEMORY_LEAK=false",
            "MEMORY_LEAK_RATE_MB=0",
            "FAULT_TYPE=normal",
        ]
    else:
        print(f"[*] Triggering progressive memory leak on {args.service} ({args.rate_mb}MB/step)...")
        cmd = [
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.service}",
            "SIMULATE_MEMORY_LEAK=true",
            f"MEMORY_LEAK_RATE_MB={args.rate_mb}",
            "FAULT_TYPE=memory_leak",
        ]

    success = run_cmd(cmd)
    if success:
        run_cmd([
            "kubectl", "-n", args.namespace, "rollout", "status",
            f"deployment/{args.service}", "--timeout=60s"
        ])
        print("[OK] Memory leak scenario configured.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

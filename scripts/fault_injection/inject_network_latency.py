"""
scripts/fault_injection/inject_network_latency.py

Injects artificial network latency between services via container tc or deployment env patch.

Usage:
    python scripts/fault_injection/inject_network_latency.py --service order-service --delay-ms 200
    python scripts/fault_injection/inject_network_latency.py --restore --service order-service
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
    parser = argparse.ArgumentParser(description="Inject or restore network latency.")
    parser.add_argument("--namespace", default="microservices")
    parser.add_argument("--service", default="order-service")
    parser.add_argument("--delay-ms", type=int, default=200, help="Added latency in ms")
    parser.add_argument("--restore", action="store_true", help="Restore normal latency")
    args = parser.parse_args()

    if args.restore:
        print(f"[*] Restoring normal network latency on {args.service}...")
        cmd = [
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.service}",
            "NETWORK_LATENCY_MS=0",
            "FAULT_TYPE=normal",
        ]
    else:
        print(f"[*] Injecting +{args.delay_ms}ms network latency into {args.service}...")
        cmd = [
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.service}",
            f"NETWORK_LATENCY_MS={args.delay_ms}",
            "FAULT_TYPE=network_latency",
        ]

    success = run_cmd(cmd)
    if success:
        run_cmd([
            "kubectl", "-n", args.namespace, "rollout", "status",
            f"deployment/{args.service}", "--timeout=60s"
        ])
        print("[OK] Finished network latency update.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

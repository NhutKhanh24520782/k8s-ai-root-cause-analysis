"""
scripts/fault_injection/inject_db_slowness.py

Injects artificial database latency into order-service via deployment env var patch,
or directly executes pg_sleep in postgresql order-db.

Usage:
    # Inject 500ms DB delay into order-service
    python scripts/fault_injection/inject_db_slowness.py --delay-ms 500 --namespace microservices

    # Restore to normal
    python scripts/fault_injection/inject_db_slowness.py --restore --namespace microservices
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
    parser = argparse.ArgumentParser(description="Inject or restore database query slowness.")
    parser.add_argument("--namespace", default="microservices")
    parser.add_argument("--deployment", default="order-service")
    parser.add_argument("--delay-ms", type=int, default=500, help="Artificial delay in milliseconds")
    parser.add_argument("--restore", action="store_true", help="Restore to normal")
    args = parser.parse_args()

    if args.restore:
        print(f"[*] Restoring {args.deployment} database latency to normal...")
        cmd = [
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.deployment}",
            "SIMULATE_DB_DELAY=false",
            "DB_DELAY_MS=0",
            "FAULT_TYPE=normal",
        ]
    else:
        print(f"[*] Injecting DB slowness (+{args.delay_ms}ms) into {args.deployment}...")
        cmd = [
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.deployment}",
            "SIMULATE_DB_DELAY=true",
            f"DB_DELAY_MS={args.delay_ms}",
            "FAULT_TYPE=db_slowness",
        ]

    success = run_cmd(cmd)
    if success:
        run_cmd([
            "kubectl", "-n", args.namespace, "rollout", "status",
            f"deployment/{args.deployment}", "--timeout=60s"
        ])
        print("[OK] Operation completed successfully.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

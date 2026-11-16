"""Run bounded CPU stress on a Kubernetes microservice pod.

Examples:
  py scripts/fault_injection/inject_cpu_stress.py --service order-service --duration 300
  py scripts/fault_injection/inject_cpu_stress.py --namespace microservices --workers 2 --duration 60

Requires kubectl access to the intended Kubernetes cluster and a POSIX sh in the pod.
The stress automatically ends after --duration; it does not change deployment env vars.
To undo older environment-based fault injections explicitly, use --restore.
"""

import argparse
import json
import subprocess
import sys

SERVICES = ("api-gateway", "order-service", "payment-service")

# POSIX sh only: unlike prior implementation, does not require Python in the pod.
# Positional args prevent interpolating user-controlled input into shell code.
STRESS_SH = r'''
duration=$1
workers=$2
end=$(( $(date +%s) + duration ))
i=0
pids=""
trap 'kill $pids 2>/dev/null || :; wait 2>/dev/null || :' HUP INT TERM EXIT
while [ "$i" -lt "$workers" ]; do
  (while [ "$(date +%s)" -lt "$end" ]; do :; done) &
  pids="$pids $!"
  i=$((i + 1))
done
wait
trap - HUP INT TERM EXIT
'''.strip()


def select_ready_pod(pods, service):
    """Use app label and readiness status to avoid stale/terminating pods."""
    ready = []
    for pod in pods:
        metadata = pod.get("metadata", {})
        status = pod.get("status", {})
        if status.get("phase") != "Running" or metadata.get("deletionTimestamp"):
            continue
        if metadata.get("labels", {}).get("app") != service:
            continue
        container_statuses = status.get("containerStatuses", [])
        if not any(cs.get("name") == service and cs.get("ready") for cs in container_statuses):
            continue
        ready.append(metadata["name"])
    if not ready:
        raise RuntimeError(f"No Ready running pod for app={service}. Check kubectl get pods -n <namespace>.")
    return sorted(ready)[0]


def run_cmd(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="microservices")
    parser.add_argument("--service", choices=SERVICES, default="order-service")
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--restore", action="store_true", help="Explicitly reset old deployment environment flags; triggers a rollout")
    args = parser.parse_args(argv)
    if args.duration <= 0 or not 1 <= args.workers <= 16:
        parser.error("--duration must be positive and --workers must be between 1 and 16")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.restore:
            command = [
                "kubectl", "-n", args.namespace, "set", "env", f"deployment/{args.service}",
                "FAULT_TYPE=normal", "FAULT_CPU_STRESS=false",
            ]
            print("Restoring earlier environment-based fault flags (deployment rollout may occur)...", flush=True)
            run_cmd(command)
            print("[OK] Deployment environment reset")
            return 0

        pods_raw = run_cmd([
            "kubectl", "get", "pods", "-n", args.namespace, "-l", f"app={args.service}", "-o", "json"
        ]).stdout
        pod = select_ready_pod(json.loads(pods_raw).get("items", []), args.service)
        command = [
            "kubectl", "exec", "-n", args.namespace, pod, "-c", args.service,
            "--", "sh", "-c", STRESS_SH, "sh", str(args.duration), str(args.workers)
        ]
        print(f"CPU stress: namespace={args.namespace}, pod={pod}, duration={args.duration}s, workers={args.workers}", flush=True)
        # The command is foreground and ends itself after --duration seconds.
        run_cmd(command, timeout=args.duration + 60)
        print("[OK] CPU stress completed")
        return 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError, OSError, ValueError, KeyError) as exc:
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print("kubectl stderr:", exc.stderr.strip(), file=sys.stderr)
        print("[ERROR] CPU stress failed:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

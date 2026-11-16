import argparse
import subprocess
import sys

def run_cmd(cmd: list) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout.strip()

def get_pod_name(namespace: str, service: str) -> str:
    for label in [f"app={service}", f"app.kubernetes.io/name={service}"]:
        try:
            name = run_cmd(["kubectl", "get", "pods", "-n", namespace, "-l", label, "-o", "jsonpath={.items[0].metadata.name}"])
            if name:
                return name
        except Exception:
            continue
    return ""

def main():
    parser = argparse.ArgumentParser(description="Inject CPU stress into service pod.")
    parser.add_argument("--namespace", default="microservices")
    parser.add_argument("--service", default="order-service")
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    if args.restore:
        print(f"[*] Removing CPU stress flags from {args.service}...")
        subprocess.run([
            "kubectl", "-n", args.namespace, "set", "env",
            f"deployment/{args.service}",
            "FAULT_TYPE=normal",
            "FAULT_CPU_STRESS=false",
            "SIMULATE_CPU_STRESS=false",
        ], check=False)
        return

    print(f"[*] Patching deployment/{args.service} with SIMULATE_CPU_STRESS=true...")
    subprocess.run([
        "kubectl", "-n", args.namespace, "set", "env",
        f"deployment/{args.service}",
        "FAULT_TYPE=cpu_stress",
        "FAULT_CPU_STRESS=true",
        "SIMULATE_CPU_STRESS=true",
    ], check=False)

    pod = get_pod_name(args.namespace, args.service)
    if not pod:
        print(f"[*] Deployment patched. Pod name not immediately resolved, will take effect on rollout.")
        return

    print(f"[*] Executing direct CPU load on pod {pod} for {args.duration}s with {args.workers} workers...")
    stress_cmd = (
        f"python3 -c \"import time, multiprocessing; "
        f"def f(): t=time.time()+{args.duration}; [x*x for x in iter(lambda: time.time()<t, False)]; "
        f"[multiprocessing.Process(target=f).start() for _ in range({args.workers})]\""
    )
    subprocess.run(["kubectl", "exec", "-n", args.namespace, pod, "--", "sh", "-c", stress_cmd], check=False)
    print("[OK] Finished.")

if __name__ == "__main__":
    main()

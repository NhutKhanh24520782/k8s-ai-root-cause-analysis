#!/usr/bin/env bash
# scripts/fault_injection/inject_cpu_stress.sh
# Injects CPU stress into target microservice pod using stress-ng or burn-in loop.
# Usage:
#   bash scripts/fault_injection/inject_cpu_stress.sh [service_name] [duration_seconds] [cpu_workers]

set -euo pipefail

NAMESPACE="${NAMESPACE:-microservices}"
SERVICE="${1:-order-service}"
DURATION="${2:-300}"
WORKERS="${3:-2}"

echo "[*] Locating pod for service: ${SERVICE} in namespace ${NAMESPACE}..."
POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l "app=${SERVICE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [[ -z "${POD_NAME}" ]]; then
    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l "app.kubernetes.io/name=${SERVICE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
fi

if [[ -z "${POD_NAME}" ]]; then
    echo "[!] Error: No pod found for service ${SERVICE} in namespace ${NAMESPACE}"
    exit 1
fi

echo "[*] Injecting CPU stress on pod: ${POD_NAME} for ${DURATION}s with ${WORKERS} workers..."

# Attempt stress-ng first, fallback to python/sh busy loop if stress-ng not in container
kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- /bin/sh -c \
  "if command -v stress-ng >/dev/null 2>&1; then \
     stress-ng --cpu ${WORKERS} --timeout ${DURATION}s; \
   elif command -v python3 >/dev/null 2>&1; then \
     python3 -c \"import time, multiprocessing; def f(): t=time.time()+${DURATION}; [x*x for x in iter(lambda: time.time()<t, False)]; [multiprocessing.Process(target=f).start() for _ in range(${WORKERS})]\"; \
   else \
     for i in \$(seq 1 ${WORKERS}); do (timeout ${DURATION}s sh -c 'while :; do :; done') & done; wait; \
   fi"

echo "[✓] CPU stress injection completed on ${POD_NAME}"

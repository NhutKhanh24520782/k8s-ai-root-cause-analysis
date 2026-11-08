#!/usr/bin/env bash
# scripts/fault_injection/inject_network_latency.sh
# Injects cross-service network latency using Linux Traffic Control (tc netem)
# Usage:
#   bash scripts/fault_injection/inject_network_latency.sh [service_name] [delay_ms] [restore]

set -euo pipefail

NAMESPACE="${NAMESPACE:-microservices}"
SERVICE="${1:-order-service}"
DELAY_MS="${2:-200ms}"
RESTORE="${3:-false}"

echo "[*] Locating pod for service: ${SERVICE} in namespace ${NAMESPACE}..."
POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l "app=${SERVICE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [[ -z "${POD_NAME}" ]]; then
    POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l "app.kubernetes.io/name=${SERVICE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
fi

if [[ -z "${POD_NAME}" ]]; then
    echo "[!] Error: No pod found for service ${SERVICE} in namespace ${NAMESPACE}"
    exit 1
fi

if [[ "${RESTORE}" == "true" || "${RESTORE}" == "restore" ]]; then
    echo "[*] Removing traffic control delay from ${POD_NAME}..."
    kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- tc qdisc del dev eth0 root netem 2>/dev/null || true
    echo "[✓] Network restored to normal."
else
    echo "[*] Adding ${DELAY_MS} network latency on ${POD_NAME}..."
    kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- tc qdisc add dev eth0 root netem delay "${DELAY_MS}"
    echo "[✓] Latency of ${DELAY_MS} injected."
fi

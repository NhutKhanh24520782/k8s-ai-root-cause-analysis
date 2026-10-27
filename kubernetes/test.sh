#!/usr/bin/env bash

set -uo pipefail

# ============================================================
# Configuration
# ============================================================

KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config_NT548}"
NAMESPACE="${NAMESPACE:-microservices}"

ORDER_PORT=18001
PAYMENT_PORT=18002
GATEWAY_PORT=18000

PASS=0
FAIL=0
SKIP=0

PORT_FORWARD_PIDS=()

# ============================================================
# Helpers
# ============================================================

log() {
    printf '\n\033[1;34m[TEST]\033[0m %s\n' "$1"
}

pass() {
    printf '\033[1;32m[PASS]\033[0m %s\n' "$1"
    PASS=$((PASS + 1))
}

fail() {
    printf '\033[1;31m[FAIL]\033[0m %s\n' "$1"
    FAIL=$((FAIL + 1))
}

skip() {
    printf '\033[1;33m[SKIP]\033[0m %s\n' "$1"
    SKIP=$((SKIP + 1))
}

cleanup() {
    echo
    echo "Cleaning up background port-forward processes..."

    # Tắt trap trước khi cleanup để tránh gọi lặp
    trap - EXIT INT TERM

    # Kill tất cả port-forward do script khởi chạy
    for pid in "${PORT_FORWARD_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "Stopping port-forward PID=$pid"
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done

    # Chờ tiến trình kết thúc
    for pid in "${PORT_FORWARD_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            sleep 0.2
        fi

        # Nếu vẫn chạy thì buộc dừng
        if kill -0 "$pid" 2>/dev/null; then
            echo "Force killing PID=$pid"
            kill -KILL "$pid" 2>/dev/null || true
        fi

        # Thu hồi tiến trình con
        wait "$pid" 2>/dev/null || true
    done

    PORT_FORWARD_PIDS=()

    echo "Cleanup completed."
}

trap cleanup EXIT INT TERM

kube() {
    kubectl --kubeconfig "$KUBECONFIG" "$@"
}

check_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing dependency: $1"
        exit 1
    fi
}

# ============================================================
# HTTP checks
# ============================================================

check_http() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"

    local response
    local actual_status

    response=$(curl \
        --silent \
        --show-error \
        --max-time 5 \
        --output /tmp/eks-test-response \
        --write-out '%{http_code}' \
        "$url" 2>/dev/null) || response="000"

    actual_status="$response"

    if [[ "$actual_status" == "$expected_status" ]]; then
        pass "$name (HTTP $actual_status)"
        return 0
    fi

    fail "$name (expected HTTP $expected_status, received $actual_status)"

    if [[ -s /tmp/eks-test-response ]]; then
        echo "Response:"
        head -c 500 /tmp/eks-test-response
        echo
    fi

    return 1
}

check_health() {
    local name="$1"
    local url="$2"

    local response

    response=$(curl \
        --silent \
        --show-error \
        --max-time 5 \
        "$url" 2>/dev/null) || response=""

    if [[ "$response" == *'"status":"ok"'* ]] ||
       [[ "$response" == *'"status": "ok"'* ]]; then
        pass "$name health check"
        return 0
    fi

    fail "$name health check: unexpected response: ${response:-no response}"
    return 1
}

# ============================================================
# Kubernetes port-forward
# ============================================================

start_port_forward() {
    local resource="$1"
    local local_port="$2"
    local remote_port="$3"
    local name="$4"

    log "Starting port-forward for $name"

    kube port-forward \
        -n "$NAMESPACE" \
        "$resource" \
        "${local_port}:${remote_port}" \
        >"/tmp/eks-pf-${local_port}.log" 2>&1 &

    local pid=$!
    PORT_FORWARD_PIDS+=("$pid")

    for _ in $(seq 1 30); do
        if ! kill -0 "$pid" 2>/dev/null; then
            fail "Port-forward failed for $name"
            cat "/tmp/eks-pf-${local_port}.log"
            return 1
        fi

        if curl --silent --max-time 1 \
            "http://127.0.0.1:${local_port}/health" >/dev/null 2>&1; then
            pass "Port-forward ready: $name"
            return 0
        fi

        sleep 1
    done

    fail "Port-forward timeout for $name"
    cat "/tmp/eks-pf-${local_port}.log"
    return 1
}

# ============================================================
# Prerequisites
# ============================================================

check_command kubectl
check_command curl

if [[ ! -f "$KUBECONFIG" ]]; then
    echo "Kubeconfig not found: $KUBECONFIG"
    exit 1
fi

echo "============================================================"
echo " EKS Microservices Functional Smoke Test"
echo "============================================================"
echo "Namespace : $NAMESPACE"
echo "Kubeconfig: $KUBECONFIG"

# ============================================================
# Test 1: Cluster connectivity
# ============================================================

log "1. Checking Kubernetes cluster"

if kube get namespace "$NAMESPACE" >/dev/null 2>&1; then
    pass "Namespace $NAMESPACE exists"
else
    fail "Namespace $NAMESPACE not found or inaccessible"
    exit 1
fi

if kube get nodes >/dev/null 2>&1; then
    pass "Kubernetes API is accessible"
else
    fail "Cannot access Kubernetes API"
    exit 1
fi

# ============================================================
# Test 2: Database StatefulSets and Pods
# ============================================================

log "2. Checking PostgreSQL"

for db in order-db payment-db; do
    if kube get statefulset "$db" -n "$NAMESPACE" >/dev/null 2>&1; then
        ready=$(kube get statefulset "$db" \
            -n "$NAMESPACE" \
            -o jsonpath='{.status.readyReplicas}' 2>/dev/null)

        if [[ "${ready:-0}" -ge 1 ]]; then
            pass "$db StatefulSet is ready"
        else
            fail "$db StatefulSet has no ready replicas"
        fi
    else
        fail "$db StatefulSet not found"
    fi

    if kube get pod "${db}-0" -n "$NAMESPACE" >/dev/null 2>&1; then
        phase=$(kube get pod "${db}-0" \
            -n "$NAMESPACE" \
            -o jsonpath='{.status.phase}')

        if [[ "$phase" == "Running" ]]; then
            pass "$db-0 Pod is Running"
        else
            fail "$db-0 Pod status: $phase"
        fi
    else
        fail "$db-0 Pod not found"
    fi

    if kube get pvc "postgres-data-${db}-0" \
        -n "$NAMESPACE" >/dev/null 2>&1; then

        pvc_status=$(kube get pvc "postgres-data-${db}-0" \
            -n "$NAMESPACE" \
            -o jsonpath='{.status.phase}')

        if [[ "$pvc_status" == "Bound" ]]; then
            pass "$db PVC is Bound"
        else
            fail "$db PVC status: $pvc_status"
        fi
    else
        fail "$db PVC not found"
    fi
done

# ============================================================
# Test 3: Application Deployments
# ============================================================

log "3. Checking application Deployments"

for app in api-gateway order-service payment-service; do
    if ! kube get deployment "$app" -n "$NAMESPACE" >/dev/null 2>&1; then
        fail "$app Deployment not found"
        continue
    fi

    ready=$(kube get deployment "$app" \
        -n "$NAMESPACE" \
        -o jsonpath='{.status.readyReplicas}' 2>/dev/null)

    desired=$(kube get deployment "$app" \
        -n "$NAMESPACE" \
        -o jsonpath='{.spec.replicas}' 2>/dev/null)

    ready="${ready:-0}"
    desired="${desired:-1}"

    if [[ "$ready" -ge 1 && "$ready" -eq "$desired" ]]; then
        pass "$app Deployment ($ready/$desired replicas ready)"
    else
        fail "$app Deployment ($ready/$desired replicas ready)"
    fi
done

# ============================================================
# Test 4: Kubernetes Services
# ============================================================

log "4. Checking Kubernetes Services"

SERVICES_READY=true

for svc in order-service payment-service api-gateway; do
    if kube get service "$svc" -n "$NAMESPACE" >/dev/null 2>&1; then
        pass "$svc Service exists"
    else
        fail "$svc Service is missing"
        SERVICES_READY=false
    fi
done

# ============================================================
# Test 5: Port-forward to application Deployments
# ============================================================

log "5. Connecting to application Pods"

start_port_forward deployment/order-service \
    "$ORDER_PORT" 8001 order-service || true

start_port_forward deployment/payment-service \
    "$PAYMENT_PORT" 8002 payment-service || true

start_port_forward deployment/api-gateway \
    "$GATEWAY_PORT" 8000 api-gateway || true

# ============================================================
# Test 6: Health checks
# ============================================================

log "6. Testing /health"

check_health order-service \
    "http://127.0.0.1:${ORDER_PORT}/health" || true

check_health payment-service \
    "http://127.0.0.1:${PAYMENT_PORT}/health" || true

check_health api-gateway \
    "http://127.0.0.1:${GATEWAY_PORT}/health" || true

# ============================================================
# Test 7: Prometheus metrics
# ============================================================

log "7. Testing /metrics"

for item in \
    "order-service:${ORDER_PORT}" \
    "payment-service:${PAYMENT_PORT}" \
    "api-gateway:${GATEWAY_PORT}"
do
    name="${item%%:*}"
    port="${item##*:}"

    metrics=$(curl \
        --silent \
        --show-error \
        --max-time 5 \
        --write-out '\n%{http_code}' \
        "http://127.0.0.1:${port}/metrics" 2>/dev/null) || metrics=""

    http_status="${metrics##*$'\n'}"
    body="${metrics%$'\n'*}"

    if [[ "$http_status" == "200" ]] &&
       [[ "$body" == *"#"* ]]; then
        pass "$name /metrics returns Prometheus exposition"
    else
        fail "$name /metrics failed (HTTP ${http_status:-000})"
    fi
done

# ============================================================
# Test 8: Gateway routing prerequisites
# ============================================================

log "8. Checking gateway routing prerequisites"

if [[ "$SERVICES_READY" == true ]]; then
    for svc in order-service payment-service; do
        endpoints=$(kube get endpoints "$svc" \
            -n "$NAMESPACE" \
            -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)

        if [[ -n "$endpoints" ]]; then
            pass "$svc has ready endpoints"
        else
            fail "$svc has no ready endpoints"
        fi
    done

    check_http "Gateway /orders route" \
        "http://127.0.0.1:${GATEWAY_PORT}/orders" 200 || true

    check_http "Gateway /payments route" \
        "http://127.0.0.1:${GATEWAY_PORT}/payments" 200 || true
else
    skip "Gateway routing tests: required application Services are missing"
fi

# ============================================================
# Summary
# ============================================================

echo
echo "============================================================"
echo " Test Summary"
echo "============================================================"
printf '\033[1;32mPASS: %d\033[0m\n' "$PASS"
printf '\033[1;31mFAIL: %d\033[0m\n' "$FAIL"
printf '\033[1;33mSKIP: %d\033[0m\n' "$SKIP"
echo "============================================================"

if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
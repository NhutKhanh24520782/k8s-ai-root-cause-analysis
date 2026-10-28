#!/usr/bin/env bash
# =============================================================================
# test_monitoring.sh — Kiểm tra toàn bộ monitoring stack
# Chạy bằng: bash monitoring/test_monitoring.sh
# Yêu cầu: kubectl, curl, helm (tùy chọn)
# =============================================================================

set -uo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config_NT548}"
MON_NAMESPACE="${MON_NAMESPACE:-monitoring}"
APP_NAMESPACE="${APP_NAMESPACE:-microservices}"

PROM_LOCAL_PORT=19090
GRAFANA_LOCAL_PORT=13000

PASS=0
FAIL=0
SKIP=0

PORT_FORWARD_PIDS=()

# ── Helpers ──────────────────────────────────────────────────────────────────

log()  { printf '\n\033[1;34m[TEST]\033[0m %s\n' "$1"; }
pass() { printf '\033[1;32m[PASS]\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
skip() { printf '\033[1;33m[SKIP]\033[0m %s\n' "$1"; SKIP=$((SKIP+1)); }

cleanup() {
    echo; echo "Cleaning up port-forwards..."
    trap - EXIT INT TERM
    for pid in "${PORT_FORWARD_PIDS[@]:-}"; do
        kill -TERM "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    echo "Done."
}
trap cleanup EXIT INT TERM

kube() { kubectl --kubeconfig "$KUBECONFIG" "$@"; }

# ── Port-forward helper ───────────────────────────────────────────────────────

start_port_forward() {
    local resource="$1" ns="$2" local_port="$3" remote_port="$4" name="$5"

    kube port-forward -n "$ns" "$resource" "${local_port}:${remote_port}" \
        >"/tmp/mon-pf-${local_port}.log" 2>&1 &
    local pid=$!
    PORT_FORWARD_PIDS+=("$pid")

    for _ in $(seq 1 20); do
        sleep 1
        if ! kill -0 "$pid" 2>/dev/null; then
            fail "Port-forward died for $name"; cat "/tmp/mon-pf-${local_port}.log"; return 1
        fi
        if curl --silent --max-time 1 "http://127.0.0.1:${local_port}/-/healthy" >/dev/null 2>&1 ||
           curl --silent --max-time 1 "http://127.0.0.1:${local_port}/api/health" >/dev/null 2>&1; then
            pass "Port-forward ready: $name (:${local_port})"; return 0
        fi
    done
    fail "Port-forward timeout for $name"; cat "/tmp/mon-pf-${local_port}.log"; return 1
}

# ── Test 1: kube-prometheus-stack Pods ───────────────────────────────────────

log "1. Checking kube-prometheus-stack pods in namespace: $MON_NAMESPACE"

EXPECTED_APPS=(prometheus grafana alertmanager)

for app in "${EXPECTED_APPS[@]}"; do
    count=$(kube get pods -n "$MON_NAMESPACE" \
        --field-selector=status.phase=Running \
        -l "app.kubernetes.io/name=${app}" \
        --no-headers 2>/dev/null | wc -l | tr -d ' ')

    if [[ "${count:-0}" -ge 1 ]]; then
        pass "$app pod is Running ($count pod(s))"
    else
        fail "$app pod NOT Running in $MON_NAMESPACE"
    fi
done

# ── Test 2: ServiceMonitor objects ───────────────────────────────────────────

log "2. Checking ServiceMonitor CRDs for microservices"

for smon in api-gateway order-service payment-service; do
    if kube get servicemonitor "$smon" -n "$MON_NAMESPACE" >/dev/null 2>&1; then
        pass "ServiceMonitor/$smon exists"
    else
        fail "ServiceMonitor/$smon NOT found in $MON_NAMESPACE"
    fi
done

# ── Test 3: Prometheus port-forward + API ────────────────────────────────────

log "3. Connecting to Prometheus"

PROM_POD=$(kube get pod -n "$MON_NAMESPACE" \
    -l "app.kubernetes.io/name=prometheus" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [[ -z "${PROM_POD:-}" ]]; then
    skip "Prometheus pod not found — skipping API tests"
else
    kube port-forward -n "$MON_NAMESPACE" \
        "pod/$PROM_POD" "${PROM_LOCAL_PORT}:9090" \
        >"/tmp/mon-pf-${PROM_LOCAL_PORT}.log" 2>&1 &
    PROM_PID=$!
    PORT_FORWARD_PIDS+=("$PROM_PID")
    sleep 3

    # 3a. Prometheus health
    if curl --silent --max-time 5 \
        "http://127.0.0.1:${PROM_LOCAL_PORT}/-/healthy" | grep -q "Prometheus"; then
        pass "Prometheus /-/healthy is OK"
    else
        fail "Prometheus /-/healthy failed"
    fi

    # 3b. Targets scraping microservices
    log "3b. Checking Prometheus scrape targets"
    TARGETS=$(curl --silent --max-time 5 \
        "http://127.0.0.1:${PROM_LOCAL_PORT}/api/v1/targets" 2>/dev/null)

    for svc in api-gateway order-service payment-service; do
        if echo "$TARGETS" | grep -q "\"$svc\""; then
            # Check if it's UP
            if echo "$TARGETS" | python3 -c "
import json,sys
data=json.load(sys.stdin)
targets=data.get('data',{}).get('activeTargets',[])
for t in targets:
    if '$svc' in str(t.get('labels',{})):
        print(t.get('health',''))
        break
" 2>/dev/null | grep -q "up"; then
                pass "Prometheus scraping $svc (health=up)"
            else
                fail "Prometheus target $svc exists but health != up"
            fi
        else
            fail "Prometheus target for $svc NOT found"
        fi
    done

    # 3c. PromQL queries — custom metrics
    log "3c. Querying custom application metrics"

    QUERIES=(
        "http_requests_total"
        "http_request_duration_seconds_count"
        "http_requests_in_flight"
        "payment_attempts_total"
    )

    for q in "${QUERIES[@]}"; do
        result=$(curl --silent --max-time 5 \
            "http://127.0.0.1:${PROM_LOCAL_PORT}/api/v1/query?query=${q}" 2>/dev/null)

        if echo "$result" | grep -q '"status":"success"'; then
            count=$(echo "$result" | python3 -c \
                "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',{}).get('result',[])))" 2>/dev/null)
            if [[ "${count:-0}" -gt 0 ]]; then
                pass "PromQL: $q → $count series found"
            else
                fail "PromQL: $q → 0 series (metric not scraped yet)"
            fi
        else
            fail "PromQL: $q → query failed"
        fi
    done

    # 3d. Error rate check
    log "3d. Checking 5xx error rate"
    err_result=$(curl --silent --max-time 5 \
        "http://127.0.0.1:${PROM_LOCAL_PORT}/api/v1/query?query=sum(rate(http_requests_total{status=~\"5..\"}[5m]))" \
        2>/dev/null)
    err_val=$(echo "$err_result" | python3 -c \
        "import json,sys; d=json.load(sys.stdin); r=d.get('data',{}).get('result',[]); print(r[0][1] if r else '0')" \
        2>/dev/null)
    if python3 -c "exit(0 if float('${err_val:-0}') < 0.1 else 1)" 2>/dev/null; then
        pass "5xx error rate is low: ${err_val:-0} req/s"
    else
        fail "5xx error rate is HIGH: ${err_val} req/s — check application logs"
    fi
fi

# ── Test 4: Grafana ───────────────────────────────────────────────────────────

log "4. Connecting to Grafana"

GRAFANA_POD=$(kube get pod -n "$MON_NAMESPACE" \
    -l "app.kubernetes.io/name=grafana" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [[ -z "${GRAFANA_POD:-}" ]]; then
    skip "Grafana pod not found — skipping"
else
    kube port-forward -n "$MON_NAMESPACE" \
        "pod/$GRAFANA_POD" "${GRAFANA_LOCAL_PORT}:3000" \
        >"/tmp/mon-pf-${GRAFANA_LOCAL_PORT}.log" 2>&1 &
    PORT_FORWARD_PIDS+=($!)
    sleep 3

    # 4a. Grafana API health
    if curl --silent --max-time 5 \
        "http://127.0.0.1:${GRAFANA_LOCAL_PORT}/api/health" | grep -q '"ok"'; then
        pass "Grafana /api/health is OK"
    else
        fail "Grafana /api/health failed"
    fi

    # 4b. Check dashboards loaded
    DASHBOARDS=$(curl --silent --max-time 5 \
        -u "admin:admin" \
        "http://127.0.0.1:${GRAFANA_LOCAL_PORT}/api/search?type=dash-db" 2>/dev/null)

    for dash in "microservices-overview" "rca-model-monitoring"; do
        if echo "$DASHBOARDS" | grep -q "$dash"; then
            pass "Grafana dashboard: $dash found"
        else
            fail "Grafana dashboard: $dash NOT found — import manually"
        fi
    done

    # 4c. Prometheus datasource configured
    DS=$(curl --silent --max-time 5 \
        -u "admin:admin" \
        "http://127.0.0.1:${GRAFANA_LOCAL_PORT}/api/datasources" 2>/dev/null)

    if echo "$DS" | grep -qi "prometheus"; then
        pass "Grafana Prometheus datasource configured"
    else
        fail "Grafana Prometheus datasource NOT configured"
    fi
fi

# ── Test 5: Alertmanager ─────────────────────────────────────────────────────

log "5. Checking Alertmanager"

AM_POD=$(kube get pod -n "$MON_NAMESPACE" \
    -l "app.kubernetes.io/name=alertmanager" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [[ -z "${AM_POD:-}" ]]; then
    skip "Alertmanager pod not found"
else
    AM_STATUS=$(kube get pod "$AM_POD" -n "$MON_NAMESPACE" \
        -o jsonpath='{.status.phase}' 2>/dev/null)
    if [[ "$AM_STATUS" == "Running" ]]; then
        pass "Alertmanager pod is Running"
    else
        fail "Alertmanager pod status: ${AM_STATUS:-unknown}"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo
echo "============================================================"
echo " Monitoring Test Summary"
echo "============================================================"
printf '\033[1;32mPASS: %d\033[0m\n' "$PASS"
printf '\033[1;31mFAIL: %d\033[0m\n' "$FAIL"
printf '\033[1;33mSKIP: %d\033[0m\n' "$SKIP"
echo "============================================================"

[[ "$FAIL" -gt 0 ]] && exit 1 || exit 0

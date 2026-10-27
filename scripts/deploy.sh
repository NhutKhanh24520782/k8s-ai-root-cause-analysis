#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Full deployment flow sau khi terraform apply xong
# Chạy từ thư mục gốc: bash scripts/deploy.sh
#
# Yêu cầu: aws cli, kubectl, helm, docker
# =============================================================================

set -euo pipefail

# ── Cấu hình ─────────────────────────────────────────────────────────────────

AWS_REGION="${AWS_REGION:-ap-southeast-1}"
CLUSTER_NAME="${CLUSTER_NAME:-ai-rca-dev-cluster}"
APP_NAMESPACE="microservices"
MON_NAMESPACE="monitoring"

# Lấy ECR registry từ terraform output
ECR_REGISTRY=$(terraform -chdir=terraform output -raw ecr_repository_urls 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d.values())[0].split('/')[0])" 2>/dev/null \
    || echo "")

# Fallback: lấy từ AWS account ID
if [[ -z "$ECR_REGISTRY" ]]; then
    AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    ECR_REGISTRY="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
fi

log()     { printf '\n\033[1;34m[STEP]\033[0m %s\n' "$1"; }
success() { printf '\033[1;32m[OK]\033[0m %s\n' "$1"; }
warn()    { printf '\033[1;33m[WARN]\033[0m %s\n' "$1"; }
die()     { printf '\033[1;31m[ERROR]\033[0m %s\n' "$1"; exit 1; }

echo "============================================================"
echo " Full Deployment — AI RCA Project"
echo "============================================================"
echo "Region       : $AWS_REGION"
echo "Cluster      : $CLUSTER_NAME"
echo "ECR Registry : $ECR_REGISTRY"
echo "============================================================"

# ── Step 1: Configure kubectl ─────────────────────────────────────────────────

log "1. Updating kubeconfig for EKS cluster"
aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER_NAME"
kubectl get nodes || die "Cannot connect to EKS cluster"
success "kubectl configured"

# ── Step 2: Create namespaces ─────────────────────────────────────────────────

log "2. Creating Kubernetes namespaces"
kubectl apply -f kubernetes/namespaces/namespaces.yaml
success "Namespaces created"

# ── Step 3: Create Secrets ────────────────────────────────────────────────────

log "3. Creating database secrets"

# Dùng biến môi trường hoặc giá trị mặc định (CHỈ cho dev/lab)
ORDER_DB_PASS="${ORDER_DB_PASSWORD:-$(openssl rand -hex 16)}"
PAYMENT_DB_PASS="${PAYMENT_DB_PASSWORD:-$(openssl rand -hex 16)}"

kubectl create secret generic order-db-secret \
    --namespace "$APP_NAMESPACE" \
    --from-literal=POSTGRES_DB=orders_db \
    --from-literal=POSTGRES_USER=order_user \
    --from-literal=POSTGRES_PASSWORD="$ORDER_DB_PASS" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic payment-db-secret \
    --namespace "$APP_NAMESPACE" \
    --from-literal=POSTGRES_DB=payment_db \
    --from-literal=POSTGRES_USER=payment_user \
    --from-literal=POSTGRES_PASSWORD="$PAYMENT_DB_PASS" \
    --dry-run=client -o yaml | kubectl apply -f -

success "Secrets created"

# ── Step 4: Build & Push Docker images to ECR ─────────────────────────────────

log "4. Authenticating Docker with ECR"
aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"
success "Docker authenticated with ECR"

log "4b. Building and pushing images"

SERVICES=("api-gateway" "order-service" "payment-service")
SERVICE_DIRS=("api-gateway" "order-service" "payment-service")

for i in "${!SERVICES[@]}"; do
    svc="${SERVICES[$i]}"
    dir="microservices/services/${SERVICE_DIRS[$i]}"
    tag="1.0.0"
    image="${ECR_REGISTRY}/${svc}:${tag}"

    echo "  → Building $svc..."
    docker build -t "$image" "$dir"
    docker push "$image"
    success "Pushed $image"
done

# ── Step 5: Deploy PostgreSQL StatefulSets ────────────────────────────────────

log "5. Deploying PostgreSQL databases"
kubectl apply -f kubernetes/postgres/order_db/
kubectl apply -f kubernetes/postgres/payment_db/

echo "Waiting for databases to be ready..."
kubectl rollout status statefulset/order-db   -n "$APP_NAMESPACE" --timeout=120s
kubectl rollout status statefulset/payment-db -n "$APP_NAMESPACE" --timeout=120s
success "Databases ready"

# ── Step 6: Deploy Microservices ──────────────────────────────────────────────

log "6. Deploying microservices"

# Thay ECR_REGISTRY placeholder trong YAML trước khi apply
for svc in api-gateway order-service payment-service; do
    sed "s|\${ECR_REGISTRY}|${ECR_REGISTRY}|g" \
        "kubernetes/microservices/${svc}/deployment.yaml" \
        | kubectl apply -f -
    kubectl apply -f "kubernetes/microservices/${svc}/service.yaml"
done

echo "Waiting for microservices to be ready..."
for svc in api-gateway order-service payment-service; do
    kubectl rollout status deployment/"$svc" -n "$APP_NAMESPACE" --timeout=180s
done
success "All microservices running"

# ── Step 7: Install kube-prometheus-stack ─────────────────────────────────────

log "7. Installing kube-prometheus-stack (Helm)"

helm repo add prometheus-community \
    https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update

helm upgrade --install kube-prometheus-stack \
    prometheus-community/kube-prometheus-stack \
    --namespace "$MON_NAMESPACE" \
    --create-namespace \
    --values monitoring/helm-values/kube-prometheus-stack-values.yaml \
    --wait --timeout 5m

success "Monitoring stack installed"

# ── Step 8: Smoke test ────────────────────────────────────────────────────────

log "8. Running smoke tests"
bash kubernetes/test.sh        || warn "Some k8s smoke tests failed — check output above"
bash monitoring/test_monitoring.sh || warn "Some monitoring tests failed — pods may still be starting"

echo
echo "============================================================"
echo " Deployment Complete!"
echo "============================================================"
echo
echo "Access services:"
echo "  kubectl port-forward -n $APP_NAMESPACE svc/api-gateway 8000:8000"
echo "  kubectl port-forward -n $MON_NAMESPACE svc/kube-prometheus-stack-prometheus 9090:9090"
echo "  kubectl port-forward -n $MON_NAMESPACE svc/kube-prometheus-stack-grafana 3000:80"
echo
echo "Grafana password:"
echo "  kubectl get secret -n $MON_NAMESPACE kube-prometheus-stack-grafana \\"
echo "    -o jsonpath='{.data.admin-password}' | base64 --decode"
echo "============================================================"

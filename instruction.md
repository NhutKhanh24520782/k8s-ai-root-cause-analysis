# Full Deployment Flow — Sau Terraform Apply

## Kiến trúc tổng quan

```
Terraform Apply
    ↓
EKS Cluster + ECR Repos + VPC
    ↓
kubectl config → Namespaces → Secrets
    ↓
Docker Build → ECR Push
    ↓
PostgreSQL (StatefulSet) → Microservices → kube-prometheus-stack
    ↓
Smoke Tests
```

---

## Cách 1 — Chạy script tự động (khuyến nghị)

```bash
# Từ thư mục d:\mlops
bash scripts/deploy.sh
```

Script sẽ tự làm toàn bộ 8 bước bên dưới.

---

## Cách 2 — Chạy thủ công từng bước

### Bước 1 — Cấu hình kubectl
```bash
aws eks update-kubeconfig --region ap-southeast-1 --name ai-rca-dev-cluster

# Kiểm tra node đã Ready
kubectl get nodes
```

### Bước 2 — Tạo Namespaces
```bash
kubectl apply -f kubernetes/namespaces/namespaces.yaml

# Verify
kubectl get namespaces | grep -E "microservices|monitoring|ml-stack"
```

### Bước 3 — Tạo Kubernetes Secrets (bắt buộc trước khi deploy)
```bash
kubectl create secret generic order-db-secret \
  --namespace microservices \
  --from-literal=POSTGRES_DB=orders_db \
  --from-literal=POSTGRES_USER=order_user \
  --from-literal=POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD

kubectl create secret generic payment-db-secret \
  --namespace microservices \
  --from-literal=POSTGRES_DB=payment_db \
  --from-literal=POSTGRES_USER=payment_user \
  --from-literal=POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD

# Verify
kubectl get secrets -n microservices
```

### Bước 4 — Build & Push Docker images lên ECR

```bash
# Lấy ECR registry URL từ terraform output
ECR_REGISTRY=$(terraform -chdir=terraform output -json ecr_repository_urls \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d.values())[0].split('/')[0])")

echo "ECR: $ECR_REGISTRY"
# Ví dụ: 274118253913.dkr.ecr.ap-southeast-1.amazonaws.com

# Login Docker vào ECR
aws ecr get-login-password --region ap-southeast-1 \
  | docker login --username AWS --password-stdin $ECR_REGISTRY

# Build và push từng service
for svc in api-gateway order-service payment-service; do
  docker build -t $ECR_REGISTRY/$svc:1.0.0 microservices/services/$svc/
  docker push $ECR_REGISTRY/$svc:1.0.0
  echo "✅ Pushed $svc"
done
```

### Bước 5 — Deploy PostgreSQL StatefulSets
```bash
kubectl apply -f kubernetes/postgres/order_db/
kubectl apply -f kubernetes/postgres/payment_db/

# Chờ DB ready (khoảng 1-2 phút)
kubectl rollout status statefulset/order-db   -n microservices --timeout=120s
kubectl rollout status statefulset/payment-db -n microservices --timeout=120s

# Verify
kubectl get pods -n microservices
```

### Bước 6 — Deploy Microservices

```bash
# Thay placeholder ${ECR_REGISTRY} rồi apply
for svc in api-gateway order-service payment-service; do
  sed "s|\${ECR_REGISTRY}|${ECR_REGISTRY}|g" \
    kubernetes/microservices/$svc/deployment.yaml | kubectl apply -f -

  kubectl apply -f kubernetes/microservices/$svc/service.yaml
done

# Chờ tất cả pods Ready
kubectl rollout status deployment/api-gateway     -n microservices --timeout=180s
kubectl rollout status deployment/order-service   -n microservices --timeout=180s
kubectl rollout status deployment/payment-service -n microservices --timeout=180s

# Verify
kubectl get pods -n microservices
kubectl get services -n microservices
```

### Bước 7 — Cài kube-prometheus-stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Phải chạy từ d:\mlops
helm upgrade --install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --values monitoring/helm-values/kube-prometheus-stack-values.yaml \
  --wait --timeout 5m

# Chờ pods (khoảng 3-5 phút)
kubectl get pods -n monitoring -w
```

### Bước 8 — Kiểm tra toàn bộ

```bash
# Test microservices
KUBECONFIG=~/.kube/config bash kubernetes/test.sh

# Test monitoring
bash monitoring/test_monitoring.sh
```

---

## Vì sao monitoring test đang FAIL?

Các pods mới được cài, cần **3-5 phút** để khởi động. Chạy lại sau:

```bash
# Xem trạng thái pods
kubectl get pods -n monitoring

# Khi thấy tất cả Running/Ready thì chạy lại test
bash monitoring/test_monitoring.sh
```

Lý do khác có thể: Script test tìm pod theo label `app.kubernetes.io/name=prometheus` nhưng kube-prometheus-stack dùng label khác. Kiểm tra:
```bash
kubectl get pods -n monitoring --show-labels
```

---

## Truy cập sau khi deploy

### API Gateway (test requests)
```bash
kubectl port-forward -n microservices svc/api-gateway 8000:8000
curl http://localhost:8000/health
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"item_name":"Laptop","quantity":1}'
```

### Prometheus UI
```bash
kubectl port-forward -n monitoring \
  svc/kube-prometheus-stack-prometheus 9090:9090
# → http://localhost:9090
```

### Grafana
```bash
kubectl port-forward -n monitoring \
  svc/kube-prometheus-stack-grafana 3000:80
# → http://localhost:3000  (user: admin)

# Lấy password
kubectl get secret -n monitoring kube-prometheus-stack-grafana \
  -o jsonpath="{.data.admin-password}" | base64 --decode
```

---

## Xóa toàn bộ resources (khi không dùng nữa)

```bash
# Xóa k8s resources
kubectl delete namespace microservices monitoring ml-stack

# Xóa AWS resources (tính phí)
terraform -chdir=terraform destroy
```

> ⚠️ **Chi phí:** EKS cluster + NAT Gateway + EC2 nodes tốn ~$5–10/ngày. Nhớ `terraform destroy` sau khi test xong!

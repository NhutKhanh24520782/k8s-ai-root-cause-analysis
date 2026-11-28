# End-to-End Deployment & CI/CD GitOps Guide

Tài liệu hướng dẫn toàn diện quy trình khởi tạo và vận hành hệ thống từ hạ tầng **Terraform**, quy trình **CI/CD bằng GitHub Actions** đến triển khai tự động **GitOps qua ArgoCD** trên Amazon EKS.

---

## 1. Kiến trúc luồng triển khai (GitOps Flow)

```
[ Terraform Apply ]
        ↓
[ AWS EKS Cluster + ECR + VPC ]
        ↓
[ Cấu hình kubectl → Tạo Namespaces → Tạo DB Secrets ]
        ↓
[ Deploy PostgreSQL StatefulSets (order-db, payment-db) ]
        ↓
[ Cài đặt ArgoCD GitOps Controller & App-of-Apps ]
        ↓
[ Developer: Push Git Tag v*.*.* ] ──→ [ GitHub Actions CI: Build & Push ECR ]
                                                        ↓
[ GitHub Actions CD (cd-approve.yml) ] ←── [ Phê duyệt Release (Target Env & Tag) ]
        ↓ (Cập nhật newTag trong kubernetes/overlays/<env>/kustomization.yaml)
[ Push commit lên Git ]
        ↓ (Tự động đồng bộ hóa)
[ ArgoCD tự động Reconcile & Rollout Deployment mới trên EKS ]
```

---

## 2. Quy trình triển khai chi tiết từng bước

### Bước 1 — Khởi tạo hạ tầng AWS bằng Terraform

1. **Khởi tạo S3 Remote State & DynamoDB Lock** (nếu chưa có):
   ```bash
   cd terraform/bootstrap
   terraform init
   terraform apply -auto-approve
   cd ../
   ```

2. **Provision VPC, EKS Cluster, ECR & IAM Roles**:
   ```bash
   terraform init
   terraform plan -out=tfplan
   terraform apply tfplan
   ```

---

### Bước 2 — Cấu hình `kubectl` & EBS CSI Driver

1. **Cập nhật kubeconfig local**:
   ```bash
   aws eks update-kubeconfig --region ap-southeast-1 --name ai-rca-dev-cluster

   # Kiểm tra các node đã ở trạng thái Ready
   kubectl get nodes
   ```

2. **Cài đặt AWS EBS CSI Driver Add-on** (cần thiết cho PVC của database):
   ```bash
   aws eks create-addon \
     --cluster-name ai-rca-dev-cluster \
     --addon-name aws-ebs-csi-driver \
     --region ap-southeast-1

   # Kiểm tra StorageClass
   kubectl get sc
   ```

---

### Bước 3 — Tạo Namespaces & Secrets (Bắt buộc trước khi chạy App)

> ⚠️ **Lưu ý quan trọng về Secret trong GitOps:**  
> Mật khẩu và thông tin đăng nhập database **không được commit lên Git**. Do đó, bạn phải tạo Secret trực tiếp trên cluster một lần lúc bootstrap hoặc thông qua Secret Manager.

1. **Tạo Namespaces**:
   ```bash
   kubectl apply -f kubernetes/base/namespaces.yaml
   # Kiểm tra:
   kubectl get namespaces | grep -E "microservices|monitoring|ml-stack"
   ```

2. **Tạo Secrets cho Database & Microservices**:
   ```bash
   # Secret cho Order Service & Order DB
   kubectl create secret generic order-db-secret \
     --namespace microservices \
     --from-literal=POSTGRES_HOST=order-db \
     --from-literal=POSTGRES_PORT=5432 \
     --from-literal=POSTGRES_DB=orders_db \
     --from-literal=POSTGRES_USER=order_user \
     --from-literal=POSTGRES_PASSWORD=order_password_123

   # Secret cho Payment Service & Payment DB
   kubectl create secret generic payment-db-secret \
     --namespace microservices \
     --from-literal=POSTGRES_HOST=payment-db \
     --from-literal=POSTGRES_PORT=5432 \
     --from-literal=POSTGRES_DB=payment_db \
     --from-literal=POSTGRES_USER=payment_user \
     --from-literal=POSTGRES_PASSWORD=payment_password_123

   # Kiểm tra lại Secret:
   kubectl get secrets -n microservices
   ```

---

### Bước 4 — Triển khai PostgreSQL StatefulSets

Microservices phụ thuộc vào database để vượt qua kiểm tra Readiness Probe (`/health`). Hãy deploy database trước:

```bash
# Triển khai Order DB & Payment DB
kubectl apply -f kubernetes/postgres/order_db/
kubectl apply -f kubernetes/postgres/payment_db/

# Chờ cả 2 database đạt trạng thái Ready (khoảng 1-2 phút)
kubectl wait --for=condition=ready pod/order-db-0 -n microservices --timeout=120s
kubectl wait --for=condition=ready pod/payment-db-0 -n microservices --timeout=120s

# Kiểm tra Pods & PVC:
kubectl get statefulset,pvc,svc -n microservices
```

---

### Bước 5 — Cài đặt và cấu hình ArgoCD (GitOps Engine)

1. **Cài đặt ArgoCD vào EKS Cluster**:
   ```bash
   kubectl create namespace argocd
   kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

   # Chờ các pod ArgoCD sẵn sàng:
   kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=argocd-server -n argocd --timeout=180s
   ```

2. **Lấy mật khẩu đăng nhập ArgoCD UI**:
   - Trên Linux / macOS / Git Bash:
     ```bash
     kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 --decode
     ```
   - Trên Windows PowerShell:
     ```powershell
     kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | %{ [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
     ```

3. **Mở giao diện ArgoCD UI**:
   ```bash
   kubectl port-forward svc/argocd-server -n argocd 8080:443
   # Truy cập: https://localhost:8080 (User: admin)
   ```

4. **Triển khai ArgoCD Application**:
   ```bash
   # Triển khai môi trường dev (trỏ vào kubernetes/overlays/dev)
   kubectl apply -f argocd/apps/microservices-dev.yaml

   # (Tùy chọn) Hoặc triển khai toàn bộ qua App-of-Apps:
   # kubectl apply -f argocd/apps/app-of-apps.yaml
   ```

---

### Bước 6 — Quy trình CI: Đóng gói & Đẩy Image lên ECR

Khi có thay đổi code và sẵn sàng release:

1. **Tạo và đẩy Git Tag định dạng SemVer (`v*.*.*`)**:
   ```bash
   # Ví dụ release v1.0.12
   git tag v1.0.12
   git push origin v1.0.12
   ```

2. **GitHub Actions (`ci.yml`) sẽ tự động**:
   - Chạy Unit tests & linter.
   - Build Docker images cho các services (`api-gateway`, `order-service`, `payment-service`).
   - Đẩy images lên Amazon ECR với tag chính xác `v1.0.12`.
   - Tạo GitHub Release tự động.

---

### Bước 7 — Quy trình CD: Phê duyệt & Cập nhật Kustomize Overlay

Để đưa phiên bản mới vào môi trường cụ thể (`dev`, `staging`, hoặc `prod`):

1. Vào GitHub Repository $\rightarrow$ chọn tab **Actions**.
2. Chọn workflow **CD Release Approval & Promote** (`cd-approve.yml`).
3. Nhấp vào **Run workflow**:
   - **Target Environment**: chọn `dev` (hoặc `staging`, `prod`).
   - **Release Image Tag**: nhập `v1.0.12` (bắt buộc đúng định dạng `v*.*.*`).
4. **Workflow sẽ tự động thực hiện**:
   - Kiểm tra tag `v1.0.12` đã tồn tại trên Amazon ECR chưa.
   - Cập nhật trường `newTag: v1.0.12` trong file [kubernetes/overlays/dev/kustomization.yaml](file:///d:/new-devops/k8s-ai-root-cause-analysis/kubernetes/overlays/dev/kustomization.yaml).
   - Chạy `kubectl kustomize` kiểm tra tính hợp lệ.
   - Tự động tạo commit và push lên Git với `[skip ci]`.

---

### Bước 8 — ArgoCD Tự động Đồng bộ (Reconcile) & Kiểm tra

1. ArgoCD tự động phát hiện commit mới trên Git.
2. ArgoCD tiến hành Rolling Update các Deployment tương ứng với tag mới.
3. Kiểm tra trạng thái Pods trong cluster:
   ```bash
   kubectl get pods -n microservices -w
   ```
4. Khi quá trình hoàn tất:
   - Các pods `api-gateway`, `order-service`, `payment-service` đều ở trạng thái `Running (1/1)`.
   - Trên ArgoCD UI: Ứng dụng báo **Synced** và **Healthy**.

---

### Bước 9 — Cài đặt Monitoring (Prometheus & Grafana)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --values monitoring/helm-values/kube-prometheus-stack-values.yaml \
  --wait --timeout 5m

# Kiểm tra pods monitoring:
kubectl get pods -n monitoring
```

---

## 3. Xử lý sự cố thường gặp (Troubleshooting)

### Lỗi 1: `CreateContainerConfigError: secret "order-db-secret" not found`
- **Nguyên nhân**: Pod `order-service` cần các biến môi trường từ `order-db-secret` nhưng Secret này chưa được tạo trong namespace `microservices`.
- **Khắc phục**: Chạy lệnh tạo Secret ở **Bước 3.2**. Pod sẽ tự động nhận Secret và chuyển sang trạng thái `Running`.

### Lỗi 2: `Readiness probe failed: connect: connection refused (port 8001 / 8002)`
- **Nguyên nhân**: `order-service` hoặc `payment-service` không thể kết nối tới cơ sở dữ liệu `order-db` hoặc `payment-db` qua DNS nội bộ `5432`.
- **Khắc phục**: Kiểm tra database đã chạy chưa:
  ```bash
  kubectl get pods -n microservices | grep db
  ```
  Nếu chưa, chạy lại lệnh apply database ở **Bước 4**.

### Lỗi 3: `ImagePullBackOff` hoặc `ErrImagePull`
- **Nguyên nhân**:
  - Image tag trong Kustomize overlay không tồn tại trên Amazon ECR.
  - Node group của EKS thiếu quyền IAM `AmazonEC2ContainerRegistryReadOnly` để pull image từ ECR.
- **Khắc phục**:
  - Kiểm tra các image tags trên ECR:
    ```bash
    aws ecr describe-images --repository-name order-service --region ap-southeast-1
    ```
  - Kiểm tra xem đã kích hoạt workflow CI cho tag đó chưa (Bước 6).

---

## 4. Kiểm thử hệ thống sau khi triển khai (Smoke Tests)

```bash
# 1. Port-forward API Gateway
kubectl port-forward -n microservices svc/api-gateway 8000:8000

# 2. Kiểm tra Health Check
curl http://localhost:8000/health

# 3. Tạo đơn hàng mẫu
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"item_name":"Laptop Gaming","quantity":1}'

# 4. Kiểm tra danh sách đơn hàng
curl http://localhost:8000/orders
```

---

## 5. Dọn dẹp tài nguyên (Teardown)

Khi không sử dụng, hủy tài nguyên AWS để tránh phát sinh chi phí duy trì:

```bash
# 1. Xóa các applications và namespaces trên K8s
kubectl delete -f argocd/apps/microservices-dev.yaml --ignore-not-found
kubectl delete namespace microservices monitoring ml-stack argocd --ignore-not-found

# 2. Hủy toàn bộ hạ tầng AWS qua Terraform
cd terraform
terraform destroy -auto-approve
```

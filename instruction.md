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
Smoke Tests (Phase A1 & A2)
    ↓
Fault Injection & Metrics Collection (Phase A3 — Đình Tân)
    ↓
Feature Engineering & Model Training / MLflow (Phase B1 — Đình Tân)
    ↓
RCA FastAPI & Slack Alert (Phase B2 — Phước Thọ)
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

## Quy trình Chạy Fault Injection, Thu thập Data & Train Model ML (Thành viên 3 — Đình Tân)

Phần này hướng dẫn các thành viên trong nhóm (hoặc người kiểm thử) chạy và kiểm tra toàn bộ pipeline của **Thành viên 3 (Phase A3 & Phase B1)**: từ **Bơm lỗi (Fault Injection)**, **Thu thập dữ liệu Prometheus**, **Feature Engineering**, đến **Huấn luyện mô hình ML (MLflow tracking)** và **Kiểm tra suy luận (Inference test)**.

### 1. Chuẩn bị môi trường Python

Cài đặt các thư viện cần thiết cho phần Machine Learning:
```bash
pip install -r ml/requirements.txt
```
*(Yêu cầu Python >= 3.10. Gồm: `scikit-learn`, `pandas`, `numpy`, `joblib`, `mlflow-skinny`, `pydantic`, `skops`, `matplotlib`)*

---

### Cách 1: Kiểm thử nhanh không cần bật cluster EKS (Offline Synthetic Mode — Khuyến nghị)
> 💡 **Phù hợp nhất để các bạn trong nhóm test nhanh code ML trên máy cá nhân mà không tốn chi phí AWS EKS.**

#### Bước 1 — Tạo dataset chuẩn hóa:
```bash
python scripts/data_collection/generate_synthetic_data.py --samples 900 --output ml/data/dataset_cleaned.csv
```
*Tạo 900 mẫu metrics theo 36 chu kỳ (`run_id`), đầy đủ 6 nhãn sự cố theo đúng phân phối Prometheus thực tế.*

#### Bước 2 — Huấn luyện mô hình (Feature Engineering + Group Split + MLflow):
```bash
python ml/src/train.py
```
*Script sẽ tự động:*
1. Tính toán 5 derived features: `gw_to_order_latency_ratio`, `error_cascade_score`, `order_cpu_spike`, `payment_mem_growth_rate`, `db_latency_vs_order_latency`.
2. Chia tập Train/Test theo `run_id` (tránh rò rỉ dữ liệu).
3. Huấn luyện 3 mô hình: Baseline (Dummy), Random Forest, Gradient Boosting.
4. Log metrics, tham số và model vào MLflow (`./mlruns`).
5. Xuất model tối ưu ra `ml/models/rca_random_forest.joblib`, ma trận nhầm lẫn `ml/models/confusion_matrix.png`, và báo cáo `ml/models/evaluation_report.json` (Macro F1 đạt **~0.99**).

#### Bước 3 — Bật giao diện MLflow UI xem kết quả thực nghiệm:
```bash
mlflow ui --backend-store-uri ./mlruns --port 5000
```
*Mở trình duyệt truy cập: [http://localhost:5000](http://localhost:5000) để xem bảng so sánh các lần train, biểu đồ tham số, confusion matrix.*

#### Bước 4 — Kiểm thử hàm suy luận (Inference test) bàn giao cho Phase B2:
```bash
python ml/src/predict.py
```
*Script sẽ kiểm thử dự đoán trên 2 mẫu dữ liệu giả định và trả về kết quả JSON đúng chuẩn `rca-api/schemas.py`: nhãn chẩn đoán nguyên nhân gốc (`predicted_root_cause`), độ tin cậy (`confidence`), và top 2 khả năng cao nhất (`top_2_predictions`).*

---

### Cách 2: Chạy trực tiếp trên Live EKS Cluster (Live EKS + Prometheus)
> 💡 **Sử dụng khi cụm EKS đang chạy và đã triển khai microservices + kube-prometheus-stack.**

#### Bước 1 — Port-forward Prometheus về máy local:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

#### Bước 2 — Bơm lỗi vào cụm (Fault Injection):
Có 2 lựa chọn:

* **Lựa chọn A — Bơm lỗi tự động toàn bộ chu kỳ (Khuyến nghị để lấy dataset đầy đủ):**
  ```bash
  # Tự động lần lượt chạy: normal → cpu_stress → memory_leak → db_slowness → payment_failure → network_latency
  python scripts/fault_injection/run_collection_cycle.py --cycles 2 --step-duration 180
  ```

* **Lựa chọn B — Bơm từng lỗi cụ thể để test riêng lẻ:**
  * **CPU Stress (Order Service):**
    ```bash
    python scripts/fault_injection/inject_cpu_stress.py --duration 120
    # Hoặc qua shell script:
    bash scripts/fault_injection/inject_cpu_stress.sh 120
    ```
  * **Payment Service Failure (500 Error):**
    ```bash
    python scripts/fault_injection/inject_payment_failure.py --duration 120 --rate 0.8
    ```
  * **Database Slowness (Trì hoãn query):**
    ```bash
    python scripts/fault_injection/inject_db_slowness.py --delay 3.0 --duration 120
    ```
  * **Memory Leak:**
    ```bash
    python scripts/fault_injection/inject_memory_leak.py --duration 120
    ```
  * **Network Latency:**
    ```bash
    python scripts/fault_injection/inject_network_latency.py --latency 200ms --duration 120
    # Hoặc:
    bash scripts/fault_injection/inject_network_latency.sh 200ms 120
    ```

#### Bước 3 — Thu thập metrics từ Prometheus:
```bash
# Thu thập metrics với rate(...[2m]) tránh jitter
python scripts/data_collection/collect_metrics.py \
  --prom-url http://localhost:9090 \
  --output ml/data/dataset_raw.csv \
  --window 60m \
  --step 15s
```

#### Bước 4 — Làm sạch & Export dataset chuẩn:
```bash
python scripts/data_collection/export_dataset.py \
  --input ml/data/dataset_raw.csv \
  --output ml/data/dataset_cleaned.csv
```
*(Tùy chọn tải lên S3: `python scripts/data_collection/upload_to_s3.py --bucket <S3_BUCKET_NAME> --file ml/data/dataset_cleaned.csv`)*

#### Bước 5 — Huấn luyện và cập nhật mô hình:
```bash
python ml/src/train.py
```

---

### 3. Cấu trúc tài nguyên bàn giao cho Phase B2 (Phước Thọ — FastAPI)

Các thành viên phụ trách Phase B2 có thể tích hợp trực tiếp dựa trên các artifacts đã chuẩn bị sẵn:
1. **Model đã huấn luyện:** `ml/models/rca_random_forest.joblib`
2. **Hàm suy luận chuẩn:** `ml/src/predict.py` (`predict_root_cause(metrics_dict)`)
3. **Pydantic Schemas:** `rca-api/schemas.py` (`RCARequest`, `RCAResponse`, `TopPrediction`)
4. **Tài liệu bàn giao chi tiết:** `docs/handover_b1_to_b2.md`

---

## Xóa toàn bộ resources (khi không dùng nữa)

```bash
# Xóa k8s resources
kubectl delete namespace microservices monitoring ml-stack

# Xóa AWS resources (tính phí)
terraform -chdir=terraform destroy
```

> ⚠️ **Chi phí:** EKS cluster + NAT Gateway + EC2 nodes tốn ~$5–10/ngày. Nhớ `terraform destroy` sau khi test xong!

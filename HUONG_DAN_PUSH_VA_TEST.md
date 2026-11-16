# Sửa lỗi thu thập metrics cho Docker local và Amazon EKS

## Thay đổi chính

1. **`scripts/data_collection/collect_metrics_prometheus.py`**:
   - Vẫn hỗ trợ `--environment local` (chạy `--fault ... --duration ...` trên Docker local như cũ).
   - Thêm `--environment eks`: truy vấn CPU và RAM trực tiếp từ cAdvisor/kubelet qua Prometheus của cụm EKS bằng PromQL (`container_cpu_usage_seconds_total` và `container_memory_working_set_bytes`).
   - Đơn vị đo được chuẩn hóa đồng nhất:
     - **CPU**: % của một logical core (`100% = 1 core`).
     - **RAM**: tính bằng **MiB**.
   - Bảo vệ dataset gốc: mặc định lưu riêng vào `dataset/a3_metrics_clean_local.csv` (local) và `dataset/a3_metrics_clean_eks.csv` (EKS). Không ghi đè hay xóa dataset 354 mẫu cũ (`dataset/a3_prometheus_metrics_v2.csv`).
   - Kiểm tra nghiêm ngặt: nếu thiếu metric hoặc PromQL rỗng, script báo lỗi và từ chối ghi hàng rác vào CSV.

2. **`scripts/fault_injection/inject_cpu_stress.py`**:
   - Bơm lỗi CPU vào Kubernetes Pod bằng POSIX shell (`STRESS_SH`), có giới hạn thời gian (bounded duration) và tự dọn tiến trình (`trap`).
   - Không yêu cầu Python hay thư viện ngoài trong container ứng dụng.
   - Không can thiệp sửa biến môi trường của Deployment (`kubectl set env`), tránh gây rollout/restart Pod ngoài ý muốn.
   - Tự động lọc chọn Pod đang ở trạng thái `Running` và `Ready`, bỏ qua Pod đang terminating.
   - Có timeout và trả mã lỗi thực (exit code khác 0 khi thất bại, không in giả `[OK]`).

3. **`tests/test_metrics_and_fault.py`**:
   - 12 bài unit test kiểm thử offline toàn bộ logic thu thập metrics, tính toán đơn vị, guard schema CSV, và logic inject fault.
   - Đã xử lý tương thích Windows: tự động skip bài test POSIX shell trên Windows (tránh lỗi `WinError 2`).
   - Kết quả: **11 PASS, 1 SKIP** trên Windows (`OK (skipped=1)`), **12/12 PASS** trên Linux.

4. **Trường database**:
   - Hai cột `db_query_latency_p95` và `db_connection_count` được giữ nguyên trong schema 19 cột nhưng để trống vì hiện chưa có instrumentation DB tương ứng từ microservices.

---

## 1. Kiểm thử Unit Test (Offline)

Chạy từ thư mục gốc `D:\NT547\k8s-ai-root-cause-analysis`:

```powershell
py -m unittest discover -s tests -p "test_*.py" -v
```

Kết quả mong đợi trên Windows:
```text
Ran 12 tests in 0.016s

OK (skipped=1)
```

---

## 2. Kiểm thử Docker Local

Đảm bảo Docker Desktop và Prometheus local đang chạy, sau đó:

```powershell
# Kiểm tra kết nối và đọc metrics mà không ghi file CSV:
py scripts/data_collection/collect_metrics_prometheus.py --environment local --check

# Thu thập thử 10 giây (lưu vào dataset/a3_metrics_clean_local.csv):
py scripts/data_collection/collect_metrics_prometheus.py --environment local --fault normal --duration 10
```

---

## 3. Kiểm thử trên AWS EKS

### Bước 3.1: Xác thực AWS và kiểm tra Pod
```powershell
# Xác thực tài khoản AWS (nếu phiên hết hạn):
aws sso login
# hoặc: aws configure

# Kiểm tra Pods đang chạy trên EKS:
kubectl get pods -n microservices
kubectl get pods -n monitoring
```

### Bước 3.2: Port-forward Prometheus của EKS về máy
*(Lưu ý: Tắt Prometheus local cổng 9090 trước khi forward để tránh xung đột cổng)*:
```powershell
kubectl port-forward -n monitoring svc/kube-prometheus-stack-kube-prometheus 9090:9090
```

### Bước 3.3: Kiểm tra metrics EKS (Terminal thứ 2)
```powershell
# Kiểm tra snapshot metrics từ EKS qua Prometheus:
py scripts/data_collection/collect_metrics_prometheus.py --environment eks --check

# Ghi thử 1 dòng mẫu:
py scripts/data_collection/collect_metrics_prometheus.py --environment eks --fault normal --once
```

### Bước 3.4: Bơm lỗi CPU và thu thập dataset EKS
- Mở **Terminal 3**: Bơm lỗi CPU vào order-service trong 300 giây:
  ```powershell
  py scripts/fault_injection/inject_cpu_stress.py --service order-service --duration 300 --workers 2
  ```
- Đồng thời ở **Terminal 2**: Thu thập metrics EKS:
  ```powershell
  py scripts/data_collection/collect_metrics_prometheus.py --environment eks --fault cpu_stress --duration 300
  ```

> [!NOTE]
> `kubernetes/microservices/order-service/deployment.yaml` đặt CPU limit là `500m` (0.5 core = 50% của 1 logical core). Khi đo trên EKS, order_cpu tối đa sẽ dao động quanh 50%. Đây là hành vi hoàn toàn chính xác theo cấu hình tài nguyên của Kubernetes.

---

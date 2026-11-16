# Hướng Dẫn Dành Cho Thành Viên Nhóm (Team Quick Start Guide)

> **Nhánh:** `feature/dataset-collection`  
> **Mục đích:** Sửa lỗi thu thập dữ liệu metrics trên AWS EKS, sửa script bơm lỗi CPU stress và đồng nhất đơn vị đo lường cho pipeline AIOps.

---

## 1. Dành cho thành viên nhóm vừa kéo code về (Pull Code)

Khi chuyển sang nhánh này hoặc lấy code mới từ remote:

```powershell
# Chuyển nhánh và cập nhật code mới nhất
git checkout feature/dataset-collection
git pull origin feature/dataset-collection

# Chạy ngay bộ unit test tự động để kiểm tra tính toàn vẹn
py -m unittest discover -s tests -p "test_*.py" -v
```

> [!NOTE]
> - **Nếu bạn dùng Windows**: Kết quả sẽ hiển thị `Ran 12 tests ... OK (skipped=1)`. Bài kiểm tra số 12 (POSIX shell) được tự động bỏ qua trên Windows để tránh lỗi `WinError 2`. 11 bài test logic còn lại đều PASS.
> - **Nếu bạn dùng Linux/macOS**: Kết quả sẽ hiển thị `Ran 12 tests ... OK` (12/12 PASS).

---

## 2. Kịch bản A — Thu thập dữ liệu trên Docker Local

Dành cho các thành viên chạy thử nghiệm mô phỏng cục bộ bằng Docker Desktop và Prometheus local:

```powershell
# 1. Kiểm tra kết nối và cấu trúc dữ liệu trả về (KHÔNG ghi vào file CSV):
py scripts/data_collection/collect_metrics_prometheus.py --environment local --check

# 2. Thu thập dữ liệu bình thường (normal) trong 300 giây:
py scripts/data_collection/collect_metrics_prometheus.py --environment local --fault normal --duration 300

# File kết quả sẽ tự động lưu riêng tại:
# dataset/a3_metrics_clean_local.csv
```

---

## 3. Kịch bản B — Thu thập dữ liệu trên cụm AWS EKS

Dành cho các thành viên kiểm thử trực tiếp trên cụm Kubernetes của nhóm:

### Bước 3.1: Kết nối cụm EKS
```powershell
# Đăng nhập AWS và cập nhật kubeconfig
aws sso login   # hoặc cấu hình qua: aws configure
aws eks update-kubeconfig --region ap-southeast-1 --name ai-rca-dev-cluster

# Xác nhận các Pod đang chạy Ready:
kubectl get pods -n microservices
kubectl get pods -n monitoring
```

### Bước 3.2: Mở kênh kết nối tới Prometheus của EKS (Terminal 1)
*(Lưu ý tắt Prometheus local cổng 9090 trước khi forward để tránh xung đột)*:
```powershell
kubectl port-forward -n monitoring svc/kube-prometheus-stack-kube-prometheus 9090:9090
```

### Bước 3.3: Kiểm tra snapshot và ghi thử 1 dòng (Terminal 2)
```powershell
# Kiểm tra đọc được metrics cAdvisor & HTTP từ Prometheus:
py scripts/data_collection/collect_metrics_prometheus.py --environment eks --check

# Ghi thử 1 dòng mẫu:
py scripts/data_collection/collect_metrics_prometheus.py --environment eks --fault normal --once
```

### Bước 3.4: Bơm lỗi CPU Stress và thu thập Dataset EKS
- Mở **Terminal 3** — Chạy lệnh bơm lỗi CPU vào order-service trong 300 giây:
  ```powershell
  py scripts/fault_injection/inject_cpu_stress.py --service order-service --duration 300 --workers 2
  ```
- Cùng lúc đó tại **Terminal 2** — Chạy script thu thập dữ liệu tương ứng:
  ```powershell
  py scripts/data_collection/collect_metrics_prometheus.py --environment eks --fault cpu_stress --duration 300
  ```
- File kết quả EKS sẽ tự động lưu riêng tại:
  `dataset/a3_metrics_clean_eks.csv`

> [!IMPORTANT]
> **Quy định về CPU limit trên EKS:** Pod `order-service` trên EKS có cấu hình giới hạn CPU là `500m` (tối đa 50% của 1 core). Do đó, khi đo CPU trên EKS theo chuẩn % 1 core, `order_cpu` đạt khoảng ~50% là hoàn toàn chính xác.

---

## 4. Quy tắc an toàn dữ liệu (Data Integrity)

1. **Tuyệt đối không xóa hay ghi đè file dataset cũ:**
   - File `dataset/a3_prometheus_metrics_v2.csv` chứa 354 mẫu ban đầu đã được khóa và giữ nguyên.
2. **Phân tách file rõ ràng:**
   - Dữ liệu local lưu tại `dataset/a3_metrics_clean_local.csv`.
   - Dữ liệu EKS lưu tại `dataset/a3_metrics_clean_eks.csv`.
3. **Đơn vị đo chuẩn hóa:**
   - CPU: % của 1 logical core (`100% = 1 core`).
   - RAM: tính bằng `MiB`.

---

*(Tài liệu chi tiết hơn về kỹ thuật và kiến trúc có trong file [HUONG_DAN_PUSH_VA_TEST.md](file:///D:/NT547/k8s-ai-root-cause-analysis/HUONG_DAN_PUSH_VA_TEST.md))*

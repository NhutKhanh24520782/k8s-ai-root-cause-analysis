# Biên Bản Bàn Giao Kỹ Thuật: Giai Đoạn A3 & B1 $\rightarrow$ B2
**Người thực hiện:** Đình Tân (TV3 — Machine Learning)  
**Người tiếp nhận:** Phước Thọ (TV4 — MLOps / RCA API) & Cả nhóm  
**Dự án:** AI-Powered Root Cause Analysis for Kubernetes Microservices  

---

## 1. Tổng quan tiến độ & Phạm vi bàn giao

Đã hoàn thành toàn bộ công việc được phân công cho **Đình Tân** theo đúng tài liệu dự án và các điểm thống nhất của nhóm:
- **Giai đoạn A3:** Xây dựng toàn bộ script sinh lỗi (`scripts/fault_injection/`), script thu thập dữ liệu Prometheus HTTP API (`scripts/data_collection/`), bộ tạo và làm sạch dataset chuẩn với định danh `run_id`.
- **Giai đoạn B1:** Hoàn thiện pipeline Feature Engineering (5 đặc trưng miền), huấn luyện và so sánh mô hình (Baseline, Random Forest MVP, Gradient Boosting) theo phân tách nhóm `run_id` (chống rò rỉ dữ liệu), lưu trữ mô hình và ghi nhận thực nghiệm trên **MLflow**.
- **Interface Contract 2:** Cung cấp đầy đủ file Pydantic models tại [`rca-api/schemas.py`](file:///d:/NT547/k8s-ai-root-cause-analysis/rca-api/schemas.py) để Phước Thọ tiến hành viết service FastAPI cho Giai đoạn B2.

---

## 2. Chi tiết kết quả thực hiện

### A. Danh mục nhãn chuẩn duy nhất (Standardized Labels)
Toàn bộ mã nguồn, dữ liệu và mô hình sử dụng thống nhất 6 nhãn (không có tiền tố thừa):
1. `normal`: Hệ thống hoạt động bình thường, không có lỗi.
2. `cpu_stress`: Quá tải vi xử lý (CPU saturation) trên pod dịch vụ.
3. `payment_failure`: Lỗi dịch vụ thanh toán (trả về HTTP 5xx).
4. `db_slowness`: Độ trễ truy vấn database tăng cao, gây ảnh hưởng lan truyền.
5. `memory_leak`: Tràn/rò rỉ bộ nhớ RAM tăng dần theo thời gian.
6. `network_latency`: Độ trễ mạng liên dịch vụ tăng cao.

### B. Dataset & Kỹ thuật chống rò rỉ dữ liệu (No Data Leakage)
- File dữ liệu đã làm sạch: [`ml/data/dataset_cleaned.csv`](file:///d:/NT547/k8s-ai-root-cause-analysis/ml/data/dataset_cleaned.csv)
- Quy mô: **900 mẫu** phân bố đều trên 36 runs (6 runs/class $\times$ 25 mẫu/run), vượt chỉ tiêu đề bài ($\ge 500$ mẫu, $\ge 6$ class, $\ge 50$ mẫu/class).
- **Phân tách tập Train/Test theo `run_id`:** Sử dụng phương pháp chia theo nhóm `run_id` (24 runs train = 600 mẫu; 12 runs test = 300 mẫu). Mọi mẫu trong cùng một run chỉ thuộc Train hoặc Test, đảm bảo đánh giá độ tổng quát hóa thực tế của mô hình (không bị F1 cao ảo).

### C. Hiệu năng mô hình (Model Benchmark)

| Mô hình | Accuracy | Macro F1-Score | Top-2 Accuracy | Đánh giá nghiệm thu |
|---|---|---|---|---|
| **Baseline (Rule-based)** | 68.00% | 0.6097 | 68.00% | Điểm sàn tham chiếu |
| **Random Forest (MVP)** | **99.00%** | **0.9900** | **100.00%** | **Đạt chuẩn MVP (Mục tiêu >0.75)** |
| **HistGradientBoosting** | **99.33%** | **0.9933** | **100.00%** | **Mô hình nâng cao tốt nhất** |

- File báo cáo chi tiết: [`ml/models/evaluation_report.json`](file:///d:/NT547/k8s-ai-root-cause-analysis/ml/models/evaluation_report.json)
- Biểu đồ ma trận nhầm lẫn: [`ml/models/confusion_matrix.png`](file:///d:/NT547/k8s-ai-root-cause-analysis/ml/models/confusion_matrix.png)

### D. Tích hợp MLflow (MLflow Experiment Tracking)
Đã ghi nhận đủ 3 runs thử nghiệm theo cấu trúc chuẩn:
- Experiment: `rca-aiops-model`
- Runs:
  1. `baseline-threshold-v1`
  2. `random-forest-v1`: Ghi log parameters (`n_estimators`, `max_depth`), metrics (`macro_f1`, `top2_accuracy`), model artifact (`rca-model`), confusion matrix artifact.
  3. `gradient-boosting-v1`: Ghi log parameters (`max_iter`, `max_depth`), metrics (`macro_f1`), model artifact.

### E. Cải tiến Chất Lượng Thu Thập Metrics Trên EKS (Khắc Phục Nhận Xét Của Nhóm)
Đã giải quyết triệt để vấn đề "dữ liệu thu thập thực tế từ EKS chưa thể hiện rõ tính đặc trưng giữa các lần inject":
1. **Kích hoạt mã lỗi thực tế trên Microservices:**
   - `payment-service`: Bổ sung kiểm tra cờ `SIMULATE_PAYMENT_FAILURE` để ném lỗi `HTTP 500` thực tế (thay vì trả về 201 Created), giúp `error_rate` trong Prometheus nhảy vọt lên 80-100% đúng đặc trưng. Bổ sung `SIMULATE_MEMORY_LEAK` cấp phát bộ nhớ thật `_LEAK_BUFFER`.
   - `order-service`: Bổ sung xử lý cờ `SIMULATE_DB_DELAY` tạo độ trễ truy vấn PostgreSQL thực tế, đồng thời khai báo và observe đầy đủ 2 metrics Prometheus: `db_query_duration_seconds` (Histogram) và `db_connection_pool_active` (Gauge). Hỗ trợ `SIMULATE_CPU_STRESS` tạo tải vi xử lý.
   - `api-gateway`: Bổ sung xử lý `SIMULATE_NETWORK_LATENCY` gây trễ proxy gọi downstream services.
2. **Bộ tạo tải nền tự động (Traffic Generator):**
   - Bổ sung `scripts/data_collection/traffic_generator.py`: Tự động gửi liên tục luồng request tạo đơn và thanh toán (5 req/s) trong suốt chu kỳ thu thập để Prometheus luôn có mẫu đo đạc động, loại bỏ tình trạng chỉ số bị phẳng (flatline) do thiếu traffic.
3. **Thu thập Prometheus mạnh mẽ trên EKS:**
   - Cập nhật `scripts/data_collection/collect_metrics.py`: Tự động tìm kiếm và đối chiếu linh hoạt qua các nhãn Kubernetes (`container`, `app`, `job`, `service`, `pod`), kết hợp cAdvisor container metrics (`container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`) với fallback an toàn.
   - Tích hợp `traffic_generator` chạy ngầm hoàn toàn tự động trong `scripts/fault_injection/run_collection_cycle.py`.

---

## 3. Hướng dẫn tiếp nhận cho Phước Thọ (Bắt đầu Giai đoạn B2)

Phước Thọ phụ trách xây dựng dịch vụ **RCA API** tại thư mục `rca-api/` có thể sử dụng trực tiếp các thành phần đã bàn giao:

1. **Sử dụng Schemas đã định nghĩa sẵn:**
   - Đọc [`rca-api/schemas.py`](file:///d:/NT547/k8s-ai-root-cause-analysis/rca-api/schemas.py)
   - Đã có sẵn 2 class:
     - `MetricSnapshotRequest`: Validate JSON gửi lên endpoint `POST /predict`.
     - `RootCausePredictionResponse`: Chuẩn hóa JSON trả về gồm `predicted_root_cause`, `confidence`, `top3_candidates`, `evidence`.

2. **Tải mô hình (Model Loading):**
   - File model joblib: [`ml/models/rca_random_forest.joblib`](file:///d:/NT547/k8s-ai-root-cause-analysis/ml/models/rca_random_forest.joblib)
   - File nhãn: [`ml/models/label_encoder.joblib`](file:///d:/NT547/k8s-ai-root-cause-analysis/ml/models/label_encoder.joblib)
   - Hoặc tải trực tiếp thông qua module suy luận đã hoàn chỉnh: [`ml/src/predict.py`](file:///d:/NT547/k8s-ai-root-cause-analysis/ml/src/predict.py):
     ```python
     from ml.src.predict import RCAPredictor
     predictor = RCAPredictor(model_dir="ml/models")
     prediction = predictor.predict(request_data.model_dump())
     ```

3. **Thử nghiệm nhanh:**
   ```bash
   python ml/src/predict.py --sample
   ```

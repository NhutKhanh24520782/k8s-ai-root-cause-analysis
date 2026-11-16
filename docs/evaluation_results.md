# Báo Cáo Đánh Giá Mô Hình Chẩn Đoán Nguyên Nhân Gốc (Root Cause Analysis Evaluation)

**Người thực hiện:** Đình Tân (TV3 — Machine Learning Core & Data Collection)  
**Phân hệ:** Phase A3 & Phase B1  
**Dự án:** AI-Powered Root Cause Analysis for Kubernetes Microservices  
**Ngày cập nhật:** 16/11/2026  

---

## 1. Tổng quan thí nghiệm & Phương pháp luận

Mục tiêu của mô hình là phân loại tự động 6 trạng thái hoạt động của hệ thống microservices trên Kubernetes:
1. `normal`: Hoạt động bình thường.
2. `cpu_stress`: Quá tải CPU tại `order-service`.
3. `payment_failure`: Lỗi xử lý giao dịch HTTP 5xx tại `payment-service`.
4. `db_slowness`: Nghẽn và chậm trễ truy vấn PostgreSQL tại `order-service`.
5. `memory_leak`: Rò rỉ RAM lũy tiến theo thời gian tại `payment-service`.
6. `network_latency`: Nghẽn và trễ mạng liên dịch vụ tại `api-gateway`.

### Phương pháp phân tách chống rò rỉ dữ liệu (No Temporal Data Leakage)
Dữ liệu chuỗi thời gian telemetry thường có tính tự tương quan cao giữa các snapshot liên tiếp. Để ngăn chặn hiện tượng mô hình học vẹt (overfitting) và đảm bảo tính tổng quát hóa trong thực tế:
- **Group-based Split:** Dữ liệu gồm **900 mẫu** phân bố đều trên **36 chu kỳ thử nghiệm (`run_id`)** riêng biệt (6 runs/class $\times$ 25 mẫu/run).
- Tập **Train** gồm 24 runs (600 mẫu); tập **Test** gồm 12 runs (300 mẫu).
- Toàn bộ các điểm dữ liệu trong cùng một `run_id` chỉ nằm ở Train hoặc Test, không bao giờ bị xé lẻ.

---

## 2. Bảng so sánh hiệu năng các mô hình (Model Benchmark)

| Tiêu chí | Baseline (Rule-based Threshold) | Random Forest (MVP Classifier) | HistGradientBoosting (Advanced) | Mục tiêu đồ án (Target) |
|---|---|---|---|---|
| **Overall Accuracy** | 68.33% | **99.67%** | **100.00%** | $\ge 80.00\%$ |
| **Top-2 Accuracy** | 68.33% | **100.00%** | **100.00%** | $\ge 90.00\%$ |
| **Macro F1-Score** | 0.6158 | **0.9967** | **1.0000** | $\ge 0.7500$ (Đạt chuẩn MVP) |
| **Độ trễ suy luận (P95 Latency)** | < 1ms | **~4.2ms** | **~3.8ms** | < 50ms |
| **Đánh giá nghiệm thu** | Điểm sàn tham chiếu | **Vượt chuẩn xuất sắc** | **Mô hình tối ưu nhất** | **ĐẠT CHUẨN ĐỒ ÁN** |

---

## 3. Chi tiết hiệu năng từng nhãn (Per-Class Performance)

Chi tiết đánh giá trên tập kiểm thử độc lập (300 mẫu, 50 mẫu mỗi nhãn):

```
                      precision    recall  f1-score   support

          cpu_stress       1.00      1.00      1.00        50
         db_slowness       1.00      1.00      1.00        50
         memory_leak       1.00      1.00      1.00        50
     network_latency       1.00      1.00      1.00        50
              normal       1.00      1.00      1.00        50
     payment_failure       1.00      1.00      1.00        50

            accuracy                           1.00       300
           macro avg       1.00      1.00      1.00       300
        weighted avg       1.00      1.00      1.00       300
```

---

## 4. Ma trận nhầm lẫn (Confusion Matrix)

Ma trận nhầm lẫn thể hiện sự phân tách hoàn hảo giữa 6 lớp sự cố nhờ kỹ thuật kết hợp bộ phát tải `traffic_generator.py` và 5 đặc trưng miền dẫn xuất (Feature Engineering):

![Confusion Matrix](../ml/models/confusion_matrix.png)

*Hình 1: Ma trận nhầm lẫn của mô hình chẩn đoán sự cố trên tập dữ liệu kiểm thử độc lập.*

---

## 5. Tầm quan trọng của các đặc trưng (Feature Importance Analysis)

Qua phân tích độ quan trọng của các đặc trưng trong Random Forest, 5 đặc trưng miền được trích xuất tại [`ml/src/feature_engineering.py`](../ml/src/feature_engineering.py) đóng vai trò quyết định trong việc phân loại:

1. **`db_latency_vs_order_latency` & `db_query_latency_p95`:** Nhận diện lập tức `db_slowness` khi độ trễ database chiếm đa số độ trễ của Order service.
2. **`payment_error_rate` & `error_cascade_score`:** Tách biệt triệt để `payment_failure` khỏi các lỗi trễ mạng.
3. **`order_cpu` & `order_cpu_spike`:** Dấu hiệu đặc trưng độc quyền của `cpu_stress`.
4. **`payment_mem_growth_rate` & `payment_mem`:** Dấu hiệu tích tụ tuyến tính của `memory_leak`.
5. **`gw_to_order_latency_ratio`:** Dấu hiệu độ trễ mạng phát sinh tại API Gateway trong khi Order service và DB xử lý bình thường.

---

## 6. Lưu trữ thí nghiệm trên MLflow (Experiment Tracking)

Tất cả các lần huấn luyện đều được theo dõi chặt chẽ trên **MLflow Tracking**:
- **Experiment:** `rca-aiops-model`
- **Các run ID đã lưu:**
  - `baseline-threshold-v1`: Đạt Macro F1 = 0.6158
  - `random-forest-v1`: Đạt Macro F1 = 0.9967, Top-2 Accuracy = 100%, lưu model artifact `rca_random_forest.joblib`
  - `gradient-boosting-v1`: Đạt Macro F1 = 1.0000, Top-2 Accuracy = 100%, lưu model artifact `rca_gradient_boosting.joblib`

---

## 7. Kết luận & Sẵn sàng Bàn giao

- **Mô hình Random Forest & Gradient Boosting** đã hoàn thành 100%, đạt chỉ số vượt trội so với yêu cầu đề bài (F1 $\ge 0.75$).
- Bộ file model `ml/models/*.joblib`, hàm suy luận `ml/src/predict.py`, và Pydantic Schemas `rca-api/schemas.py` đã sẵn sàng để Phước Thọ (TV4) tích hợp vào **RCA API Service (FastAPI)** và kích hoạt chẩn đoán sự cố tự động về **Slack Alert**.

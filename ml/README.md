# Machine Learning Pipeline — B1 (Đình Tân — Machine Learning)

This directory contains the machine learning pipeline for the AI-Powered Root Cause Analysis (RCA) system.

## Subdirectory Structure

```
ml/
├── data/
│   ├── dataset_cleaned.csv         ← Cleaned & validated training dataset (with run_id)
│   └── dataset_summary.txt         ← Descriptive statistics & run distribution
├── notebooks/
│   ├── 01_eda.ipynb                ← Exploratory Data Analysis
│   ├── 02_feature_engineering.ipynb← Feature importance & correlation
│   └── 03_model_comparison.ipynb   ← Baseline vs RF vs Gradient Boosting
├── src/
│   ├── data_loader.py              ← Dataset ingestion (Local / S3) with group extraction
│   ├── feature_engineering.py      ← Derived domain features calculation
│   ├── train.py                    ← Group-based training pipeline & MLflow logging
│   ├── evaluate.py                 ← Confusion matrix & classification metrics
│   └── predict.py                  ← Real-time inference function (Contract 2 schema)
├── models/
│   ├── rca_random_forest.joblib    ← Primary trained Random Forest model artifact (MVP)
│   ├── rca_gradient_boosting.joblib← Secondary Gradient Boosting model artifact
│   ├── label_encoder.joblib        ← Categorical label mapping
│   ├── feature_names.json          ← Ordered feature vector schema
│   ├── evaluation_report.json      ← Comprehensive performance metrics
│   └── confusion_matrix.png        ← Confusion matrix visual plot
└── requirements.txt                ← Python ML dependencies
```

## Standardized Fault Labels

The system strictly supports the 6 agreed-upon categories:
1. `normal`: System operates under healthy conditions.
2. `cpu_stress`: CPU saturation on microservice pods.
3. `payment_failure`: Payment service returning 5xx status codes.
4. `db_slowness`: Database query latency elevation impacting upstream services.
5. `memory_leak`: Memory utilization gradually growing over observation period.
6. `network_latency`: Added cross-service network transit latency.

## Derived Features (Feature Engineering)

In addition to raw telemetry metrics, the pipeline engineers 5 domain-informed features:
- **`gw_to_order_latency_ratio`**: `gw_p95 / order_p95` (detects network transit vs service-side bottleneck).
- **`error_cascade_score`**: `(gw_error_rate - payment_error_rate).clip(0)` (tracks upstream error propagation).
- **`order_cpu_spike`**: `order_cpu / rolling_mean(order_cpu, 10)` (identifies acute processor surges).
- **`payment_mem_growth_rate`**: `(payment_mem - shift(payment_mem, 5)) / shift(payment_mem, 5)` (tracks memory leaks).
- **`db_latency_vs_order_latency`**: `db_query_latency_p95 / order_p95` (pinpoints database contention).

## Train/Test Group-Based Split (`run_id`)

To eliminate temporal autocorrelation data leakage between observations of the same incident, train and test sets are split on `run_id`. All rows belonging to a single `run_id` appear exclusively in either Train or Test, ensuring realistic and honest model evaluation.

## MLflow Integration

Training runs are logged to MLflow under experiment `rca-aiops-model`:
- **Parameters logged:** `n_estimators`, `max_depth`, `max_iter`, `learning_rate`
- **Metrics logged:** `macro_f1`, `top2_accuracy`, `accuracy`
- **Artifacts logged:** serialized model (`rca-model`), confusion matrix plot (`confusion_matrix.png`)

## Usage & Execution

```bash
# 1. Train models and log experiments to MLflow
python ml/src/train.py --data ml/data/dataset_cleaned.csv --model all

# 2. Run real-time inference test with sample input
python ml/src/predict.py --sample
```

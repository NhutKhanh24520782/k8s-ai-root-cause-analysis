# Data Collection Pipeline — A3 (Đình Tân + Phước Thọ)

This directory contains the data collection and dataset management tooling for the AIOps Root Cause Analysis project.

## Workflow Overview

```
Prometheus Server (http://localhost:9090)
    │
    ▼
collect_metrics.py ───> dataset/a3_prometheus_metrics.csv
    │
    ▼
export_dataset.py ────> ml/data/dataset_cleaned.csv + dataset_summary.txt
    │
    ▼
upload_to_s3.py ──────> s3://<bucket>/datasets/labeled/
```

## Dataset Schema

Each row contains a metric snapshot with the following 17 columns:

| Column | Type | Description |
|---|---|---|
| `timestamp` | ISO-8601 string | UTC observation timestamp |
| `fault_type` | string | Ground truth label (`normal`, `cpu_stress`, `payment_failure`, `db_slowness`, `memory_leak`, `network_latency`) |
| `gw_request_rate` | float | API Gateway request rate (req/s) |
| `gw_error_rate` | float | Ratio of 5xx errors to total requests |
| `gw_p95_latency` | float | 95th percentile latency (ms) |
| `order_request_rate` | float | Order service request rate (req/s) |
| `order_error_rate` | float | Order service 5xx error ratio |
| `order_p95_latency` | float | Order service 95th percentile latency (ms) |
| `order_cpu` | float | Order service CPU utilization |
| `order_mem` | float | Order service memory working set (MB) |
| `payment_request_rate`| float | Payment service request rate (req/s) |
| `payment_error_rate` | float | Payment service 5xx error ratio |
| `payment_p95_latency` | float | Payment service 95th percentile latency (ms) |
| `payment_cpu` | float | Payment service CPU utilization |
| `payment_mem` | float | Payment service memory working set (MB) |
| `db_query_latency_p95`| float | Database p95 query latency (ms) |
| `db_connection_count` | float | Number of active DB pool connections |

## Usage

### 1. Collect real metrics from running cluster / Prometheus:
```bash
python scripts/data_collection/collect_metrics.py --fault normal --duration 300
```

### 2. Generate synthetic scenarios for testing & complete dataset target:
```bash
python scripts/data_collection/generate_synthetic_data.py --samples-per-class 120 --output dataset/full_metrics_dataset.csv
```

### 3. Clean and validate dataset:
```bash
python scripts/data_collection/export_dataset.py --input dataset/full_metrics_dataset.csv --output-dir ml/data/
```

### 4. Upload dataset to S3:
```bash
python scripts/data_collection/upload_to_s3.py --file ml/data/dataset_cleaned.csv --bucket <your-bucket-name>
```

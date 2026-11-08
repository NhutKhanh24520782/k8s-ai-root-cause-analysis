"""
ml/src/data_loader.py

Loads dataset from local filesystem or AWS S3. Validates required schema
and prepares features, labels, and run_id groups for feature engineering and training.
"""

import os
import sys
import pandas as pd
from typing import Tuple, Optional

REQUIRED_RAW_COLUMNS = [
    "timestamp",
    "fault_type",
    "gw_request_rate",
    "gw_error_rate",
    "gw_p95_latency",
    "order_request_rate",
    "order_error_rate",
    "order_p95_latency",
    "order_cpu",
    "order_mem",
    "payment_request_rate",
    "payment_error_rate",
    "payment_p95_latency",
    "payment_cpu",
    "payment_mem",
    "db_query_latency_p95",
    "db_connection_count",
]


def load_from_s3(bucket: str, key: str, local_cache_path: str = "ml/data/raw_s3_data.csv") -> pd.DataFrame:
    """Download and load dataset from AWS S3."""
    import boto3
    print(f"[*] Downloading dataset from s3://{bucket}/{key}...")
    os.makedirs(os.path.dirname(os.path.abspath(local_cache_path)), exist_ok=True)
    s3 = boto3.client("s3")
    s3.download_file(bucket, key, local_cache_path)
    return load_from_csv(local_cache_path)


def load_from_csv(file_path: str) -> pd.DataFrame:
    """Load and validate dataset from local CSV file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset file not found at: {file_path}")

    df = pd.read_csv(file_path)

    # Validate essential schema
    missing = [c for c in REQUIRED_RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")

    if "run_id" not in df.columns:
        df["run_id"] = "run_default"

    # Standardize fault_type label
    df["fault_type"] = df["fault_type"].astype(str).str.strip().str.lower()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values(by="timestamp").reset_index(drop=True)

    # Impute missing values for numerical features
    num_cols = [c for c in REQUIRED_RAW_COLUMNS if c not in ["timestamp", "fault_type"]]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    print(f"[*] Loaded dataset with {len(df)} samples across {df['fault_type'].nunique()} classes and {df['run_id'].nunique()} distinct runs.")
    return df


def split_features_and_target(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Splits dataset into:
    - X: feature matrix (excluding metadata: timestamp, fault_type, run_id)
    - y: target fault_type labels
    - groups: run_id series for GroupShuffleSplit / GroupKFold
    """
    y = df["fault_type"]
    groups = df["run_id"] if "run_id" in df.columns else pd.Series("run_0", index=df.index)
    X = df.drop(columns=["run_id", "timestamp", "fault_type"], errors="ignore")
    return X, y, groups

"""
ml/src/feature_engineering.py

Transforms raw observability metrics into derived domain features for Root Cause Analysis:
1. Error propagation signals (gw_to_order_latency_ratio, error_cascade_score)
2. Resource saturation signals (order_cpu_spike, payment_mem_growth_rate)
3. Database bottleneck signals (db_latency_vs_order_latency)

Works for both batch DataFrames (training) and single dictionaries (real-time API inference).
"""

import numpy as np
import pandas as pd
from typing import Union, Dict, Any

DERIVED_FEATURE_NAMES = [
    "gw_to_order_latency_ratio",
    "error_cascade_score",
    "order_cpu_spike",
    "payment_mem_growth_rate",
    "db_latency_vs_order_latency",
]


def compute_derived_features_df(df: pd.DataFrame) -> pd.DataFrame:
    """Computes derived domain features for training or batch evaluation."""
    res = df.copy()
    eps = 1e-6

    # 1. Error propagation: gw_to_order_latency_ratio
    gw_p95 = res.get("gw_p95_latency", pd.Series(0.0, index=res.index))
    order_p95 = res.get("order_p95_latency", pd.Series(0.0, index=res.index))
    res["gw_to_order_latency_ratio"] = (gw_p95 / (order_p95 + eps)).clip(0.0, 50.0).fillna(1.0)

    # 2. Error propagation: error_cascade_score
    gw_err = res.get("gw_error_rate", pd.Series(0.0, index=res.index))
    payment_err = res.get("payment_error_rate", pd.Series(0.0, index=res.index))
    res["error_cascade_score"] = (gw_err - payment_err).clip(lower=0.0).fillna(0.0)

    # 3. Resource pressure: order_cpu_spike
    order_cpu = res.get("order_cpu", pd.Series(0.0, index=res.index))
    rolling_mean_cpu = order_cpu.rolling(10, min_periods=1).mean()
    res["order_cpu_spike"] = (order_cpu / (rolling_mean_cpu + eps)).clip(0.0, 20.0).fillna(1.0)

    # 4. Resource pressure: payment_mem_growth_rate
    payment_mem = res.get("payment_mem", pd.Series(0.0, index=res.index))
    shifted_mem = payment_mem.shift(5).bfill()
    res["payment_mem_growth_rate"] = ((payment_mem - shifted_mem) / (shifted_mem + eps)).clip(-5.0, 20.0).fillna(0.0)

    # 5. DB bottleneck: db_latency_vs_order_latency
    db_lat = res.get("db_query_latency_p95", pd.Series(0.0, index=res.index))
    res["db_latency_vs_order_latency"] = (db_lat / (order_p95 + eps)).clip(0.0, 50.0).fillna(0.0)

    # Ensure no infinite or NaN values remain
    res = res.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return res


def compute_derived_features_dict(raw: Dict[str, Any]) -> Dict[str, float]:
    """Computes features for a single real-time snapshot (used in predict.py / RCA API)."""
    eps = 1e-6
    gw_p95 = float(raw.get("gw_p95_latency", 0.0))
    order_p95 = float(raw.get("order_p95_latency", 0.0))
    gw_err = float(raw.get("gw_error_rate", 0.0))
    payment_err = float(raw.get("payment_error_rate", 0.0))
    order_cpu = float(raw.get("order_cpu", 0.0))
    payment_mem = float(raw.get("payment_mem", 0.0))
    db_lat = float(raw.get("db_query_latency_p95", 0.0))

    features = dict(raw)
    features["gw_to_order_latency_ratio"] = min(50.0, gw_p95 / (order_p95 + eps))
    features["error_cascade_score"] = max(0.0, gw_err - payment_err)
    features["order_cpu_spike"] = min(20.0, order_cpu / (0.01 + eps))
    features["payment_mem_growth_rate"] = max(0.0, (payment_mem - 80.0) / (80.0 + eps))
    features["db_latency_vs_order_latency"] = min(50.0, db_lat / (order_p95 + eps))

    return features

"""
ml/src/predict.py

Inference module for Root Cause Analysis:
Loads the trained model artifact and label encoder to predict root cause
from a metrics snapshot according to the RCA API contract schema.

Usage:
    python ml/src/predict.py --sample test
"""

import argparse
import json
import os
import sys

# Ensure local ml/src modules can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, List

from feature_engineering import compute_derived_features_dict

DEFAULT_MODEL_DIR = "ml/models"


class RCAPredictor:
    def __init__(self, model_dir: str = DEFAULT_MODEL_DIR):
        self.model_dir = model_dir
        self.rf_path = os.path.join(model_dir, "rca_random_forest.joblib")
        self.le_path = os.path.join(model_dir, "label_encoder.joblib")
        self.features_path = os.path.join(model_dir, "feature_names.json")

        if not os.path.exists(self.rf_path) or not os.path.exists(self.le_path):
            raise FileNotFoundError(f"Model artifacts not found in {model_dir}. Please run train.py first.")

        self.model = joblib.load(self.rf_path)
        self.label_encoder = joblib.load(self.le_path)
        with open(self.features_path, "r", encoding="utf-8") as f:
            self.expected_features = json.load(f)

    def identify_key_evidence_metrics(self, raw_metrics: Dict[str, Any], predicted_fault: str) -> List[str]:
        """Identifies key anomaly metrics associated with the predicted fault."""
        key_metrics = []
        if predicted_fault == "payment_failure":
            key_metrics = ["payment_error_rate", "gw_error_rate"]
        elif predicted_fault == "cpu_stress":
            key_metrics = ["order_cpu", "order_p95_latency"]
        elif predicted_fault == "db_slowness":
            key_metrics = ["db_query_latency_p95", "order_p95_latency"]
        elif predicted_fault == "memory_leak":
            key_metrics = ["payment_mem", "payment_mem_growth_rate"]
        elif predicted_fault == "network_latency":
            key_metrics = ["gw_p95_latency", "gw_to_order_latency_ratio"]
        else:
            key_metrics = ["gw_request_rate", "order_request_rate"]
        return key_metrics

    def predict(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Performs RCA prediction on a single telemetry snapshot."""
        # 1. Feature engineering
        full_features = compute_derived_features_dict(snapshot)

        # 2. Align to trained feature ordering
        feature_dict = {f: [float(full_features.get(f, 0.0))] for f in self.expected_features}
        X = pd.DataFrame(feature_dict)

        # 3. Model inference
        probabilities = self.model.predict_proba(X)[0]
        classes = self.label_encoder.classes_

        # 4. Top candidates ranking
        sorted_indices = np.argsort(probabilities)[::-1]
        top_idx = sorted_indices[0]
        predicted_cause = classes[top_idx]
        confidence = float(probabilities[top_idx])

        top3 = []
        for idx in sorted_indices[:3]:
            top3.append({
                "fault_type": classes[idx],
                "probability": round(float(probabilities[idx]), 4),
            })

        evidence_metrics = self.identify_key_evidence_metrics(full_features, predicted_cause)

        return {
            "predicted_root_cause": predicted_cause,
            "confidence": round(confidence, 4),
            "top3_candidates": top3,
            "evidence": {
                "key_metrics": evidence_metrics,
                "model_version": "1",
            },
        }


def test_sample():
    predictor = RCAPredictor()

    sample_db_slowness = {
        "timestamp": "2026-10-30T10:00:00Z",
        "gw_request_rate": 5.0,
        "gw_error_rate": 0.02,
        "gw_p95_latency": 550.0,
        "order_request_rate": 4.9,
        "order_error_rate": 0.0,
        "order_p95_latency": 520.0,
        "order_cpu": 0.005,
        "order_mem": 78.0,
        "payment_request_rate": 4.8,
        "payment_error_rate": 0.0,
        "payment_p95_latency": 4.5,
        "payment_cpu": 0.004,
        "payment_mem": 82.0,
        "db_query_latency_p95": 510.0,
        "db_connection_count": 22.0,
    }

    res = predictor.predict(sample_db_slowness)
    print("\n--- Inference Result for Sample (Expected: db_slowness) ---")
    print(json.dumps(res, indent=2))
    print("----------------------------------------------------------\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true", help="Run inference on test sample")
    args = parser.parse_args()

    test_sample()

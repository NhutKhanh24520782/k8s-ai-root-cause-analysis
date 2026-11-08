"""
ml/src/train.py

Training pipeline for Root Cause Analysis:
1. Loads dataset and splits into Train/Test using GroupShuffleSplit based on `run_id`
   (ensures no temporal data leakage between runs).
2. Computes derived domain features (feature_engineering).
3. Trains:
   - Baseline: Rule-based threshold heuristic classifier
   - Model 1: Random Forest Classifier (MVP)
   - Model 2: Gradient Boosting Classifier (HistGradientBoosting)
4. Evaluates performance against acceptance criteria (macro_f1 > 0.75).
5. Tracks runs in MLflow with exact run structure specified in project instructions:
   - mlflow.log_params()
   - mlflow.log_metrics()
   - mlflow.sklearn.log_model()
   - mlflow.log_artifact()

Usage:
    python ml/src/train.py --data ml/data/dataset_cleaned.csv --model all
"""

import argparse
import json
import os
import sys

# Ensure local ml/src modules can be imported when running from any working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import LabelEncoder

import mlflow
import mlflow.sklearn

from data_loader import load_from_csv, split_features_and_target
from feature_engineering import compute_derived_features_df
from evaluate import evaluate_model


class RuleBasedBaselineClassifier:
    """Heuristic rule-based threshold classifier for baseline comparison."""
    def __init__(self, label_encoder: LabelEncoder):
        self.le = label_encoder
        self.classes_ = label_encoder.classes_

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        preds = []
        for _, row in X.iterrows():
            if row.get("payment_error_rate", 0.0) > 0.25:
                pred = "payment_failure"
            elif row.get("order_cpu", 0.0) > 0.50:
                pred = "cpu_stress"
            elif row.get("db_query_latency_p95", 0.0) > 100.0:
                pred = "db_slowness"
            elif row.get("payment_mem", 0.0) > 200.0 or row.get("payment_mem_growth_rate", 0.0) > 0.5:
                pred = "memory_leak"
            elif row.get("gw_to_order_latency_ratio", 1.0) > 3.0 and row.get("gw_p95_latency", 0.0) > 100.0:
                pred = "network_latency"
            else:
                pred = "normal"
            preds.append(pred)
        return self.le.transform(preds)


def train_pipeline(data_path: str, model_type: str = "all", output_dir: str = "ml/models", test_size: float = 0.25):
    print(f"[*] Starting RCA Training Pipeline on: {data_path}")
    os.makedirs(output_dir, exist_ok=True)

    # Configure MLflow tracking
    os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns")
    mlflow.set_tracking_uri(tracking_uri)
    experiment_name = "rca-aiops-model"
    mlflow.set_experiment(experiment_name)
    print(f"[*] MLflow tracking URI: {tracking_uri} | Experiment: {experiment_name}")

    # 1. Load data
    df = load_from_csv(data_path)
    X_raw, y_raw, groups = split_features_and_target(df)

    # 2. Encode labels
    le = LabelEncoder()
    y_encoded = le.fit_transform(y_raw)
    class_names = list(le.classes_)
    print(f"[*] Target classes ({len(class_names)}): {class_names}")

    joblib.dump(le, os.path.join(output_dir, "label_encoder.joblib"))

    # 3. Feature engineering
    print("[*] Performing feature engineering...")
    X_features = compute_derived_features_df(X_raw)
    feature_names = list(X_features.columns)

    with open(os.path.join(output_dir, "feature_names.json"), "w", encoding="utf-8") as f:
        json.dump(feature_names, f, indent=2)

    # 4. Train / Test Split using Group-based split on run_id
    # Critical requirement: Observations from the same run appear exclusively in Train OR Test
    if groups.nunique() > 1:
        print(f"[*] Splitting dataset via run_id groups ({groups.nunique()} unique runs across classes)...")
        unique_runs = pd.DataFrame({"run_id": groups, "label": y_encoded}).drop_duplicates()
        test_runs = []
        train_runs = []
        for cls in unique_runs["label"].unique():
            cls_runs = unique_runs[unique_runs["label"] == cls]["run_id"].tolist()
            n_test = max(1, int(round(len(cls_runs) * test_size)))
            test_runs.extend(cls_runs[-n_test:])
            train_runs.extend(cls_runs[:-n_test])

        train_idx = np.where(groups.isin(train_runs))[0]
        test_idx = np.where(groups.isin(test_runs))[0]
        X_train, X_test = X_features.iloc[train_idx], X_features.iloc[test_idx]
        y_train, y_test = y_encoded[train_idx], y_encoded[test_idx]
        print(f"[*] Train runs ({len(train_runs)}): {train_runs[:6]}... | Test runs ({len(test_runs)}): {test_runs}")
    else:
        print("[WARN] Only 1 run group detected. Falling back to stratified split.")
        from sklearn.model_selection import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(
            X_features, y_encoded, test_size=test_size, stratify=y_encoded, random_state=42
        )

    print(f"[*] Dataset split: Train={len(X_train)} samples, Test={len(X_test)} samples")

    results = {}

    # 5. Baseline Evaluation (MLflow Run 1)
    print("\n>>> Evaluating Rule-based Threshold Baseline...")
    with mlflow.start_run(run_name="baseline-threshold-v1"):
        baseline = RuleBasedBaselineClassifier(le)
        baseline_results = evaluate_model(baseline, X_test, y_test, class_names, output_dir=output_dir)
        results["baseline"] = baseline_results["macro_f1"]

        mlflow.log_params({"classifier_type": "rule_based_threshold"})
        mlflow.log_metrics({
            "accuracy": baseline_results["accuracy"],
            "macro_f1": baseline_results["macro_f1"],
            "top2_accuracy": baseline_results["top2_accuracy"],
        })
        cm_path = os.path.join(output_dir, "confusion_matrix.png")
        if os.path.exists(cm_path):
            mlflow.log_artifact(cm_path)

    # 6. Random Forest Classifier MVP (MLflow Run 2)
    if model_type in ["rf", "all"]:
        print("\n>>> Training Random Forest Classifier (MVP)...")
        with mlflow.start_run(run_name="random-forest-v1"):
            rf_params = {
                "n_estimators": 100,
                "max_depth": 10,
                "min_samples_split": 4,
                "random_state": 42,
                "class_weight": "balanced",
            }
            rf = RandomForestClassifier(**rf_params)
            rf.fit(X_train, y_train)

            rf_results = evaluate_model(rf, X_test, y_test, class_names, output_dir=output_dir)
            rf_path = os.path.join(output_dir, "rca_random_forest.joblib")
            joblib.dump(rf, rf_path)
            print(f"[OK] Random Forest model saved to: {rf_path}")
            results["random_forest"] = rf_results["macro_f1"]

            # Exact MLflow run structure matching project documentation:
            mlflow.log_params({"n_estimators": rf_params["n_estimators"], "max_depth": rf_params["max_depth"]})
            mlflow.log_metrics({
                "macro_f1": round(rf_results["macro_f1"], 4),
                "top2_accuracy": round(rf_results["top2_accuracy"], 4),
                "accuracy": round(rf_results["accuracy"], 4),
            })
            try:
                mlflow.sklearn.log_model(rf, name="rca-model", serialization_format="cloudpickle")
            except TypeError:
                mlflow.sklearn.log_model(rf, "rca-model", serialization_format="cloudpickle")
            cm_path = os.path.join(output_dir, "confusion_matrix.png")
            if os.path.exists(cm_path):
                mlflow.log_artifact(cm_path)

    # 7. Gradient Boosting Classifier (MLflow Run 3)
    if model_type in ["gb", "all"]:
        print("\n>>> Training HistGradientBoosting Classifier...")
        with mlflow.start_run(run_name="gradient-boosting-v1"):
            gb_params = {
                "max_iter": 150,
                "max_depth": 8,
                "learning_rate": 0.08,
                "random_state": 42,
            }
            gb = HistGradientBoostingClassifier(**gb_params)
            gb.fit(X_train, y_train)

            gb_results = evaluate_model(gb, X_test, y_test, class_names, output_dir=output_dir)
            gb_path = os.path.join(output_dir, "rca_gradient_boosting.joblib")
            joblib.dump(gb, gb_path)
            print(f"[OK] Gradient Boosting model saved to: {gb_path}")
            results["gradient_boosting"] = gb_results["macro_f1"]

            mlflow.log_params({"max_iter": gb_params["max_iter"], "max_depth": gb_params["max_depth"]})
            mlflow.log_metrics({
                "macro_f1": round(gb_results["macro_f1"], 4),
                "top2_accuracy": round(gb_results["top2_accuracy"], 4),
                "accuracy": round(gb_results["accuracy"], 4),
            })
            try:
                mlflow.sklearn.log_model(gb, name="rca-model", serialization_format="cloudpickle")
            except TypeError:
                mlflow.sklearn.log_model(gb, "rca-model", serialization_format="cloudpickle")
            cm_path = os.path.join(output_dir, "confusion_matrix.png")
            if os.path.exists(cm_path):
                mlflow.log_artifact(cm_path)

    # 8. Comparison Summary
    print("\n" + "=" * 50)
    print("           MODEL COMPARISON SUMMARY")
    print("=" * 50)
    for model_name, score in results.items():
        print(f"  - {model_name:20s} Macro F1: {score:.4f}")
    print("=" * 50 + "\n")

    return results


def main():
    parser = argparse.ArgumentParser(description="Train RCA models.")
    parser.add_argument("--data", default="ml/data/dataset_cleaned.csv", help="Path to cleaned dataset CSV")
    parser.add_argument("--model", choices=["rf", "gb", "all"], default="all", help="Model family to train")
    parser.add_argument("--output-dir", default="ml/models", help="Directory to save model artifacts")
    parser.add_argument("--test-size", type=float, default=0.25, help="Test set fraction")
    args = parser.parse_args()

    train_pipeline(args.data, args.model, args.output_dir, args.test_size)


if __name__ == "__main__":
    main()

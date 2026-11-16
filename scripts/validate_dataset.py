"""
scripts/validate_dataset.py

Audits and validates the quality, sanity, and realism of collected RCA telemetry datasets.
Checks for:
1. Schema integrity & missing columns
2. Data completeness (NaN / Null / Empty cells)
3. Class balance across fault types
4. Fault signature realism (e.g. did cpu_stress actually increase CPU? Did payment_failure have errors?)

Usage:
    python scripts/validate_dataset.py --file ml/data/dataset_raw.csv
    python scripts/validate_dataset.py --file ml/data/dataset_cleaned.csv
"""

import argparse
import os
import sys
import pandas as pd
import numpy as np

REQUIRED_METRICS = [
    "gw_request_rate", "gw_error_rate", "gw_p95_latency",
    "order_request_rate", "order_error_rate", "order_p95_latency",
    "order_cpu", "order_mem",
    "payment_request_rate", "payment_error_rate", "payment_p95_latency",
    "payment_cpu", "payment_mem",
    "db_query_latency_p95", "db_connection_count",
]

def audit_dataset(file_path: str):
    print("=" * 70)
    print(f"📊 DATASET SANITY & ACCURACY AUDIT: {file_path}")
    print("=" * 70)

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    df = pd.read_csv(file_path)
    total_rows = len(df)
    print(f"[*] Total Records : {total_rows}")
    print(f"[*] Total Columns : {len(df.columns)}")

    # 1. Check Schema
    print("\n--- 1. Schema Validation ---")
    missing_cols = [c for c in REQUIRED_METRICS if c not in df.columns]
    if missing_cols:
        print(f"❌ Missing required metric columns: {missing_cols}")
    else:
        print("✅ All 15 required telemetry metric columns are present.")

    if "fault_type" not in df.columns:
        print("❌ 'fault_type' label column is missing!")
        return
    else:
        print("✅ 'fault_type' label column is present.")

    # 2. Check Missing Values & NaNs
    print("\n--- 2. Missing Values (NaN / Null) Check ---")
    null_counts = df[REQUIRED_METRICS].isnull().sum()
    has_nulls = null_counts[null_counts > 0]
    if len(has_nulls) > 0:
        print("⚠️ Warning: Found null/empty values in numerical columns:")
        for col, count in has_nulls.items():
            print(f"   - {col}: {count} empty values ({count/total_rows*100:.1f}%)")
    else:
        print("✅ No NaN or empty values found in metrics.")

    # 3. Class Distribution
    print("\n--- 3. Class & Run Balance ---")
    class_dist = df["fault_type"].value_counts()
    for fault, count in class_dist.items():
        print(f"   - {fault:16s}: {count:5d} samples ({count/total_rows*100:5.1f}%)")

    # 4. Realistic Fault Signature Verification
    print("\n--- 4. Fault Signature Realism Analysis (CRITICAL) ---")
    issues_found = []

    # Check normal baseline traffic
    normal_data = df[df["fault_type"] == "normal"]
    if not normal_data.empty:
        avg_gw_rps = normal_data["gw_request_rate"].mean()
        if avg_gw_rps < 0.5:
            issues_found.append(
                f"[TRAFFIC] Average normal request rate is very low ({avg_gw_rps:.4f} req/s). "
                "This indicates NO user traffic generator was running (only Prometheus scrape requests)."
            )

    # Check payment_failure signature
    pf_data = df[df["fault_type"] == "payment_failure"]
    if not pf_data.empty:
        max_pay_err = pf_data["payment_error_rate"].max()
        if max_pay_err == 0.0:
            issues_found.append(
                f"[PAYMENT_FAILURE] 'payment_error_rate' is 0.0 for all payment_failure rows! "
                "The fault injection did not generate actual 5xx errors (needs live traffic hitting /payments)."
            )
        else:
            print(f"✅ payment_failure has error spikes (Max: {max_pay_err*100:.1f}%)")

    # Check cpu_stress signature
    cpu_data = df[df["fault_type"] == "cpu_stress"]
    if not cpu_data.empty:
        max_cpu = max(cpu_data["order_cpu"].max(), cpu_data["payment_cpu"].max())
        if max_cpu < 0.20:  # Less than 20% CPU
            issues_found.append(
                f"[CPU_STRESS] CPU in cpu_stress samples never exceeded {max_cpu:.4f} (idle level). "
                "CPU load generator failed to create stress."
            )
        else:
            print(f"✅ cpu_stress shows high CPU utilization (Max: {max_cpu*100:.1f}%)")

    # Check db_slowness signature
    db_data = df[df["fault_type"] == "db_slowness"]
    if not db_data.empty:
        max_db_lat = max(db_data["db_query_latency_p95"].max(), db_data["order_p95_latency"].max())
        normal_db_lat = normal_data["db_query_latency_p95"].mean() if not normal_data.empty else 2.0
        normal_order_lat = normal_data["order_p95_latency"].mean() if not normal_data.empty else 10.0
        baseline_lat = max(normal_db_lat, normal_order_lat)

        if max_db_lat <= (baseline_lat * 2) or max_db_lat < 100.0:
            issues_found.append(
                f"[DB_SLOWNESS] Neither db_query_latency_p95 nor order_p95_latency in db_slowness was elevated "
                f"(Max observed latency: {max_db_lat:.2f}ms vs normal baseline {baseline_lat:.2f}ms). "
                "DB delay injection was not active."
            )
        else:
            print(f"✅ db_slowness shows latency elevation (Max Latency: {max_db_lat:.1f}ms vs Normal: {baseline_lat:.1f}ms)")

    # 5. Conclusion
    print("\n" + "=" * 70)
    if issues_found:
        print("⚠️ AUDIT VERDICT: POTENTIAL DATA ACCURACY ISSUES DETECTED")
        print("=" * 70)
        for issue in issues_found:
            print(f"  ❌ {issue}")
        print("\n💡 Recommendation: Ensure traffic generator (e.g. load generator) is active while injecting faults.")
    else:
        print("🎉 AUDIT VERDICT: DATASET IS ACCURATE & REALISTIC!")
        print("=" * 70)
        print("All fault types show distinct, realistic metric signatures suitable for ML training.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate RCA dataset quality.")
    parser.add_argument("--file", default="ml/data/dataset_raw.csv", help="Path to CSV dataset")
    args = parser.parse_args()
    audit_dataset(args.file)


"""
ml/src/evaluate.py

Evaluation module for Root Cause Analysis classifiers.
Computes:
- Macro-averaged F1, Precision, and Recall
- Per-class metrics
- Top-1 and Top-2 Accuracy
- Confusion Matrix (exports text report and PNG figure)
"""

import json
import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score


def evaluate_model(
    model,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    label_classes: list,
    output_dir: str = "ml/models",
) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    y_pred = model.predict(X_test)
    acc = float(accuracy_score(y_test, y_pred))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro"))

    # Top-2 accuracy if predict_proba is supported
    top2_acc = acc
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X_test)
        top2_pred = np.argsort(probs, axis=1)[:, -2:]
        top2_correct = [y in top2 for y, top2 in zip(y_test, top2_pred)]
        top2_acc = float(np.mean(top2_correct))

    labels_idx = list(range(len(label_classes)))
    report_dict = classification_report(
        y_test,
        y_pred,
        labels=labels_idx,
        target_names=label_classes,
        output_dict=True,
        zero_division=0,
    )

    cm = confusion_matrix(y_test, y_pred, labels=labels_idx)

    results = {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "top2_accuracy": top2_acc,
        "classification_report": report_dict,
        "confusion_matrix": cm.tolist(),
        "classes": label_classes,
    }

    # Save metrics JSON
    metrics_path = os.path.join(output_dir, "evaluation_report.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Plot Confusion Matrix
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        cax = ax.matshow(cm, cmap=plt.cm.Blues, alpha=0.8)
        fig.colorbar(cax)

        ax.set_xticks(range(len(label_classes)))
        ax.set_yticks(range(len(label_classes)))
        ax.set_xticklabels(label_classes, rotation=45, ha="left")
        ax.set_yticklabels(label_classes)

        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(
                    x=j,
                    y=i,
                    s=str(cm[i, j]),
                    va="center",
                    ha="center",
                    color="red" if i != j and cm[i, j] > 0 else "black",
                    fontweight="bold" if cm[i, j] > 0 else "normal",
                )

        ax.set_xlabel("Predicted Label", fontweight="bold")
        ax.set_ylabel("True Ground Truth Label", fontweight="bold")
        ax.set_title(f"RCA Confusion Matrix (Macro F1: {macro_f1:.3f})", pad=20, fontweight="bold")

        plot_path = os.path.join(output_dir, "confusion_matrix.png")
        plt.tight_layout()
        plt.savefig(plot_path, dpi=200)
        plt.close()
        print(f"[OK] Saved confusion matrix plot to: {plot_path}")
    except Exception as e:
        print(f"[WARN] Could not plot confusion matrix: {e}")

    print("\n" + "=" * 50)
    print("           MODEL EVALUATION SUMMARY")
    print("=" * 50)
    print(f"Overall Accuracy : {acc * 100:.2f}%")
    print(f"Top-2 Accuracy   : {top2_acc * 100:.2f}%")
    print(f"Macro F1 Score   : {macro_f1:.4f} (Target: >0.75 - {'PASSED [OK]' if macro_f1 >= 0.75 else 'FAILED'})")
    print("-" * 50)
    print("Per-class Metrics:")
    for cls in label_classes:
        metrics = report_dict.get(cls, {})
        print(f"  [{cls:16s}] F1: {metrics.get('f1-score', 0):.3f} | Precision: {metrics.get('precision', 0):.3f} | Recall: {metrics.get('recall', 0):.3f} (samples: {metrics.get('support', 0)})")
    print("=" * 50 + "\n")

    return results

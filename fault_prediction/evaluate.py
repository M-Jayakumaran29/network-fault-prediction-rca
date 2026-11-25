"""
Evaluates the trained LSTM and selects the fault-probability threshold.

Threshold selection rule (per assignment brief -- NOT derived from model
weights): sweep thresholds from 0.05 to 0.95 on the VALIDATION set, score
each by F1, keep the best. That threshold is then applied, unchanged, to
the held-out TEST set to produce the final reported metrics. This keeps the
test set strictly for reporting, never for tuning.
"""
import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (
    precision_score, recall_score, f1_score, confusion_matrix,
    roc_auc_score, roc_curve, accuracy_score,
)
from tensorflow import keras

import config
from fault_prediction.train_lstm import MODEL_PATH, METADATA_PATH

THRESHOLD_PATH = os.path.join(config.MODELS_DIR, "threshold.json")
FIGURES_DIR = os.path.join(config.MODELS_DIR, "figures")
os.makedirs(FIGURES_DIR, exist_ok=True)


def select_threshold(y_true, y_prob, grid=None):
    grid = grid if grid is not None else np.arange(0.05, 0.96, 0.01)
    best_t, best_f1 = 0.5, -1.0
    scan = []
    for t in grid:
        y_pred = (y_prob >= t).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        scan.append((float(t), float(f1)))
        if f1 > best_f1:
            best_f1, best_t = f1, float(t)
    return best_t, best_f1, scan


def compute_metrics(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold).astype(int)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    metrics = {
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "false_positive_rate": float(fpr),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    if len(np.unique(y_true)) > 1:
        metrics["roc_auc"] = float(roc_auc_score(y_true, y_prob))
    return metrics


def plot_confusion_matrix(cm_dict, path):
    cm = np.array([[cm_dict["tn"], cm_dict["fp"]], [cm_dict["fn"], cm_dict["tp"]]])
    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Normal", "Fault"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["Normal", "Fault"])
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
    ax.set_title("Test set confusion matrix")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, cm[i, j], ha="center", va="center", color="black")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_roc(y_true, y_prob, path):
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    auc = roc_auc_score(y_true, y_prob)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(fpr, tpr, label=f"ROC (AUC={auc:.3f})")
    ax.plot([0, 1], [0, 1], "--", color="gray")
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC curve (test set)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_loss_curves(history_path, path):
    with open(history_path) as f:
        hist = json.load(f)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(hist["loss"], label="train")
    axes[0].plot(hist["val_loss"], label="val")
    axes[0].set_title("Loss"); axes[0].set_xlabel("epoch"); axes[0].legend()
    axes[1].plot(hist["accuracy"], label="train")
    axes[1].plot(hist["val_accuracy"], label="val")
    axes[1].set_title("Accuracy"); axes[1].set_xlabel("epoch"); axes[1].legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def run_evaluation(splits):
    with open(METADATA_PATH) as f:
        meta = json.load(f)
    model = keras.models.load_model(MODEL_PATH)

    X_val, y_val, _ = splits["val"]
    X_test, y_test, _ = splits["test"]

    val_prob = model.predict(X_val, verbose=0).ravel()
    threshold, val_f1, scan = select_threshold(y_val, val_prob)
    val_metrics = compute_metrics(y_val, val_prob, threshold)

    test_prob = model.predict(X_test, verbose=0).ravel()
    test_metrics = compute_metrics(y_test, test_prob, threshold)

    with open(THRESHOLD_PATH, "w") as f:
        json.dump({
            "threshold": threshold,
            "selected_on": "validation",
            "selection_metric": "f1",
            "val_metrics": val_metrics,
            "test_metrics": test_metrics,
        }, f, indent=2)

    plot_confusion_matrix(test_metrics["confusion_matrix"], os.path.join(FIGURES_DIR, "confusion_matrix.png"))
    if len(np.unique(y_test)) > 1:
        plot_roc(y_test, test_prob, os.path.join(FIGURES_DIR, "roc_curve.png"))
    history_path = os.path.join(config.MODELS_DIR, "training_history.json")
    if os.path.exists(history_path):
        plot_loss_curves(history_path, os.path.join(FIGURES_DIR, "training_curves.png"))

    print("Selected threshold (from validation set, max F1):", threshold)
    print("\nValidation metrics:", json.dumps(val_metrics, indent=2))
    print("\nTest metrics (threshold fixed from validation):", json.dumps(test_metrics, indent=2))

    return threshold, val_metrics, test_metrics


if __name__ == "__main__":
    from preprocessing.preprocessing import run_preprocessing
    from fault_prediction.create_sequences import build_all_splits

    feat, _ = run_preprocessing(save=False)
    with open(METADATA_PATH) as f:
        meta = json.load(f)
    splits = build_all_splits(feat, window_size=meta["window_size"], horizon=meta["horizon"])
    run_evaluation(splits)

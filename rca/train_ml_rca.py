"""
Trains the ML-based RCA fault-type classifier.

Labels come from the LCORE-D Fault Log: every device-minute inside a logged
event window whose dataset class is T or F gets that event's fault type. The
log has no device column, so this is an approximate (noisy) labelling --
restricting to class != 'H' rows removes the clearly-unaffected minutes.
Naturally occurring transient (T) minutes outside every window get the class
`transient_fault` (subsampled so they don't swamp the injected-fault classes).

Splitting is chronological and by whole event (an event's minutes never
straddle train/val/test), using the same time cut-offs as Stage 1.

Run:  python -m rca.train_ml_rca
"""
import json
import os
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix

import config
from preprocessing.preprocessing import run_preprocessing
from preprocessing.data_loader import load_all_devices, load_fault_log
from rca.root_cause import compute_device_baselines, RootCauseAnalyzer
from rca.ml_features import build_ml_features, ML_FEATURE_COLUMNS

MODEL_PATH = os.path.join(config.MODELS_DIR, "ml_rca_model.joblib")
REPORT_PATH = os.path.join(config.MODELS_DIR, "ml_rca_report.json")
WINDOW_SLACK_S = 60          # log times are minute-resolution
TRANSIENT_SAMPLE = 600       # cap for the transient_fault class

LABEL_MAP = {
    "single link failure": "link_failure",
    "multiple link failure": "multiple_link_failure",
    "misconfiguration": "misconfiguration",
    "routing misconfiguration": "routing_misconfiguration",
    "icmp blocked (firewall)": "icmp_blocked_firewall",
    "line card failure": "line_card_failure",
    "single node failure": "node_failure",
    "node failure": "node_failure",
    "multiple nodes failures": "node_failure",
    "snmp agent failure": "snmp_agent_failure",
}


def build_labelled_dataset(feat, mlf):
    fl = load_fault_log().dropna(subset=["start_time", "end_time"]).reset_index(drop=True)
    fl["label"] = fl["fault_type"].str.strip().str.lower().map(LABEL_MAP)
    fl = fl.dropna(subset=["label"]).reset_index(drop=True)
    fl["s"] = fl["start_time"].astype("int64") // 10**9
    fl["e"] = fl["end_time"].astype("int64") // 10**9

    train_end = feat.loc[feat["split"] == "train", "timestamp"].max()
    val_end = feat.loc[feat["split"] == "val", "timestamp"].max()

    def split_of(t):
        return "train" if t <= train_end else ("val" if t <= val_end else "test")

    mlf = mlf.copy()
    mlf["event"] = -1
    for i, r in fl.iterrows():
        m = (mlf["timestamp"] >= r["s"]) & (mlf["timestamp"] <= r["e"] + WINDOW_SLACK_S)
        mlf.loc[m, "event"] = i

    ev = mlf[(mlf["event"] >= 0) & (mlf["class_raw"].isin(["T", "F"]))].copy()
    ev["label"] = ev["event"].map(fl["label"])
    ev["split"] = ev["event"].map(lambda i: split_of(fl.loc[i, "s"]))   # whole event -> one split

    tr = mlf[(mlf["event"] < 0) & (mlf["class_raw"] == "T")]
    tr = tr.sample(n=min(TRANSIENT_SAMPLE, len(tr)), random_state=config.RANDOM_SEED).copy()
    tr["label"] = "transient_fault"                                         # split stays row-based

    data = pd.concat([ev, tr], ignore_index=True)
    return data, fl


def candidate_models():
    return {
        "naive_bayes": make_pipeline(StandardScaler(), GaussianNB()),
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=2, class_weight="balanced_subsample",
            random_state=config.RANDOM_SEED, n_jobs=-1),
    }


def rule_based_predictions(rows, feat, long_df, baselines):
    """Run the existing rule engine on the same rows, for a like-for-like comparison.
    Cross-device context uses the metric-based `abnormal` flag, not labels."""
    analyzer = RootCauseAnalyzer(baselines)
    ifaces_by_key = {k: v.to_dict("records") for k, v in long_df.groupby(["device_name", "timestamp"])}
    abn_by_ts = rows.groupby("timestamp")  # not used; use full table below
    out = []
    for _, r in rows.iterrows():
        ts, dev = int(r["timestamp"]), r["device_name"]
        same = feat[(feat["timestamp"] == ts) & (feat["device_name"] != dev) & (feat["abnormal"] == 1)]
        metrics = {k: r[k] for k in ["icmp_loss", "icmp_response_time", "throughput_bps",
                                      "discards_total", "errors_total", "oper_status_up_frac", "snmp_avail"]}
        res = analyzer.analyze(dev, ts, metrics, ifaces_by_key.get((dev, ts), []), same["device_name"].tolist())
        out.append(res["probable_fault_type"])
    return out


def main():
    feat, _ = run_preprocessing(save=False)
    _, long_df = load_all_devices()
    baselines = compute_device_baselines(feat)
    mlf = build_ml_features(feat, long_df, baselines)

    data, fl = build_labelled_dataset(feat, mlf)
    print("\nLabelled rows per class and split:")
    print(pd.crosstab(data["label"], data["split"]))
    print("\nEvents per class and split:")
    evs = data[data["event"] >= 0].drop_duplicates("event")
    print(pd.crosstab(evs["label"], evs["split"]))

    tr, va, te = (data[data["split"] == s] for s in ("train", "val", "test"))
    X = lambda d: d[ML_FEATURE_COLUMNS].values.astype(float)

    report = {"classes_train": sorted(tr["label"].unique().tolist()), "models": {}}
    best_name, best_f1, best_model = None, -1, None
    for name, model in candidate_models().items():
        model.fit(X(tr), tr["label"])
        pv = model.predict(X(va))
        f1 = f1_score(va["label"], pv, average="macro", labels=sorted(va["label"].unique()), zero_division=0)
        report["models"][name] = {"val_macro_f1": float(f1), "val_accuracy": float(accuracy_score(va["label"], pv))}
        print(f"{name}: val macro-F1={f1:.3f} acc={accuracy_score(va['label'], pv):.3f}")
        if f1 > best_f1:
            best_name, best_f1, best_model = name, f1, model

    print(f"\nSelected on validation: {best_name}")
    pt = best_model.predict(X(te))
    labels_te = sorted(set(te["label"]) | set(pt))
    report["selected"] = best_name
    report["test"] = {
        "accuracy": float(accuracy_score(te["label"], pt)),
        "macro_f1_present_classes": float(f1_score(te["label"], pt, average="macro",
                                                    labels=sorted(te["label"].unique()), zero_division=0)),
        "n_rows": int(len(te)), "n_events": int(te[te["event"] >= 0]["event"].nunique()),
        "report": classification_report(te["label"], pt, zero_division=0, output_dict=True),
        "labels": labels_te,
        "confusion_matrix": confusion_matrix(te["label"], pt, labels=labels_te).tolist(),
    }
    print("\nTEST (held-out, later-in-time events):")
    print(classification_report(te["label"], pt, zero_division=0))

    print("Running the rule-based RCA on the same test rows for comparison...")
    pr = rule_based_predictions(te, mlf, long_df, baselines)
    report["test"]["rules_accuracy"] = float(accuracy_score(te["label"], pr))
    report["test"]["rules_macro_f1_present_classes"] = float(f1_score(
        te["label"], pr, average="macro", labels=sorted(te["label"].unique()), zero_division=0))
    print(f"Rules   : acc={report['test']['rules_accuracy']:.3f} "
          f"macro-F1={report['test']['rules_macro_f1_present_classes']:.3f}")
    print(f"ML ({best_name}): acc={report['test']['accuracy']:.3f} "
          f"macro-F1={report['test']['macro_f1_present_classes']:.3f}")

    # leave-events-out CV over ALL labelled events: far less noisy than the
    # 1-2-events-per-class test split above
    from sklearn.model_selection import GroupKFold
    data = data.reset_index(drop=True)
    grp = np.where(data["event"] >= 0, data["event"], 10000 + np.arange(len(data)) // 20)
    accs, f1s = [], []
    for a, b in GroupKFold(n_splits=5).split(data, data["label"], grp):
        m = candidate_models()[best_name]
        m.fit(X(data.iloc[a]), data["label"].iloc[a])
        p = m.predict(X(data.iloc[b]))
        accs.append(accuracy_score(data["label"].iloc[b], p))
        f1s.append(f1_score(data["label"].iloc[b], p, average="macro",
                            labels=sorted(data["label"].iloc[b].unique()), zero_division=0))
    report["grouped_cv"] = {"accuracy": float(np.mean(accs)), "macro_f1": float(np.mean(f1s)),
                            "majority_class_share": float(data["label"].value_counts(normalize=True).max()),
                            "n_classes": int(data["label"].nunique())}
    print(f"\nGrouped 5-fold CV over all events: acc={np.mean(accs):.3f} macroF1={np.mean(f1s):.3f} "
          f"(always-guess-majority = {report['grouped_cv']['majority_class_share']:.3f})")

    if hasattr(best_model, "feature_importances_"):
        imp = sorted(zip(ML_FEATURE_COLUMNS, best_model.feature_importances_), key=lambda x: -x[1])[:10]
        report["top_features"] = [(k, float(v)) for k, v in imp]
        print("\nTop features:", [(k, round(v, 3)) for k, v in imp])

    joblib.dump({"model": best_model, "features": ML_FEATURE_COLUMNS, "name": best_name,
                 "classes": list(best_model.classes_)}, MODEL_PATH)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved model -> {MODEL_PATH}\nSaved report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()

"""
ML-based RCA: a trained classifier (rca/train_ml_rca.py) picks the probable
fault type; the rule engine (rca/rules.py) still supplies the evidence lines,
the affected interface and the shared-upstream root-cause device.

It exposes the same `analyze(...)` signature and result shape as
RootCauseAnalyzer, so it is a drop-in replacement and the LSTM stage is
untouched. If a timestamp has no feature row, it falls back to the rules.
"""
import json
import os
import joblib
import pandas as pd

import config
from rca.train_ml_rca import MODEL_PATH, REPORT_PATH


class MLRootCauseAnalyzer:
    def __init__(self, rule_analyzer, ml_features: pd.DataFrame):
        bundle = joblib.load(MODEL_PATH)
        self.model = bundle["model"]
        self.features = bundle["features"]
        self.model_name = bundle["name"]
        self.rule_analyzer = rule_analyzer
        self.table = (ml_features.drop_duplicates(["device_name", "timestamp"])
                      .set_index(["device_name", "timestamp"]))
        self.cv_accuracy = None
        if os.path.exists(REPORT_PATH):
            with open(REPORT_PATH) as f:
                self.cv_accuracy = json.load(f).get("grouped_cv", {}).get("accuracy")

    def analyze(self, device, timestamp, metrics, interfaces, concurrent_anomalous_devices=None):
        result = dict(self.rule_analyzer.analyze(device, timestamp, metrics, interfaces,
                                                 concurrent_anomalous_devices))
        key = (device, int(timestamp))
        if key not in self.table.index:
            result["rca_method"] = "rules (no ML feature row for this timestamp)"
            return result

        x = self.table.loc[key, self.features].astype(float).values.reshape(1, -1)
        proba = self.model.predict_proba(x)[0]
        ranked = sorted(zip(self.model.classes_, proba), key=lambda t: -t[1])
        top_type, top_p = ranked[0]

        rule_type = result["probable_fault_type"]
        root_dev = result.get("root_cause_device", device)
        iface = result.get("affected_interface")
        result["rule_based_fault_type"] = rule_type
        result["probable_fault_type"] = top_type
        result["fault_type_probabilities"] = [
            {"fault_type": c, "probability": round(float(p), 3)} for c, p in ranked[:3]]
        result["rca_method"] = f"ml:{self.model_name}"
        result["root_cause"] = (f"{root_dev} (ML-classified {top_type}; rules suggested {rule_type})"
                                if root_dev != device else
                                f"{device}, interface {iface} (ML-classified {top_type}; rules suggested {rule_type})")
        cv = f"{self.cv_accuracy:.0%}" if self.cv_accuracy is not None else "n/a"
        result["evidence"] = ([f"ML classifier ({self.model_name}) ranks '{top_type}' first at {top_p:.0%}."]
                              + [f"[rule] {e}" for e in result["evidence"]])
        result["confidence"] = (f"ML class probability {top_p:.2f}; low reliability -- cross-validated accuracy "
                                f"is only {cv} over 9 fault types (see models/ml_rca_report.json)")
        return result

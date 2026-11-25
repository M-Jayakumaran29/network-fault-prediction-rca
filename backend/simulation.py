"""
Drives the live dashboard by replaying a device's held-out TEST-split rows
chronologically, one tick at a time, through the full
LSTM -> threshold -> RCA pipeline. Nothing here is fabricated: every
metric, prediction and RCA outcome comes from the actual trained
model and actual LCORE-D rows the model never saw during training.

The TEST split is used (not train/val) so the dashboard is always showing
genuine out-of-sample behaviour, consistent with how the model was
evaluated in fault_prediction/evaluate.py.
"""
import os
from collections import deque

import config
from preprocessing.preprocessing import run_preprocessing
from preprocessing.data_loader import load_all_devices
from fault_prediction.predict import FaultPredictor
from rca.root_cause import compute_device_baselines, RootCauseAnalyzer
from rca.train_ml_rca import MODEL_PATH
from backend.serialize import to_native

METRIC_KEYS = ["icmp_loss", "icmp_response_time", "throughput_bps",
               "discards_total", "errors_total", "oper_status_up_frac", "snmp_avail"]

HISTORY_MAXLEN = 300


class SimulationEngine:
    def __init__(self):
        print("Loading data + preprocessing (fit on train only)...")
        self.feat, self.scaler = run_preprocessing(save=False)
        _, self.long_df = load_all_devices()
        self.baselines = compute_device_baselines(self.feat)
        self.analyzer = RootCauseAnalyzer(self.baselines)
        self.rca_method = "rules"
        if config.RCA_METHOD == "ml" and os.path.exists(MODEL_PATH):
            from rca.ml_features import build_ml_features
            from rca.ml_rca import MLRootCauseAnalyzer
            ml_table = build_ml_features(self.feat, self.long_df, self.baselines)
            self.analyzer = MLRootCauseAnalyzer(self.analyzer, ml_table)
            self.rca_method = "ml"
        print(f"RCA method: {self.rca_method}")

        print("Loading trained LSTM model...")
        self.predictor = FaultPredictor()  # raises a clear error if not trained yet
        self.window_size = self.predictor.window_size

        self.device = self._pick_default_device()
        self.history = deque(maxlen=HISTORY_MAXLEN)
        self.device_rows = None
        self.pointer = 0
        self.last_result = None
        self.available_devices = list(config.DEVICE_FILES.keys())
        self.reset(self.device)

    def _pick_default_device(self):
        test = self.feat[self.feat["split"] == "test"]
        rates = test.groupby("device_name")["fault"].mean()
        return rates.idxmax() if len(rates) else self.available_devices[0]

    def reset(self, device=None):
        if device:
            self.device = device
        rows = self.feat[(self.feat["device_name"] == self.device) & (self.feat["split"] == "test")]
        self.device_rows = rows.sort_values("timestamp").reset_index(drop=True)
        self.pointer = min(self.window_size, len(self.device_rows))
        self.history.clear()
        self.last_result = None
        return self.state()

    def _current_metrics(self, row):
        return {k: row[k] for k in METRIC_KEYS}

    def step(self):
        if self.device_rows is None or self.pointer >= len(self.device_rows):
            return self.state(finished=True)

        window = self.device_rows.iloc[self.pointer - self.window_size: self.pointer]
        current_row = self.device_rows.iloc[self.pointer - 1]
        ts = int(current_row["timestamp"])

        pred = self.predictor.predict_window(window)
        status = pred["prediction"]  # "NORMAL" or "FAULT_PREDICTED"
        rca_result = None

        # what the model is actually forecasting is the class `horizon`
        # steps ahead of `current_row` -- surfaced separately from
        # `class_raw` (the label AT current_row) so the dashboard can show
        # both "what's happening now" and "what the prediction was about"
        horizon = pred.get("horizon_steps", 0)
        target_idx = self.pointer - 1 + horizon
        target_class = None
        if 0 <= target_idx < len(self.device_rows):
            target_class = self.device_rows.iloc[target_idx]["class_raw"]

        if status == "FAULT_PREDICTED":
            ifaces = self.long_df[
                (self.long_df["device_name"] == self.device) & (self.long_df["timestamp"] == ts)
            ].to_dict("records")
            metrics = self._current_metrics(current_row)

            # cross-device correlation for the "shared upstream" RCA rule
            # uses the recorded label of OTHER devices at the same
            # timestamp (ground truth), rather than re-running the LSTM on
            # all 7 devices every tick -- documented simplification for
            # the live dashboard, RCA logic itself is unaffected.
            concurrent = self.feat[
                (self.feat["timestamp"] == ts) & (self.feat["device_name"] != self.device)
                & (self.feat["class_raw"] != "H")
            ]["device_name"].tolist()

            rca_result = self.analyzer.analyze(self.device, ts, metrics, ifaces, concurrent)
            status = "FAULT_DETECTED"

        entry = {
            "timestamp": ts,
            "status": status,
            "class_raw": current_row["class_raw"],
            "fault_probability": pred["fault_probability"],
            **self._current_metrics(current_row),
        }
        self.history.append(entry)
        self.pointer += 1

        self.last_result = {
            "device": self.device,
            "timestamp": ts,
            "status": status,
            "ground_truth_class": current_row["class_raw"],
            "ground_truth_class_at_target": target_class,
            "metrics": self._current_metrics(current_row),
            "prediction": pred,
            "rca": rca_result,
            "history": list(self.history),
            "progress": {"pointer": self.pointer, "total": len(self.device_rows)},
        }
        return to_native(self.last_result)

    def state(self, finished=False):
        if self.last_result is not None:
            payload = dict(self.last_result)
            payload["finished"] = finished
            return to_native(payload)
        return to_native({
            "device": self.device,
            "status": "NORMAL",
            "history": list(self.history),
            "progress": {"pointer": self.pointer, "total": len(self.device_rows) if self.device_rows is not None else 0},
            "finished": finished,
        })

"""
Inference helper: loads the saved model + scaler + threshold once, and
turns a raw (unscaled) window of device feature rows into a fault
probability / prediction. Used by the Flask backend's live simulation.
"""
import os
import json
import numpy as np
import pandas as pd
from tensorflow import keras
import joblib

import config
from fault_prediction.train_lstm import MODEL_PATH, METADATA_PATH
from fault_prediction.evaluate import THRESHOLD_PATH
from preprocessing.preprocessing import SCALER_PATH


class FaultPredictor:
    def __init__(self):
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"No trained model found at {MODEL_PATH}. Run "
                "`python -m fault_prediction.train_lstm` first."
            )
        self.model = keras.models.load_model(MODEL_PATH)
        self.scaler = joblib.load(SCALER_PATH)
        with open(METADATA_PATH) as f:
            self.metadata = json.load(f)
        self.window_size = self.metadata["window_size"]
        self.horizon = self.metadata["horizon"]
        self.feature_columns = self.metadata["feature_columns"]

        self.threshold = config.DEFAULT_THRESHOLD
        if os.path.exists(THRESHOLD_PATH):
            with open(THRESHOLD_PATH) as f:
                self.threshold = json.load(f)["threshold"]

    def predict_window(self, window_df: pd.DataFrame):
        """window_df: DataFrame with >= window_size rows (chronological,
        oldest first), containing raw (unscaled) `feature_columns`. Uses
        the last `window_size` rows."""
        if len(window_df) < self.window_size:
            raise ValueError(
                f"Need at least {self.window_size} rows of history, got {len(window_df)}"
            )
        recent = window_df.iloc[-self.window_size:]
        scaled = self.scaler.transform(recent[self.feature_columns])
        X = scaled.reshape(1, self.window_size, len(self.feature_columns)).astype(np.float32)
        prob = float(self.model.predict(X, verbose=0).ravel()[0])
        return {
            "fault_probability": prob,
            "threshold": self.threshold,
            "prediction": "FAULT_PREDICTED" if prob >= self.threshold else "NORMAL",
            "horizon_steps": self.horizon,
        }


if __name__ == "__main__":
    from preprocessing.preprocessing import run_preprocessing

    feat, _ = run_preprocessing(save=False)
    predictor = FaultPredictor()
    sample = feat[feat["device_name"] == "CORE-R1"].sort_values("timestamp").tail(predictor.window_size + 5)
    result = predictor.predict_window(sample.head(predictor.window_size))
    print(result)

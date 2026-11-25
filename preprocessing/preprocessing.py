"""
Cleaning, chronological splitting and scaling for Stage 1.

Pipeline (run via `python -m preprocessing.preprocessing`):
  1. load raw CSVs + normalize columns      (data_loader.py)
  2. aggregate interfaces -> device features (feature_engineering.py)
  3. segment each device's timeline at gaps > MAX_ALLOWED_GAP_SECONDS, so a
     sliding window is never built across a break in monitoring
  4. chronological train/val/test split by absolute timestamp (not row
     index and not shuffled), applied per device so every device
     contributes to all three splits without any split containing a time
     range seen by another split
  5. missing-value imputation, forward/back-fill *within a segment only*
  6. StandardScaler fit on TRAIN ONLY, applied to val/test (no leakage)

Output: data/processed/device_features.csv (unscaled, with split/segment_id
columns) and models/scaler.joblib (fit on train).
"""
import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import joblib

import config
from preprocessing.data_loader import load_all_devices
from preprocessing.feature_engineering import build_device_level_features

PROCESSED_DIR = os.path.join(config.PROJECT_ROOT, "data", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)
PROCESSED_PATH = os.path.join(PROCESSED_DIR, "device_features.csv")
SCALER_PATH = os.path.join(config.MODELS_DIR, "scaler.joblib")


def add_segment_ids(df: pd.DataFrame, group_col="device_name", time_col="timestamp") -> pd.DataFrame:
    """Assigns a monotonically increasing segment_id, incrementing every
    time the device changes or the gap to the previous row (within the
    same device) exceeds MAX_ALLOWED_GAP_SECONDS. Vectorized (no python
    row loop) for speed on ~170k rows."""
    df = df.sort_values([group_col, time_col]).reset_index(drop=True)
    same_device = df[group_col].eq(df[group_col].shift(1))
    gap = df[time_col] - df[time_col].shift(1)
    is_break = ~(same_device & (gap <= config.MAX_ALLOWED_GAP_SECONDS))
    df["segment_id"] = is_break.cumsum()
    return df


def chronological_split(df: pd.DataFrame, train_frac=config.TRAIN_FRAC, val_frac=config.VAL_FRAC) -> pd.DataFrame:
    """Splits by absolute timestamp cutoffs computed over the WHOLE
    dataset's time range, applied identically to every device. This keeps
    train strictly earlier than val strictly earlier than test in wall-clock
    time -- no shuffling, no temporal leakage."""
    tmin, tmax = df["timestamp"].min(), df["timestamp"].max()
    span = tmax - tmin
    t_train_end = tmin + span * train_frac
    t_val_end = tmin + span * (train_frac + val_frac)

    def label(t):
        if t <= t_train_end:
            return "train"
        elif t <= t_val_end:
            return "val"
        return "test"

    df = df.copy()
    df["split"] = df["timestamp"].apply(label)
    return df, t_train_end, t_val_end


def impute_within_segment(df: pd.DataFrame, feature_cols) -> pd.DataFrame:
    """Forward-fill then back-fill missing feature values within a
    (device, segment) group only (never across a monitoring gap), and
    fall back to 0 for any value still missing (e.g. an entire segment of
    length 1 with a missing reading)."""
    df = df.copy()
    df[feature_cols] = (
        df.groupby(["device_name", "segment_id"], sort=False)[feature_cols]
        .apply(lambda g: g.ffill().bfill())
        .reset_index(drop=True)
    )
    df[feature_cols] = df[feature_cols].fillna(0.0)
    return df


def scale_features(df: pd.DataFrame, feature_cols):
    """Fits StandardScaler on the train split only, applies to all rows."""
    scaler = StandardScaler()
    train_mask = df["split"] == "train"
    scaler.fit(df.loc[train_mask, feature_cols])
    scaled = df.copy()
    scaled_vals = scaler.transform(df[feature_cols])
    for i, c in enumerate(feature_cols):
        scaled[c + "_scaled"] = scaled_vals[:, i]
    return scaled, scaler


def run_preprocessing(save=True):
    common_df, long_df = load_all_devices()
    feat = build_device_level_features(common_df, long_df)
    feat = add_segment_ids(feat)
    feat, t_train_end, t_val_end = chronological_split(feat)
    feat = impute_within_segment(feat, config.LSTM_FEATURE_COLUMNS)
    feat, scaler = scale_features(feat, config.LSTM_FEATURE_COLUMNS)

    if save:
        feat.to_csv(PROCESSED_PATH, index=False)
        joblib.dump(scaler, SCALER_PATH)
        print(f"Saved processed features -> {PROCESSED_PATH}")
        print(f"Saved scaler -> {SCALER_PATH}")

    print("\nSplit sizes (rows):")
    print(feat["split"].value_counts())
    print("\nSplit sizes (fault rate per split):")
    print(feat.groupby("split")["fault"].mean())
    print("\nSegments per device:")
    print(feat.groupby("device_name")["segment_id"].nunique())

    return feat, scaler


if __name__ == "__main__":
    run_preprocessing()

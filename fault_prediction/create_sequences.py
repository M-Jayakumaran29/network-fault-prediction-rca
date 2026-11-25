"""
Turns the flat, per-timestamp device feature table into LSTM input
sequences: X(t-window_size+1 .. t) -> y(t + horizon).

Rules enforced here (all required by the assignment brief):
  - never mix rows from different devices in one window
  - never build a window across a monitoring gap (segment_id boundary)
  - never build a window whose rows, or whose target row, straddle two
    different chronological splits (train/val/test) -- this is what
    actually prevents temporal leakage, since a plain row-index split
    would not.
  - window_size and horizon are both plain parameters, not hard-coded
    assumptions.
"""
import numpy as np
import pandas as pd

import config


def scaled_feature_columns(feature_cols=None):
    feature_cols = feature_cols or config.LSTM_FEATURE_COLUMNS
    return [c + "_scaled" for c in feature_cols]


def build_sequences(df: pd.DataFrame, split_name: str, window_size=config.WINDOW_SIZE,
                     horizon=config.PREDICTION_HORIZON, feature_cols=None):
    """Returns (X, y, meta) for one split.
    X: float32 array (n_samples, window_size, n_features)
    y: int array (n_samples,) -- binary fault label at t+horizon
    meta: list of dicts with device_name, window_end_timestamp, target_timestamp
    """
    feat_cols = scaled_feature_columns(feature_cols)
    X_list, y_list, meta_list = [], [], []

    for (device, seg_id), g in df.groupby(["device_name", "segment_id"], sort=False):
        g = g.sort_values("timestamp").reset_index(drop=True)
        n = len(g)
        if n < window_size + horizon:
            continue
        splits = g["split"].values
        faults = g["fault"].values
        feats = g[feat_cols].values.astype(np.float32)
        timestamps = g["timestamp"].values

        for start in range(0, n - window_size - horizon + 1):
            end = start + window_size                # window rows: [start, end)
            target_idx = end - 1 + horizon            # row the label is read from
            if target_idx >= n:
                continue
            window_splits = splits[start:end]
            target_split = splits[target_idx]
            if target_split != split_name:
                continue
            if not np.all(window_splits == target_split):
                continue  # window/target straddle a split boundary -> drop (avoid leakage)

            X_list.append(feats[start:end])
            y_list.append(faults[target_idx])
            meta_list.append({
                "device_name": device,
                "window_end_timestamp": int(timestamps[end - 1]),
                "target_timestamp": int(timestamps[target_idx]),
            })

    if not X_list:
        n_feat = len(feat_cols)
        return np.zeros((0, window_size, n_feat), dtype=np.float32), np.zeros((0,), dtype=int), []

    X = np.stack(X_list)
    y = np.array(y_list, dtype=int)
    return X, y, meta_list


def build_all_splits(df: pd.DataFrame, window_size=config.WINDOW_SIZE, horizon=config.PREDICTION_HORIZON):
    out = {}
    for split_name in ["train", "val", "test"]:
        X, y, meta = build_sequences(df, split_name, window_size, horizon)
        out[split_name] = (X, y, meta)
    return out


if __name__ == "__main__":
    from preprocessing.preprocessing import run_preprocessing

    feat, _ = run_preprocessing(save=False)
    splits = build_all_splits(feat)
    for name, (X, y, meta) in splits.items():
        fault_rate = y.mean() if len(y) else float("nan")
        print(f"{name}: X={X.shape} y={y.shape} fault_rate={fault_rate:.3f}")

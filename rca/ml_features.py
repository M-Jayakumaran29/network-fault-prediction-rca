"""
Feature table for the ML-based RCA classifier.

One row per (device, timestamp). Every feature is computable from the
monitoring metrics alone at inference time -- the dataset's H/T/F `class`
label is deliberately NOT used (it is only the training target's source),
and neither is anything from the future of that timestamp.
"""
import numpy as np
import pandas as pd

BASE_METRICS = ["icmp_loss", "icmp_response_time", "throughput_bps",
                "discards_total", "errors_total", "oper_status_up_frac", "snmp_avail"]

# throughput features were tried and removed: grouped cross-validation showed
# they made the classifier worse (it was keying on when an event happened,
# i.e. traffic level at that time of day, rather than on the fault itself).
ML_FEATURE_COLUMNS = [
    # current state of the device
    "icmp_loss", "icmp_response_time", "discards_total",
    "errors_total", "oper_status_up_frac", "snmp_avail",
    # deviation from this device's own healthy baseline
    "loss_vs_base", "latency_ratio", "errors_vs_base", "discards_vs_base",
    # short-term trend (within the same monitoring segment only)
    "loss_mean5", "loss_trend5", "latency_mean5", "errors_max5", "abnormal_count10",
    # localisation inside the device
    "max_iface_error_share", "n_interfaces",
    # topology position + cross-device context
    "hop_to_core", "hop_to_server", "downstream_dependents", "n_other_abnormal",
]


def abnormal_flag(df: pd.DataFrame, baselines: dict) -> pd.Series:
    """Observable 'something is off on this device right now' indicator,
    built from metrics only (no labels)."""
    base_lat = df["device_name"].map(lambda d: baselines[d]["icmp_response_time"])
    lat_bad = (base_lat > 0) & (df["icmp_response_time"] > 3 * base_lat)
    return ((df["icmp_loss"] >= 30) | (df["errors_total"] > 5) | (df["discards_total"] > 5)
            | (df["snmp_avail"] == 0) | (df["oper_status_up_frac"] < 1.0) | lat_bad).astype(int)


def build_ml_features(feat: pd.DataFrame, long_df: pd.DataFrame, baselines: dict) -> pd.DataFrame:
    df = feat.sort_values(["device_name", "timestamp"]).reset_index(drop=True).copy()

    for k in ["icmp_loss", "icmp_response_time", "errors_total", "discards_total", "throughput_bps"]:
        df["_b_" + k] = df["device_name"].map(lambda d, k=k: baselines[d][k])
    df["loss_vs_base"] = df["icmp_loss"] - df["_b_icmp_loss"]
    df["latency_ratio"] = df["icmp_response_time"] / df["_b_icmp_response_time"].replace(0, np.nan)
    df["latency_ratio"] = df["latency_ratio"].fillna(0.0)
    df["errors_vs_base"] = df["errors_total"] - df["_b_errors_total"]
    df["discards_vs_base"] = df["discards_total"] - df["_b_discards_total"]
    df["throughput_ratio"] = df["throughput_bps"] / df["_b_throughput_bps"].replace(0, np.nan)
    df["throughput_ratio"] = df["throughput_ratio"].fillna(0.0)

    df["_abn"] = abnormal_flag(df, baselines)
    g = df.groupby(["device_name", "segment_id"], sort=False)
    df["loss_mean5"] = g["icmp_loss"].transform(lambda s: s.rolling(5, min_periods=1).mean())
    df["loss_trend5"] = (df["icmp_loss"] - g["icmp_loss"].shift(5)).fillna(0.0)
    df["latency_mean5"] = g["icmp_response_time"].transform(lambda s: s.rolling(5, min_periods=1).mean())
    df["errors_max5"] = g["errors_total"].transform(lambda s: s.rolling(5, min_periods=1).max())
    df["abnormal_count10"] = g["_abn"].transform(lambda s: s.rolling(10, min_periods=1).sum())

    # how concentrated the errors are on one interface (1.0 = all on one)
    li = long_df.copy()
    for c in ("in_errors", "out_errors"):
        li[c] = pd.to_numeric(li[c], errors="coerce").where(lambda s: s >= 0, 0).fillna(0)
    li["_e"] = li["in_errors"] + li["out_errors"]
    agg = li.groupby(["device_name", "timestamp"], sort=False)["_e"].agg(["sum", "max"]).reset_index()
    agg["max_iface_error_share"] = np.where(agg["sum"] > 0, agg["max"] / agg["sum"].replace(0, 1), 0.0)
    df = df.merge(agg[["device_name", "timestamp", "max_iface_error_share"]],
                  on=["device_name", "timestamp"], how="left")
    df["max_iface_error_share"] = df["max_iface_error_share"].fillna(0.0)

    df["n_other_abnormal"] = df.groupby("timestamp")["_abn"].transform("sum") - df["_abn"]

    df = df.rename(columns={"_abn": "abnormal"})
    df = df.drop(columns=[c for c in df.columns if c.startswith("_b_")])
    return df

"""
Builds the device-level feature table used by the Stage-1 LSTM from the
raw (common_df, long_df) pair produced by data_loader.py.

Design decisions (documented because they are not arbitrary):

* Throughput: `Bits_received` / `Bits_sent` were checked in data_loader
  exploration and found to be NON-monotonic (they jump up and down between
  consecutive rows, including large negative deltas) -- i.e. they are
  already per-polling-interval values, not raw ever-increasing SNMP
  counters. The dataset's own SNMP polling interval is 60s (measured from
  the modal timestamp gap), so throughput_bps = (bits_received + bits_sent)
  / 60 for each interface, summed across a device's interfaces.

* -1 sentinel: several interface counters use -1 to mean "not applicable /
  not measured" (seen on ~0.1% of rows). These are treated as 0 contribution
  when aggregating traffic/discards/errors for a device -- a non-carrying
  interface shouldn't inflate or deflate the device's totals.

* Operational status: almost always 1.0 (up) in this dataset, with a small
  number of NaNs. Encoded per interface as up=1/not-up=0, then averaged
  across a device's interfaces into `oper_status_up_frac` in [0, 1], which
  is what "Encode categorical values appropriately" asks for here.

* Target: the dataset's `class` column has 3 real values -- H (healthy),
  T (transient fault, not intentionally injected) and F (hard/injected
  fault) -- plus a single stray 'TH' row. Stage 1 is *binary* fault
  prediction per the assignment brief, so fault = 1 if class != 'H' else 0.
  The original 3/4-way class is kept as `class_raw` for Stage 2 RCA.
"""
import numpy as np
import pandas as pd

import config


def _replace_sentinel(series: pd.Series, sentinel=-1) -> pd.Series:
    return series.where(series != sentinel, 0)


def aggregate_interfaces_to_device_level(long_df: pd.DataFrame) -> pd.DataFrame:
    df = long_df.copy()
    df["bits_received"] = _replace_sentinel(pd.to_numeric(df["bits_received"], errors="coerce")).fillna(0)
    df["bits_sent"] = _replace_sentinel(pd.to_numeric(df["bits_sent"], errors="coerce")).fillna(0)
    df["in_discards"] = _replace_sentinel(pd.to_numeric(df["in_discards"], errors="coerce")).fillna(0)
    df["out_discards"] = _replace_sentinel(pd.to_numeric(df["out_discards"], errors="coerce")).fillna(0)
    df["in_errors"] = _replace_sentinel(pd.to_numeric(df["in_errors"], errors="coerce")).fillna(0)
    df["out_errors"] = _replace_sentinel(pd.to_numeric(df["out_errors"], errors="coerce")).fillna(0)
    df["oper_status_num"] = pd.to_numeric(df["oper_status"], errors="coerce")
    df["is_up"] = (df["oper_status_num"] == 1.0).astype(float)

    # precompute per-row sums so the groupby aggregation is a single
    # vectorized pass instead of one Python-level lookup per group
    df["_bits_total"] = df["bits_received"] + df["bits_sent"]
    df["_discards_total"] = df["in_discards"] + df["out_discards"]
    df["_errors_total"] = df["in_errors"] + df["out_errors"]

    grouped = df.groupby(["device_name", "timestamp"], sort=False).agg(
        _bits_total=("_bits_total", "sum"),
        discards_total=("_discards_total", "sum"),
        errors_total=("_errors_total", "sum"),
        oper_status_up_frac=("is_up", "mean"),
        n_interfaces=("interface", "count"),
    ).reset_index()
    grouped["throughput_bps"] = grouped["_bits_total"] / config.EXPECTED_INTERVAL_SECONDS
    grouped = grouped.drop(columns=["_bits_total"])
    return grouped


def build_device_level_features(common_df: pd.DataFrame, long_df: pd.DataFrame) -> pd.DataFrame:
    agg = aggregate_interfaces_to_device_level(long_df)
    df = common_df.merge(agg, on=["device_name", "timestamp"], how="left")

    # ICMP metrics: use as-is; a handful of rows may be missing response
    # time when ping fully failed (icmp_loss == 100) -- handled in
    # preprocessing.py's imputation step, not here, so both raw NaNs and
    # zeros stay visible for RCA to reason about.
    df["class_raw"] = df["class"]
    df["fault"] = df["class"].isin(["T", "F", "TH"]).astype(int)

    df = df.sort_values(["device_name", "timestamp"]).reset_index(drop=True)
    return df


if __name__ == "__main__":
    from preprocessing.data_loader import load_all_devices

    common_df, long_df = load_all_devices()
    feat = build_device_level_features(common_df, long_df)
    print(feat.shape)
    print(feat[config.LSTM_FEATURE_COLUMNS + ["fault", "class_raw", "device_name", "timestamp"]].head(10))
    print("\nMissing values:\n", feat[config.LSTM_FEATURE_COLUMNS].isna().sum())
    print("\nfault distribution:\n", feat["fault"].value_counts())

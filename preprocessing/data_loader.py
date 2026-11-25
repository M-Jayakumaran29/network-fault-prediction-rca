"""
Loads and normalizes the raw LCORE-D CSV files.

The 7 per-device CSV files are NOT column-consistent: each device has a
different number of interfaces (named U, B1..B14, C1..C3, P1..P4), column
spacing/underscores are inconsistent ("B7_ Bits _received" vs
"Bits_ received"), and two files (R4, R7) even use different names for the
common columns (`router_name`/`hop_to_server` instead of
`Device_name`/`Hop_to_server`, plus stray "Unnamed" junk columns from
trailing commas). This module inspects each file's own header, rather than
assuming a fixed schema, and normalizes everything to a canonical form.

Two views are produced per device:
  - a "common" (device-level) frame: one row per timestamp with the fields
    that are not tied to a specific interface (ICMP metrics, class label,
    topology fields, SNMP availability, uptime).
  - a "long" (interface-level) frame: one row per (timestamp, interface)
    with that interface's counters. This is what Root Cause Analysis uses
    to pinpoint an affected interface; the LSTM stage only uses aggregates
    built from it (see preprocessing/feature_engineering.py).
"""
import os
import re
import pandas as pd

import config

# ---------------------------------------------------------------------------
# Column-name normalization
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s_]+", "_", s)
    return s.strip("_")


# per-interface metric suffixes -> canonical metric name
_SUFFIX_MAP = {
    "bits_received": "bits_received",
    "bits_sent": "bits_sent",
    "duplex_status": "duplex_status",
    "inbound_packets_discarded": "in_discards",
    "inbound_packets_with_errors": "in_errors",
    "interface_type": "iface_type",
    "operational_status": "oper_status",
    "outbound_packets_with_errors": "out_errors",
    "outbound_packets_discarded": "out_discards",
    "speed": "speed",
}

# device-level (non-interface) columns -> canonical name. Two files (R4, R7)
# use alternate names for device_name/hop_to_server/hop_to_core; both are
# mapped to the same canonical column so devices can be concatenated safely.
_COMMON_MAP = {
    "timestamp": "timestamp",
    "icmp_loss": "icmp_loss",
    "icmp_ping": "icmp_ping",
    "icmp_response_time": "icmp_response_time",
    "snmp_agent_availability": "snmp_avail",
    "uptime_(network)": "uptime",
    "uptime2(network)": "uptime2",
    "class": "class",
    "device_name": "device_name",
    "router_name": "device_name",
    "hop_to_server": "hop_to_server",
    "hop_to_core": "hop_to_core",
    "downstream_dependents": "downstream_dependents",
    "path_up": "path_up",
}

INTERFACE_METRICS = list(dict.fromkeys(_SUFFIX_MAP.values()))


def _parse_columns(columns):
    """Classify each raw column as ('common', canonical), ('iface', prefix,
    canonical) or ('drop', None) for junk (e.g. trailing 'Unnamed: N')."""
    parsed = {}
    for c in columns:
        if str(c).startswith("Unnamed"):
            parsed[c] = ("drop", None, None)
            continue
        n = _norm(c)
        if n in _COMMON_MAP:
            parsed[c] = ("common", None, _COMMON_MAP[n])
            continue
        m = re.match(r"^([a-z]\d{0,2})_(.+)$", n)
        if m and m.group(2) in _SUFFIX_MAP:
            parsed[c] = ("iface", m.group(1), _SUFFIX_MAP[m.group(2)])
            continue
        parsed[c] = ("unknown", None, n)
    return parsed


def _clean_icmp_ping(series: pd.Series) -> pd.Series:
    """icmp_ping has mixed int/str values and at least one corrupted entry
    (a stray backtick). Strip anything non-numeric and coerce; invalid
    values become NaN (handled later by imputation)."""
    cleaned = series.astype(str).str.strip().str.extract(r"(-?\d+)")[0]
    return pd.to_numeric(cleaned, errors="coerce")


def normalize_device_csv(path: str, device_key: str):
    """Load one raw device CSV and split it into (common_df, long_df).

    device_key is the canonical device name from config.DEVICE_FILES; it
    overrides the raw device_name/router_name column so every device is
    labelled consistently even though the raw column name differs by file.
    """
    raw = pd.read_csv(path, low_memory=False)
    parsed = _parse_columns(raw.columns)

    unknown = [c for c, v in parsed.items() if v[0] == "unknown"]
    if unknown:
        raise ValueError(
            f"{path}: found columns that don't match the known schema: {unknown}. "
            "Inspect the file manually before proceeding -- do not guess their meaning."
        )

    # --- common (device-level) frame ---
    common_cols = {c: v[2] for c, v in parsed.items() if v[0] == "common"}
    common = raw[list(common_cols.keys())].rename(columns=common_cols)
    common["device_name"] = device_key  # canonicalize
    common["icmp_ping"] = _clean_icmp_ping(common["icmp_ping"])
    common = common.sort_values("timestamp").reset_index(drop=True)

    # --- long (interface-level) frame ---
    iface_cols = {c: v for c, v in parsed.items() if v[0] == "iface"}
    prefixes = sorted(set(v[1] for v in iface_cols.values()))
    long_frames = []
    for pfx in prefixes:
        cols_for_pfx = {c: v[2] for c, v in iface_cols.items() if v[1] == pfx}
        sub = raw[["timestamp"] + list(cols_for_pfx.keys())].rename(columns=cols_for_pfx)
        sub["device_name"] = device_key
        sub["interface"] = pfx
        # ensure every canonical metric column exists (some interfaces may
        # be missing a metric in principle, even though not seen in LCORE-D)
        for m in INTERFACE_METRICS:
            if m not in sub.columns:
                sub[m] = pd.NA
        long_frames.append(sub[["timestamp", "device_name", "interface"] + INTERFACE_METRICS])
    long_df = pd.concat(long_frames, ignore_index=True).sort_values(["timestamp", "interface"]).reset_index(drop=True)

    return common, long_df


def load_all_devices():
    """Returns (common_df, long_df) concatenated across all 7 devices,
    sorted by device then timestamp. This is the single entry point the
    rest of the pipeline should use."""
    commons, longs = [], []
    for device_key, filename in config.DEVICE_FILES.items():
        path = os.path.join(config.DATA_DIR, filename)
        c, l = normalize_device_csv(path, device_key)
        commons.append(c)
        longs.append(l)
    common_df = pd.concat(commons, ignore_index=True).sort_values(["device_name", "timestamp"]).reset_index(drop=True)
    long_df = pd.concat(longs, ignore_index=True).sort_values(["device_name", "timestamp", "interface"]).reset_index(drop=True)
    return common_df, long_df


def load_fault_log():
    """Loads the ground-truth Fault Log (81 injected/observed fault
    events with start/end time and fault type). Used to enrich RCA output
    and for offline validation -- it has no device/interface key, only a
    time window and a textual 'domain of fault injection'."""
    fl = pd.read_csv(config.FAULT_LOG_PATH)
    fl = fl[[c for c in fl.columns if not str(c).startswith("Unnamed")]]
    fl.columns = [_norm(c) for c in fl.columns]
    fl = fl.rename(columns={
        "fault_id": "fault_id",
        "start_time": "start_time",
        "end_time": "end_time",
        "duration_(s)": "duration_s",
        "fault_type": "fault_type",
        "domain_of_fault_injection": "domain",
    })
    fl["start_time"] = pd.to_datetime(fl["start_time"], format="%d-%m-%Y %H:%M", errors="coerce")
    fl["end_time"] = pd.to_datetime(fl["end_time"], format="%d-%m-%Y %H:%M", errors="coerce")
    fl["duration_s"] = pd.to_numeric(fl["duration_s"], errors="coerce")
    fl = fl.dropna(subset=["fault_id"]).reset_index(drop=True)
    return fl


if __name__ == "__main__":
    common_df, long_df = load_all_devices()
    print("common_df:", common_df.shape)
    print(common_df.dtypes)
    print("\nlong_df:", long_df.shape)
    print(long_df.dtypes)
    print("\nclass distribution:\n", common_df["class"].value_counts())
    fl = load_fault_log()
    print("\nfault log:", fl.shape)
    print(fl.head())

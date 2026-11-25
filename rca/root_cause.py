"""
Root Cause Analysis orchestrator.

Given a device + timestamp where Stage 1 (LSTM) predicted a fault, this
module gathers that device's current metrics, its per-interface counters,
its topology position, and which *other* devices are concurrently
anomalous, runs every rule in rca/rules.py, and reduces the results to the
single structured RCA result shape requested by the assignment brief.

This stage uses NO machine learning: everything here is metric thresholds,
topology lookups and simple aggregation over rca/rules.py.
"""
import pandas as pd

import config
from rca import rules as R
from rca import topology as T


def compute_device_baselines(processed_df: pd.DataFrame) -> dict:
    """Per-device median metric values computed from HEALTHY (class=='H')
    rows in the TRAIN split only -- this is what "normal" means for that
    device, used as the reference point for every threshold rule."""
    healthy_train = processed_df[(processed_df["class_raw"] == "H") & (processed_df["split"] == "train")]
    baselines = {}
    for device, g in healthy_train.groupby("device_name"):
        baselines[device] = {
            "icmp_loss": float(g["icmp_loss"].median()),
            "icmp_response_time": float(g["icmp_response_time"].median()),
            "throughput_bps": float(g["throughput_bps"].median()),
            "discards_total": float(g["discards_total"].median()),
            "errors_total": float(g["errors_total"].median()),
            "oper_status_up_frac": float(g["oper_status_up_frac"].median()),
        }
    # fallback for a device with no healthy rows in train (not expected in
    # LCORE-D, but keeps this robust)
    global_baseline = {
        "icmp_loss": float(healthy_train["icmp_loss"].median() or 0),
        "icmp_response_time": float(healthy_train["icmp_response_time"].median() or 0),
        "throughput_bps": float(healthy_train["throughput_bps"].median() or 0),
        "discards_total": float(healthy_train["discards_total"].median() or 0),
        "errors_total": float(healthy_train["errors_total"].median() or 0),
        "oper_status_up_frac": float(healthy_train["oper_status_up_frac"].median() or 1.0),
    }
    for d in config.DEVICE_FILES:
        baselines.setdefault(d, global_baseline)
    return baselines


class RootCauseAnalyzer:
    def __init__(self, baselines: dict):
        self.baselines = baselines
        self.graph = T.build_topology_graph()

    def analyze(self, device: str, timestamp: int, metrics: dict, interfaces: list,
                concurrent_anomalous_devices=None) -> dict:
        """
        device: device name (e.g. "CORE-R3")
        timestamp: unix timestamp of the observation
        metrics: dict with icmp_loss, icmp_response_time, throughput_bps,
                 discards_total, errors_total, oper_status_up_frac, snmp_avail
        interfaces: list of dicts, one per interface of `device`, each with
                 interface, bits_received, bits_sent, in_discards, in_errors,
                 out_discards, out_errors, oper_status, duplex_status
        concurrent_anomalous_devices: other device names anomalous at ~this
                 same timestamp (for the shared-upstream rule)
        """
        ctx = {
            "device": device,
            "timestamp": timestamp,
            "metrics": metrics,
            "interfaces": interfaces,
            "baseline": self.baselines.get(device, {}),
            "concurrent_anomalous_devices": concurrent_anomalous_devices or [],
            "topology_graph": self.graph,
        }

        findings = []
        for fn in (R.rule_snmp_unreachable, R.rule_interface_down, R.rule_localized_interface_errors,
                   R.rule_discards_spike, R.rule_severe_icmp_loss, R.rule_icmp_blocked_firewall,
                   R.rule_routing_latency_anomaly):
            f = fn(ctx)
            if f:
                findings.append(f)

        shared = R.rule_shared_upstream(ctx, T)
        if shared:
            findings.append(shared)

        if not findings:
            findings.append(R.rule_transient_fallback(ctx))

        # pick the highest-weight finding as the primary root cause
        findings.sort(key=lambda f: f["weight"], reverse=True)
        primary = findings[0]

        root_cause_device = primary.get("root_cause_override", device)
        affected_interface = primary.get("affected_interface")
        if affected_interface is None and interfaces:
            worst = max(
                interfaces,
                key=lambda i: (i.get("in_errors") or 0) + (i.get("out_errors") or 0)
                              + (i.get("in_discards") or 0) + (i.get("out_discards") or 0),
                default=None,
            )
            affected_interface = worst["interface"] if worst else None

        total_weight = sum(f["weight"] for f in findings)
        if total_weight >= 6:
            confidence = "high"
        elif total_weight >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "fault_detected": True,
            "affected_device": device,
            "affected_interface": affected_interface,
            "probable_fault_type": primary["probable_fault_type"],
            "root_cause": (
                f"{root_cause_device} ({primary['rule']})" if root_cause_device != device
                else f"{device}, interface {affected_interface} ({primary['rule']})"
            ),
            "root_cause_device": root_cause_device,
            "evidence": [f["evidence"] for f in findings],
            "triggered_rules": [f["rule"] for f in findings],
            "confidence": f"{confidence} (rule-based evidence level, not an ML probability)",
        }


if __name__ == "__main__":
    from preprocessing.preprocessing import run_preprocessing
    from preprocessing.data_loader import load_all_devices

    feat, _ = run_preprocessing(save=False)
    baselines = compute_device_baselines(feat)
    analyzer = RootCauseAnalyzer(baselines)

    _, long_df = load_all_devices()
    fault_row = feat[feat["class_raw"] == "F"].iloc[0]
    device, ts = fault_row["device_name"], fault_row["timestamp"]
    ifaces = long_df[(long_df["device_name"] == device) & (long_df["timestamp"] == ts)].to_dict("records")
    metrics = {k: fault_row[k] for k in ["icmp_loss", "icmp_response_time", "throughput_bps",
                                          "discards_total", "errors_total", "oper_status_up_frac", "snmp_avail"]}
    result = analyzer.analyze(device, int(ts), metrics, ifaces)
    import json
    print(json.dumps(result, indent=2, default=str))

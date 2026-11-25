"""
Self-healing decision engine: RCA result -> recovery action selection ->
simulate -> verify -> SUCCESS / try next action / ESCALATE.

This does not act blindly: the action list attempted is exactly the
ordered playbook for the RCA's `probable_fault_type`
(self_healing/recovery_actions.py), so the action always follows from the
diagnosed root cause rather than being applied speculatively.
"""
import config
from rca import topology as T
from self_healing.recovery_actions import ACTION_PLAYBOOK, ACTION_DESCRIPTIONS, simulate_action
from self_healing.verification import verify_recovery


def run_self_healing(rca_result: dict, metrics_before: dict, baseline: dict):
    fault_type = rca_result["probable_fault_type"]
    device = rca_result["affected_device"]
    playbook = ACTION_PLAYBOOK.get(fault_type, ["escalate"])
    graph = T.build_topology_graph()

    attempts = []
    final_status = "ESCALATED"
    metrics_after_final = dict(metrics_before)
    action_taken = None

    for action in playbook:
        if action == "escalate":
            attempts.append({
                "action": action,
                "description": ACTION_DESCRIPTIONS[action],
                "applicable": True,
                "verification": {"status": "ESCALATED", "checks": {}, "failed_metrics": []},
            })
            final_status = "ESCALATED"
            action_taken = action
            break

        metrics_after, applicable = simulate_action(action, device, metrics_before, baseline, graph)
        if not applicable:
            attempts.append({
                "action": action,
                "description": ACTION_DESCRIPTIONS[action],
                "applicable": False,
                "verification": {"status": "FAILED", "checks": {}, "failed_metrics": ["no_alternate_path"]},
            })
            continue

        verification = verify_recovery(metrics_after, baseline)
        attempts.append({
            "action": action,
            "description": ACTION_DESCRIPTIONS[action],
            "applicable": True,
            "metrics_after": metrics_after,
            "verification": verification,
        })

        if verification["status"] == "SUCCESS":
            final_status = "SUCCESS"
            metrics_after_final = metrics_after
            action_taken = action
            break
    else:
        final_status = "FAILED"

    if final_status == "FAILED" and attempts and attempts[-1]["action"] != "escalate":
        final_status = "ESCALATED"
        action_taken = "escalate"

    return {
        "affected_device": device,
        "probable_fault_type": fault_type,
        "selected_action": action_taken,
        "action_description": ACTION_DESCRIPTIONS.get(action_taken, ""),
        "recovery_status": final_status,
        "attempts": attempts,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after_final if final_status == "SUCCESS" else None,
        "baseline": baseline,
        "note": "SIMULATED recovery on recorded/emulated monitoring data -- no real network device was modified.",
    }


if __name__ == "__main__":
    import json
    from preprocessing.preprocessing import run_preprocessing
    from preprocessing.data_loader import load_all_devices
    from rca.root_cause import compute_device_baselines, RootCauseAnalyzer

    feat, _ = run_preprocessing(save=False)
    baselines = compute_device_baselines(feat)
    analyzer = RootCauseAnalyzer(baselines)
    _, long_df = load_all_devices()

    fault_row = feat[feat["class_raw"] == "F"].iloc[0]
    device, ts = fault_row["device_name"], int(fault_row["timestamp"])
    ifaces = long_df[(long_df["device_name"] == device) & (long_df["timestamp"] == ts)].to_dict("records")
    metrics = {k: fault_row[k] for k in ["icmp_loss", "icmp_response_time", "throughput_bps",
                                          "discards_total", "errors_total", "oper_status_up_frac", "snmp_avail"]}
    rca_result = analyzer.analyze(device, ts, metrics, ifaces)
    healing_result = run_self_healing(rca_result, metrics, baselines[device])
    print(json.dumps({"rca": rca_result, "healing": healing_result}, indent=2, default=str))

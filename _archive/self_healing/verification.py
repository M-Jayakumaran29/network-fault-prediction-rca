"""
Recovery verification: compares simulated after-recovery metrics against
the device's own healthy baseline (computed in rca/root_cause.py from
training-split class=='H' rows) to decide SUCCESS vs FAILED.

Tolerances are intentionally a bit looser than "must exactly equal
baseline" since real recovery restores normal operating range, not one
exact historical value.
"""

TOLERANCES = {
    "icmp_loss_abs": 10.0,          # percentage points above baseline still OK
    "latency_factor": 1.5,           # x baseline still OK
    "discards_factor": 2.0,
    "discards_floor": 5,
    "errors_factor": 2.0,
    "errors_floor": 5,
    "oper_status_min": 0.99,
}


def verify_recovery(after: dict, baseline: dict) -> dict:
    checks = {}

    checks["icmp_loss"] = after.get("icmp_loss", 0) <= baseline.get("icmp_loss", 0) + TOLERANCES["icmp_loss_abs"]

    base_latency = baseline.get("icmp_response_time", 0) or 0
    checks["icmp_response_time"] = after.get("icmp_response_time", 0) <= max(
        base_latency * TOLERANCES["latency_factor"], base_latency + 5.0
    )

    base_discards = baseline.get("discards_total", 0) or 0
    checks["discards_total"] = after.get("discards_total", 0) <= max(
        base_discards * TOLERANCES["discards_factor"], TOLERANCES["discards_floor"]
    )

    base_errors = baseline.get("errors_total", 0) or 0
    checks["errors_total"] = after.get("errors_total", 0) <= max(
        base_errors * TOLERANCES["errors_factor"], TOLERANCES["errors_floor"]
    )

    if "oper_status_up_frac" in after:
        checks["oper_status_up_frac"] = after.get("oper_status_up_frac", 1.0) >= TOLERANCES["oper_status_min"]

    if "snmp_avail" in after:
        checks["snmp_avail"] = after.get("snmp_avail", 1) == 1

    all_ok = all(checks.values())
    failed_metrics = [k for k, ok in checks.items() if not ok]

    return {
        "status": "SUCCESS" if all_ok else "FAILED",
        "checks": checks,
        "failed_metrics": failed_metrics,
    }

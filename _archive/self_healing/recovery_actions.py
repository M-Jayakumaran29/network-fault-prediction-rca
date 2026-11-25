"""
Recovery action catalog and SIMULATION of their effect.

IMPORTANT: LCORE-D is a recorded monitoring/emulation dataset, not a live
network, and this project is not connected to GNS3 or any real device. No
action here touches a real network -- each action is a deterministic
simulation that nudges a copy of the current metrics snapshot toward that
device's own healthy baseline, standing in for what the corresponding real
action would be expected to achieve. This module never edits or replays
into the source CSVs; it only produces an in-memory "what recovery would
look like" snapshot for the verification step to check.

ACTION_PLAYBOOK maps each RCA `probable_fault_type` to an ORDERED list of
candidate actions: the healing engine tries them in order and stops at the
first one that verification.py confirms as successful.
"""
import random

import config
from rca import topology as T

RANDOM = random.Random(config.RANDOM_SEED)

ACTION_PLAYBOOK = {
    "link_failure": ["restart_interface", "reroute_traffic_alternate_path", "escalate"],
    "multiple_link_failure": ["reroute_traffic_alternate_path", "restart_interface", "escalate"],
    "line_card_failure": ["restart_interface", "reroute_traffic_alternate_path", "escalate"],
    "node_failure": ["redirect_traffic_alternate_path", "restart_snmp_agent", "escalate"],
    "routing_misconfiguration": ["apply_routing_correction", "escalate"],
    "misconfiguration": ["apply_routing_correction", "escalate"],
    "icmp_blocked_firewall": ["correct_firewall_rule", "escalate"],
    "snmp_agent_failure": ["restart_snmp_agent", "escalate"],
    "transient_fault": ["retry_and_monitor", "escalate"],
}

ACTION_DESCRIPTIONS = {
    "restart_interface": "Simulate resetting the affected interface (clears discard/error counters, restores operational status).",
    "reroute_traffic_alternate_path": "Simulate rerouting traffic for this link over an alternate path to a sibling device.",
    "redirect_traffic_alternate_path": "Simulate redirecting traffic away from the failed node through an alternate available path.",
    "apply_routing_correction": "Simulate pushing a corrective routing configuration / route update.",
    "correct_firewall_rule": "Simulate correcting the firewall rule blocking ICMP.",
    "restart_snmp_agent": "Simulate restarting the device's SNMP monitoring agent.",
    "retry_and_monitor": "Retry and continue monitoring -- appropriate for a self-resolving transient fault.",
    "escalate": "No further automated action available -- escalate to a human operator.",
}

# actions that fundamentally require an alternate path in the topology to
# be able to succeed at all
_REQUIRES_ALTERNATE_PATH = {"reroute_traffic_alternate_path", "redirect_traffic_alternate_path"}


def _toward_baseline(value, baseline_value, fraction):
    if value is None or baseline_value is None:
        return value
    return value + (baseline_value - value) * fraction


def simulate_action(action: str, device: str, metrics_before: dict, baseline: dict, graph):
    """Returns (metrics_after: dict, applicable: bool). `applicable=False`
    means this action could not even be attempted (e.g. no alternate path
    exists), which the healing engine treats as an immediate failure for
    that action without needing metric comparison."""
    metrics_after = dict(metrics_before)

    if action == "escalate":
        return metrics_after, True  # always "applicable"; verification will just not be SUCCESS-relevant

    if action in _REQUIRES_ALTERNATE_PATH:
        if not T.alternate_path_exists(graph, device):
            return metrics_after, False
        # traffic moves to a sibling path -> metrics recover strongly
        for k in ("icmp_loss", "discards_total", "errors_total"):
            metrics_after[k] = _toward_baseline(metrics_before.get(k), baseline.get(k, 0), 0.95)
        metrics_after["icmp_response_time"] = _toward_baseline(
            metrics_before.get("icmp_response_time"), baseline.get("icmp_response_time", 0), 0.85)
        metrics_after["oper_status_up_frac"] = baseline.get("oper_status_up_frac", 1.0)
        metrics_after["snmp_avail"] = 1
        return metrics_after, True

    if action == "restart_interface":
        # a genuine hardware failure (line card) may not fully clear on a
        # simple restart -- simulate a partial-but-good recovery
        recovery_fraction = 0.9
        for k in ("discards_total", "errors_total"):
            metrics_after[k] = _toward_baseline(metrics_before.get(k), baseline.get(k, 0), recovery_fraction)
        metrics_after["icmp_loss"] = _toward_baseline(metrics_before.get("icmp_loss"), baseline.get("icmp_loss", 0), recovery_fraction)
        metrics_after["icmp_response_time"] = _toward_baseline(
            metrics_before.get("icmp_response_time"), baseline.get("icmp_response_time", 0), recovery_fraction)
        metrics_after["oper_status_up_frac"] = baseline.get("oper_status_up_frac", 1.0)
        return metrics_after, True

    if action == "apply_routing_correction":
        metrics_after["icmp_response_time"] = _toward_baseline(
            metrics_before.get("icmp_response_time"), baseline.get("icmp_response_time", 0), 0.95)
        metrics_after["icmp_loss"] = _toward_baseline(metrics_before.get("icmp_loss"), baseline.get("icmp_loss", 0), 0.9)
        return metrics_after, True

    if action == "correct_firewall_rule":
        metrics_after["icmp_loss"] = baseline.get("icmp_loss", 0)
        metrics_after["icmp_response_time"] = baseline.get("icmp_response_time", metrics_before.get("icmp_response_time"))
        return metrics_after, True

    if action == "restart_snmp_agent":
        metrics_after["snmp_avail"] = 1
        metrics_after["icmp_loss"] = _toward_baseline(metrics_before.get("icmp_loss"), baseline.get("icmp_loss", 0), 0.8)
        return metrics_after, True

    if action == "retry_and_monitor":
        # transient faults are, by the dataset's own definition, brief and
        # self-resolving -- simulate near-complete recovery
        for k in ("icmp_loss", "discards_total", "errors_total"):
            metrics_after[k] = _toward_baseline(metrics_before.get(k), baseline.get(k, 0), 0.97)
        metrics_after["icmp_response_time"] = _toward_baseline(
            metrics_before.get("icmp_response_time"), baseline.get("icmp_response_time", 0), 0.9)
        return metrics_after, True

    raise ValueError(f"Unknown recovery action: {action}")

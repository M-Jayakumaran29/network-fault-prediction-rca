"""
Rule-based (NOT machine-learning) fault-type and evidence detection.

Every rule below is grounded in something actually observed in LCORE-D
during inspection (see preprocessing/data_loader.py docstring), not in the
assignment brief's illustrative examples verbatim -- notably:
  - `path_up` is constant 1 across the whole dataset, so it CANNOT be used
    as a down/up signal (the brief's example rule assumed it would toggle).
  - `operational_status` is 1.0 (up) for 533298/533392 interface-rows and
    otherwise NaN -- it almost never reports "down" outright, so a missing
    reading is treated as the down/unknown signal instead of a distinct
    status code.
  - Interface counters (discards/errors) and ICMP loss/latency are the
    metrics that actually move during induced/transient faults, so they
    carry most of the diagnostic weight here.

Each rule function takes a `ctx` dict (built by rca/root_cause.py) and
returns a finding dict or None. `weight` is a rule-based evidence weight,
not a probability -- root_cause.py sums it to produce a coarse
"low/medium/high" confidence label, which is explicitly NOT presented as a
machine-learning probability.
"""

# thresholds picked from the measured "healthy" baseline distribution, not
# arbitrary numbers -- see rca/root_cause.py:compute_device_baselines
ICMP_LOSS_SEVERE = 80.0       # percent
ICMP_LOSS_MODERATE = 30.0     # percent
LATENCY_SPIKE_FACTOR = 3.0    # x baseline
ERROR_SPIKE_FACTOR = 5.0      # x baseline (or absolute floor below)
ERROR_ABS_FLOOR = 5
DISCARD_SPIKE_FACTOR = 5.0
DISCARD_ABS_FLOOR = 5


def rule_snmp_unreachable(ctx):
    if ctx["metrics"].get("snmp_avail", 1) == 0:
        return {
            "rule": "snmp_unreachable",
            "probable_fault_type": "node_failure",
            "evidence": f"SNMP agent on {ctx['device']} is unreachable (snmp_avail=0) -- device appears down.",
            "weight": 4,
        }
    return None


def rule_interface_down(ctx):
    frac = ctx["metrics"].get("oper_status_up_frac")
    if frac is not None and frac < 1.0:
        n_iface = len(ctx["interfaces"])
        n_down = sum(1 for i in ctx["interfaces"] if i.get("oper_status") != 1.0)
        return {
            "rule": "interface_down",
            "probable_fault_type": "link_failure" if n_down < n_iface else "multiple_link_failure",
            "evidence": f"{n_down}/{n_iface} interfaces on {ctx['device']} not reporting operational (up).",
            "weight": 3,
        }
    return None


def rule_localized_interface_errors(ctx):
    base = ctx["baseline"]
    ifaces = ctx["interfaces"]
    if not ifaces:
        return None
    scored = []
    for i in ifaces:
        errs = (i.get("in_errors") or 0) + (i.get("out_errors") or 0)
        scored.append((i["interface"], errs))
    scored.sort(key=lambda x: x[1], reverse=True)
    worst_iface, worst_errs = scored[0]
    baseline_errors = base.get("errors_total", 0) or 0
    spike = worst_errs > max(ERROR_ABS_FLOOR, baseline_errors * ERROR_SPIKE_FACTOR)
    localized = len(scored) == 1 or (len(scored) > 1 and scored[1][1] <= max(1, worst_errs * 0.2))
    if spike and localized:
        return {
            "rule": "localized_interface_errors",
            "probable_fault_type": "line_card_failure",
            "evidence": f"Interface {worst_iface} on {ctx['device']} shows {worst_errs} packet errors "
                        f"(baseline ~{baseline_errors:.1f}), other interfaces normal -> localized hardware issue.",
            "weight": 3,
            "affected_interface": worst_iface,
        }
    return None


def rule_discards_spike(ctx):
    base = ctx["baseline"]
    discards = ctx["metrics"].get("discards_total", 0) or 0
    baseline_discards = base.get("discards_total", 0) or 0
    if discards > max(DISCARD_ABS_FLOOR, baseline_discards * DISCARD_SPIKE_FACTOR):
        ifaces = ctx["interfaces"]
        worst = max(ifaces, key=lambda i: (i.get("in_discards") or 0) + (i.get("out_discards") or 0), default=None)
        return {
            "rule": "discards_spike",
            "probable_fault_type": "link_failure",
            "evidence": f"{ctx['device']} total packet discards = {discards} (baseline ~{baseline_discards:.1f}) -- congestion/link issue.",
            "weight": 2,
            "affected_interface": worst["interface"] if worst else None,
        }
    return None


def rule_severe_icmp_loss(ctx):
    loss = ctx["metrics"].get("icmp_loss", 0) or 0
    if loss >= ICMP_LOSS_SEVERE:
        return {
            "rule": "severe_icmp_loss",
            "probable_fault_type": "link_failure",
            "evidence": f"ICMP loss on {ctx['device']} = {loss:.1f}% (severe, threshold {ICMP_LOSS_SEVERE}%).",
            "weight": 3,
        }
    return None


def rule_icmp_blocked_firewall(ctx):
    """High ICMP loss but the device is otherwise healthy (SNMP reachable,
    no interface errors/discards) -- matches LCORE-D's actual
    'ICMP Blocked (Firewall)' fault type, which is ICMP-specific rather
    than a real link/node failure."""
    loss = ctx["metrics"].get("icmp_loss", 0) or 0
    snmp_ok = ctx["metrics"].get("snmp_avail", 1) == 1
    errs = ctx["metrics"].get("errors_total", 0) or 0
    discards = ctx["metrics"].get("discards_total", 0) or 0
    base = ctx["baseline"]
    if loss >= ICMP_LOSS_MODERATE and snmp_ok and errs <= max(ERROR_ABS_FLOOR, (base.get("errors_total", 0) or 0) * 2) \
            and discards <= max(DISCARD_ABS_FLOOR, (base.get("discards_total", 0) or 0) * 2):
        return {
            "rule": "icmp_blocked_firewall",
            "probable_fault_type": "icmp_blocked_firewall",
            "evidence": f"ICMP loss {loss:.1f}% while SNMP is reachable and interface counters stay near baseline "
                        "-- ICMP-specific blocking rather than a physical link/node failure.",
            "weight": 2,
        }
    return None


def rule_routing_latency_anomaly(ctx):
    base = ctx["baseline"]
    latency = ctx["metrics"].get("icmp_response_time", 0) or 0
    baseline_latency = base.get("icmp_response_time", 0) or 0
    loss = ctx["metrics"].get("icmp_loss", 0) or 0
    errs = ctx["metrics"].get("errors_total", 0) or 0
    if baseline_latency > 0 and latency > baseline_latency * LATENCY_SPIKE_FACTOR \
            and loss < ICMP_LOSS_MODERATE and errs <= max(ERROR_ABS_FLOOR, (base.get("errors_total", 0) or 0) * 2):
        return {
            "rule": "routing_latency_anomaly",
            "probable_fault_type": "routing_misconfiguration",
            "evidence": f"Latency on {ctx['device']} = {latency:.2f}ms vs baseline {baseline_latency:.2f}ms "
                        "with low loss and no interface errors -- consistent with a routing/path change rather than a hard failure.",
            "weight": 2,
        }
    return None


def rule_shared_upstream(ctx, topology_mod):
    """If several devices are anomalous at the same timestamp, blame their
    common upstream ancestor instead of each device individually."""
    concurrent = ctx.get("concurrent_anomalous_devices", [])
    all_affected = list(dict.fromkeys(concurrent + [ctx["device"]]))
    if len(all_affected) < 2:
        return None
    g = ctx["topology_graph"]
    ancestor = topology_mod.lowest_common_ancestor(g, all_affected)
    if ancestor is None or ancestor == "SERVER":
        return None
    return {
        "rule": "shared_upstream_component",
        "probable_fault_type": "node_failure" if ancestor not in all_affected or ancestor == ctx["device"] else "multiple_link_failure",
        "evidence": f"Devices {all_affected} are anomalous simultaneously and all depend on {ancestor} "
                    "in the reconstructed topology -- investigate it as the common root cause.",
        "weight": 4,
        "root_cause_override": ancestor,
    }


def rule_transient_fallback(ctx):
    """Weak catch-all: something is off (this function is only called when
    the LSTM already predicted a fault) but no stronger rule matched --
    consistent with LCORE-D's naturally-occurring 'T' (transient) class."""
    return {
        "rule": "transient_fallback",
        "probable_fault_type": "transient_fault",
        "evidence": "Fault predicted by the LSTM but no interface/ICMP metric crossed a hard-fault threshold -- "
                    "likely a brief, self-resolving transient event.",
        "weight": 1,
    }

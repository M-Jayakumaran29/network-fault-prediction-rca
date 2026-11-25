"""
Network topology reconstruction for Root Cause Analysis.

LCORE-D does not ship an explicit adjacency list. What it does give, per
device, is:
    hop_to_core          -- hop distance from this device to the core router
    hop_to_server         -- hop distance from this device to the server
    downstream_dependents -- how many things sit behind this device

Inspecting these across the 7 devices gives a single consistent tree
(verified in preprocessing/data_loader.py exploration):

    SERVER -- EDGE-MS(hop_to_core=1, hop_to_server=1)
                   |
              CORE-R1 (hop_to_core=0 -- this *is* the core)
                   |
              CORE-R2 (hop_to_core=1)
                   |
              CORE-R3 (hop_to_core=2)
                 / | \
           CORE-R4 R5  R6   (hop_to_core=3)

This is a best-effort reconstruction from hop counts, not a literal
adjacency list from the dataset -- it is documented here rather than
hidden, and is only used to support the "shared upstream component" RCA
rule and the dashboard's topology view.
"""
import networkx as nx

import config

# (parent, child) edges of the reconstructed dependency tree, parent being
# the node closer to the core / server side.
TOPOLOGY_EDGES = [
    ("SERVER", "EDGE-MS"),
    ("EDGE-MS", "CORE-R1"),
    ("CORE-R1", "CORE-R2"),
    ("CORE-R2", "CORE-R3"),
    ("CORE-R3", "CORE-R4"),
    ("CORE-R3", "CORE-R5"),
    ("CORE-R3", "CORE-R6"),
]

NODE_ATTRS = {
    "SERVER": {"hop_to_core": None, "hop_to_server": 0, "downstream_dependents": None, "domain": "server"},
    "EDGE-MS": {"hop_to_core": 1, "hop_to_server": 1, "downstream_dependents": 13, "domain": "edge"},
    "CORE-R1": {"hop_to_core": 0, "hop_to_server": 2, "downstream_dependents": 12, "domain": "core"},
    "CORE-R2": {"hop_to_core": 1, "hop_to_server": 3, "downstream_dependents": 11, "domain": "core"},
    "CORE-R3": {"hop_to_core": 2, "hop_to_server": 4, "downstream_dependents": 10, "domain": "core"},
    "CORE-R4": {"hop_to_core": 3, "hop_to_server": 5, "downstream_dependents": 4, "domain": "core"},
    "CORE-R5": {"hop_to_core": 3, "hop_to_server": 5, "downstream_dependents": 4, "domain": "core"},
    "CORE-R6": {"hop_to_core": 3, "hop_to_server": 5, "downstream_dependents": 1, "domain": "core"},
}

MONITORED_DEVICES = list(config.DEVICE_FILES.keys())  # devices we actually have telemetry for


def build_topology_graph() -> nx.Graph:
    g = nx.Graph()
    for node, attrs in NODE_ATTRS.items():
        g.add_node(node, **attrs)
    g.add_edges_from(TOPOLOGY_EDGES)
    return g


def get_parent(g: nx.Graph, device: str):
    """The neighbor strictly closer to the core/server (smaller hop_to_server)."""
    if device not in g:
        return None
    my_hops = g.nodes[device]["hop_to_server"]
    for nb in g.neighbors(device):
        if g.nodes[nb]["hop_to_server"] is not None and my_hops is not None and g.nodes[nb]["hop_to_server"] < my_hops:
            return nb
    return None


def get_children(g: nx.Graph, device: str):
    my_hops = g.nodes[device]["hop_to_server"]
    return [nb for nb in g.neighbors(device)
            if g.nodes[nb]["hop_to_server"] is not None and my_hops is not None and g.nodes[nb]["hop_to_server"] > my_hops]


def get_siblings(g: nx.Graph, device: str):
    parent = get_parent(g, device)
    if parent is None:
        return []
    return [c for c in get_children(g, parent) if c != device]


def lowest_common_ancestor(g: nx.Graph, devices):
    """Returns the device that is the common upstream point for all given
    devices (the node through which all their traffic to the core/server
    passes), used by the "shared upstream root cause" rule."""
    devices = [d for d in devices if d in g]
    if not devices:
        return None
    if len(devices) == 1:
        return get_parent(g, devices[0]) or devices[0]
    root = "SERVER"
    paths = [nx.shortest_path(g, root, d) for d in devices]
    common = set(paths[0])
    for p in paths[1:]:
        common &= set(p)
    # deepest common node = the one with max hop_to_server among the common set
    return max(common, key=lambda n: (g.nodes[n]["hop_to_server"] or 0))


if __name__ == "__main__":
    g = build_topology_graph()
    for d in MONITORED_DEVICES:
        print(d, "parent:", get_parent(g, d), "children:", get_children(g, d), "siblings:", get_siblings(g, d))
    print("\nLCA of R4,R5:", lowest_common_ancestor(g, ["CORE-R4", "CORE-R5"]))
    print("LCA of R4,EDGE-MS:", lowest_common_ancestor(g, ["CORE-R4", "EDGE-MS"]))

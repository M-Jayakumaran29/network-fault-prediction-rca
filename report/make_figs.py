import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
os.chdir(os.path.dirname(os.path.abspath(__file__)))
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"], "font.size": 8, "axes.linewidth": 0.6})
M = "../models/"
H = json.load(open(M + "training_history.json"))
T = json.load(open(M + "threshold.json"))

def box(ax, x, y, w, h, text, fc="#f3ece1", ec="#5a4632", fs=7.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=fc, ec=ec, lw=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)

def arrow(ax, p, q):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=8, lw=0.8, color="#333"))

# Fig 1: architecture
fig, ax = plt.subplots(figsize=(3.5, 4.1)); ax.set_xlim(0, 10); ax.set_ylim(0, 12); ax.axis("off")
box(ax, 1, 10.3, 8, 1.3, "LCORE-D telemetry\n(7 devices, 60 s samples)")
box(ax, 1, 8.3, 8, 1.3, "Preprocessing\naggregate ports, segment, split, scale")
box(ax, 1, 6.3, 8, 1.3, "Objective 1: LSTM predictor\n10 x 6 window -> fault probability", fc="#e8f0e4")
box(ax, 1, 4.5, 8, 1.1, "Threshold 0.22 (validation F1)")
box(ax, 1, 2.4, 8, 1.4, "Objective 2: rule-based RCA\n9 rules + topology graph", fc="#e4ebf3")
box(ax, 1, 0.3, 8, 1.3, "Flask API + web dashboard")
for a, b in [(10.3, 9.6), (8.3, 7.6), (6.3, 5.6), (4.5, 3.8), (2.4, 1.6)]:
    arrow(ax, (5, a), (5, b))
fig.savefig("fig/arch.png", dpi=300, bbox_inches="tight"); plt.close(fig)

# Fig 2: topology
fig, ax = plt.subplots(figsize=(3.5, 1.9)); ax.set_xlim(0, 12); ax.set_ylim(0, 6.2); ax.axis("off")
nodes = {"SERVER": (0.9, 4.6), "EDGE-MS": (3.0, 4.6), "CORE-R1": (5.1, 4.6), "CORE-R2": (7.2, 4.6), "CORE-R3": (9.3, 4.6),
         "CORE-R4": (5.3, 1.0), "CORE-R5": (8.0, 1.0), "CORE-R6": (10.7, 1.0)}
for a, b in [("SERVER", "EDGE-MS"), ("EDGE-MS", "CORE-R1"), ("CORE-R1", "CORE-R2"), ("CORE-R2", "CORE-R3"),
             ("CORE-R3", "CORE-R4"), ("CORE-R3", "CORE-R5"), ("CORE-R3", "CORE-R6")]:
    ax.plot([nodes[a][0], nodes[b][0]], [nodes[a][1], nodes[b][1]], color="#555", lw=1, zorder=1)
for n, (x, y) in nodes.items():
    fc = "#d9d9d9" if n == "SERVER" else "#f3ece1"
    ax.add_patch(FancyBboxPatch((x - 0.95, y - 0.5), 1.9, 1.0, boxstyle="round,pad=0.02,rounding_size=0.1", fc=fc, ec="#5a4632", lw=0.8, zorder=2))
    ax.text(x, y, n, ha="center", va="center", fontsize=6.5, zorder=3)
fig.savefig("fig/topology.png", dpi=300, bbox_inches="tight"); plt.close(fig)

# Fig 3: training curves
ep = np.arange(1, len(H["loss"]) + 1)
fig, axs = plt.subplots(1, 2, figsize=(3.5, 1.9))
axs[0].plot(ep, H["loss"], "o-", ms=2.5, lw=1, label="train"); axs[0].plot(ep, H["val_loss"], "s-", ms=2.5, lw=1, label="validation")
axs[0].set_xlabel("Epoch"); axs[0].set_ylabel("BCE loss"); axs[0].legend(fontsize=6, frameon=False)
axs[1].plot(ep, H["auc"], "o-", ms=2.5, lw=1, label="train"); axs[1].plot(ep, H["val_auc"], "s-", ms=2.5, lw=1, label="validation")
axs[1].set_xlabel("Epoch"); axs[1].set_ylabel("AUC"); axs[1].legend(fontsize=6, frameon=False)
for a in axs: a.grid(alpha=0.25, lw=0.4); a.tick_params(labelsize=6.5)
fig.tight_layout(); fig.savefig("fig/training.png", dpi=300); plt.close(fig)

# Fig 4: confusion matrices val + test
fig, axs = plt.subplots(1, 2, figsize=(3.5, 1.8))
for a, key, ttl in [(axs[0], "val_metrics", "Validation"), (axs[1], "test_metrics", "Test")]:
    c = T[key]["confusion_matrix"]; cm = np.array([[c["tn"], c["fp"]], [c["fn"], c["tp"]]])
    a.imshow(cm, cmap="Oranges", vmin=0, vmax=cm.max() * 1.4)
    a.set_xticks([0, 1]); a.set_xticklabels(["Normal", "Fault"], fontsize=6.5); a.set_yticks([0, 1]); a.set_yticklabels(["Normal", "Fault"], fontsize=6.5, rotation=90, va="center")
    a.set_xlabel("Predicted", fontsize=7); a.set_ylabel("Actual", fontsize=7); a.set_title(ttl, fontsize=7.5)
    for i in range(2):
        for j in range(2): a.text(j, i, f"{cm[i, j]:,}", ha="center", va="center", fontsize=7)
fig.tight_layout(); fig.savefig("fig/confusion.png", dpi=300); plt.close(fig)

# Fig 5: RCA flow
fig, ax = plt.subplots(figsize=(3.5, 3.6)); ax.set_xlim(0, 10); ax.set_ylim(0, 12); ax.axis("off")
box(ax, 1, 10.4, 8, 1.2, "LSTM predicts fault (p >= 0.22)", fc="#e8f0e4")
box(ax, 1, 8.4, 8, 1.2, "Collect device metrics, ports,\nbaseline, concurrent faulty devices")
box(ax, 1, 6.2, 8, 1.6, "Evaluate rules 1-8\n(each returns weighted finding)")
box(ax, 1, 4.4, 8, 1.2, "No finding? -> rule 9 (transient)")
box(ax, 1, 2.4, 8, 1.4, "Sort by weight; highest = root cause\nsum of weights -> confidence", fc="#e4ebf3")
box(ax, 1, 0.3, 8, 1.3, "Structured result + evidence")
for a, b in [(10.4, 9.6), (8.4, 7.8), (6.2, 5.6), (4.4, 3.8), (2.4, 1.6)]:
    arrow(ax, (5, a), (5, b))
fig.savefig("fig/rcaflow.png", dpi=300, bbox_inches="tight"); plt.close(fig)

# Fig 6: threshold scan on... only stored points: skip. Fig: metrics bar val vs test
fig, ax = plt.subplots(figsize=(3.5, 1.9))
names = ["Accuracy", "Precision", "Recall", "F1", "ROC-AUC"]; keys = ["accuracy", "precision", "recall", "f1", "roc_auc"]
x = np.arange(len(names)); w = 0.38
v = [T["val_metrics"][k] for k in keys]; t = [T["test_metrics"][k] for k in keys]
b1 = ax.bar(x - w / 2, v, w, label="Validation", color="#c9a679"); b2 = ax.bar(x + w / 2, t, w, label="Test", color="#6b4a2b")
for b in list(b1) + list(b2): ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01, f"{b.get_height():.2f}", ha="center", fontsize=5.8)
ax.set_xticks(x); ax.set_xticklabels(names, fontsize=6.5); ax.set_ylim(0, 1.12); ax.legend(fontsize=6, frameon=False, ncol=2, loc="upper center")
ax.tick_params(labelsize=6.5); ax.grid(axis="y", alpha=0.25, lw=0.4)
fig.tight_layout(); fig.savefig("fig/metrics.png", dpi=300); plt.close(fig)
print("done")

# Fig 8: per-device test behaviour (from analysis.json)
A = json.load(open("analysis.json"))
devs = list(A["per_device"].keys())
rate = [A["per_device"][d]["pos"] / A["per_device"][d]["n"] for d in devs]
rec = [A["per_device"][d]["rec"] for d in devs]
fig, ax = plt.subplots(figsize=(3.5, 2.0)); x = np.arange(len(devs)); w = 0.38
ax.bar(x - w / 2, rate, w, label="Share of non-healthy windows", color="#c9a679")
ax.bar(x + w / 2, rec, w, label="LSTM recall", color="#6b4a2b")
ax.set_xticks(x); ax.set_xticklabels([d.replace("CORE-", "") for d in devs], fontsize=6.5); ax.set_ylim(0, 1.25)
ax.legend(fontsize=6, frameon=False, ncol=1, loc="upper center"); ax.tick_params(labelsize=6.5); ax.grid(axis="y", alpha=0.25, lw=0.4)
ax.set_xlabel("Device", fontsize=7)
fig.tight_layout(); fig.savefig("fig/perdevice.png", dpi=300); plt.close(fig); print("fig8")

#!/usr/bin/env python3
"""Two-panel before/after figure for the real-repo KB audit workflow (task-72)."""
from __future__ import annotations
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

summary = json.load(open(os.path.join(RAW, "summary.json"), encoding="utf-8"))
adjud = json.load(open(os.path.join(HERE, "adjudication.json"), encoding="utf-8"))
scans = {(s["repo"], s["condition"], s["config"].split(".")[1]): s for s in summary["scans"]}
REPOS = ["R2", "R3"]
SHORT = {"R2": "R2", "R3": "R3"}  # anonymous codes in the paper

# committed-config scans drive the workflow numbers; generic is the FP sensitivity
def counts(repo, cond, cfg):
    s = scans[(repo, cond, cfg)]
    c = s["counts"]
    return {"claims": c.get("claims", 0), "queue": c.get("queue", 0),
            "findings": s["r9_findings"], "exit": s["exit_code"],
            "runtime": s["runtime_s"]}

before = {r: counts(r, "parent-stale", "kblint") for r in REPOS}
after = {r: counts(r, "repaired", "kblint") for r in REPOS}
generic_before = {r: counts(r, "parent-stale", "generic") for r in REPOS}
generic_after = {r: counts(r, "repaired", "generic") for r in REPOS}

fig, (axA, axB) = plt.subplots(1, 2, figsize=(11.6, 4.3))

# ---- Panel A: claims -> rule-addressable queue -> confirmed findings (parent, stale) ----
stages = ["claims extracted", "rule-addressable queue\n(not a defect list)", "confirmed R9 findings"]
palette = {"R2": "#3b6ea5", "R3": "#c26b2e"}
y = [0, 1, 2]
for j, r in enumerate(REPOS):
    vals = [before[r]["claims"], before[r]["queue"], before[r]["findings"]]
    off = (j - 0.5) * 0.34
    bars = axA.barh([v + off for v in y], vals, height=0.30,
                    color=palette[r], alpha=0.9, label=f"{SHORT[r]} (parent, stale)")
    for b, v in zip(bars, vals):
        axA.text(v + max(1, v * 0.02), b.get_y() + b.get_height() / 2, str(v),
                 va="center", ha="left", fontsize=9)
axA.set_yticks(y)
axA.set_yticklabels(stages, fontsize=9)
axA.invert_yaxis()
axA.set_xlim(0, 95)
axA.set_xlabel("count (parent-stale condition, committed KB config)")
axA.set_title("A. Audit funnel: claims → queue → confirmed findings", fontsize=10, loc="left")
axA.legend(fontsize=8, frameon=False, loc="lower right")
axA.grid(axis="x", alpha=0.25)
for s in ("top", "right"):
    axA.spines[s].set_visible(False)

# ---- Panel B: before/after repair (findings + queue), committed config ----
x = range(len(REPOS))
w = 0.19
for j, r in enumerate(REPOS):
    pass
b_before = [before[r]["findings"] for r in REPOS]
b_after = [after[r]["findings"] for r in REPOS]
g_before = [generic_before[r]["findings"] for r in REPOS]
g_after = [generic_after[r]["findings"] for r in REPOS]
xs = list(range(len(REPOS)))
axB.bar([i - 1.5 * w for i in xs], b_before, w, color="#b23a48", label="R9 findings before (committed config)")
axB.bar([i - 0.5 * w for i in xs], b_after, w, color="#4c956c", label="R9 findings after repair (committed config)")
axB.bar([i + 0.5 * w for i in xs], g_before, w, color="#b23a48", alpha=0.35, hatch="//",
        label="R9 before (generic config: incl. FP-by-contract)")
axB.bar([i + 1.5 * w for i in xs], g_after, w, color="#4c956c", alpha=0.35, hatch="//",
        label="R9 after (generic config)")
for i, r in enumerate(REPOS):
    for dx, v in ((-1.5 * w, b_before[i]), (-0.5 * w, b_after[i]),
                  (0.5 * w, g_before[i]), (1.5 * w, g_after[i])):
        axB.text(i + dx, v + 0.12, str(v), ha="center", fontsize=8.5)
axB.set_xticks(xs)
axB.set_xticklabels(["%s\nqueue %d → %d (not defects)" % (SHORT[r], before[r]["queue"], after[r]["queue"])
                     for r in REPOS], fontsize=8.6)
axB.set_ylim(0, 7.2)
axB.set_ylabel("R9 findings")
axB.set_title("B. Before vs after the minimal KB repair", fontsize=10, loc="left")
axB.legend(fontsize=7.4, frameon=False, loc="upper right")
axB.grid(axis="y", alpha=0.25)
for s in ("top", "right"):
    axB.spines[s].set_visible(False)

fig.suptitle("kblint v0.2.1 on real repositories: stale-KB audit and minimal repair "
             "(parent vs fix-commit KB, no model calls)", fontsize=10.5, x=0.01, ha="left")
fig.tight_layout(rect=(0, 0, 1, 0.94))
for ext in ("pdf", "png"):
    path = os.path.join(FIG, "before_after_repair." + ext)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    print("wrote", path)

# data snapshot for REPORT/table consistency
snap = {
    "before": {r: before[r] for r in REPOS},
    "after": {r: after[r] for r in REPOS},
    "generic_before": {r: generic_before[r] for r in REPOS},
    "generic_after": {r: generic_after[r] for r in REPOS},
    "adjudication_summary": adjud["summary"],
}
with open(os.path.join(RAW, "figure_data.json"), "w", encoding="utf-8") as f:
    json.dump(snap, f, ensure_ascii=False, indent=1)
    f.write("\n")
print(json.dumps(snap, indent=1))

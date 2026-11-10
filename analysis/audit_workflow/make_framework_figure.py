import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from pathlib import Path

fig, ax = plt.subplots(figsize=(7.2, 2.9))
ax.set_xlim(0, 10); ax.set_ylim(0, 4.2); ax.axis("off")

W, H = 2.9, 1.3
top_y, bot_y = 2.55, 0.95
cols = [0.25, 3.55, 6.85]

boxes = {
 "kb":   (cols[0], top_y, "Repository KB\npaths · pins · conventions\nresults · skills", "#e8eef7"),
 "l1":   (cols[1], top_y, "L1 Deterministic checks\nkblint R1–R9 · surface-flagged\nreview candidates + witnesses", "#dfe9f5"),
 "l2":   (cols[2], top_y, "L2 Decision probes\ntriage only; not a\nharm detector", "#eef2e6"),
 "l3":   (cols[2], bot_y, "L3 Outcome tests\ncontrolled tasks;\nreal-repo counterfactuals", "#f4eee2"),
 "disp": (cols[1], bot_y, "Claim disposition\nVerified · Stale\nUnknown · Removed", "#f0e4e4"),
 "rep":  (cols[0], bot_y, "Repair → re-audit\nversioned knowledge", "#e4efe6"),
}
for key, (x, y, txt, col) in boxes.items():
    ax.add_patch(FancyBboxPatch((x, y), W, H, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor=col, edgecolor="#44546a", linewidth=0.8))
    ax.text(x + W/2, y + H/2, txt, ha="center", va="center", fontsize=6.7, color="#1c2733")

def arrow(x1, y1, x2, y2, rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=7,
                                 linewidth=0.8, color="#44546a", connectionstyle=f"arc3,rad={rad}"))

# row 1 left -> right
for a, b in [("kb", "l1"), ("l1", "l2")]:
    xa = boxes[a][0] + W; xb = boxes[b][0]
    arrow(xa + 0.03, top_y + H/2, xb - 0.03, top_y + H/2)
# down from L2 to L3
arrow(cols[2] + W/2, top_y - 0.03, cols[2] + W/2, bot_y + H + 0.03)
# row 2 right -> left
for a, b in [("l3", "disp"), ("disp", "rep")]:
    xa = boxes[a][0]; xb = boxes[b][0] + W
    arrow(xa - 0.03, bot_y + H/2, xb + 0.03, bot_y + H/2)
# loop repair -> KB
arrow(cols[0] + W/2, bot_y + H + 0.03, cols[0] + W/2, top_y - 0.03)

ax.text(5.0, 4.02, "Tiered repository-knowledge maintenance: evidence tiers, dispositions, and the repair loop",
        ha="center", va="center", fontsize=7.6, color="#1c2733")
ax.text(5.0, 0.28, "Unknown \u2260 Verified · last_checked \u2260 Verified · deterministic rules cover the reference layer, not semantic conventions",
        ha="center", va="center", fontsize=6.3, color="#44546a")
out = Path("paper_workshop/figures")
for ext in ("pdf", "png"):
    fig.savefig(out / f"fig_framework.{ext}", bbox_inches="tight", dpi=300)
print("saved")

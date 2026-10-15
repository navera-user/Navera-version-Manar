#!/usr/bin/env python3
"""Teacher only — draws the figures of lesson 33 into courses/33-final-project/assets/ (SVG, text kept as text).

    NAVERA_LITE_SIM_DATA=~/navera-academy-v2/datasets/31-simulator python3 solutions/33-final-project/make_figures.py

paired.svg flies the lesson's worked example (make_lesson_numbers.py: lake.json, seeds 1201–1230, day_timeout_s
5.0 → 2.0) with the given bench; the other three are diagrams.
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_lesson_numbers as L  # noqa: E402

ACADEMY = L.ACADEMY
OUT = os.path.join(ACADEMY, "courses", "33-final-project", "assets")
INK, BLUE, RED, AMBER, GREY, BG, GREEN = "#1d2733", "#0b6e8a", "#d64545", "#c98a06", "#8a96a3", "#f7fafc", "#2e9e4f"
plt.rcParams.update({"svg.fonttype": "none", "font.family": "sans-serif", "font.size": 11, "axes.edgecolor": INK,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "text.color": INK,
                     "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
                     "axes.spines.top": False, "axes.spines.right": False})


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, name), format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    print("wrote", name)


def box(ax, x, y, w, h, text, fc, ec=INK, fs=10, bold=False):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, weight="bold" if bold else "normal")


def arrow(ax, x0, y0, x1, y1, color=INK):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", color=color, lw=1.3))


def loop():
    fig, ax = plt.subplots(figsize=(9.0, 4.4))
    ax.set_xlim(0, 9.0)
    ax.set_ylim(0, 4.4)
    ax.axis("off")
    steps = [("Step 3\npre-register", "#e6f1f5"), ("Step 4\nred test (fails)", "#fbe3e3"),
             ("Step 5\ngit tag before", "#eeeeee"), ("Step 5\nfly before", "#e6f1f5"),
             ("Step 6\nONE change", "#fff3d6"), ("Step 6\ngreen", "#e3f4e7"), ("Step 7\nfly after", "#e6f1f5"),
             ("Step 8\nevaluate: D, CI", "#e6f1f5"), ("Step 8\ndecide (rule)", "#eeeeee"),
             ("Steps 9–10\nreport, patch", "#fff3d6")]
    xs = [0.95 + 1.75 * i for i in range(5)]
    pos = [(x, 3.0) for x in xs] + [(x, 1.3) for x in reversed(xs)]      # a snake: row 2 runs right to left
    for (t_, fc), (x, y) in zip(steps, pos):
        box(ax, x, y, 1.45, 0.8, t_, fc, fs=9.5)
    for (x0, y0), (x1, y1) in zip(pos[:4], pos[1:5]):
        arrow(ax, x0 + 0.73, y0, x1 - 0.73, y1)
    for (x0, y0), (x1, y1) in zip(pos[5:9], pos[6:10]):
        arrow(ax, x0 - 0.73, y0, x1 + 0.73, y1)
    arrow(ax, pos[4][0], 2.58, pos[5][0], 1.72)
    ax.add_patch(plt.Rectangle((0.14, 2.5), 5.12, 1.03, fc="none", ec=BLUE, ls="--", lw=1.2))
    ax.text(2.58, 3.75, "frozen at 'before': the rule, the seeds, the red test, the ruler", ha="center", color=BLUE,
            fontsize=9.8)
    ax.annotate("", xy=(pos[3][0], 2.58), xytext=(pos[6][0], 1.72),
                arrowprops=dict(arrowstyle="<->", color=AMBER, lw=1.6))
    ax.text(pos[3][0] - 0.1, 2.15, "same scenarios, same seeds:\nonly the code differs (paired)", ha="right",
            va="center", color=AMBER, fontsize=9.3)
    ax.text(4.5, 0.35, "The numbers come only from Step 8; accept / reject / inconclusive only from the rule of Step 3.",
            ha="center", fontsize=9.8, style="italic")
    save(fig, "loop.svg")


def commits():
    fig, ax = plt.subplots(figsize=(9.6, 3.3))
    ax.set_xlim(0, 10.6)
    ax.set_ylim(0, 3.3)
    ax.axis("off")
    ax.plot([0.5, 9.9], [1.9, 1.9], color=GREY, lw=2, zorder=0)
    nodes = [(0.9, "start", "the stack as given\n(init_repo.sh)", "#eeeeee"),
             (2.9, "(optional)", "use my own parts\n(adopt --apply)", "#eeeeee"),
             (5.0, "before", "red test +\nproject.json", "#fbe3e3"),
             (7.1, "", "the change\n(green)", "#e3f4e7"),
             (9.1, "", "REPORT.md\nanswers.py", "#fff3d6")]
    for x, tag, text, fc in nodes:
        ax.add_patch(plt.Circle((x, 1.9), 0.17, fc=fc, ec=INK, lw=1.3, zorder=2))
        ax.text(x, 1.25, text, ha="center", va="top", fontsize=9.2)
        if tag:
            ax.text(x, 2.32, f"tag {tag}" if tag not in ("(optional)",) else tag, ha="center", fontsize=9.5,
                    color=BLUE if tag in ("start", "before") else GREY, weight="bold" if tag == "before" else None)
    ax.annotate("campaign 'before'\nflies this commit", xy=(5.0, 2.1), xytext=(4.3, 2.95), fontsize=9.2, color=BLUE,
                arrowprops=dict(arrowstyle="-|>", color=BLUE))
    ax.annotate("campaign 'after'\nflies this commit", xy=(7.1, 2.1), xytext=(6.6, 2.95), fontsize=9.2, color=AMBER,
                arrowprops=dict(arrowstyle="-|>", color=AMBER))
    ax.text(10.15, 1.9, "branch\nproject/<name>", va="center", fontsize=9, color=GREY)
    ax.text(5.25, 0.2, "Between 'before' and 'after' only the stack changes: not the test, not project.json, not the "
                       "simulator's world.", ha="center", fontsize=9.5, style="italic")
    save(fig, "commits.svg")


def paired():
    seeds = list(range(1201, 1231))
    base, short = L.variant(), L.variant(("day_timeout_s: 5.0", "day_timeout_s: 2.0"))
    rb, ra = L.campaign(base, "campaign/lake.json", seeds), L.campaign(short, "campaign/lake.json", seeds)
    m = {"name": "err_p95", "window": "fault"}
    b, a = L.vals(rb, m), L.vals(ra, m)
    lo, hi = L.stats.paired_diff_ci(a, b, lambda x: float(np.mean(x)), B=2000, seed=33)
    fig, ax = plt.subplots(1, 2, figsize=(9.0, 3.9), gridspec_kw={"width_ratios": [1, 1.3]})
    for i in range(len(b)):
        ax[0].plot([0, 1], [b[i], a[i]], color=GREY, lw=0.8)
    ax[0].plot(np.zeros(len(b)), b, "o", ms=4, color=BLUE)
    ax[0].plot(np.ones(len(a)), a, "o", ms=4, color=AMBER)
    ax[0].set_xticks([0, 1], ["before\n(timeout 5 s)", "after\n(timeout 2 s)"])
    ax[0].set_xlim(-0.3, 1.3)
    ax[0].set_ylabel("err_p95 during the jam (m)")
    ax[0].set_title("30 runs, each flown twice (same seed)", fontsize=10.5)
    d = a - b
    ax[1].hist(d, bins=np.arange(-24.0, 3.0, 1.5), color=GREY, ec=BG)
    ax[1].set_xlim(-24, 2)
    ax[1].axvspan(lo, hi, color=AMBER, alpha=0.3, label=f"95 % interval of the mean D [{lo:.1f}, {hi:.1f}] m")
    ax[1].axvline(float(np.mean(d)), color=AMBER, lw=2, label=f"mean D = {np.mean(d):.1f} m")
    ax[1].axvline(0, color=INK, lw=1)
    ax[1].axvline(-3, color=RED, lw=1.2, ls="--", label="minimum effect −3 m")
    ax[1].set_xlabel("D per run = after − before (m)")
    ax[1].set_ylabel("runs")
    ax[1].legend(fontsize=8.3, loc="upper left", frameon=False)
    ax[1].set_ylim(0, 14)
    fig.tight_layout()
    save(fig, "paired.svg")
    for dd in (base, short):
        L.shutil.rmtree(dd, ignore_errors=True)


def decision():
    fig, ax = plt.subplots(figsize=(9.0, 3.9))
    rows = [("A", (-9.9, -5.6), "ACCEPT: the whole interval is\nbeyond the minimum effect", GREEN),
            ("B", (-8.0, -2.5), "INCONCLUSIVE: a gain, but maybe\nsmaller than the minimum effect", AMBER),
            ("C", (-4.0, 3.0), "INCONCLUSIVE: it contains 0 —\nnot shown (never 'equal')", AMBER),
            ("D", (1.5, 6.0), "REJECT: the whole interval is\non the bad side of 0", RED)]
    for i, (k, (lo, hi), text, col) in enumerate(rows):
        y = 3 - i
        ax.plot([lo, hi], [y, y], color=col, lw=6, solid_capstyle="butt")
        ax.text(-14.6, y, k, va="center", fontsize=11, weight="bold")
        ax.text(7.5, y, text, va="center", fontsize=9.4)
    ax.axvline(0, color=INK, lw=1)
    ax.axvline(-5, color=RED, lw=1.2, ls="--")
    ax.text(0.25, 3.55, "0", fontsize=9.5)
    ax.text(-5.25, 3.55, "minimum effect −5", fontsize=9.3, color=RED, ha="right")
    ax.set_xlim(-15, 21)
    ax.set_ylim(-0.6, 3.9)
    ax.set_yticks([])
    ax.set_xticks([-15, -10, -5, 0, 5])
    ax.set_xlabel("95 % interval of D = after − before (m), for a metric where LOWER is better", loc="left")
    ax.spines["left"].set_visible(False)
    save(fig, "decision.svg")


if __name__ == "__main__":
    loop()
    commits()
    decision()
    paired()

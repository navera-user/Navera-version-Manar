#!/usr/bin/env python3
"""Teacher only — draws the figures of lesson 32 into courses/32-measuring/assets/ (SVG, text kept as text).

    python3 solutions/32-measuring/make_figures.py

Every number drawn is computed here with the course reference (solutions/_navera_lite stats.py) or quoted from
NAVERA's validation report of 2026-10-03 (cold_open.svg). The other figures use their own synthetic examples,
never the lab's flights, so that no lab answer is shown.
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite import stats as S  # noqa: E402

OUT = os.path.join(ACADEMY, "courses", "32-measuring", "assets")
INK, BLUE, RED, AMBER, GREY, BG, GREEN = "#1d2733", "#0b6e8a", "#d64545", "#c98a06", "#8a96a3", "#f7fafc", "#2e9e4f"
plt.rcParams.update({"svg.fonttype": "none", "font.family": "sans-serif", "font.size": 11, "axes.edgecolor": INK,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "text.color": INK,
                     "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
                     "axes.spines.top": False, "axes.spines.right": False})
EX = [3.1, 2.4, 5.0, 2.8, 4.1, 3.6, 19.0, 2.2, 3.3, 4.4]       # lesson §2's ten errors


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    print("wrote", name)


def cold_open():
    rows = [("DINOv2 retrieval, search within 600 m", 442, BLUE), ("repeat the previous position (baseline)", 480, GREY),
            ("random tile in the circle (baseline)", 536, GREY), ("best tile available (the limit)", 107, GREEN)]
    fig, ax = plt.subplots(figsize=(8.2, 3.0))
    for i, (lab, v, col) in enumerate(rows):
        ax.barh(i, v, color=col, height=0.6)
        ax.text(v + 8, i, f"{v} m", va="center")
        ax.text(-10, i, lab, va="center", ha="right")
    ax.set_yticks([])
    ax.invert_yaxis()
    ax.set_xlim(0, 640)
    ax.set_xlabel("median error on 33 labelled replay frames (m)")
    ax.annotate("38 m better than doing nothing:\nreal, or luck of 33 frames?", xy=(461, 0.5), xytext=(330, 3.05),
                ha="center", color=RED, arrowprops=dict(arrowstyle="->", color=RED))
    ax.set_title("NAVERA's validation report, 3 October 2026 (day vision, former method)", fontsize=11, loc="left")
    save(fig, "cold_open.svg")


def rules():
    s = sorted(EX)
    fig, ax = plt.subplots(figsize=(8.2, 2.4))
    ax.plot(s, [0] * len(s), "o", color=BLUE, ms=8, zorder=3)
    for i, v in enumerate(s):
        ax.text(v, 0.18, f"{i}", ha="center", fontsize=9, color=GREY)
    lin, near = S.percentile(EX, 95), S.pct_nearest(EX, 95)
    ax.plot([lin], [0], "D", color=AMBER, ms=10, zorder=4)
    ax.annotate(f"linear p95 = {lin:.1f} m\n(position 8.55: between\nsample 8 and sample 9)", xy=(lin, 0), xytext=(lin, -0.75),
                ha="center", color=AMBER, arrowprops=dict(arrowstyle="->", color=AMBER))
    ax.annotate(f"nearest-sample p95 = {near:.1f} m\n(index round(8.55) = 9)", xy=(near, 0), xytext=(near - 1.5, 0.75),
                ha="center", color=RED, arrowprops=dict(arrowstyle="->", color=RED))
    ax.text(2.0, 0.55, "sorted errors (m); grey numbers: their index", fontsize=9, color=GREY)
    ax.set_ylim(-1.2, 1.2)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("error (m)")
    save(fig, "rules.svg")


def availability():
    rng = np.random.default_rng(7)
    t = np.arange(60)
    a = np.abs(rng.normal(0, 9, 60)) + 4
    ok_b = np.zeros(60, bool)
    ok_b[[2, 3, 4, 17, 18, 31, 32, 33, 34, 50, 51, 52]] = True
    b = np.abs(rng.normal(0, 1.5, 60)) + 1.0
    fig, axs = plt.subplots(2, 1, figsize=(8.2, 3.6), sharex=True)
    for ax, err, ok, lab in ((axs[0], a, np.ones(60, bool), "method A answers every second"),
                             (axs[1], b, ok_b, "method B answers only when it is sure")):
        ax.plot(t[ok], err[ok], "o", color=BLUE, ms=4)
        ax.plot(t[~ok], np.zeros((~ok).sum()), "|", color=GREY, ms=10)
        med = np.median(err[ok])
        ax.set_title(f"{lab}: median {med:.1f} m on {ok.sum()} s — availability {100 * ok.mean():.0f} %",
                     fontsize=10, loc="left")
        ax.set_ylim(-2, 30)
        ax.set_ylabel("error (m)")
    axs[1].set_xlabel("time (s); grey ticks: no position")
    fig.tight_layout()
    save(fig, "availability.svg")
    return np.median(a), np.median(b[ok_b]), ok_b.mean()


def baseline():
    rng = np.random.default_rng(11)
    t = np.arange(1, 41)
    base = 20.0 * t
    vis = S.ar1_radial(rng, 40, 0.8, 170.0)
    fig, ax = plt.subplots(figsize=(8.2, 3.2))
    ax.plot(t, base, "-", color=RED, lw=2, label="baseline: the last GPS position (20 m/s)")
    ax.plot(t, vis, "o", color=BLUE, ms=4, label="a vision method")
    for i in (4, 19, 34):
        ax.annotate("", xy=(t[i], vis[i]), xytext=(t[i], base[i]),
                    arrowprops=dict(arrowstyle="<->", color=AMBER, lw=1))
    ax.text(t[34] + 0.6, (vis[34] + base[34]) / 2, "paired\ndifference", color=AMBER, fontsize=9)
    ax.set_xlabel("seconds since GPS was lost")
    ax.set_ylabel("error (m)")
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    save(fig, "baseline.svg")


def bootstrap():
    x = np.array(EX)
    rng = np.random.default_rng(1)
    fig = plt.figure(figsize=(8.6, 3.4))
    ax0 = fig.add_axes([0.0, 0.05, 0.42, 0.9])
    ax0.axis("off")
    ax0.text(0, 0.92, "your 10 errors (m):", fontsize=10, weight="bold")
    ax0.text(0, 0.82, " ".join(f"{v:g}" for v in x), fontsize=9.5, color=BLUE)
    for k in range(3):
        idx = rng.integers(0, 10, 10)
        r = x[idx]
        ax0.text(0, 0.64 - 0.2 * k, f"resample {k + 1}:", fontsize=10)
        ax0.text(0, 0.56 - 0.2 * k, " ".join(f"{v:g}" for v in r), fontsize=9.5, color=GREY)
        ax0.text(0.98, 0.56 - 0.2 * k, f"median {np.median(r):.2f}", fontsize=9.5, color=AMBER, ha="right")
    ax0.text(0, 0.0, "… 2000 resamples, drawn WITH replacement", fontsize=10)
    rng = np.random.default_rng(1)
    reps = [np.median(x[rng.integers(0, 10, 10)]) for _ in range(2000)]
    lo, hi = S.bootstrap_ci(EX, np.median, seed=1)
    ax = fig.add_axes([0.5, 0.17, 0.48, 0.73])
    ax.hist(reps, bins=np.arange(2.0, 6.0, 0.1), color=AMBER, alpha=0.85)
    for v in (lo, hi):
        ax.axvline(v, color=RED, lw=1.5)
    ax.axvline(np.median(x), color=BLUE, lw=2)
    ax.set_title(f"2000 medians: 95 % of them between {lo:.2f} and {hi:.2f} m", fontsize=10)
    ax.set_xlabel("median of a resample (m); blue: the data's own median")
    ax.set_yticks([])
    save(fig, "bootstrap.svg")
    return lo, hi


def blocks():
    rng = np.random.default_rng(5)
    e = S.ar1_radial(rng, 30, 0.9, 10.0)
    fig, axs = plt.subplots(3, 1, figsize=(8.2, 4.4), sharex=True, sharey=True)
    axs[0].plot(range(30), e, "o-", color=BLUE, ms=4, lw=0.8)
    axs[0].set_title("30 seconds of a correlated error: neighbours look alike", fontsize=10, loc="left")
    g = np.random.default_rng(2)
    idx = g.integers(0, 30, 30)
    axs[1].plot(range(30), e[idx], "o-", color=GREY, ms=4, lw=0.8)
    axs[1].set_title("iid resample: single seconds, shuffled — the slow wave is gone", fontsize=10, loc="left")
    starts = g.integers(0, 30 - 6 + 1, 5)
    idx = np.concatenate([np.arange(s, s + 6) for s in starts])[:30]
    axs[2].plot(range(30), e[idx], "o-", color=AMBER, ms=4, lw=0.8)
    for k in range(1, 5):
        axs[2].axvline(6 * k - 0.5, color=GREY, lw=0.6, ls=":")
    axs[2].set_title("block resample: runs of 6 consecutive seconds — inside a run the wave is kept", fontsize=10,
                     loc="left")
    axs[2].set_xlabel("position in the resample")
    for ax in axs:
        ax.set_ylabel("m")
    fig.tight_layout()
    save(fig, "blocks.svg")


def coverage():
    rng = np.random.default_rng(3)
    true = S.RAYLEIGH_MEDIAN * 10.0
    fig, ax = plt.subplots(figsize=(8.2, 3.4))
    miss = 0
    for k in range(25):
        x = S.ar1_radial(rng, 40, 0.0, 10.0)
        lo, hi = S.bootstrap_ci(x, np.median, B=500, seed=k)
        bad = not (lo <= true <= hi)
        miss += bad
        ax.plot([k, k], [lo, hi], "-", color=RED if bad else BLUE, lw=3)
    ax.axhline(true, color=INK, lw=1, ls="--")
    ax.text(25.3, true, "the true\nmedian", va="center", fontsize=9)
    ax.set_xlabel("25 imaginary experiments (40 independent errors each)")
    ax.set_ylabel("95 % interval of the median (m)")
    ax.set_title(f"{25 - miss} of 25 intervals contain the truth; red: the ones that miss it", fontsize=10, loc="left")
    save(fig, "coverage.svg")
    return miss


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cold_open()
    rules()
    print("availability medians A, B, share B:", availability())
    baseline()
    print("bootstrap CI:", bootstrap())
    blocks()
    print("coverage misses:", coverage())

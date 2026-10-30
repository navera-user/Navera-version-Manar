"""chi2_sim.py — the χ² law, learned by simulation (lab Step 3; lesson §3).

    python3 chi2_sim.py          needs TODO 4 below (and nothing else)

An honest 2-D error, measured in sigmas of its own covariance, is a pair (x, y) of independent standard normal
numbers, and its squared Mahalanobis distance is d² = x² + y². This program draws 10 000 of them with YOUR
function, counts how many fall inside the 1-, 2- and 3-sigma ellipses (d² ≤ 1, 4, 9), finds the d² that 95 % and
99 % of them stay below, and compares with the same counts for ONE axis (x² alone). It draws out/chi2.png.
"""
import json
import math
import os
import sys

import numpy as np

import runner_kit as rk


# TODO 4 -------------------------------------------------------------------------------------------
def d2_samples(n, seed=0):
    """n random values of d² = x² + y², where x and y are independent standard normal numbers (mean 0, σ 1): the
    squared Mahalanobis distance of an honest 2-D error (lesson §3). Use ONE generator,
    rng = np.random.default_rng(seed), for all the draws, so that a run can be repeated exactly.
    Returns a numpy array of n floats (all ≥ 0).
    Example: d2_samples(4, seed=1) → 4 numbers ≥ 0, the same ones at every run;
             d2_samples(200000).mean() → about 2.0
    """
    return None   # TODO: replace this line with your code


# ---- you don't need to change anything below this line ----

N = 10000


def one_axis(n, seed=0):
    """The same experiment on ONE axis: n values of x² (the course's own code, for the comparison)."""
    return np.random.default_rng(seed + 1).standard_normal(n) ** 2


def save_results(update):
    os.makedirs("out", exist_ok=True)
    path = "out/results.json"
    try:
        with open(path) as f:
            res = json.load(f)
    except (OSError, ValueError):
        res = {}
    res.update(update)
    with open(path, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)


def main():
    here = sys.modules[__name__]
    d2 = rk.need_ok(here, "d2_samples", N, seed=27)
    try:
        d2 = np.asarray(d2, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        sys.exit(f"d2_samples() must return a numpy array of numbers, but it returned {type(d2).__name__}")
    if d2.shape != (N,):
        sys.exit(f"d2_samples({N}) must return {N} numbers, but it returned {d2.size}")
    if np.any(d2 < 0):
        sys.exit("d2_samples() returned negative values: a sum of SQUARES is never negative")
    x2 = one_axis(N, seed=27)
    print(f"{N} honest errors, in sigmas of their own covariance\n")
    print(f"{'':28s}{'2-D: d² = x² + y²':>20s}{'1-D: x² alone':>16s}")
    shares = {}
    for k in (1, 2, 3):
        a, b = 100 * np.mean(d2 <= k * k), 100 * np.mean(x2 <= k * k)
        shares[k] = a
        print(f"inside {k} sigma (d² ≤ {k * k}):     {a:15.1f} %{b:15.1f} %")
    p95, p99 = np.percentile(d2, 95), np.percentile(d2, 99)
    print(f"95 % of the d² stay below:   {p95:15.2f}  {np.percentile(x2, 95):15.2f}")
    print(f"99 % of the d² stay below:   {p99:15.2f}  {np.percentile(x2, 99):15.2f}")
    print(f"mean of d²:                  {d2.mean():15.2f}  {x2.mean():15.2f}")
    save_results({"chi2": {"inside1_pct": round(shares[1], 2), "p95": round(float(p95), 3),
                           "p99": round(float(p99), 3), "mean": round(float(d2.mean()), 3)}})
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    bins = np.linspace(0, 14, 57)
    ax.hist(d2, bins=bins, density=True, alpha=0.6, label="your d² = x² + y² (2-D)")
    ax.hist(x2, bins=bins, density=True, histtype="step", lw=1.5, label="x² alone (1-D)")
    for k in (1, 2, 3):
        ax.axvline(k * k, color="grey", lw=0.8, ls=":")
        ax.text(k * k + 0.1, ax.get_ylim()[1] * 0.92, f"{k}σ", color="grey", fontsize=8)
    ax.axvline(p95, color="tab:red", lw=1.2, label=f"95 % of your d² below {p95:.2f}")
    ax.set_xlabel("squared distance in sigmas (d²)")
    ax.set_ylabel("density")
    ax.set_xlim(0, 14)
    ax.legend(fontsize=8)
    ax.set_title("How far does an honest error fall? (10 000 draws)", fontsize=10)
    fig.tight_layout()
    fig.savefig("out/chi2.png", dpi=90)
    rk.saved("out/chi2.png")


if __name__ == "__main__":
    main()

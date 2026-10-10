#!/usr/bin/env python3
"""bootstrap.py — how sure is a number computed from a few dozen errors?

    python3 bootstrap.py              # a small demo on 12 errors
    python3 bootstrap.py --coverage   # the coverage experiment -> coverage.json (about 1 minute)

Functions (used by measure.py too):
    bootstrap_ci(values, stat, B, alpha, seed, block)  percentile bootstrap (iid, or moving blocks)
    paired_diff_ci(a, b, stat, B, alpha, seed, block)  CI of stat(a) - stat(b) on PAIRED samples
    wilson(k, n, z)                                    95 % interval of a proportion k/n
    covers(lo, hi, truth)                              does [lo, hi] contain the true value?
    coverage(...)                                      how often a 95 % CI really contains the truth
"""
import json
import math
import sys

import numpy as np


def bootstrap_ci(values, stat=np.median, B=2000, alpha=0.05, seed=29, block=1):
    """Percentile-bootstrap confidence interval (lo, hi) of stat(values).

    block == 1 : ordinary bootstrap. Each of the B resamples is n indices drawn WITH replacement:
                 idx = rng.integers(0, n, size=n)
    block  > 1 : moving-block bootstrap. Each resample is made of k = ceil(n / block) blocks of
                 `block` CONSECUTIVE values; the block starts are rng.integers(0, n - block + 1, size=k);
                 the blocks are joined and cut to n values.
    rng = np.random.default_rng(seed). The interval is the (100*alpha/2, 100*(1-alpha/2))
    percentiles (np.percentile) of the B resampled statistics. Returns (lo, hi) as floats."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n == 0:
        return None
    block = max(1, min(int(block), n))
    # TODO 7a: rng = ...; for each of the B resamples: idx = _resample_idx(rng, n, block), the
    #          statistic stat(x[idx]); then the two percentiles. Return (float(lo), float(hi)).
    return None


def _resample_idx(rng, n, block):
    """The n indices of ONE resample (an integer numpy array). Used by bootstrap_ci and paired_diff_ci."""
    # TODO 7b: block == 1 -> n random indices; block > 1 -> moving blocks (see bootstrap_ci's docstring)
    raise NotImplementedError("TODO 7b")


def paired_diff_ci(a, b, stat=np.median, B=2000, alpha=0.05, seed=29, block=1):
    """CI (lo, hi) of stat(a) - stat(b), where a[i] and b[i] were measured at the SAME instant
    (e.g. NAVERA's error and the baseline's error at second i). Each resample uses the SAME
    indices for a and b (that is what "paired" means). Same resampling rules as bootstrap_ci."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) != len(b) or len(a) == 0:
        return None
    return None   # TODO 8: like bootstrap_ci, but each resample gives stat(a[idx]) - stat(b[idx])


def wilson(k, n, z=1.96):
    """Wilson score interval (lo, hi) of a proportion k/n, as fractions in [0, 1].
    p = k/n;  centre = (p + z^2/(2n)) / (1 + z^2/n);
    half = z / (1 + z^2/n) * sqrt(p(1-p)/n + z^2/(4 n^2))."""
    if n <= 0:
        return None
    return None   # TODO 9: the three lines of the docstring; clip to [0, 1]


def covers(lo, hi, truth):
    """True when the interval [lo, hi] contains the true value."""
    return lo <= truth <= hi


def coverage(trials=200, n=60, rho=0.0, block=1, B=400, seed=1):
    """Coverage experiment: the fraction (0..1) of `trials` simulated flights whose 95 % bootstrap
    CI of the median error contains the TRUE median error.
    Each flight is make_errors(rng, n, rho) (below the line); its CI is
    bootstrap_ci(errors, np.median, B=B, seed=<a different seed per trial>, block=block)."""
    rng = np.random.default_rng(seed)
    # TODO 10: for t in range(trials): e = make_errors(rng, n, rho); its CI with seed=1000 + t and
    #          block=block; count how often covers(lo, hi, TRUE_MEDIAN). Return hits / trials.
    return None


# ---- you don't need to change anything below this line (but you can read it!) ----
SIGMA = 10.0                                         # m per axis
TRUE_MEDIAN = SIGMA * math.sqrt(2 * math.log(2))     # median of a 2-D Gaussian error: 1.1774 sigma


def make_errors(rng, n, rho):
    """n horizontal errors (m) of a simulated 1 Hz source with SIGMA m per axis.
    rho = correlation between one second and the next (AR(1) process, per axis):
    x[t] = rho * x[t-1] + sqrt(1 - rho^2) * w[t]. rho = 0: independent errors."""
    w = rng.normal(0.0, SIGMA, size=(n, 2))
    x = np.empty_like(w)
    x[0] = w[0]
    for t in range(1, n):
        x[t] = rho * x[t - 1] + math.sqrt(1 - rho * rho) * w[t]
    return np.hypot(x[:, 0], x[:, 1])


def demo():
    e = [3.1, 4.0, 2.2, 5.9, 3.7, 4.4, 2.8, 31.0, 3.3, 4.9, 3.0, 6.2]
    print(f"12 errors (m): {e}")
    print(f"  median {float(np.median(e)):.2f} m")
    print(f"  95 % CI of the median (iid bootstrap) : {bootstrap_ci(e, np.median)}")
    print(f"  95 % CI of the mean   (iid bootstrap) : {bootstrap_ci(e, np.mean)}")
    print(f"  Wilson 95 % interval of 32/33         : {wilson(32, 33)}")


def run_coverage():
    print(f"true median error = {TRUE_MEDIAN:.2f} m (2-D Gaussian, {SIGMA:.0f} m per axis)")
    res = {}
    for key, n, rho, block in (("iid_n30", 30, 0.0, 1), ("iid_n60", 60, 0.0, 1),
                               ("corr_n60_iid", 60, 0.9, 1), ("corr_n60_block10", 60, 0.9, 10)):
        cov = coverage(n=n, rho=rho, block=block)
        res[key] = None if cov is None else round(float(cov), 3)
        print(f"  {key:18s} n={n:3d} rho={rho:.1f} block={block:2d} : coverage "
              f"{'—' if cov is None else f'{100 * cov:.1f} %'}  (target 95 %)")
    with open("coverage.json", "w") as f:
        json.dump(res, f, indent=1)
    print("saved coverage.json")


if __name__ == "__main__":
    if "--coverage" in sys.argv:
        run_coverage()
    else:
        demo()

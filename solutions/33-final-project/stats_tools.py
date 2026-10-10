#!/usr/bin/env python3
"""stats_tools.py — the statistics of a before/after measurement.

    python3 stats_tools.py        # a small demo: iid vs block bootstrap on correlated errors

You complete three functions (TODO 1 to TODO 3). They work for ANY project, not only the example:
  percentile(values, q)                                   the q-th percentile, linear interpolation
  bootstrap_ci(values, stat, n_boot, alpha, seed)         percentile bootstrap, independent samples
  block_bootstrap_ci(n, metric, block_len, n_boot, alpha, seed)
                                                          moving-block bootstrap, time series
Below the line: write_results(), which writes results.json in the format the check reads.
"""
import json
import math

import numpy as np


def percentile(values, q):
    """The q-th percentile (0 <= q <= 100) of `values`, with LINEAR INTERPOLATION:

        sort the n values: x[0] <= ... <= x[n-1];  h = (n - 1) * q / 100
        result = x[floor(h)] + (h - floor(h)) * (x[floor(h) + 1] - x[floor(h)])

    (the same definition as numpy's default np.percentile). Empty input -> nan."""
    x = sorted(float(v) for v in values)
    n = len(x)
    if n == 0:
        return math.nan
    h = (n - 1) * q / 100.0
    lo = int(math.floor(h))
    if lo >= n - 1:
        return x[-1]
    return x[lo] + (h - lo) * (x[lo + 1] - x[lo])


def bootstrap_ci(values, stat, n_boot=2000, alpha=0.05, seed=0):
    """Percentile bootstrap confidence interval of stat(values), for INDEPENDENT samples.

    rng = np.random.default_rng(seed); for b in 1..n_boot: draw n indices uniformly WITH
    replacement (rng.integers(0, n, size=n)), compute stat on that resample. The interval is the
    (alpha/2, 1 - alpha/2) percentiles of the n_boot statistics. Returns (lo, hi) as floats."""
    v = np.asarray(values, dtype=float)
    n = len(v)
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        stats[b] = stat(v[rng.integers(0, n, size=n)])
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def block_indices(n, block_len, rng):
    """One moving-block resample of the indices 0..n-1: ceil(n / block_len) blocks of
    block_len CONSECUTIVE indices, each starting at rng.integers(0, n - block_len + 1),
    concatenated and cut to length n."""
    k = math.ceil(n / block_len)
    starts = rng.integers(0, n - block_len + 1, size=k)
    return (starts[:, None] + np.arange(block_len)[None, :]).ravel()[:n]


def block_bootstrap_ci(n, metric, block_len=60, n_boot=2000, alpha=0.05, seed=0):
    """Moving-block bootstrap CI for a metric of a TIME SERIES of n epochs.

    metric(idx) receives an integer numpy array of n epoch indices (a resample) and returns a
    float. For b in 1..n_boot: idx = block_indices(n, block_len, rng); value = metric(idx).
    nan values are ignored. Returns (lo, hi): the (alpha/2, 1 - alpha/2) percentiles.
    With block_len = 1 it is the ordinary (iid) bootstrap."""
    rng = np.random.default_rng(seed)
    vals = np.empty(n_boot)
    for b in range(n_boot):
        vals[b] = metric(block_indices(n, block_len, rng))
    vals = vals[np.isfinite(vals)]
    lo, hi = np.percentile(vals, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


# ---- you don't need to change anything below this line ----

def write_results(path, *, project, metric, unit, better, data, n, before, after, difference,
                  bootstrap, acceptance, decision, secondary=None, target=None):
    """Write results.json in the format the check reads.

    before / after / difference: {"value": float, "ci95": [lo, hi]}
    better: "lower" or "higher" (which direction of the metric is an improvement), or
            "closer" for a CALIBRATION metric that has a right value (e.g. "2-sigma coverage
            should be 86 %"): then give target=86.0, and before / after / difference must be the
            DISTANCE to the target, |value - target|, each with its own bootstrap CI (compute
            abs(stat - target) inside the resample). It is saved as better="lower" plus the target.
    bootstrap: {"method": "moving-block" or "iid", "block_len": int, "n_boot": int, "seed": int}
    decision: "accept", "reject" or "inconclusive"  (from the acceptance criterion, fixed BEFORE)
    secondary: optional dict of other metrics (same {"before","after","difference"} shape). A
               GUARD-RAIL also gets "limit" (the worst acceptable value of its difference) and
               "better" ("lower"/"higher"); the check then applies it to the decision."""
    if better == "closer":
        if target is None:
            raise ValueError('better="closer" needs target=<the right value of the metric>')
        better = "lower"
    elif better not in ("lower", "higher"):
        raise ValueError(f'better must be "lower", "higher" or "closer", not {better!r}')
    elif target is not None:
        raise ValueError('target=... only makes sense with better="closer"')

    def clean(d):
        return {"value": round(float(d["value"]), 4), "ci95": [round(float(x), 4) for x in d["ci95"]]}
    out = {"project": project, "metric": metric, "unit": unit, "better": better, "data": data,
           "n": int(n), "before": clean(before), "after": clean(after), "difference": clean(difference),
           "bootstrap": bootstrap, "acceptance": acceptance, "decision": decision}
    if target is not None:
        out["target"] = float(target)
        out["metric"] = f"|{metric} - {float(target):g}| (distance to the target)"
    if secondary:
        out["secondary"] = {k: {kk: (clean(vv) if isinstance(vv, dict) else vv) for kk, vv in v.items()}
                            for k, v in secondary.items()}
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    return out


def _ar1(n, rho, seed):
    rng = np.random.default_rng(seed)
    e = np.empty(n)
    e[0] = rng.normal()
    for k in range(1, n):
        e[k] = rho * e[k - 1] + math.sqrt(1 - rho ** 2) * rng.normal()
    return e


if __name__ == "__main__":
    x = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
    print("percentile(x, 50) =", percentile(x, 50), "  numpy says", float(np.percentile(x, 50)))
    print("percentile(x, 95) =", percentile(x, 95), "  numpy says", float(np.percentile(x, 95)))
    e = _ar1(1800, 0.9, seed=1)                # a correlated error series, true mean 0, sigma 1
    if bootstrap_ci(e, np.mean, n_boot=500) is None:
        print("bootstrap_ci() returns None — complete TODO 2")
    else:
        lo, hi = bootstrap_ci(e, np.mean, n_boot=500, seed=1)
        print(f"mean = {e.mean():+.3f}; iid bootstrap 95 % CI   [{lo:+.3f}, {hi:+.3f}]  width {hi - lo:.3f}")
        r = block_bootstrap_ci(len(e), lambda idx: float(np.mean(e[idx])), block_len=60, n_boot=500, seed=1)
        if r is None:
            print("block_bootstrap_ci() returns None — complete TODO 3")
        else:
            lo, hi = r
            print(f"                block bootstrap 95 % CI [{lo:+.3f}, {hi:+.3f}]  width {hi - lo:.3f}")
            print("theory for rho = 0.9: the honest width is about sqrt((1+rho)/(1-rho)) = 4.4 x the iid width")

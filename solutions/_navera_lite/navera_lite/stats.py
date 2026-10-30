"""navera_lite/stats.py — measuring a navigation source honestly: errors, percentiles, availability, gaps,
bootstrap and Wilson confidence intervals, and the coverage experiment that tests them. Part of NAVERA Lite,
the course's teaching stack (mission 32; mission 33 reuses it). Written for the course; it is not NAVERA code.

A flight table is a pandas DataFrame with one row per output instant (one every DT_S seconds) and at least:
    t_s                   time (s)
    state                 the judge's state: "FIX", "DEGRADED", "NO_FIX" or "STARTING"
    lat, lon              the position the judge gave (degrees; empty = no position)
    truth_lat, truth_lon  where the vehicle really was at t_s (degrees)

Percentiles follow the course rule (CONVENTIONS.md §6): linear interpolation, like numpy's default.
pct_nearest() is the "nearest sample" rule, given here so that the two can be compared.
"""
import math

import numpy as np

from navera_lite.logbook import haversine_m, outage_runs

# @part 32
DT_S = 1.0                                   # one row per second in the course's flight tables
# @part 32
USABLE = ("FIX", "DEGRADED")                 # states in which the judge gives a position the autopilot may use
# @part 32
RAYLEIGH_MEDIAN = math.sqrt(2.0 * math.log(2.0))   # median radial error of a round 2-D Gaussian, in σ (1.1774)


# @part 32 todo 1
def errors_m(df):
    """The horizontal error (m) of every row that has a position: the distance between the position the
    judge gave (lat, lon) and the truth (truth_lat, truth_lon), with logbook.haversine_m. Rows without a
    position (lat or lon empty, NaN) or without a truth are left out. The order of the rows is kept.

    df: a flight table (see the top of this file). Returns a 1-D numpy array of floats (metres).
    Example: rows (lat 35.8000, truth 35.8000), (lat NaN), (lat 35.8001, truth 35.8000), same lon 10.6
             → array([0.0, 11.12])   (0.0001° of latitude is 11.12 m; the NaN row is left out)
    """
    est = df[["lat", "lon", "truth_lat", "truth_lon"]].to_numpy(dtype=float)
    keep = np.all(np.isfinite(est), axis=1)
    e = est[keep]
    return np.asarray(haversine_m(e[:, 2], e[:, 3], e[:, 0], e[:, 1]), dtype=float)


# @part 32 todo 2
def percentile(v, q):
    """The q-th percentile of the values v with the course rule, linear interpolation (lesson 32 §2): the
    same number as np.percentile(v, q) — written by you, so that you know what it does.

    v: a non-empty sequence of numbers (any order); q: 0 to 100. Returns a float.
    Raises ValueError("percentile of an empty sequence") when v is empty.
    Example: percentile([7, 1, 3, 5], 50) → 4.0;   percentile([7, 1, 3, 5], 90) → 6.4
    """
    s = sorted(float(x) for x in v)
    if not s:
        raise ValueError("percentile of an empty sequence")
    pos = (len(s) - 1) * q / 100.0
    i = int(math.floor(pos))
    if i >= len(s) - 1:
        return s[-1]
    return s[i] + (pos - i) * (s[i + 1] - s[i])


# @part 32
def pct_nearest(v, q):
    """The q-th percentile with the NEAREST-SAMPLE rule (lesson 32 §2): the sorted value at index
    round(q / 100 × (n − 1)), with Python's round() (halves go to the even integer). No interpolation:
    the answer is always one of the values. NAVERA's evaluation tool uses this rule (lesson 32, in words);
    NAVERA Lite gives it only to compare it with percentile().

    Example: pct_nearest([7, 1, 3, 5], 50) → 5.0;  pct_nearest([7, 1, 3, 5], 90) → 7.0
    """
    s = sorted(float(x) for x in v)
    if not s:
        raise ValueError("percentile of an empty sequence")
    return s[min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1))))]


# @part 32 todo 3
def summary(errs):
    """The error statistics of a list of errors (m), as a dict of plain Python numbers:
      n       how many errors (an int)
      mean    the mean
      median  the 50th percentile (CEP50 for radial errors)
      p90     the 90th percentile
      p95     the 95th percentile (CEP95)
      max     the largest error
      rmse    the root mean square: the square root of the mean of the squared errors
    Percentiles with YOUR percentile() (TODO 2). With no error at all: {"n": 0} and every other key None.

    Example: summary([2, 4, 4, 10]) → {"n": 4, "mean": 5.0, "median": 4.0, "p90": 8.2, "p95": 9.1,
                                       "max": 10.0, "rmse": 5.831}
    """
    e = [float(x) for x in errs]
    if not e:
        return {"n": 0, "mean": None, "median": None, "p90": None, "p95": None, "max": None, "rmse": None}
    return {"n": len(e), "mean": sum(e) / len(e), "median": percentile(e, 50), "p90": percentile(e, 90),
            "p95": percentile(e, 95), "max": max(e), "rmse": math.sqrt(sum(x * x for x in e) / len(e))}


# @part 32
def usable_mask(df, ok=USABLE):
    """A boolean numpy array: True for the rows whose state is in ok AND that carry a position (lat, lon
    finite). The autopilot can use those rows; it cannot use the others.

    Example: states FIX (with a position), NO_FIX, DEGRADED (lat NaN) → array([True, False, False])
    """
    has = np.isfinite(df["lat"].to_numpy(dtype=float)) & np.isfinite(df["lon"].to_numpy(dtype=float))
    return np.asarray(df["state"].isin(list(ok)).to_numpy() & has, dtype=bool)


# @part 32 todo 4
def availability(df, ok=USABLE):
    """The share of the rows (0 to 1) in which the autopilot gets a usable position: a state in ok AND a
    position (usable_mask() says it row by row). An empty table gives nan.

    df: a flight table. Returns a float.
    Example: states FIX, FIX, NO_FIX, DEGRADED (all with a position except the NO_FIX row) → 0.75
    """
    m = usable_mask(df, ok)
    return float(m.mean()) if m.size else float("nan")


# @part 32 todo 5
def longest_gap_s(df, dt_s=DT_S, ok=USABLE):
    """Continuity: the longest stretch of time without a usable position, in seconds. A stretch of
    unusable rows i0 … i1 − 1 lasts  t_s[i1 − 1] − t_s[i0] + dt_s  (one lost row lasts one period, as
    in mission 04's outage table). 0.0 when every row is usable.

    df: a flight table sorted by t_s; dt_s: the period of the rows (s). Returns a float (s).
    Example: t_s 0, 1, 2, 3, 4, 5 with usable rows yes, no, no, yes, no, yes → 2.0
    """
    t = df["t_s"].to_numpy(dtype=float)
    runs = outage_runs(usable_mask(df, ok).astype(int))
    return float(max((t[b - 1] - t[a] + dt_s for a, b in runs), default=0.0))


# @part 32 todo 6
def bootstrap_ci(x, stat, B=2000, alpha=0.05, seed=None, block=1):
    """A (1 − alpha) percentile-bootstrap confidence interval of stat(x) (lesson 32 §5): B resamples of x,
    each the same length as x, drawn WITH replacement; stat of each; the alpha/2 and 1 − alpha/2
    percentiles (linear rule) of those B values.
    block = 1: the values are drawn one by one (iid bootstrap).
    block = L > 1: moving-block bootstrap (lesson 32 §6): the resample is made of runs of L CONSECUTIVE
    values of x; a run may start at any index from 0 to len(x) − L (runs never wrap around the end);
    enough runs are joined to reach len(x) values, and the extra values at the end are cut off.
    seed: the seed of np.random.default_rng(seed); the same seed must give the same interval.

    x: a sequence of numbers; stat: a function of a numpy array that returns a number (np.median, …).
    Returns (lo, hi), two floats. Raises ValueError if block is not between 1 and len(x).
    Example: bootstrap_ci([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], np.mean, seed=0) → about (3.7, 7.3)   (width > 0);
             bootstrap_ci([4.0] * 20, np.median) → (4.0, 4.0)   (every resample is the same);
             bootstrap_ci(list(range(60)), np.median, block=60) → (29.5, 29.5)   (only one run fits)
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if not 1 <= block <= n:
        raise ValueError(f"block must be between 1 and len(x) = {n}, got {block}")
    rng = np.random.default_rng(seed)
    reps = np.empty(B)
    k = -(-n // block)
    for i in range(B):
        if block == 1:
            idx = rng.integers(0, n, size=n)
        else:
            starts = rng.integers(0, n - block + 1, size=k)
            idx = (starts[:, None] + np.arange(block)).ravel()[:n]
        reps[i] = stat(x[idx])
    lo, hi = np.percentile(reps, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


# @part 32 todo 7
def paired_diff_ci(a, b, stat, B=2000, alpha=0.05, seed=None, block=1):
    """A (1 − alpha) bootstrap confidence interval of the DIFFERENCE stat(a) − stat(b), for two methods
    measured at the same instants (lesson 32 §6): a[i] and b[i] belong together, so every resample uses
    the SAME indices for a and for b. Resampling (block, seed) as in bootstrap_ci().

    a, b: sequences of the same length (else ValueError). Returns (lo, hi), two floats.
    Example: b = [3, 9, 4, 12, 7], a = b + 5 everywhere → paired_diff_ci(a, b, np.mean) → (5.0, 5.0)
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n = len(a)
    if len(b) != n:
        raise ValueError(f"a and b must have the same length, got {n} and {len(b)}")
    if not 1 <= block <= n:
        raise ValueError(f"block must be between 1 and len(a) = {n}, got {block}")
    rng = np.random.default_rng(seed)
    reps = np.empty(B)
    k = -(-n // block)
    for i in range(B):
        if block == 1:
            idx = rng.integers(0, n, size=n)
        else:
            starts = rng.integers(0, n - block + 1, size=k)
            idx = (starts[:, None] + np.arange(block)).ravel()[:n]
        reps[i] = stat(a[idx]) - stat(b[idx])
    lo, hi = np.percentile(reps, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


# @part 32 todo 8
def wilson(k, n, z=1.96):
    """The Wilson score interval (lesson 32 §7) for a success rate: k successes in n trials, z = 1.96 for
    95 %. Always inside [0, 1], also for k = 0 or k = n.

    k, n: integers, 0 ≤ k ≤ n, n ≥ 1 (else ValueError). Returns (lo, hi), two floats (shares, 0 to 1).
    Example: wilson(8, 10) → (0.490, 0.943)   (to 3 decimals)
    """
    if n < 1 or not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n and n >= 1, got k = {k}, n = {n}")
    p = k / n
    z2 = z * z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z / (1 + z2 / n) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


# @part 32
def wald(k, n, z=1.96):
    """The naive interval for a success rate, p ± z·sqrt(p(1 − p)/n), NOT clipped to [0, 1] — given only to
    compare it with wilson() (lesson 32 §7). Returns (lo, hi).

    Example: wald(8, 10) → (0.552, 1.048)   (an upper end above 100 %: impossible)
    """
    p = k / n
    half = z * math.sqrt(p * (1 - p) / n)
    return p - half, p + half


# @part 32 todo 9
def coverage_experiment(make_sample, ci_of, true_value, trials=200, seed=0):
    """Does a "95 %" interval really contain the truth 95 % of the time? (lesson 32 §8). Repeat `trials`
    imaginary experiments whose true answer is known: each one draws a new sample, computes its interval,
    and counts a hit when lo ≤ true_value ≤ hi. Returns the share of hits (0 to 1).

    make_sample(rng) → one sample (the data of one experiment); ci_of(sample, rng) → (lo, hi).
    Both receive the SAME generator rng = np.random.default_rng(seed), made once before the first trial,
    so the whole experiment is reproducible.
    Example: make_sample = lambda rng: rng.normal(0.0, 1.0, size=5),
             ci_of = lambda s, rng: (s.min(), s.max()), true_value 0.0, trials 1000 → about 0.94
             (the truth 0 lies between the smallest and the largest of 5 values unless all 5 are on one side)
    """
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(trials):
        sample = make_sample(rng)
        lo, hi = ci_of(sample, rng)
        if lo <= true_value <= hi:
            hits += 1
    return hits / trials


# @part 32
def ar1_radial(rng, n, rho, sigma_m):
    """n radial errors (m) of a source whose east and north errors are each an AR(1) process: every second
    keeps the fraction rho of the previous error plus fresh noise, with the stationary σ sigma_m per axis
    (lesson 32 §6). rho = 0 gives independent errors. Their true median is RAYLEIGH_MEDIAN × sigma_m.

    rng: np.random.default_rng(…); returns a numpy array of n floats.
    Example: ar1_radial(np.random.default_rng(0), 4, 0.9, 10.0) → 4 errors that change slowly
    """
    k = math.sqrt(1.0 - rho * rho)
    e = np.empty((n, 2))
    e[0] = rng.normal(0.0, sigma_m, 2)
    for i in range(1, n):
        e[i] = rho * e[i - 1] + k * rng.normal(0.0, sigma_m, 2)
    return np.hypot(e[:, 0], e[:, 1])

import contextlib
import io
import json
import math
import os
import re

import numpy as np
import pandas as pd

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run

c = Checker()

# Unseen inputs and the course reference's answers: courses/32-measuring/hidden/cases.json, written by
# solutions/32-measuring/make_hidden.py (check.py never runs the reference).
CASES = json.loads(hidden("cases.json"))
FLIGHTS = ("target", "retrieval", "selective")


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def todo(mod_name, fname, k, where="navera_lite/stats.py"):
    m = quiet(mod_name)
    (f,) = need(m, fname)
    if is_stub(f):
        raise CheckFailed(f"{fname}() is not written yet (TODO {k} in {where})")
    return m, f


TIPS = [("'NoneType'", " — one of your functions returned None: is every TODO it uses written, and does every path "
                       "end with a return?"),
        ("KeyError", " — a column name misspelt? The flight tables use lat, lon, truth_lat, truth_lon, state, t_s, gps, "
                     "source"),
        ("integers", " — check the range you give rng.integers(low, high): high is EXCLUDED, and it must be > low"),
        ("could not be broadcast", " — two arrays of different lengths were combined: print their len()")]


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def table(d):
    return pd.DataFrame({k: [np.nan if v is None else v for v in col] for k, col in d.items()})


def as_array(v, what):
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} must be numbers (a numpy array), got {type(v).__name__}")
    if a.ndim != 1:
        raise CheckFailed(f"{what} must be a 1-D array, its shape is {a.shape}")
    return a


def pair(v, what):
    try:
        lo, hi = float(v[0]), float(v[1])
        ok = len(v) == 2
    except (TypeError, ValueError, IndexError, KeyError):
        ok = False
    if not ok:
        raise CheckFailed(f"{what} must be a pair (lo, hi) of numbers, got {v!r:.80}")
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise CheckFailed(f"{what} = ({lo}, {hi}): not usable numbers")
    if lo > hi:
        raise CheckFailed(f"{what} = ({lo:.4g}, {hi:.4g}): the lower end is above the upper end")
    return lo, hi


def raise_value_error(call, what, rule):
    """The student's function must refuse an impossible input with ValueError."""
    try:
        call()
    except CheckFailed as e:
        if "ValueError" in str(e):
            return
        raise CheckFailed(f"{what} must raise ValueError ({rule}); it stopped with: {e}")
    raise CheckFailed(f"{what} must raise ValueError ({rule}), it returned a value")


# ================================================================ Session 1 — the numbers
@c.test("TODO 1 — errors_m() on an unseen table (far north, three kinds of empty cells)",
        hint="One error per row that has a position AND a truth (NaN in lat, lon, truth_lat or truth_lon: left out); "
             "the distance with logbook.haversine_m, truth vs position; return a numpy array.")
def _():
    m, f = todo("navera_lite.stats", "errors_m", 1)
    d = CASES["errors"]
    got = as_array(go(f, table(d["table"])), "errors_m()")
    want = d["want"]
    if np.any(~np.isfinite(got)):
        raise CheckFailed("errors_m() returned NaN values: rows without a position (or without a truth) must be "
                          "LEFT OUT")
    c.ok(len(got) == len(want), f"errors_m() gave {len(got)} errors for this 9-row table, but only {len(want)} rows "
                                "have both a position and a truth (NaN in lat, lon, truth_lat or truth_lon: leave the "
                                "row out)")
    for i, (g, w) in enumerate(zip(got, want)):
        if abs(g - w) > max(0.05, 1e-4 * w):
            hint = (" — an east offset comes out wrong: a flat formula without cos(latitude) overestimates east "
                    "distances at 64° N; use haversine_m") if i in (1, 4) else ""
            raise CheckFailed(f"error number {i + 1} is {g:.3f} m: not right (it must be within 0.05 m){hint}")


@c.test("TODO 2 — percentile(): the linear rule on 40 unseen cases (q from 0 to 100, n from 1 to 23)",
        hint="Sort; the position is (n − 1) × q / 100; interpolate between the two values on either side of it. "
             "Compare with np.percentile in a terminal.")
def _():
    m, f = todo("navera_lite.stats", "percentile", 2)
    for case in CASES["percentile"]:
        got = go(f, list(case["v"]), case["q"])
        try:
            g = float(got)
        except (TypeError, ValueError):
            raise CheckFailed(f"percentile() must return a number, got {got!r}")
        if abs(g - case["want"]) > 1e-6 * max(1, abs(case["want"])):
            v = case["v"]
            shown = v if len(v) <= 11 else f"{len(v)} values"
            near = sorted(v)[min(len(v) - 1, int(round(case["q"] / 100 * (len(v) - 1))))]
            tip = (" — you returned the nearest sample: interpolate between the two neighbours (lesson §2)"
                   if abs(g - near) < 1e-9 else " — did you sort the values first? Is the position (n − 1)·q/100?")
            raise CheckFailed(f"percentile({shown}, {case['q']}) = {g:.6g}: not right{tip}")
    raise_value_error(lambda: go(f, [], 50), "percentile([], 50)", "an empty sequence has no percentile")


@c.test("TODO 3 — summary() on unseen errors (an outlier, one value, none)",
        hint="Seven keys n, mean, median, p90, p95, max, rmse; percentiles with YOUR percentile(); "
             "rmse = sqrt(mean of the squares); for an empty list {'n': 0} and None for the others.")
def _():
    m, f = todo("navera_lite.stats", "summary", 3)
    for case in CASES["summary"]:
        s = go(f, list(case["v"]))
        c.ok(isinstance(s, dict), f"summary() must return a dict, got {type(s).__name__}")
        for k, w in case["want"].items():
            c.ok(k in s, f"summary() has no key {k!r} (keys: n, mean, median, p90, p95, max, rmse)")
            if k == "n":
                c.eq(s[k], w, f"summary({len(case['v'])} errors)['n']")
            else:
                hint = (" — rmse is the square root of the MEAN of the squares (not the sum, not the std)"
                        if k == "rmse" else "")
                if s[k] is None or abs(float(s[k]) - w) > 1e-3 * max(1, abs(w)):
                    raise CheckFailed(f"summary(...)['{k}'] = {s[k]!r} for {len(case['v'])} errors: not right{hint}")
    s = go(f, [])
    c.ok(isinstance(s, dict) and s.get("n") == 0 and all(s.get(k) is None for k in ("mean", "median", "max", "rmse")),
         f"summary([]) must be n 0 and None for the other keys, got {s!r:.120}")


@c.test("TODO 4–5 — availability() and longest_gap_s() on an unseen 0.5 s table",
        hint="A usable row: a state in ok AND a position (usable_mask() does both). A gap of rows i0..i1−1 lasts "
             "t_s[i1−1] − t_s[i0] + dt_s; mission 04's outage_runs() finds the runs, also one that lasts to the end.")
def _():
    m, fa = todo("navera_lite.stats", "availability", 4)
    _, fg = todo("navera_lite.stats", "longest_gap_s", 5)
    d = CASES["avail"]
    t = table(d["table"])
    c.near(go(fa, t), d["availability"], 1e-6, "availability (5 usable rows of 13: a DEGRADED row without a position "
                                               "is not usable)")
    c.near(go(fa, t, ok=("FIX",)), d["availability_fix_only"], 1e-6, "availability(…, ok=('FIX',))")
    g = go(fg, t, dt_s=0.5)
    if isinstance(g, (int, float)) and abs(g - 1.5) < 1e-9:
        raise CheckFailed("longest_gap_s(…, dt_s=0.5) = 1.5: the longest gap is the one that lasts until the END of "
                          "the table (4 rows, 2.0 s) — is a run at the end closed?")
    c.near(g, d["gap"], 1e-6, "longest_gap_s(…, dt_s=0.5) (use dt_s, not 1)")
    c.near(go(fg, t.iloc[:6], dt_s=0.5), d["gap_first5"], 1e-6, "longest_gap_s of the first 6 rows")


@c.test("TODO A — last_fix_baseline() on an unseen flight (London; a vision row just before the jam)",
        hint="The frozen position is the judge's last position whose source is 'gps' BEFORE the first jammed row "
             "(not the truth, not the last row); one error per jammed row: haversine_m(truth, frozen).")
def _():
    m, f = todo("baseline", "last_fix_baseline", "A", where="baseline.py")
    d = CASES["baseline"]
    got = as_array(go(f, table(d["table"])), "last_fix_baseline()")
    want = d["want"]
    c.ok(len(got) == len(want), f"last_fix_baseline() gave {len(got)} values: one per jammed row ({len(want)} here)")
    if all(abs(g - w) <= 0.05 for g, w in zip(got, want)):
        return
    if abs(got[0] - 40.0) < 0.5:
        raise CheckFailed("the first baseline error is 40.0 m: you froze the TRUE position; the baseline repeats the "
                          "position the judge GAVE (lat, lon of the last row whose source is gps)")
    if abs(got[0] - 80.2) < 1.0:
        raise CheckFailed("the first baseline error is about 80 m: you froze the last row before the jam, which is a "
                          "day-vision position; the baseline is the last position whose source is 'gps'")
    raise CheckFailed(f"the baseline errors start {got[0]:.1f}, {got[1]:.1f} m: not right — the frozen position is the "
                      "judge's last 'gps' position before the FIRST jammed row; one error per jammed row")


def results(part):
    if not os.path.exists("results.json"):
        raise CheckFailed("results.json does not exist yet: run python3 measure_lab.py flights")
    try:
        r = json.load(open("results.json"))
    except json.JSONDecodeError:
        raise CheckFailed("results.json is not valid JSON: run measure_lab.py again")
    if part not in r:
        cmd = {"flights": "flights", "ci": "ci"}[part]
        raise CheckFailed(f"results.json has no '{part}' part yet: run python3 measure_lab.py {cmd}")
    return r[part]


@c.test("Step 3 — results.json: the three flights (errors, baseline, availability, gaps)",
        hint="Run python3 measure_lab.py flights after TODO 1–5 and TODO A.")
def _():
    fl = results("flights")
    for name in FLIGHTS:
        got, want = fl.get(name) or {}, CASES["flights"][name]
        for part in ("all", "jam", "baseline"):
            g, w = got.get(part) or {}, want[part]
            c.ok(g.get("n") == w["n"], f"{name} {part}: n = {g.get('n')}, not right — run measure_lab.py flights again "
                                       "after fixing TODO 1 / A")
            for k in ("median", "p90", "rmse", "max"):
                if g.get(k) is None or abs(float(g[k]) - w[k]) > max(0.05, 1e-3 * w[k]):
                    raise CheckFailed(f"{name} {part} {k} = {g.get(k)!r}: not right — run measure_lab.py flights again")
        for k in ("availability", "availability_jam"):
            c.near(got.get(k), want[k], 1e-3, f"{name} {k}")
        for k in ("longest_gap_s", "longest_gap_jam_s"):
            c.near(got.get(k), want[k], 1e-6, f"{name} {k}")


@c.test("Steps 0–4 — answers.py: your numbers and explanations",
        hint="PREDICT_BEAT before Step 3; the numbers come from measure_lab.py flights; EXPLAIN_SELECTIVE: the "
             "seconds it chose and the availability; EXPLAIN_MAX: the old position over the lake; EXPLAIN_RULE: "
             "interpolation vs a sample.")
def _():
    a = quiet("answers.py")
    v = need(a, "PREDICT_BEAT", "RETR_JAM_MEDIAN_M", "BASE_JAM_MEDIAN_M", "TARGET_LONGEST_GAP_S", "EXPLAIN_MAX",
             "SELECTIVE_JAM_MEDIAN_M", "SELECTIVE_JAM_AVAIL_PCT", "EXPLAIN_SELECTIVE", "EXPLAIN_RULE")
    predicted("PREDICT_BEAT", v[0])
    F = CASES["flights"]
    for name, got, want, tol in (("RETR_JAM_MEDIAN_M", v[1], F["retrieval"]["jam"]["median"], 1.0),
                                 ("BASE_JAM_MEDIAN_M", v[2], F["retrieval"]["baseline"]["median"], 1.0),
                                 ("TARGET_LONGEST_GAP_S", v[3], F["target"]["longest_gap_s"], 0.01),
                                 ("SELECTIVE_JAM_MEDIAN_M", v[5], F["selective"]["jam"]["median"], 1.0),
                                 ("SELECTIVE_JAM_AVAIL_PCT", v[6], 100 * F["selective"]["availability_jam"], 0.6)):
        if isinstance(got, (int, float)) and got == -1:
            raise CheckFailed(f"{name} is still -1: copy the number from measure_lab.py flights")
        c.near(got, want, tol, name)
    explained("EXPLAIN_MAX", v[4], ([r"stale", r"\bold", r"age", r"5 ?s", r"timeout", r"last (stored )?fix", r"kept"],
                                    "that the judge kept giving an OLD position"),
              ([r"lake", r"no match", r"gap", r"missed", r"no (vision|new) fix", r"water"], "why there was no new fix"))
    explained("EXPLAIN_SELECTIVE", v[7], ([r"availab", r"3[12] ?%", r"19", r"gap", r"no position", r"missing"],
                                          "what it costs (availability, gaps)"),
              ([r"withh", r"remov", r"chose", r"only", r"condition", r"easy", r"delet", r"select", r"good (ones|seconds)"],
               "why its median looks better"))
    explained("EXPLAIN_RULE", v[8], ([r"interpol", r"between", r"halfway"], "what the linear rule does"),
              ([r"sample", r"one of the", r"nearest", r"exact", r"position 25", r"index"],
               "why the median is the same (it falls on a sample)"))


# ================================================================ Session 2 — error bars
def stats_np(m):
    """numpy as the student's module sees it (its functions run in the student's process)."""
    return m.np


@c.test("TODO 6 — bootstrap_ci(): an iid percentile bootstrap that behaves like one",
        hint="B resamples of len(x) values drawn with replacement (rng = np.random.default_rng(seed)); stat of each; "
             "the alpha/2 and 1 − alpha/2 percentiles of the B results. Same seed → same interval.")
def _():
    m, f = todo("navera_lite.stats", "bootstrap_ci", 6)
    npx = stats_np(m)
    lo, hi = pair(go(f, [7.5] * 15, npx.median), "bootstrap_ci(15 × 7.5, median)")
    c.ok(lo == hi == 7.5, f"constant data must give (7.5, 7.5), got ({lo}, {hi})")
    x = np.random.default_rng(3271).normal(10.0, 3.0, 400)
    se = x.std() / math.sqrt(len(x))
    lo, hi = pair(go(f, x, npx.mean, B=2000, seed=5, seconds=60), "bootstrap_ci(400 values, mean)")
    for end, got, want in (("lower", lo, x.mean() - 1.96 * se), ("upper", hi, x.mean() + 1.96 * se)):
        if abs(got - want) > 0.07:
            width = hi - lo
            tip = (f" — your interval is {width:.3f} wide, about {width / (2 * 1.96 * se):.1f}× the right width: "
                   "resample len(x) values each time, with replacement, and take the 2.5 and 97.5 percentiles")
            raise CheckFailed(f"the {end} end of the 95 % interval of the mean of 400 values is {got:.3f}: not right{tip}")
    n_len = pair(go(f, x[:37], len, B=50, seed=1), "bootstrap_ci(37 values, len)")
    c.ok(n_len == (37.0, 37.0), f"every resample must have len(x) values: stat = len gave {n_len}, not (37, 37)")
    a1 = pair(go(f, x[:50], npx.median, B=500, seed=9), "seed 9")
    a2 = pair(go(f, x[:50], npx.median, B=500, seed=9), "seed 9 again")
    a3 = pair(go(f, x[:50], npx.median, B=500, seed=10), "seed 10")
    c.ok(a1 == a2, f"the same seed must give the same interval: {a1} then {a2} — make the generator from seed, inside "
                   "the function")
    c.ok(a1 != a3, "seeds 9 and 10 gave exactly the same interval: is the seed used?")
    n90 = pair(go(f, x, npx.mean, B=2000, seed=5, alpha=0.10, seconds=60), "alpha 0.10")
    c.ok(n90[1] - n90[0] < 0.9 * (hi - lo), "alpha = 0.10 (a 90 % interval) must be narrower than the 95 % one: use "
                                            "alpha/2 and 1 − alpha/2")


@c.test("TODO 6 — bootstrap_ci(block=L): moving blocks that never wrap, cut to len(x)",
        hint="Runs of L consecutive values starting anywhere from 0 to len(x) − L; join enough runs, cut to len(x). "
             "block=len(x) leaves one possible run: the data itself. ValueError outside 1 … len(x).")
def _():
    m, f = todo("navera_lite.stats", "bootstrap_ci", 6)
    npx = stats_np(m)
    ramp = list(range(40))
    first = pair(go(f, ramp, lambda v: v[0], B=60, seed=3, block=40), "bootstrap_ci(0..39, first value, block=40)")
    c.ok(first == (0.0, 0.0), f"block = len(x): the only run starts at 0, so the first value is always 0; got {first} "
                              "— do your runs wrap around the end, or start beyond len(x) − L?")
    c.ok(pair(go(f, ramp[:37], len, B=40, seed=3, block=10), "block 10, stat len") == (37.0, 37.0),
         "with blocks of 10 on 37 values the resample must still have 37 values: cut the joined runs to len(x)")
    for bad in (0, 41):
        raise_value_error(lambda: go(f, ramp, npx.median, block=bad), f"bootstrap_ci(…, block={bad})",
                          "block must be 1 … len(x)")
    e = np.empty(300)
    g = np.random.default_rng(3272)
    e[0] = 0.0
    for i in range(1, 300):
        e[i] = 0.95 * e[i - 1] + g.normal()
    iid = pair(go(f, e, npx.mean, B=1000, seed=4, seconds=60), "iid on correlated data")
    blk = pair(go(f, e, npx.mean, B=1000, seed=4, block=30, seconds=60), "block 30 on correlated data")
    c.ok(blk[1] - blk[0] > 2.0 * (iid[1] - iid[0]),
         f"on strongly correlated data the block interval must be much wider than the iid one: "
         f"{blk[1] - blk[0]:.2f} vs {iid[1] - iid[0]:.2f} — are your runs made of CONSECUTIVE values?")


@c.test("TODO 7 — paired_diff_ci(): the SAME indices for a and b",
        hint="Each resample picks one set of indices and uses it for a AND b: stat(a[idx]) − stat(b[idx]). "
             "Different lengths: ValueError.")
def _():
    m, f = todo("navera_lite.stats", "paired_diff_ci", 7)
    npx = stats_np(m)
    g = np.random.default_rng(3273)
    b = g.normal(300.0, 100.0, 50)
    for shift in (5.0, -3.0):
        lo, hi = pair(go(f, b + shift, b, npx.mean, B=300, seed=2), f"paired_diff_ci(b {shift:+g}, b)")
        if abs(lo - shift) > 1e-6 or abs(hi - shift) > 1e-6:
            tip = (" — the sign: the difference is stat(a) − stat(b)" if abs(lo + shift) < 1e-6 else
                   " — use the SAME indices for a and b in each resample")
            raise CheckFailed(f"a = b {shift:+g} everywhere must give exactly ({shift:g}, {shift:g}), got "
                              f"({lo:.3f}, {hi:.3f}){tip}")
    a = b + g.normal(2.0, 1.0, 50)
    lo, hi = pair(go(f, a, b, npx.mean, B=1000, seed=2), "paired_diff_ci(a, b)")
    c.ok(hi - lo < 2.0, f"a and b differ by 2 ± 1 m at each instant: the paired interval must be narrow (about 0.6 m), "
                        f"yours is {hi - lo:.1f} m wide — are the indices the same for a and b?")
    c.ok(lo < 2.0 < hi + 0.3 and lo > 1.0, f"the interval ({lo:.2f}, {hi:.2f}) should be around 2")
    blk = pair(go(f, a, b, npx.mean, B=300, seed=2, block=5), "paired_diff_ci(…, block=5)")
    c.ok(blk[1] - blk[0] < 3.0, "with block=5 the pairs must stay together too")
    raise_value_error(lambda: go(f, a[:10], b[:9], npx.mean), "paired_diff_ci(10 values, 9 values)",
                      "a and b must have the same length")


@c.test("TODO 8 — wilson() on unseen counts (0 of n, n of n, z = 2.576)",
        hint="centre = (p + z²/2n) / (1 + z²/n); half = z/(1 + z²/n) · sqrt(p(1−p)/n + z²/4n²) (lesson §7). "
             "ValueError for k > n or n < 1.")
def _():
    m, f = todo("navera_lite.stats", "wilson", 8)
    for case in CASES["wilson"] + [CASES["wilson_z"]]:
        args = (case["k"], case["n"]) + ((case["z"],) if "z" in case else ())
        lo, hi = pair(go(f, *args), f"wilson{args}")
        for end, g, w in (("lower", lo, case["want"][0]), ("upper", hi, case["want"][1])):
            if abs(g - w) > 1e-4:
                p, z = case["k"] / case["n"], case.get("z", 1.96)
                half = z * math.sqrt(p * (1 - p) / case["n"])
                naive = p - half if end == "lower" else p + half
                tip = " — that is the naive p ± z·SE, not Wilson (lesson §7)" if abs(g - naive) < 1e-4 else ""
                raise CheckFailed(f"wilson{args} {end} end = {g:.4f}: not right (a share between 0 and 1){tip}")
    for bad in ((5, 4), (1, 0)):
        raise_value_error(lambda: go(f, *bad), f"wilson{bad}", "0 ≤ k ≤ n and n ≥ 1")


@c.test("TODO 9 — coverage_experiment() with experiments it has never seen",
        hint="ONE generator rng = np.random.default_rng(seed), made before the loop; each trial: sample = "
             "make_sample(rng), (lo, hi) = ci_of(sample, rng), a hit if lo ≤ true_value ≤ hi; return hits / trials.")
def _():
    m, f = todo("navera_lite.stats", "coverage_experiment", 9)
    want = CASES["coverage"]
    v = go(f, lambda g: g.normal(0.0, 1.0, 3), lambda s, g: (float(np.min(s)), float(np.max(s))), 0.0,
           trials=60, seed=7, seconds=60)
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"coverage_experiment() must return a share (a number), got {v!r:.60}")
    if v > 1.0:
        raise CheckFailed(f"coverage_experiment() returned {v:g}: a SHARE between 0 and 1 (hits / trials), not a count")
    if abs(v - want["minmax"]) > 1e-9:
        raise CheckFailed(f"coverage_experiment() = {v:.4f} on 60 trials (seed 7): not right — make the generator ONCE "
                          "from seed, before the loop, and give the same one to make_sample and to ci_of")
    v = float(go(f, lambda g: g.normal(0.0, 1.0, 4),
                 lambda s, g: (float(np.mean(s) - g.uniform(0, 1)), float(np.mean(s) + g.uniform(0, 1))),
                 0.0, trials=50, seed=11, seconds=60))
    c.ok(abs(v - want["shared"]) < 1e-9, f"coverage_experiment() = {v:.4f} when ci_of also draws from rng: not right "
                                         "— ci_of must receive the SAME generator as make_sample (not a new one)")


@c.test("Steps 6 and 8 — results.json intervals and coverage.json",
        hint="Run python3 measure_lab.py ci and python3 measure_lab.py coverage after TODO 6–9.")
def _():
    ci = results("ci")
    for name in FLIGHTS:
        got, want = ci.get(name) or {}, CASES["ci"][name]
        for k, (wlo, whi) in want.items():
            lo, hi = pair(got.get(k), f"results.json ci.{name}.{k}")
            tol = max(3.0, 0.12 * (whi - wlo))
            if abs(lo - wlo) > tol or abs(hi - whi) > tol:
                raise CheckFailed(f"ci.{name}.{k} = [{lo:.1f}, {hi:.1f}]: too far from the right interval (± {tol:.0f} m)"
                                  " — run measure_lab.py ci again after fixing TODO 6–7")
    c.ok(ci.get("selective", {}).get("jam_median_block10") is None, "selective: the block interval must be n/a (null)")
    if not os.path.exists("coverage.json"):
        raise CheckFailed("coverage.json does not exist yet: run python3 measure_lab.py coverage")
    d = json.load(open("coverage.json"))
    keys = ("iid_n60_iid", "ar09_n60_iid", "ar09_n60_block10", "wald_n33_p097", "wilson_n33_p097")
    for k in keys:
        c.ok(isinstance(d.get(k), (int, float)), f"coverage.json: {k} is {d.get(k)!r} — run the coverage again")
    c.ok(0.88 <= d["iid_n60_iid"] <= 1.0, f"independent errors: coverage {d['iid_n60_iid']} should be close to 0.95")
    c.ok(d["ar09_n60_iid"] < 0.8, f"correlated errors + iid bootstrap: {d['ar09_n60_iid']} — expected well below 0.95")
    c.ok(d["ar09_n60_block10"] > d["ar09_n60_iid"] + 0.05, "the block bootstrap should cover clearly more often")
    c.ok(d["wald_n33_p097"] < 0.8 and d["wilson_n33_p097"] > 0.85,
         f"Wald {d['wald_n33_p097']} / Wilson {d['wilson_n33_p097']}: Wilson must cover far more often")


@c.test("Steps 6–9 — answers.py: intervals, success rates, coverage and the stated σ",
        hint="EXPLAIN_PAIRED quotes the interval and says whether it contains 0; WILSON_LO_PCT / ZERO_UPPER_PCT from "
             "measure_lab.py wilson; HONEST_SIGMA_DAY_M and DAY_WITHIN_2SIGMA_PCT from evaluate_bag with --truth.")
def _():
    a = quiet("answers.py")
    v = need(a, "PREDICT_BLOCK", "EXPLAIN_PAIRED", "EXPLAIN_SELECTIVE_CI", "WILSON_LO_PCT", "ZERO_UPPER_PCT",
             "PREDICT_COVERAGE", "EXPLAIN_COVERAGE", "HONEST_SIGMA_DAY_M", "DAY_WITHIN_2SIGMA_PCT", "EXPLAIN_GPS_STATED")
    predicted("PREDICT_BLOCK", v[0])
    predicted("PREDICT_COVERAGE", v[5])
    explained("EXPLAIN_PAIRED", v[1], ([r"contain", r"includ", r"\b0\b", r"zero", r"cross"], "whether it contains 0"),
              ([r"not (shown|proved|significant|better)", r"cannot", r"can't", r"no (evidence|significant|proof)",
                r"noise", r"not sure", r"not possible"], "what you may (not) claim"))
    explained("EXPLAIN_SELECTIVE_CI", v[2], ([r"chose", r"chosen", r"select", r"own", r"19", r"only", r"withh",
                                              r"good seconds", r"easy", r"condition"], "which seconds were compared"),
              ([r"availab", r"missing", r"gap", r"41", r"no position", r"other seconds", r"rest"],
               "what the comparison leaves out"))
    for name, got, want, tol in (("WILSON_LO_PCT", v[3], 84.68, 0.15), ("ZERO_UPPER_PCT", v[4], 10.43, 0.15),
                                 ("HONEST_SIGMA_DAY_M", v[7], CASES["bag"]["day_honest_true"], 0.15),
                                 ("DAY_WITHIN_2SIGMA_PCT", v[8], CASES["bag"]["day_within2_pct"], 1.0)):
        if isinstance(got, (int, float)) and got == -1:
            raise CheckFailed(f"{name} is still -1")
        if name.endswith("PCT") and isinstance(got, (int, float)) and 0 < got < 1:
            raise CheckFailed(f"{name} = {got}: write it in % (e.g. 84.7), not as a share")
        c.near(got, want, tol, name)
    explained("EXPLAIN_COVERAGE", v[6], ([r"correlat", r"depend", r"neighbou?r", r"consecutive", r"ρ", r"rho",
                                          r"similar", r"not independent"], "that the errors are correlated"),
              ([r"fewer", r"effective", r"less information", r"n_?eff", r"too narrow", r"narrow", r"few (independent|blocks)",
                r"6 blocks", r"only \d+ blocks"], "why the interval is too narrow"))
    explained("EXPLAIN_GPS_STATED", v[9], ([r"pessimis", r"conservativ", r"cautious", r"overstat", r"too (large|big|high)",
                                            r"larger", r"bigger", r"safe", r"overestimat", r"more accurate than"],
                                           "which way the GPS's statement is wrong, and why it is the safer side"))


def section(text, title):
    mm = re.search(r"^## " + re.escape(title) + r".*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return mm.group(1) if mm else ""


@c.test("Step 10 — report.md: the validation note, with your numbers and their intervals",
        hint="No '(fill in' and no '…' left; the jam medians (target, retrieval, baseline), the selective flight's "
             "availability, your retrieval block interval of the difference, the honest σ; sections 3 (40+ words), "
             "4 (25+), 5 (60+), 6 (80+); name the baseline, the confidence interval, availability, synthetic/simulated "
             "and Sousse.")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8", errors="replace").read()
    first = text.find("\n## ")
    body = text[first:] if first >= 0 else text
    left = [p for p in ("(fill in", "…") if p in body]
    c.ok(not left, f"placeholders still there: {left}")
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", body.replace("−", "-"))]

    def has(v, tol=1.0):
        return any(abs(n - v) <= tol for n in nums) or any(abs(abs(n) - abs(v)) <= tol for n in nums)
    F = CASES["flights"]
    for what, val in (("the target flight's jam median", F["target"]["jam"]["median"]),
                      ("the retrieval flight's jam median", F["retrieval"]["jam"]["median"]),
                      ("the baseline's jam median", F["retrieval"]["baseline"]["median"]),
                      ("the selective flight's availability during the jam (%)", 100 * F["selective"]["availability_jam"]),
                      ("the day source's honest σ", CASES["bag"]["day_honest_true"])):
        c.ok(has(round(val)), f"{what} (rounded to a whole number) is not in the report")
    mine = (results("ci").get("retrieval") or {}).get("diff_median_block10")
    lo, hi = pair(mine, "your ci.retrieval.diff_median_block10")
    c.ok(has(round(lo)) and has(round(hi)), f"the retrieval flight's block interval of the difference (your "
                                            f"[{lo:.0f}, {hi:.0f}]) is not in the report")
    for title, n in (("3. Is the difference real?", 40), ("4. Is the stated accuracy honest?", 25),
                     ("5. Validity and limits", 60), ("6. Conclusion", 80)):
        w = len(section(body, title).split())
        c.ok(w >= n, f"section '{title}' has {w} words (at least {n}) — or its title was changed")
    low = body.lower()
    for word, why in (("baseline", "the baseline"), ("interval", "the confidence interval"), ("availab", "availability"),
                      ("sousse", "where (Sousse)")):
        c.ok(word in low, f"the report does not mention {why}")
    c.ok("simulat" in low or "synthetic" in low, "the report does not say the flights are synthetic / simulated")
    diff = section(body, "3. Is the difference real?").lower()
    c.ok(re.search(r"contain|includ|\b0\b|zero", diff), "section 3 must say whether each interval contains 0")


c.milestone("session1", "TODO 1", "TODO 2", "TODO 3", "TODO 4", "TODO A", "Step 3", "Steps 0", label="Honest ruler")
c.milestone("session2", "TODO", "Step", label="Auditor")
c.run()

"""measure_lab.py — lab 32's runner: it calls YOUR functions (navera_lite/stats.py TODO 1–9, baseline.py
TODO A) on the flights of /data/academy/32-measuring/ and prints, plots and saves the results.

    python3 measure_lab.py test        every TODO on the example of its docstring
    python3 measure_lab.py flights     Session 1: errors, baseline, availability, gaps → results.json, out/*.png
    python3 measure_lab.py rules       the two percentile rules on the jam errors
    python3 measure_lab.py ci          Session 2: confidence intervals → results.json
    python3 measure_lab.py wilson      success rates with an interval
    python3 measure_lab.py coverage    the coverage experiment → coverage.json (1–3 minutes)
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import json
import math
import os
import sys

import numpy as np
import pandas as pd

import runner_kit as rk

DATA = "/data/academy/32-measuring"
FLIGHTS = ("target", "retrieval", "selective")
B, SEED, BLOCK = 2000, 32, 10
RESULTS = "results.json"


def stats():
    return rk.load_student("navera_lite.stats")


def load(name):
    path = os.path.join(DATA, f"flight_{name}.csv")
    if not os.path.exists(path):
        sys.exit(f"{path} is missing: is /data/academy/32-measuring mounted? (ask your teacher)")
    return pd.read_csv(path)


def array_of(v, fn):
    """The student's result as a 1-D float array, or one plain sentence and exit."""
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        sys.exit(f"{fn}() must return numbers (a numpy array), it returned {type(v).__name__}: {v!r:.80}")
    if a.ndim != 1:
        sys.exit(f"{fn}() must return a 1-D array (one number per row), its shape is {a.shape}")
    if a.size and not np.all(np.isfinite(a)):
        sys.exit(f"{fn}() returned NaN values: rows without a position must be LEFT OUT, not kept as NaN")
    return a


def pair_of(v, fn):
    ok = isinstance(v, (tuple, list, np.ndarray)) and len(v) == 2
    try:
        lo, hi = float(v[0]), float(v[1])
    except (TypeError, ValueError, IndexError):
        ok = False
    if not ok:
        sys.exit(f"{fn}() must return a pair (lo, hi) of numbers, it returned {v!r:.80}")
    if lo > hi:
        sys.exit(f"{fn}() returned ({lo:.3g}, {hi:.3g}): the lower end is above the upper end")
    return round(lo, 3), round(hi, 3)


def save(part, value):
    data = {}
    if os.path.exists(RESULTS):
        try:
            data = json.load(open(RESULTS))
        except json.JSONDecodeError:
            data = {}
    data[part] = value
    with open(RESULTS, "w") as f:
        json.dump(data, f, indent=1)
    print(f"\nsaved {RESULTS} ({part})")


def fmt(s):
    if not s or not s.get("n"):
        return "n    0"
    return (f"n {s['n']:4d}  median {s['median']:7.1f}  p90 {s['p90']:7.1f}  p95 {s['p95']:7.1f}  "
            f"rmse {s['rmse']:7.1f}  mean {s['mean']:7.1f}  max {s['max']:7.1f}")


def summary_of(S, errs, what):
    s = rk.need_ok(S, "summary", list(errs), kind=dict)
    need = ("n", "mean", "median", "p90", "p95", "max", "rmse")
    missing = [k for k in need if k not in s]
    if missing:
        sys.exit(f"summary() must return a dict with the keys {need}; missing: {missing} ({what})")
    clean = {"n": int(s["n"])}
    for k in need[1:]:
        clean[k] = None if s[k] is None else round(float(s[k]), 3)
    return clean


# ------------------------------------------------------------------------------------------- test
def cmd_test():
    S = stats()
    b = rk.load_student("baseline")
    nan = float("nan")
    t4 = pd.DataFrame({"t_s": [0.0, 1, 2, 3], "state": ["FIX", "FIX", "NO_FIX", "DEGRADED"],
                       "lat": [35.8, 35.8, nan, 35.8], "lon": [10.6, 10.6, nan, 10.6]})
    t5 = pd.DataFrame({"t_s": [0.0, 1, 2, 3, 4, 5], "state": ["FIX", "NO_FIX", "NO_FIX", "FIX", "NO_FIX", "FIX"],
                       "lat": [35.8, nan, nan, 35.8, nan, 35.8], "lon": [10.6, nan, nan, 10.6, nan, 10.6]})
    t1 = pd.DataFrame({"lat": [35.8, nan, 35.8001], "lon": [10.6, 10.6, 10.6], "truth_lat": [35.8] * 3,
                       "truth_lon": [10.6] * 3})
    ta = pd.DataFrame({"t_s": [0.0, 1, 2, 3], "gps": ["ok", "ok", "jammed", "jammed"],
                       "state": ["FIX", "FIX", "DEGRADED", "DEGRADED"], "source": ["gps", "gps", "day", "day"],
                       "lat": [35.8, 35.8001, 35.9, 35.9], "lon": [10.6] * 4,
                       "truth_lat": [35.8, 35.8001, 35.8002, 35.8003], "truth_lon": [10.6] * 4})
    cases = [
        ("TODO 1", S, "errors_m", (t1,), {}, [0.0, 11.119]),
        ("TODO 2", S, "percentile", ([7, 1, 3, 5], 50), {}, 4.0),
        ("TODO 2", S, "percentile", ([7, 1, 3, 5], 90), {}, 6.4),
        ("TODO 3", S, "summary", ([2, 4, 4, 10],), {}, {"n": 4, "mean": 5.0, "median": 4.0, "p90": 8.2,
                                                       "p95": 9.1, "max": 10.0, "rmse": 5.831}),
        ("TODO 4", S, "availability", (t4,), {}, 0.75),
        ("TODO 5", S, "longest_gap_s", (t5,), {}, 2.0),
        ("TODO 6", S, "bootstrap_ci", ([4.0] * 20, np.median), {}, (4.0, 4.0)),
        ("TODO 6", S, "bootstrap_ci", (list(range(60)), np.median), {"block": 60}, (29.5, 29.5)),
        ("TODO 7", S, "paired_diff_ci", (np.array([8, 14, 9, 17, 12.0]), np.array([3, 9, 4, 12, 7.0]), np.mean), {},
         (5.0, 5.0)),
        ("TODO 8", S, "wilson", (8, 10), {}, (0.490, 0.943)),
        ("TODO A", b, "last_fix_baseline", (ta,), {}, [11.119, 22.239]),
    ]
    bad = 0
    for todo, mod, fn, args, kw, want in cases:
        got, err = rk.call(mod, fn, *args, **kw)
        label = f"{todo:7s} {fn}()"
        if err:
            print(f"✘ {label}: {err}")
            bad += 1
            continue
        ok, shown = compare(got, want)
        print(("✔ " if ok else "✘ ") + f"{label} → {shown}" + ("" if ok else f"   (the docstring's example says {want})"))
        bad += not ok
    got, err = rk.call(S, "coverage_experiment", lambda rng: rng.normal(0.0, 1.0, size=5),
                       lambda s, rng: (s.min(), s.max()), 0.0, trials=1000, seed=0)
    if err:
        print(f"✘ TODO 9  coverage_experiment(): {err}")
        bad += 1
    else:
        ok = isinstance(got, (int, float)) and 0.9 <= got <= 0.97
        print(("✔ " if ok else "✘ ") + f"TODO 9  coverage_experiment() → {got!r}" +
              ("" if ok else "   (about 0.94 expected: a share between 0 and 1, the hits divided by the trials)"))
        bad += not ok
    print("\nall examples work" if not bad else f"\n{bad} line(s) to fix (a TODO not written yet is normal)")


def compare(got, want, tol=0.002):
    try:
        if isinstance(want, dict):
            if not isinstance(got, dict):
                return False, repr(got)
            ok = all(k in got and got[k] is not None and abs(float(got[k]) - v) <= max(tol, 1e-3 * abs(v))
                     for k, v in want.items())
            return ok, "{" + ", ".join(f"{k}: {got.get(k)!r:.6}" for k in want) + "}"
        if isinstance(want, (list, tuple)):
            g = [float(x) for x in got]
            return len(g) == len(want) and all(abs(a - b) <= 0.01 for a, b in zip(g, want)), \
                "(" + ", ".join(f"{x:.3f}" for x in g) + ")"
        return abs(float(got) - want) <= tol, f"{float(got):.4g}"
    except (TypeError, ValueError):
        return False, repr(got)


# ------------------------------------------------------------------------------------------- Session 1
def flight_numbers(S, b, name):
    df = load(name)
    jam = df[df["gps"] == "jammed"]
    e_all = array_of(rk.need_ok(S, "errors_m", df), "errors_m")
    e_jam = array_of(rk.need_ok(S, "errors_m", jam), "errors_m")
    base = array_of(rk.need_ok(b, "last_fix_baseline", df), "last_fix_baseline")
    if len(base) != len(jam):
        sys.exit(f"last_fix_baseline() gave {len(base)} values for {len(jam)} jammed rows: one per jammed row")
    out = {"all": summary_of(S, e_all, "all"), "jam": summary_of(S, e_jam, "jam"),
           "baseline": summary_of(S, base, "baseline"),
           "availability": round(float(rk.need_ok(S, "availability", df, kind=float)), 4),
           "availability_jam": round(float(rk.need_ok(S, "availability", jam, kind=float)), 4),
           "longest_gap_s": round(float(rk.need_ok(S, "longest_gap_s", df, kind=float)), 1),
           "longest_gap_jam_s": round(float(rk.need_ok(S, "longest_gap_s", jam, kind=float)), 1)}
    return df, jam, base, out


def cmd_flights():
    S, b = stats(), rk.load_student("baseline")
    plt = rk.plt_or_none()
    res = {}
    for name in FLIGHTS:
        df, jam, base, r = flight_numbers(S, b, name)
        res[name] = r
        print(f"\n=== flight_{name}.csv — {len(df)} s, GPS jammed {len(jam)} s ===")
        print(f"  whole flight     {fmt(r['all'])}")
        print(f"  jam, the judge   {fmt(r['jam'])}")
        print(f"  jam, baseline    {fmt(r['baseline'])}")
        print(f"  availability {100 * r['availability']:.1f} % (jam {100 * r['availability_jam']:.1f} %), "
              f"longest gap {r['longest_gap_s']:.0f} s (jam {r['longest_gap_jam_s']:.0f} s)")
        if plt:
            plot(plt, S, df, jam, base, name)
    save("flights", res)


def plot(plt, S, df, jam, base, name):
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4))
    t0, t1 = jam["t_s"].min(), jam["t_s"].max() + 1
    ax.axvspan(t0, t1, color="#fde68a", alpha=0.6, label="GPS jammed")
    has = df["lat"].notna().to_numpy()
    e = array_of(rk.need_ok(S, "errors_m", df), "errors_m")
    ax.plot(df["t_s"].to_numpy()[has], e, ".", color="#0b6e8a", ms=4, label="the judge's position")
    ax.plot(jam["t_s"], base, "-", color="#d64545", label="baseline: last GPS position")
    lost = df.loc[~has, "t_s"]
    ax.plot(lost, np.zeros(len(lost)), "|", color="#555", ms=12, label="no position")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("error (m)")
    ax.set_title(f"flight_{name}: error of the position the judge gave")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    path = f"out/errors_{name}.png"
    fig.savefig(path, dpi=90)
    plt.close(fig)
    rk.saved(path)


def cmd_rules():
    S = stats()
    print("the same errors, two percentile rules (linear = yours, TODO 2; nearest = pct_nearest, given)\n")
    for name in FLIGHTS:
        jam = load(name)
        jam = jam[jam["gps"] == "jammed"]
        e = array_of(rk.need_ok(S, "errors_m", jam), "errors_m")
        line = f"flight_{name:10s} jam, n {len(e):3d}:"
        for q in (50, 90, 95):
            lin = rk.need_ok(S, "percentile", list(e), q, kind=float)
            near = rk.need_ok(S, "pct_nearest", list(e), q, kind=float)
            line += f"   p{q} {lin:6.1f} / {near:6.1f}"
        print(line)


# ------------------------------------------------------------------------------------------- Session 2
def consecutive_enough(t):
    """Block resampling needs neighbours in the list to be neighbours in time: allow at most 20 % missing."""
    t = np.asarray(t, dtype=float)
    span = t.max() - t.min() + 1 if len(t) else 0
    return len(t) >= 2 * BLOCK and (span - len(t)) <= 0.2 * span


def cmd_ci():
    S, b = stats(), rk.load_student("baseline")
    res = {}
    median = np.median
    print(f"95 % percentile-bootstrap intervals, B = {B}, seed = {SEED}; blocks of {BLOCK} s\n")
    for name in FLIGHTS:
        df, jam, base, _ = flight_numbers(S, b, name)
        has = jam["lat"].notna().to_numpy()
        e = array_of(rk.need_ok(S, "errors_m", jam), "errors_m")
        t = jam["t_s"].to_numpy()[has]
        r = {"n": int(len(e)),
             "jam_median_iid": pair_of(rk.need_ok(S, "bootstrap_ci", e, median, B=B, seed=SEED), "bootstrap_ci")}
        blocky = consecutive_enough(t)
        r["jam_median_block10"] = (pair_of(rk.need_ok(S, "bootstrap_ci", e, median, B=B, seed=SEED, block=BLOCK),
                                           "bootstrap_ci") if blocky else None)
        bm = base[has]                       # the baseline at the SAME seconds as the judge's positions
        r["diff_median_iid"] = pair_of(rk.need_ok(S, "paired_diff_ci", e, bm, median, B=B, seed=SEED),
                                       "paired_diff_ci")
        r["diff_median_block10"] = (pair_of(rk.need_ok(S, "paired_diff_ci", e, bm, median, B=B, seed=SEED,
                                                       block=BLOCK), "paired_diff_ci") if blocky else None)
        r["diff_median_point"] = round(float(np.median(e) - np.median(bm)), 3)
        res[name] = r
        na = "n/a (too many seconds missing: a block would join seconds far apart)"
        print(f"flight_{name} — jam, {len(e)} positions of {len(jam)} s")
        print(f"  median error {np.median(e):7.1f} m   iid {show(r['jam_median_iid'])}   "
              f"block {show(r['jam_median_block10']) if blocky else na}")
        print(f"  median(judge) − median(baseline), same seconds: {r['diff_median_point']:7.1f} m   "
              f"iid {show(r['diff_median_iid'])}   block {show(r['diff_median_block10']) if blocky else na}\n")
    save("ci", res)


def show(p):
    return f"[{p[0]:7.1f}, {p[1]:7.1f}]" if p else "n/a"


def cmd_wilson():
    S = stats()
    print(f"{'claim':34s}{'rate':>7s}{'Wilson 95 %':>22s}{'naive ± 1.96 SE':>24s}")
    for k, n, what in ((32, 33, "32 of 33 frames within 9 m"), (30, 33, "30 of 33 accepted"),
                       (0, 33, "0 wrong positions in 33 frames"), (19, 60, "selective: 19 of 60 s")):
        lo, hi = pair_of(rk.need_ok(S, "wilson", k, n), "wilson")
        wl, wh = S.wald(k, n)
        print(f"{what:34s}{100 * k / n:6.1f}%    [{100 * lo:5.1f} %, {100 * hi:5.1f} %]    "
              f"[{100 * wl:6.1f} %, {100 * wh:6.1f} %]")


def cmd_coverage():
    S = stats()
    true_median = S.RAYLEIGH_MEDIAN * 10.0
    Bc, trials = 500, 200

    def boot(block):
        return lambda x, rng: pair_of(S.bootstrap_ci(x, np.median, B=Bc, seed=int(rng.integers(1 << 30)),
                                                     block=block), "bootstrap_ci")
    cases = [("iid_n60_iid", "independent errors, n 60, iid bootstrap", 0.0, 1),
             ("ar09_n60_iid", "correlated errors (ρ 0.9), n 60, iid bootstrap", 0.9, 1),
             ("ar09_n60_block10", "correlated errors (ρ 0.9), n 60, blocks of 10", 0.9, 10)]
    out = {}
    print(f"coverage of a '95 %' interval of the median ({trials} imaginary flights each, σ 10 m per axis; "
          f"true median {true_median:.2f} m)\n")
    for key, what, rho, block in cases:
        v = rk.need_ok(S, "coverage_experiment", (lambda r, rho=rho: S.ar1_radial(r, 60, rho, 10.0)), boot(block),
                       true_median, trials=trials, seed=320, kind=float)
        out[key] = round(float(v), 3)
        print(f"  {what:50s} {100 * v:5.1f} %", flush=True)
    for key, what, f in (("wald_n33_p097", "success rate 97 %, n 33, naive ± 1.96 SE", S.wald),
                         ("wilson_n33_p097", "success rate 97 %, n 33, Wilson", S.wilson)):
        v = rk.need_ok(S, "coverage_experiment", lambda r: int(r.binomial(33, 0.97)),
                       lambda k, r, f=f: f(k, 33), 0.97, trials=2000, seed=321, kind=float)
        out[key] = round(float(v), 3)
        print(f"  {what:50s} {100 * v:5.1f} %")
    with open("coverage.json", "w") as fh:
        json.dump(out, fh, indent=1)
    print("\nsaved coverage.json")


COMMANDS = {"test": cmd_test, "flights": cmd_flights, "rules": cmd_rules, "ci": cmd_ci, "wilson": cmd_wilson,
            "coverage": cmd_coverage}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]]()

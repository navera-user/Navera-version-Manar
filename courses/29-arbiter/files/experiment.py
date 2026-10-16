"""experiment.py — measure what the judge's design choices cost (lab Steps 7 and 8).

    python3 experiment.py test       TODO A and TODO B on their docstring examples (and one trap each)
    python3 experiment.py            runs A, B and C, writes results.json and out/tradeoffs.png

  A. Hold-off: a GPS at the edge of a jammer's range comes and goes. How often does YOUR judge change its
     winner, and how much good GPS does the hold-off leave unused?        → holdoff_metrics()  (TODO A)
  B. Freshness window: day-vision photos under CPU load. How often is day vision usable, and how old can a
     used position be?                                                    → freshness() (given)
  C. Selection or fusion: what the fused σ claims, what it really is when the errors are correlated, and
     where a spoofed GPS drags the fused position.                        → true_sigma()       (TODO B)

All inputs are SYNTHETIC and seeded (the same numbers on every run, for everybody): a model to reason with,
not a measurement of NAVERA in flight.
"""
import json
import math
import os
import random
import sys

import judge_lab as jl
import runner_kit as rk

uncertainty = rk.load_student("navera_lite.uncertainty")     # mission 27, finished

TICK_S = 0.2                      # the judge decides at 5 Hz (navera_lite.yaml tick_hz)
DURATION_S = 600.0                # 10 minutes of flight per experiment
HOLDOFFS = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]
WINDOWS = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
SPEED_MPS = 40.0                  # a fixed-wing drone at 144 km/h
SIGMA_GPS_M, SIGMA_VISION_M, RHO = 2.5, 20.0, 0.6     # experiment C
SPOOF_M = 1500.0                                       # experiment C: the spoofed GPS is this far east


# TODO A ---------------------------------------------------------------------------------------
def holdoff_metrics(ticks, duration_s=DURATION_S):
    """The cost and the benefit of a hold-off, measured on the judge's decisions at every tick.

    ticks: a list of (t_s, winner, gps_eligible), one per 0.2 s tick, in time order — winner is the source
    the judge chose ("gps", "day"… or None), gps_eligible is True when the GPS was eligible at that tick.
    Returns a dict:
      "switches_per_min"  how many times the winner differs from the winner of the tick before (None counts
                          like a source), per minute of duration_s
      "gps_share"         the fraction of the ticks (0 to 1) where the winner is "gps"
      "gps_unused_s"      the time (s) during which the GPS was eligible but did not win: TICK_S per such tick
    Example: holdoff_metrics([(0.0, "day", False), (0.2, "day", True), (0.4, "gps", True), (0.6, "day", False)],
             duration_s=60.0) → {"switches_per_min": 2.0, "gps_share": 0.25, "gps_unused_s": 0.2}
    """
    return None   # TODO: replace this line with your code


def fuse(x1, s1, x2, s2):
    """Inverse-variance fusion of two INDEPENDENT measurements of one quantity, with σ instead of covariances:
    mission 27's uncertainty.fuse() on round errors (P = σ² I), east only. Returns (x, s, w1, w2): the fused
    value, the σ the formula claims, and the two weights (w1 = (1/s1²) / (1/s1² + 1/s2²), w2 = 1 − w1). Given.
    Example: fuse(10.0, 3.0, 40.0, 30.0) → (10.297…, 2.985…, 0.990…, 0.0099…)
    """
    x, P = uncertainty.fuse([x1, 0.0], [[s1 ** 2, 0.0], [0.0, s1 ** 2]], [x2, 0.0], [[s2 ** 2, 0.0], [0.0, s2 ** 2]])
    w1 = (1.0 / s1 ** 2) / (1.0 / s1 ** 2 + 1.0 / s2 ** 2)
    return float(x[0]), math.sqrt(float(P[0][0])), w1, 1.0 - w1


# TODO B ---------------------------------------------------------------------------------------
def true_sigma(s1, s2, rho):
    """The REAL σ (m) of the value fuse() computes when the two errors are correlated with correlation rho
    (−1 … 1): fuse() keeps its weights w1, w2 (it assumes independence), so the variance of the fused error is
    w1²·s1² + w2²·s2² + 2·w1·w2·rho·s1·s2 (lesson §7). With rho = 0 it is the σ fuse() claims.
    Example: true_sigma(3.0, 30.0, 0.0) → 2.985 (to 3 decimals);  true_sigma(3.0, 30.0, 0.8) → 3.213
    """
    return None   # TODO: replace this line with your code


# ---- you don't need to change anything below this line (but you can read it!) ----

def flapping_events(duration_s=DURATION_S, mean_on_s=2.0, mean_off_s=1.0, seed=2901):
    """A GPS at the edge of a jammer's range: usable for an exponential time (mean 2 s), then "no fix"
    (valid False) for an exponential time (mean 1 s), and so on; 2 messages per second. Day vision sends one
    position a second, σ 30 m stated, 0.8 s old. Returns [(t, Estimate)] in time order."""
    E = jl.Estimate
    rng = random.Random(seed)
    segs, t, on = [], 0.0, True
    while t < duration_s:
        d = rng.expovariate(1.0 / (mean_on_s if on else mean_off_s))
        segs.append((t, t + d, on))
        t, on = t + d, not on
    evs, j = [], 0
    for k in range(int(duration_s * 2)):
        tg = round(0.5 * k + 0.1, 6)
        while segs[j][1] <= tg:
            j += 1
        if segs[j][2]:
            evs.append((tg, E("gps", 35.8245, 10.6346, jl.CLOCK0 + tg, cov=jl.cov9(3.0), cov_type=1)))
        else:
            evs.append((tg, E("gps", math.nan, math.nan, jl.CLOCK0 + tg, valid=False)))
    for k in range(int(duration_s)):
        tv = k + 0.35
        evs.append((tv, E("day", 35.8247, 10.6349, jl.CLOCK0 + tv - 0.8, cov=jl.cov9(30.0), cov_type=1)))
    return sorted(evs, key=lambda e: e[0])


def fly(events, holdoff_s, duration_s=DURATION_S):
    """YOUR judge (navera_lite/arbiter.py) with switch_holdoff_s = holdoff_s, fed with the events: on each
    arrival receive() and step(); at every 0.2 s tick step(). Returns the ticks [(t, winner, gps_eligible)]."""
    c = dict(jl.cfg())
    c["switch_holdoff_s"] = float(holdoff_s)
    arb = jl.arb_mod.Arbiter(c)
    ticks, i = [], 0
    for k in range(int(round(duration_s / TICK_S))):
        t = round(k * TICK_S, 6)
        while i < len(events) and events[i][0] <= t + 1e-9:
            now = jl.CLOCK0 + events[i][0]
            arb.receive(events[i][1], now)
            arb.step(now)
            i += 1
        d = arb.step(jl.CLOCK0 + t)
        gps = arb.latest.get("gps")
        ok = gps is not None and jl.est_mod.eligible(gps, jl.CLOCK0 + t, c)[0]
        ticks.append((t, d.source, bool(ok)))
    return ticks


def frame_times(duration_s=DURATION_S, seed=2902):
    """Day-vision photo instants under CPU load: 85 % of the gaps 1–4 s, 15 % stalls of 4–10 s."""
    rng = random.Random(seed)
    t, out = 0.5, []
    while t < duration_s:
        out.append(round(t, 3))
        t += rng.uniform(1.0, 4.0) if rng.random() < 0.85 else rng.uniform(4.0, 10.0)
    return out


def freshness(frames, window_s, duration_s=DURATION_S, speed_mps=SPEED_MPS):
    """Day vision with a freshness window: sampled every 0.1 s, a photo is usable while its age ≤ window_s (the
    rule of estimate.eligible). Returns availability (fraction of samples), dropouts (usable → not usable), the
    largest age used (s) and the largest staleness error at speed_mps (estimate.staleness_m, mission 12)."""
    n = int(round(duration_s / 0.1))
    j, usable, drops, max_age, prev = -1, 0, 0, 0.0, False
    for k in range(n):
        t = k * 0.1
        while j + 1 < len(frames) and frames[j + 1] <= t + 1e-9:
            j += 1
        ok = j >= 0 and t - frames[j] <= window_s + 1e-9
        if ok:
            usable += 1
            max_age = max(max_age, t - frames[j])
        drops += prev and not ok
        prev = ok
    return {"availability": usable / n, "dropouts": drops, "max_age_s": round(max_age, 3),
            "max_error_m": jl.est_mod.staleness_m(speed_mps, round(max_age, 3))}


def run_all():
    evs = flapping_events()
    hold = []
    for h in HOLDOFFS:
        try:
            ticks = fly(evs, h)
        except Exception as e:
            sys.exit(f"your judge stopped during experiment A (hold-off {h} s) with {type(e).__name__}: {e}"
                     f"{jl._hint(e)}\nFinish and test it first: python3 judge_lab.py test")
        m = rk.need_ok(sys.modules[__name__], "holdoff_metrics", ticks, DURATION_S, kind=dict)
        hold.append(dict(holdoff_s=h, **m))
    frames = frame_times()
    fresh = [dict(window_s=w, **freshness(frames, w)) for w in WINDOWS]
    x, s, w1, _ = fuse(0.0, SIGMA_GPS_M, 0.0, SIGMA_VISION_M)
    xs, _, _, _ = fuse(SPOOF_M, SIGMA_GPS_M, 0.0, SIGMA_VISION_M)
    ts = rk.need_ok(sys.modules[__name__], "true_sigma", SIGMA_GPS_M, SIGMA_VISION_M, RHO, kind=float)
    fusion = {"sigma_gps_m": SIGMA_GPS_M, "sigma_vision_m": SIGMA_VISION_M, "rho": RHO,
              "claimed_sigma_m": s, "true_sigma_m": ts, "weight_gps": w1, "spoof_m": SPOOF_M, "spoofed_fused_m": xs}
    return {"holdoff": hold, "freshness": fresh, "fusion": fusion}


def plot(res, path):
    plt = rk.plt_or_none()
    if plt is None:
        return
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4))
    h = res["holdoff"]
    a.plot([r["holdoff_s"] for r in h], [r["switches_per_min"] for r in h], "o-", color="#1f63d1")
    a.set_xlabel("hold-off (s)")
    a.set_ylabel("changes of winner per minute", color="#1f63d1")
    a2 = a.twinx()
    a2.plot([r["holdoff_s"] for r in h], [r["gps_unused_s"] for r in h], "s--", color="#e8553f")
    a2.set_ylabel("eligible GPS not used (s in 10 min)", color="#e8553f")
    a.set_title("A. Hold-off: stability vs unused GPS")
    f = res["freshness"]
    b.plot([r["window_s"] for r in f], [100 * r["availability"] for r in f], "o-", color="#26a69a")
    b.set_xlabel("day-vision freshness window (s)")
    b.set_ylabel("day vision usable (% of the time)", color="#26a69a")
    b2 = b.twinx()
    b2.plot([r["window_s"] for r in f], [r["max_error_m"] for r in f], "s--", color="#9b6cf0")
    b2.set_ylabel(f"largest staleness at {SPEED_MPS:.0f} m/s (m)", color="#9b6cf0")
    b.set_title("B. Freshness: usable vs old")
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=90)
    rk.saved(path)


def test():
    me = sys.modules[__name__]
    ticks = [(0.0, "day", False), (0.2, "day", True), (0.4, "gps", True), (0.6, "day", False)]
    cases = [("A", "holdoff_metrics", (ticks, 60.0), {"switches_per_min": 2.0, "gps_share": 0.25, "gps_unused_s": 0.2},
              "the docstring example"),
             ("A", "holdoff_metrics", ([(0.0, None, False), (0.2, "day", False), (0.4, None, True)], 6.0),
              {"switches_per_min": 20.0, "gps_share": 0.0, "gps_unused_s": 0.2}, "None counts like a source"),
             ("B", "true_sigma", (3.0, 30.0, 0.8), 3.2129, "the docstring example"),
             ("B", "true_sigma", (4.0, 4.0, 1.0), 4.0, "two equal σ, perfectly correlated: no gain at all")]
    bad = 0
    for todo, fn, args, want, label in cases:
        got, err = rk.call(me, fn, *args)
        if err:
            ok, note = False, err
        elif isinstance(want, dict):
            ok = isinstance(got, dict) and set(got) == set(want) and all(
                isinstance(got[k], (int, float)) and abs(got[k] - want[k]) < 1e-6 for k in want)
            note = repr(got) if ok else f"returned {got!r}, the docstring says {want!r}"
        else:
            ok = isinstance(got, (int, float)) and abs(got - want) < 5e-4
            note = f"{got:.4f}" if ok else f"returned {got!r}, it should be {want}"
        bad += not ok
        print(f"{'✔' if ok else '✘'} TODO {todo} {fn}() — {label}: {note}")
    print("\nAll the examples agree." if not bad else f"\n{bad} line(s) to fix.")


def main():
    if sys.argv[1:] == ["test"]:
        return test()
    res = run_all()
    print("A. hold-off (s) | changes of winner / min | GPS share | eligible GPS unused (s in 10 min)")
    for r in res["holdoff"]:
        print(f"   {r['holdoff_s']:12.1f} | {r['switches_per_min']:23.2f} | {r['gps_share']:9.3f} | "
              f"{r['gps_unused_s']:8.1f}")
    print("\nB. window (s) | day vision usable | dropouts | oldest position used (s) | its staleness at 40 m/s (m)")
    for r in res["freshness"]:
        print(f"   {r['window_s']:10.1f} | {100 * r['availability']:15.1f} % | {r['dropouts']:8d} | "
              f"{r['max_age_s']:24.2f} | {r['max_error_m']:10.0f}")
    f = res["fusion"]
    print(f"\nC. GPS σ {f['sigma_gps_m']} m + vision σ {f['sigma_vision_m']} m: GPS weight {f['weight_gps']:.4f}, "
          f"fused σ claimed {f['claimed_sigma_m']:.3f} m; with ρ = {f['rho']}: real σ {f['true_sigma_m']:.3f} m")
    print(f"   GPS spoofed {f['spoof_m']:.0f} m east, vision right: the fused position moves "
          f"{f['spoofed_fused_m']:.1f} m east")
    with open("results.json", "w") as fh:
        json.dump(res, fh, indent=1)
    print("\nSaved results.json")
    plot(res, os.path.join("out", "tradeoffs.png"))


if __name__ == "__main__":
    main()

"""experiment.py — measure the two design choices of the arbiter, and test fusion.

  A. Hold-off (hysteresis): how many source switches per minute does a flapping GPS cause,
     and how much good GPS time does the hold-off cost?           -> holdoff_metrics()
  B. Freshness window: availability of day vision vs the error of using an old fix.
                                                                  -> freshness_metrics()
  C. Selection vs fusion: inverse-variance fusion of GPS and vision, and what happens
     when their errors are correlated or one source is spoofed.  -> fuse(), true_sigma()

    python3 experiment.py        # runs A, B, C, writes results.json and tradeoffs.png

All inputs are SYNTHETIC and seeded (same numbers on every run): a model to reason with,
not a measurement of NAVERA in flight.
"""
import json
import math
import random

import arbiter

TICK_S = 0.2                      # the real node decides at 5 Hz (+ on each arrival)
SAMPLE_S = 0.1                    # sampling step of the freshness experiment
DURATION_S = 600.0                # 10 minutes of flight per experiment
SPEED_MPS = 40.0                  # a fixed-wing drone cruising at 144 km/h
HOLDOFFS = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]
WINDOWS = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]


# ------------------------------------------------------------------ A. hold-off
def holdoff_metrics(events, holdoff_s, duration_s=DURATION_S):
    """Replay `events` through arbiter.Arbiter(holdoff_s) and measure it.

    Use timeline(events, duration_s) (below): it yields ("arrival", t, est) and
    ("tick", t, None) in time order. On an arrival: receive(est) then step(t).
    On a tick: step(t), then MEASURE at this tick:
        gps_ok   = "gps" in arb.latest and arbiter.is_eligible(arb.latest["gps"], t)
        on_gps   = the decision's source is "gps"
    Return a dict:
        "switches_per_min": (number of arb.switches whose OLD source is not None) / (duration_s / 60)
        "gps_share":        fraction of ticks with on_gps
        "gps_unused_s":     TICK_S x (number of ticks with gps_ok and not on_gps)
    """
    # TODO A: create the Arbiter, walk timeline(events, duration_s), count, return the dict.
    raise NotImplementedError("TODO A — holdoff_metrics()")


# ------------------------------------------------------------------ B. freshness
def freshness_metrics(frame_times, window_s, duration_s=DURATION_S, speed_mps=SPEED_MPS):
    """Day-vision frames are measured at `frame_times` (sorted, s). Sample the time at
    t_k = k * SAMPLE_S for k = 0 .. round(duration_s / SAMPLE_S) - 1. At each sample the
    age is t_k - (latest frame time <= t_k); "available" means a frame exists and
    age < window_s. Return a dict:
        "availability":     fraction of samples that are available
        "dropouts":         number of times available -> not available (k-1 -> k)
        "max_age_used_s":   the largest age among the available samples
        "max_error_m":      speed_mps x max_age_used_s  (how far the drone moved since
                            the photo: the error of using that fix without carrying it)
    """
    # TODO B: one pass over the samples, moving an index j through frame_times.
    raise NotImplementedError("TODO B — freshness_metrics()")


# ------------------------------------------------------------------ C. selection vs fusion
def fuse(x1, s1, x2, s2):
    """Inverse-variance (minimum-variance) fusion of two INDEPENDENT measurements of the
    same quantity: weights w_i = (1/s_i^2) / (1/s1^2 + 1/s2^2).
    Return (x, s): the fused value and its sigma s = sqrt(1 / (1/s1^2 + 1/s2^2))."""
    # TODO C1: inverse-variance weights, fused value, fused sigma.
    raise NotImplementedError("TODO C1 — fuse()")


def true_sigma(s1, s2, rho):
    """The REAL sigma of the fused value of fuse() when the two errors have correlation rho
    (fuse() still uses the independent weights w1, w2):
        var = w1^2 s1^2 + w2^2 s2^2 + 2 w1 w2 rho s1 s2"""
    # TODO C2: the same weights as fuse(), then the variance formula above.
    raise NotImplementedError("TODO C2 — true_sigma()")


# ---- you don't need to change anything below this line (but you can read it!) ----

def timeline(events, duration_s):
    """Merge timed arrivals [(t, est)] and 5 Hz ticks into one ordered stream.
    At equal times the arrival comes first. Yields (kind, t, est)."""
    i, k = 0, 0
    n_ticks = int(round(duration_s / TICK_S))
    while k < n_ticks:
        tk = round(k * TICK_S, 6)
        if i < len(events) and events[i][0] <= tk + 1e-9:
            yield "arrival", events[i][0], events[i][1]
            i += 1
        else:
            yield "tick", tk, None
            k += 1


def flapping_gps_events(duration_s=DURATION_S, mean_on_s=2.0, mean_off_s=1.0, seed=25):
    """A GPS at the edge of a jammer's range: valid for an exponential time (mean 2 s),
    then 'no fix' (valid=False) for an exponential time (mean 1 s), and so on. GPS sends
    2 messages per second; day vision sends one frame per second, stating sigma 30 m."""
    rng = random.Random(seed)
    segments, t, on = [], 0.0, True
    while t < duration_s:
        d = rng.expovariate(1.0 / (mean_on_s if on else mean_off_s))
        segments.append((t, t + d, on))
        t, on = t + d, not on
    evs = []
    for k in range(int(duration_s * 2)):
        tg = round(0.5 * k, 6)
        on = next(s[2] for s in segments if s[0] <= tg < s[1])
        evs.append((tg, arbiter.make_est("gps", tg, 3.0, valid=on)))
    for k in range(int(duration_s)):
        evs.append((float(k) + 0.25, arbiter.make_est("day", float(k) + 0.25, 30.0, lat=35.8254, lon=10.6387)))
    evs.sort(key=lambda e: e[0])
    return evs


def day_frame_times(duration_s=DURATION_S, seed=7):
    """Day-vision frame instants under CPU load: 85 % of gaps 1-4 s, 15 % stalls of 4-10 s."""
    rng = random.Random(seed)
    t, out = 0.5, []
    while t < duration_s:
        out.append(round(t, 3))
        t += rng.uniform(1.0, 4.0) if rng.random() < 0.85 else rng.uniform(4.0, 10.0)
    return out


def run_all():
    evs = flapping_gps_events()
    hold = [dict(holdoff_s=h, **holdoff_metrics(evs, h)) for h in HOLDOFFS]
    frames = day_frame_times()
    fresh = [dict(window_s=w, **freshness_metrics(frames, w)) for w in WINDOWS]
    x, s = fuse(2.0, 3.0, -20.0, 30.0)
    xs, _ = fuse(2000.0, 3.0, -20.0, 30.0)
    fusion = {"nominal_fused_m": x, "claimed_sigma_m": s, "gps_alone_sigma_m": 3.0,
              "true_sigma_rho_0.8_m": true_sigma(3.0, 30.0, 0.8),
              "spoofed_fused_m": xs}
    return {"holdoff": hold, "freshness": fresh, "fusion": fusion}


def plot(res, path="tradeoffs.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4))
    h = res["holdoff"]
    a.plot([r["holdoff_s"] for r in h], [r["switches_per_min"] for r in h], "o-", color="#1f63d1")
    a.set_xlabel("hold-off h (s)")
    a.set_ylabel("source switches per minute", color="#1f63d1")
    a2 = a.twinx()
    a2.plot([r["holdoff_s"] for r in h], [r["gps_unused_s"] for r in h], "s--", color="#e8553f")
    a2.set_ylabel("eligible GPS not used (s / 10 min)", color="#e8553f")
    a.set_title("A. Hold-off: stability vs lost GPS time")
    f = res["freshness"]
    b.plot([r["window_s"] for r in f], [100 * r["availability"] for r in f], "o-", color="#26a69a")
    b.set_xlabel("freshness window T (s)")
    b.set_ylabel("day-vision availability (%)", color="#26a69a")
    b2 = b.twinx()
    b2.plot([r["window_s"] for r in f], [r["max_error_m"] for r in f], "s--", color="#9b6cf0")
    b2.set_ylabel(f"max staleness error at {SPEED_MPS:.0f} m/s (m)", color="#9b6cf0")
    b.set_title("B. Freshness: availability vs staleness")
    fig.tight_layout()
    fig.savefig(path, dpi=90)


if __name__ == "__main__":
    try:
        res = run_all()
    except NotImplementedError as e:
        raise SystemExit(f"Not finished yet: {e}. Complete it, then run again.")
    print("A. hold-off   h (s)  switches/min  GPS share  eligible GPS unused (s)")
    for r in res["holdoff"]:
        print(f"             {r['holdoff_s']:5.1f}  {r['switches_per_min']:12.2f}  {r['gps_share']:9.3f}"
              f"  {r['gps_unused_s']:10.1f}")
    print("B. freshness  T (s)  availability  dropouts  max age (s)  max error (m)")
    for r in res["freshness"]:
        print(f"             {r['window_s']:5.1f}  {r['availability']:12.3f}  {r['dropouts']:8d}"
              f"  {r['max_age_used_s']:11.1f}  {r['max_error_m']:13.0f}")
    print("C. fusion    ", {k: round(v, 3) for k, v in res["fusion"].items()})
    with open("results.json", "w") as fh:
        json.dump(res, fh, indent=1)
    try:
        plot(res)
        print("Saved results.json and tradeoffs.png")
    except Exception as e:                     # plotting is a bonus, results.json is what counts
        print(f"Saved results.json (no plot: {e})")

"""run_trip.py — runs YOUR trip computer (navera_lite/ros/trip_node.py, TODO 1–3) without ROS.

    python3 run_trip.py test      check update(), speed_window() and silent() on their docstring examples
    python3 run_trip.py trace     the lesson's §3 sequence of fixes, with your verdicts       (Step 2)
    python3 run_trip.py drive     a 2-minute drive with a noisy GPS: speeds, delay, odometer  (Step 4)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import math
import os
import random
import statistics
import sys
import types

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

START = (35.8256, 10.6084)          # NAVERA's test area near Sousse, Tunisia
tn = rk.load_student("navera_lite.ros.trip_node")
geo = rk.load_student("navera_lite.geo")
from navera_lite.estimate import Estimate   # noqa: E402  (given, finished)


def east_of_start(e_m, n_m=0.0):
    return geo.offset(START[0], START[1], e_m, n_m)


def fix(t, e_m, n_m=0.0, **kw):
    lat, lon = east_of_start(e_m, n_m)
    return Estimate("gps", kw.pop("lat", lat), kw.pop("lon", lon), t, **kw)


def method(obj, name):
    """A stand-in 'module' so that runner_kit.call() can call obj.name() and name the student's file."""
    return types.SimpleNamespace(__file__=tn.__file__, **{name: getattr(obj, name)})


def judge(tc, est):
    """tc.update(est) → (ok, reason), or (None, a plain sentence) when update() is not usable yet."""
    v, err = rk.call(method(tc, "update"), "update", est)
    if err:
        return None, err
    if not (isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], bool) and isinstance(v[1], str)):
        return None, (f"update() must return a pair (True or False, \"reason\"), like (True, \"ok\"), "
                      f"but it returned {v!r}")
    return v, None


def show(ok, text, want=None, got=None):
    extra = "" if ok or want is None else f"   (expected {want!r}, got {got!r})"
    print(f"{'✔' if ok else '✘'} {text}{extra}")
    return ok


# ------------------------------------------------------------------------------------------------ test
def test():
    print("TODO 1 — TripComputer.update(), the docstring's rules, one fix after the other:")
    tc = tn.TripComputer()
    steps = [("first fix at t = 0 s", fix(0.0, 0.0), (True, "first fix")),
             ("10 m east, 1 s later", fix(1.0, 10.0), (True, "ok")),
             ("5 km east, 1 s later", fix(2.0, 5000.0), (False, "jump")),
             ("valid=False (the source has no position)", fix(2.0, 20.0, valid=False), (False, "no position")),
             ("latitude NaN", fix(2.0, 20.0, lat=math.nan), (False, "bad position")),
             ("stamped t = 0.5 s, 70 m behind the last accepted", fix(0.5, -60.0), (False, "old fix")),
             ("20 m east, at t = 2 s", fix(2.0, 20.0), (True, "ok")),
             ("stamped t = 2 s again (the SAME stamp), 25 m east", fix(2.0, 25.0), (False, "old fix"))]
    good = 0
    for text, est, want in steps:
        got, err = judge(tc, est)
        if err:
            print(f"✘ {text}: {err}")
            break
        good += show(got == want, f"{text:52s} → {got}", want, got)
    if good < len(steps):
        if good:
            print("  (summary lines skipped: fix the ✘ lines above first)")
    else:
        good += show(abs(tc.distance_m - 20.0) < 0.05, f"self.distance_m after it: {tc.distance_m:.2f} m",
                     "about 20.0 m (two steps of 10 m)", round(tc.distance_m, 2))
        good += show(len(tc.fixes) == 3 and tc.refused == 5,
                     f"{len(tc.fixes)} fixes remembered, {tc.refused} refused", "3 fixes, 5 refused",
                     (len(tc.fixes), tc.refused))
        good += show(tc.last_refusal == "old fix", f"self.last_refusal = {tc.last_refusal!r}", "old fix",
                     tc.last_refusal)
        tc2 = tn.TripComputer()
        got, err = judge(tc2, fix(0.0, 0.0, lat=math.nan, valid=False))
        if not err:
            show(got == (False, "no position"), f"valid=False AND NaN: the first rule wins → {got}",
                 (False, "no position"), got)
    print("\nTODO 2 — speed_window():")
    ex = [(0.0, 35.8256, 10.6084), (5.0, 35.8256, 10.60895), (10.0, 35.8256, 10.61005)]
    v, err = rk.call(tn, "speed_window", ex, 6.0)
    if err:
        print(f"✘ {err}")
    else:
        show(isinstance(v, (int, float)) and abs(v - 19.83) < 0.01,
             f"speed_window(docstring example, 6.0) → {v!r}", "about 19.83", v)
        for args, text in (((ex[:1], 6.0), "one fix only"), (([ex[0], ex[2]], 6.0), "one fix in the window")):
            v = tn.speed_window(*args)
            show(v is None, f"speed_window({text}) → {v!r}", None if v is None else "None", v)
    print("\nTODO 3 — Watchdog.silent():")
    w = tn.Watchdog(3.0)
    v, err = rk.call(method(w, "silent"), "silent", 0.0)
    if err:
        print(f"✘ {err}")
    else:
        show(v is True, f"{'before any message: silent(0.0)':36s} → {v!r}", True, v)
        w.kick(10.0)
        for text, now, want in (("kick(10.0), then silent(13.0)", 13.0, False),
                                ("            then silent(13.1)", 13.1, True)):
            got = w.silent(now)
            show(got is want, f"{text:36s} → {got!r}", want, got)
    print("\nAll ✔? Then TODO 1–3 do what their docstrings say. The check also tries numbers it never shows you.")


# ----------------------------------------------------------------------------------------------- trace
def trace():
    """The lesson's §3 sequence: a plane at 75 m/s, one fix per second, and four bad fixes."""
    rows = [(0.0, 0.0, {}), (1.0, 75.0, {}), (2.0, 150.0, {}), (1.2, 90.0, {}), (3.0, 225.0, {"valid": False}),
            (4.0, 300.0, {}), (5.0, 5000.0, {}), (6.0, 450.0, {})]
    tc = tn.TripComputer()
    print("  stamp   east (m)  valid   your verdict")
    for t, e, kw in rows:
        got, err = judge(tc, fix(t, e, **kw))
        if err:
            sys.exit(err)
        print(f"  {t:4.1f} s  {e:8.0f}  {str(kw.get('valid', True)):5s}   {got}")
    print(f"\n  distance {tc.distance_m:.1f} m along {len(tc.fixes)} accepted fixes, {tc.refused} refused")


# ----------------------------------------------------------------------------------------------- drive
SIGMA_M = 3.0          # GPS noise, 1 σ on east and on north (the fake GPS of mission 10 states 3 m)
SPEED_MPS = 10.0       # cruising speed, east
STOP_S = 60            # the vehicle stops here and stays parked
DURATION_S = 120
WINDOW_S = 10.0
SEED = 33


def drive():
    rng = random.Random(SEED)
    tc = tn.TripComputer()
    ts, inst, win, truth = [], [], [], []
    for k in range(DURATION_S):
        t = float(k)
        e_true = SPEED_MPS * min(t, STOP_S)
        est = fix(t, e_true + rng.gauss(0.0, SIGMA_M), rng.gauss(0.0, SIGMA_M))
        got, err = judge(tc, est)
        if err:
            sys.exit(err)
        if not got[0]:
            sys.exit(f"update() refused an honest fix at t = {t:.0f} s with {got[1]!r}: run `python3 run_trip.py test`")
        v1, err = rk.call(tn, "speed_window", tc.fixes, 1.0)
        v10, err10 = rk.call(tn, "speed_window", tc.fixes, WINDOW_S)
        if k >= 1 and (err or v1 is None):
            sys.exit(err or "speed_window(fixes, 1.0) returned None with 2 fixes 1 s apart: run `python3 run_trip.py test`")
        ts.append(t)
        inst.append(v1)
        win.append(v10)
        truth.append(SPEED_MPS if t < STOP_S else 0.0)

    def pick(xs, a, b):
        return [x for t, x in zip(ts, xs) if a <= t <= b and x is not None]

    cruise_i, cruise_w = pick(inst, 20, 59), pick(win, 20, 59)
    parked_i, parked_w = pick(inst, 75, 119), pick(win, 75, 119)
    lag = next((t - STOP_S for t, v in zip(ts, win) if t >= STOP_S and v is not None and v < 1.0), None)
    true_km = SPEED_MPS * STOP_S
    print(f"A drive east at {SPEED_MPS:.0f} m/s for {STOP_S} s, then parked for {DURATION_S - STOP_S} s. "
          f"One fix per second, GPS noise σ = {SIGMA_M:.0f} m (seed {SEED}).\n")
    print(f"{'':28s}{'window 1 s':>14s}{'window 10 s':>14s}")
    print(f"{'cruising (20–59 s): mean':28s}{statistics.fmean(cruise_i):11.2f} m/s{statistics.fmean(cruise_w):11.2f} m/s")
    print(f"{'cruising (20–59 s): std':28s}{statistics.pstdev(cruise_i):11.2f} m/s{statistics.pstdev(cruise_w):11.2f} m/s")
    print(f"{'parked (75–119 s): mean':28s}{statistics.fmean(parked_i):11.2f} m/s{statistics.fmean(parked_w):11.2f} m/s")
    print(f"\nwindow 10 s: first below 1 m/s {lag} s after the stop" if lag is not None else
          "\nwindow 10 s: never below 1 m/s after the stop")
    print(f"odometer (self.distance_m): {tc.distance_m:.0f} m — the vehicle really drove {true_km:.0f} m")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(ts, truth, "k--", lw=1, label="true speed")
    ax.plot([t for t, v in zip(ts, inst) if v is not None], [v for v in inst if v is not None], ".",
            color="0.55", label="window 1 s (fix to fix)")
    ax.plot([t for t, v in zip(ts, win) if v is not None], [v for v in win if v is not None], "-",
            color="tab:blue", lw=2, label=f"window {WINDOW_S:.0f} s")
    ax.axvline(STOP_S, color="tab:red", lw=0.8)
    ax.text(STOP_S + 1, ax.get_ylim()[1] * 0.92, "stop", color="tab:red")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("speed (m/s)")
    ax.set_title(f"Your speed_window() on a noisy GPS (σ {SIGMA_M:.0f} m, 1 fix/s)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("out/drive.png", dpi=90)
    rk.saved("out/drive.png")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    modes = {"test": test, "trace": trace, "drive": drive}
    if mode not in modes:
        sys.exit("usage: python3 run_trip.py test | trace | drive")
    modes[mode]()

#!/usr/bin/env python3
"""make_hidden.py — TEACHER ONLY. Writes courses/29-arbiter/hidden/cases.json: the check's unseen situations
and the course reference's answers (computed here with solutions/29-arbiter/navera_lite, never by check.py).

    python3 solutions/29-arbiter/make_hidden.py          (from the academy root, ROS sourced)
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ACADEMY, "courses", "29-arbiter", "hidden", "cases.json")
os.chdir(HERE)
sys.path.insert(0, HERE)
from navera_lite import arbiter as A                     # noqa: E402
from navera_lite.estimate import Estimate                # noqa: E402
from navera_lite.geo import offset                       # noqa: E402
from navera_lite.settings import DEFAULTS                # noqa: E402

CLOCK0 = 1000.0
TICK = 0.2
P0 = (35.7712, 10.8265)                 # Monastir side of NAVERA's test area


def spec(source, stamp, sigma=None, e=0.0, n=0.0, valid=True, ctype=None, lat=None, lon=None):
    """An estimate as JSON: e/n metres from P0, sigma None → type 0 with zero covariance."""
    if lat is None:
        lat, lon = offset(P0[0], P0[1], e, n)
    if sigma is None:
        cov, ct = [0.0] * 9, 0 if ctype is None else ctype
    else:
        v = float(sigma) ** 2
        cov, ct = [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4.0 * v], 1 if ctype is None else ctype
    return {"source": source, "lat": lat, "lon": lon, "stamp_s": stamp, "cov": cov, "cov_type": ct, "valid": valid}


def est(s):
    return Estimate(s["source"], s["lat"], s["lon"], s["stamp_s"], cov=tuple(s["cov"]), cov_type=s["cov_type"],
                    valid=s["valid"])


def cfg(**over):
    c = dict(DEFAULTS)
    c.update(over)
    return c


NAN = float("nan")

CANDIDATES = [
    {"latest": [spec("gps", 497.1, 3.0), spec("day", 499.0, 30.0, valid=False),
                spec("night", 498.0, None)], "now": 500.0, "cfg": {}},
    {"latest": [spec("day", 497.5, 30.0), spec("celestial", 460.0, 900.0)], "now": 500.0,
     "cfg": {"day_timeout_s": 2.0}},
    {"latest": [spec("gps", 500.4, 3.0), spec("day", 501.2, 30.0)], "now": 500.0, "cfg": {}},
    {"latest": [spec("night", 499.0, 50.0, lat=NAN, lon=10.8)], "now": 500.0, "cfg": {}},
    {"latest": [spec("night", 499.0, None), spec("celestial", 480.0, 2000.0), spec("gps", 499.9, 3.0)],
     "now": 500.0, "cfg": {}},
    {"latest": [spec("gps", 497.0, 3.0), spec("day", 495.0, 30.0)], "now": 500.0, "cfg": {}},
]

TRACK = [
    ({"gps": 10.0}, ["gps"], 12.0),
    ({"gps": 10.0, "day": 5.0}, ["day", "night"], 12.0),
    ({}, ["celestial"], 7.5),
    ({"night": 3.0, "gps": 1.0}, [], 9.0),
]

PICK = [
    (["gps", "day"], "day", {"gps": 50.0, "day": 10.0}, 52.9, {"switch_holdoff_s": 3.0}),
    (["gps", "day"], "day", {"gps": 50.0, "day": 10.0}, 53.0, {"switch_holdoff_s": 3.0}),
    (["day", "night"], "gps", {"day": 99.95, "night": 20.0}, 100.0, {}),
    (["gps", "day", "night"], "night", {"gps": 99.5, "day": 90.0, "night": 80.0}, 100.0, {}),
    (["night", "celestial"], "celestial", {"night": 99.0, "celestial": 1.0}, 100.0, {}),
    (["gps"], None, {"gps": 100.0}, 100.0, {}),
    ([], "day", {}, 5.0, {}),
    (["gps", "day"], "gps", {"gps": 99.9, "day": 50.0}, 100.0, {}),
    (["gps", "day"], "day", {"gps": 100.0, "day": 50.0}, 100.0, {"switch_holdoff_s": 0.0}),
]

# receive: sequences of (estimate spec, now) on ONE Arbiter; cfg overrides per sequence
RECEIVE = [
    {"name": "a stamp 0.6 s ahead (tolerance 0.5 s), then one 0.4 s ahead", "cfg": {},
     "steps": [(spec("gps", 200.6, 3.0), 200.0), (spec("gps", 200.9, 3.0), 200.5)]},
    {"name": "late and duplicate day fixes", "cfg": {},
     "steps": [(spec("day", 300.0, 30.0), 300.5), (spec("day", 299.0, 30.0), 300.8),
               (spec("day", 300.0, 30.0), 301.0), (spec("day", 301.0, 30.0), 301.5)]},
    {"name": "the jump gate with this vehicle's settings (20 m/s + 30 m)", "cfg": {"max_speed_mps": 20.0,
                                                                                  "gps_jump_margin_m": 30.0},
     "steps": [(spec("gps", 400.0, 3.0), 400.0), (spec("gps", 402.0, 3.0, e=100.0), 402.0),
               (spec("gps", 403.0, 3.0, e=60.0), 403.0)]},
    {"name": "a GPS with no position, then a fix", "cfg": {},
     "steps": [(spec("gps", 500.0, None, valid=False, lat=NAN, lon=NAN), 500.0), (spec("gps", 501.0, 3.0), 501.0)]},
    {"name": "a GPS fix with a NaN stamp, then a good one", "cfg": {},
     "steps": [(spec("gps", NAN, 3.0), 900.0), (spec("gps", 900.5, 3.0), 900.5)]},
    {"name": "a source the judge does not know", "cfg": {},
     "steps": [(spec("radar", 600.0, 5.0), 600.0)]},
    {"name": "day vision 5 km away (the jump gate is for GPS only)", "cfg": {},
     "steps": [(spec("day", 700.0, 30.0), 700.0), (spec("day", 701.0, 30.0, e=5000.0), 701.0)]},
    {"name": "a GPS fix 30 s ahead and 800 m off, then honest fixes of a vehicle at 25 m/s", "cfg": {},
     "steps": [(spec("gps", 800.0, 3.0), 800.0), (spec("gps", 831.0, 3.0, e=825.0), 801.0)]
     + [(spec("gps", 800.0 + k, 3.0, e=25.0 * k), 800.0 + k) for k in range(2, 9)]},
]


def run_receive(seq):
    a = A.Arbiter(cfg(**seq["cfg"]))
    out = []
    for s, now in seq["steps"]:
        ok, why = a.receive(est(s), now)
        out.append({"stored": ok, "why": why, "latest": {k: v.stamp_s for k, v in a.latest.items()},
                    "t_recv": a.latest[s["source"]].t_recv_s if ok else None,
                    "refused": sorted(a.refused)})
    return out


# step: sequences of ("r", spec, now) / ("s", now) on one Arbiter
STEP = [
    {"name": "only a refused fix from the future", "cfg": {},
     "ops": [("s", 10.0), ("r", spec("celestial", 40.0, 900.0), 10.0), ("s", 10.2)]},
    {"name": "a day fix that states 12 m, then night vision with no σ", "cfg": {},
     "ops": [("r", spec("day", 49.5, 12.0), 50.0), ("s", 50.0), ("r", spec("night", 51.0, None), 51.2),
             ("s", 55.0), ("s", 57.0)]},
    {"name": "a hold-off of 3 s, GPS back", "cfg": {"switch_holdoff_s": 3.0},
     "ops": [("r", spec("day", 60.0, 30.0), 60.2), ("s", 60.2), ("r", spec("gps", 61.0, 3.0), 61.0), ("s", 61.0),
             ("r", spec("day", 62.0, 30.0), 62.2), ("s", 63.8), ("r", spec("gps", 63.5, 3.0), 63.6), ("s", 64.0),
             ("s", 64.2)]},
    {"name": "a GPS that says no position while it wins", "cfg": {},
     "ops": [("r", spec("gps", 70.0, 3.0), 70.0), ("s", 70.0), ("r", spec("day", 70.5, 30.0), 70.6), ("s", 70.6),
             ("r", spec("gps", 71.0, None, valid=False, lat=NAN, lon=NAN), 71.0), ("s", 71.0)]},
]


def run_step(seq):
    a = A.Arbiter(cfg(**seq["cfg"]))
    out = []
    for op in seq["ops"]:
        if op[0] == "r":
            a.receive(est(op[1]), op[2])
        else:
            d = a.step(op[1])
            out.append({"state": d.state, "source": d.source, "reason": d.reason, "switched": d.switched,
                        "sigma_m": d.sigma_m})
    return {"decisions": out, "switches": [list(s) for s in a.switches], "current": a.current}


# ------------------------------------------------------------------------------ scenarios (offline, unseen)
def row(t, source, e=0.0, n=0.0, sigma=None, valid=1, delay=0.0, speed=0.0):
    lat, lon = offset(P0[0], P0[1], speed * t + e, n)
    if not valid:
        lat = lon = NAN
    v = 0.0 if sigma is None else float(sigma) ** 2
    return {"t_s": round(t, 3), "source": source, "lat": lat, "lon": lon, "a": v, "b": 0.0, "c": v,
            "cov_type": 0 if sigma is None else 1, "valid": int(valid), "delay_s": delay}


def scenario_a():
    """GPS σ 6 m flapping, day σ 18 m (FIX!), a GPS at σ 30 m, night, celestial, a 1 km GPS jump."""
    r = []
    for k in range(10):
        r.append(row(0.6 + 0.5 * k, "gps", sigma=6.0, speed=12.0))
    for k in range(25):
        r.append(row(2.3 + 1.1 * k, "day", e=8.0, n=5.0, sigma=18.0, delay=0.6, speed=12.0))
    for t, v in ((6.1, 1), (6.6, 0), (7.1, 1), (7.6, 1), (8.1, 0), (8.6, 1), (9.1, 1), (9.6, 1), (10.1, 1),
                 (10.6, 1), (11.1, 1)):
        r.append(row(t, "gps", sigma=30.0 if t > 8.8 else 6.0, valid=v, speed=12.0))
    r.append(row(12.1, "gps", e=1000.0, sigma=6.0, speed=12.0))
    for k in range(6):
        r.append(row(15.0 + 2.0 * k, "night", e=-15.0, sigma=None, delay=1.2, speed=12.0))
    r.append(row(29.9, "celestial", e=3000.0, n=-2000.0, sigma=4000.0, delay=10.0, speed=12.0))
    return sorted(r, key=lambda x: x["t_s"])


def scenario_b():
    """GPS dies after one fix stamped 15 s ahead; only celestial fixes after that (45 s timeout)."""
    r = [row(0.5 + k, "gps", sigma=4.0, speed=20.0) for k in range(6)]
    r.append(row(6.5, "gps", sigma=4.0, delay=-15.0, speed=20.0))
    r.append(row(3.0, "celestial", sigma=3000.0, delay=12.0, speed=20.0))
    r.append(row(18.0, "celestial", sigma=3000.0, delay=14.0, speed=20.0))
    r.append(row(7.3, "celestial", sigma=3000.0, delay=-20.0, speed=20.0))
    return sorted(r, key=lambda x: x["t_s"])


def scenario_c():
    """A vehicle at 25 m/s; honest GPS every 0.5 s; ONE GPS fix stamped 12 s ahead and 600 m off at 4.2 s; day."""
    r = [row(0.5 + 0.5 * k, "gps", sigma=3.0, speed=25.0) for k in range(50)]
    r.append(row(4.2, "gps", e=600.0, sigma=3.0, delay=-12.0, speed=25.0))
    r += [row(1.4 + 1.0 * k, "day", e=6.0, sigma=30.0, delay=0.7, speed=25.0) for k in range(24)]
    return sorted(r, key=lambda x: x["t_s"])


def row_est(rw, now):
    a, b, c = rw["a"], rw["b"], rw["c"]
    return Estimate(rw["source"], rw["lat"], rw["lon"], now - rw["delay_s"], cov=(a, b, 0.0, b, c, 0.0, 0.0, 0.0, 0.0),
                    cov_type=rw["cov_type"], valid=bool(rw["valid"]))


def simulate(rows, until, c):
    """The check's driver (same rules as judge_lab.simulate): arrivals first, then ticks every 0.2 s."""
    a = A.Arbiter(c)
    out, i, k = [], 0, 0
    while True:
        tk = round(k * TICK, 6)
        if i < len(rows) and rows[i]["t_s"] <= tk + 1e-9:
            t = rows[i]["t_s"]
            a.receive(row_est(rows[i], CLOCK0 + t), CLOCK0 + t)
            d = a.step(CLOCK0 + t)
            i += 1
        elif tk <= until + 1e-9:
            t = tk
            d = a.step(CLOCK0 + tk)
            k += 1
        else:
            return out, [[round(s[0] - CLOCK0, 6), s[1], s[2]] for s in a.switches]
        out.append([t, d.state, d.source, d.reason])


def summary(out):
    """The decisions where (state, source) changes."""
    res, last = [], None
    for t, state, src, reason in out:
        if (state, src) != last:
            res.append([t, state, src, reason])
            last = (state, src)
    return res


def live_a():
    """The live check's scenario (about 20 s, every event ≥ 0.5 s away from another)."""
    r = [row(0.5 + k, "gps", sigma=3.0, speed=15.0) for k in range(5)]                 # GPS 0.5 … 4.5 s
    r += [row(1.0 + 1.5 * k, "day", e=5.0, sigma=20.0, delay=0.5, speed=15.0) for k in range(13)]   # σ 20: FIX
    r.append(row(9.0, "celestial", sigma=3000.0, delay=-30.0, speed=15.0))             # 30 s ahead
    r += [row(11.2 + k, "gps", sigma=3.0, speed=15.0) for k in range(8)]                # GPS back 11.2 … 18.2 s
    return sorted(r, key=lambda x: x["t_s"])


def experiment_cases():
    """TODO A (holdoff_metrics) on unseen tick lists, TODO B (true_sigma) on unseen values: the solution's answers."""
    import random
    sys.path.insert(1, os.path.join(ACADEMY, "courses", "29-arbiter", "files"))     # runner_kit, judge_lab
    import experiment as ex                           # solutions/29-arbiter/experiment.py (complete)
    rng = random.Random(2903)
    ticks_cases = []
    for n, dur in ((40, 8.0), (300, 60.0), (1500, 300.0)):
        ticks, src = [], "day"
        for k in range(n):
            if rng.random() < 0.15:
                src = rng.choice(["gps", "day", "night", None])
            ticks.append([round(k * 0.2, 6), src, rng.random() < 0.6])
        ticks_cases.append({"ticks": ticks, "duration_s": dur,
                            "want": ex.holdoff_metrics([tuple(t) for t in ticks], dur)})
    sig = [(2.0, 15.0, 0.5), (5.0, 5.0, 1.0), (4.0, 40.0, -0.5), (1.0, 100.0, 0.9), (6.0, 8.0, 0.0)]
    return ticks_cases, [{"args": list(a), "want": ex.true_sigma(*a)} for a in sig]


def main():
    data = {"candidates": [], "track_since": [], "pick": [], "receive": [], "step": [], "scenarios": [], "live": {}}
    for case in CANDIDATES:
        latest = {s["source"]: est(s) for s in case["latest"]}
        data["candidates"].append(dict(case, want=A.candidates(latest, case["now"], cfg(**case["cfg"]))))
    for since, cands, now in TRACK:
        data["track_since"].append({"since": since, "cands": cands, "now": now,
                                    "want": A.track_since(dict(since), cands, now)})
    for cands, cur, since, now, over in PICK:
        data["pick"].append({"cands": cands, "current": cur, "since": since, "now": now, "cfg": over,
                             "want": A.pick(cands, cur, since, now, cfg(**over))})
    for seq in RECEIVE:
        data["receive"].append(dict(seq, want=run_receive(seq)))
    for seq in STEP:
        data["step"].append(dict(seq, want=run_step(seq)))
    for name, fn, until in (("a", scenario_a, 36.0), ("b", scenario_b, 40.0), ("c", scenario_c, 30.0)):
        rows = fn()
        out, sw = simulate(rows, until, cfg())
        data["scenarios"].append({"name": name, "rows": rows, "until": until, "summary": summary(out),
                                  "switches": sw, "doc": fn.__doc__})
    rows = live_a()
    out, sw = simulate(rows, rows[-1]["t_s"] + 6.0, cfg())
    data["live"] = {"rows": rows, "summary": summary(out), "switches": sw}
    data["holdoff_metrics"], data["true_sigma"] = experiment_cases()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, allow_nan=True)
    for sc in data["scenarios"] + [dict(data["live"], name="live")]:
        print(f"--- scenario {sc['name']}")
        for t, state, src, reason in sc["summary"]:
            print(f"   {t:6.2f} {state:8s} {src or '-':9s} {reason[:100]}")
        print("   switches:", sc["switches"])
    print("pick:", [p["want"] for p in data["pick"]])
    print("candidates:", [p["want"] for p in data["candidates"]])


if __name__ == "__main__":
    main()

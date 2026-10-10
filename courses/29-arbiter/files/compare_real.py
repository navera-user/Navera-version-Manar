#!/usr/bin/env python3
"""compare_real.py — race your arbiter against NAVERA's REAL one on the same inputs.

    python3 compare_real.py            # ~35 s: starts the real estimator_node, plays, compares
    python3 compare_real.py --replay   # no ROS: re-compare with the last real_run.json

What it does:
  1. starts the real `estimator_node.py` from YOUR NAVERA copy (~/navera), with the
     product's own settings file estimator_params.yaml, on your private ROS domain;
  2. publishes scripted navera_msgs/PositionEstimate messages on /navera/estimate/gps,
     /day, /night, /cn (the same contract every NAVERA source uses — lesson 12);
  3. records EVERY /navera/nav_status the real arbiter publishes (state, source, reason);
  4. replays exactly the same inputs through YOUR arbiter.py (class Arbiter: receive() on
     each arrival, step() on each arrival and on a 5 Hz clock — like the real node) and
     compares (a) the decisions at 11 moments and (b) the instants of every source switch.

Everything is saved in real_run.json (the check uses it).
You don't need to change this file — but read SCENARIO below: it is the story you play.
"""
import json
import math
import os
import re
import signal
import subprocess
import sys
import time

TICK_S = 0.2                 # the real node decides at publish_rate_hz = 5 Hz (+ on each arrival)
SWITCH_TOLERANCE_S = 0.35    # a switch instant may differ by one tick + scheduling jitter


# ---------------------------------------------------------------- the scenario
# (time s, source, what) — every row is ONE published estimate. Times are seconds after
# the start. "age" makes the stamp older than the publication (a stale message), negative
# = in the future. sigma=None means "uncertainty unknown" (covariance type UNKNOWN).
def _scenario():
    rows = []
    for k in range(15):                                    # GPS good, 1.0 .. 8.0 s
        rows.append((1.0 + 0.5 * k, "gps", dict(sigma=3.0)))
    for k in range(20):                                    # day vision, 3 .. 22 s, accuracy unknown
        rows.append((3.0 + k, "day", dict(sigma=None, lat=35.8259, lon=10.6390)))
    for k in range(7):                                     # GPS back 14 .. 17 s, HDOP 20 (sigma 40 m)
        rows.append((14.0 + 0.5 * k, "gps", dict(sigma=40.0)))
    for k in range(5):                                     # GPS says "invalid" 17.5 .. 19.5 s
        rows.append((17.5 + 0.5 * k, "gps", dict(valid=False, sigma=None, lat=float("nan"), lon=float("nan"))))
    for t in (23.0, 24.0):                                 # night vision, dead-reckoned
        rows.append((t, "night", dict(mode="PROPAGATED", sigma=80.0, lat=35.8262, lon=10.6395)))
    rows.append((25.0, "cn", dict(age=-60.0, sigma=900.0, lat=35.83, lon=10.64)))   # clock 60 s ahead!
    return sorted(rows, key=lambda r: r[0])


SCENARIO = _scenario()
# (time s, what you should think about) — the moments we compare.
SAMPLES = [(0.5, "nothing published yet"),
           (2.0, "GPS only"),
           (5.0, "GPS and day vision"),
           (9.5, "GPS stopped 1.5 s ago"),
           (12.0, "GPS stopped 4 s ago"),
           (15.0, "GPS is back since 1 s"),
           (17.0, "GPS back since 3 s, sigma 40 m"),
           (18.5, "GPS says invalid"),
           (24.5, "day + night (dead-reckoned)"),
           (27.8, "day stopped 5.8 s ago"),
           (30.5, "everything old or wrong")]
END_S = 31.0
# (The positions are NAVERA's test area, Sousse, Tunisia: the real node does not care.)
BASE = dict(valid=True, mode="MEASURED", lat=35.8256, lon=10.6385, sigma=None, age=0.0)


def _cov(sigma):
    if sigma is None:
        return [0.0] * 9, "UNKNOWN"
    v = float(sigma) ** 2
    return [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4.0 * v], "APPROXIMATED"


def events():
    """The scenario as estimate dicts (arbiter.py format) with their publication time."""
    out = []
    for t, src, kw in SCENARIO:
        e = dict(BASE, **kw)
        e["source"] = src
        e["stamp"] = round(t - e.pop("age"), 6)
        e["cov"], e["cov_type"] = _cov(e.pop("sigma"))
        out.append((t, e))
    return out


# ---------------------------------------------------------------- your arbiter, replayed
def run_timeline(arb_module, evs, sample_times, holdoff_s=None, end_s=None):
    """Feed timed estimates to arb_module.Arbiter like the real node does: receive() + step()
    on each arrival, step() on a 5 Hz clock, and a step() at each sample time.
    Returns (decisions at the sample times, the Arbiter object)."""
    kw = {} if holdoff_s is None else {"holdoff_s": holdoff_s}
    a = arb_module.Arbiter(**kw)
    end = max(list(sample_times) + [e[0] for e in evs] + [end_s or 0.0])
    moments = [(t, 0, i) for i, (t, _) in enumerate(evs)]                     # arrivals first
    moments += [(round(k * TICK_S, 6), 1, None) for k in range(int(end / TICK_S) + 2)]
    moments += [(t, 2, None) for t in sample_times]
    moments.sort(key=lambda m: (m[0], m[1]))
    out = {}
    for t, kind, i in moments:
        if kind == 0:
            a.receive(evs[i][1])
        d = _step(a, t)
        if kind == 2:
            out[t] = d
    return out, a


def _step(a, t):
    try:
        d = a.step(t)
    except Exception as e:                      # your code crashed: show it, keep going
        return {"state": "ERROR", "source": None, "reason": f"{type(e).__name__}: {e}"}
    return d if isinstance(d, dict) else {"state": None, "source": None, "reason": repr(d)}


SRC = {0: None, 1: "gps", 2: "day", 3: "night", 4: "cn"}
STATE = {0: "INITIALIZING", 1: "NO_FIX", 2: "FIX", 3: "DEGRADED"}


def same_words(a, b):
    """Reasons compared without their numbers (ages differ by a few ms between runs)."""
    strip = lambda s: re.sub(r"[-0-9.]+", "#", s or "")      # noqa: E731
    return strip(a) == strip(b)


def switches_of(history):
    """[(t, old, new)] from a list of (t, state, source): every change of the source."""
    out, prev = [], None
    for t, _state, src in history:
        if src != prev:
            out.append((t, prev, src))
            prev = src
    return out


# ---------------------------------------------------------------- the real arbiter
def play_real(log=print):
    import rclpy
    from ament_index_python.packages import get_package_share_directory
    from navera_msgs.msg import NavStatus, PositionEstimate
    from rclpy.time import Time

    params = os.path.join(get_package_share_directory("navera_estimator"), "config", "estimator_params.yaml")
    log(f"starting the real arbiter: ros2 run navera_estimator estimator_node.py  (settings: {params})")
    proc = subprocess.Popen(["ros2", "run", "navera_estimator", "estimator_node.py", "--ros-args",
                             "--params-file", params], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                            start_new_session=True)
    rclpy.init()
    node = rclpy.create_node("academy_scenario_player")
    topics = {"gps": "/navera/estimate/gps", "day": "/navera/estimate/day",
              "night": "/navera/estimate/night", "cn": "/navera/estimate/cn"}
    pubs = {s: node.create_publisher(PositionEstimate, t, 10) for s, t in topics.items()}
    status = []
    node.create_subscription(NavStatus, "/navera/nav_status", status.append, 50)
    srcconst = {"gps": PositionEstimate.SOURCE_GPS, "day": PositionEstimate.SOURCE_DAY_VISION,
                "night": PositionEstimate.SOURCE_NIGHT_VISION, "cn": PositionEstimate.SOURCE_CELESTIAL}
    modeconst = {"MEASURED": 0, "PROPAGATED": 1, "HELD": 2, "REPLAYED": 3}
    typeconst = {"UNKNOWN": PositionEstimate.COVARIANCE_TYPE_UNKNOWN,
                 "APPROXIMATED": PositionEstimate.COVARIANCE_TYPE_APPROXIMATED}
    try:
        end = time.time() + 30
        while not status and time.time() < end:
            rclpy.spin_once(node, timeout_sec=0.2)
        if not status:
            raise RuntimeError("the real estimator did not answer within 30 s")
        log("real arbiter is up — playing the scenario (about 31 s)…")
        time.sleep(0.5)
        for _ in range(5):
            rclpy.spin_once(node, timeout_sec=0.05)
        t0 = node.get_clock().now()
        status.clear()
        rel = lambda: (node.get_clock().now() - t0).nanoseconds / 1e9      # noqa: E731
        evs = events()
        i, k, results = 0, 0, []
        while rel() < END_S:
            now = rel()
            while i < len(evs) and evs[i][0] <= now:
                e = evs[i][1]
                m = PositionEstimate()
                stamp = Time(nanoseconds=t0.nanoseconds + int(e["stamp"] * 1e9), clock_type=t0.clock_type)
                m.header.stamp = stamp.to_msg()
                m.sensor_stamp = m.header.stamp
                m.header.frame_id = "academy"
                m.latitude, m.longitude, m.altitude = float(e["lat"]), float(e["lon"]), math.nan
                m.position_covariance = [float(x) for x in e["cov"]]
                m.position_covariance_type = typeconst[e["cov_type"]]
                m.source, m.mode, m.valid = srcconst[e["source"]], modeconst[e["mode"]], bool(e["valid"])
                m.producer = "academy_scenario"
                m.frame_index = -1
                pubs[e["source"]].publish(m)
                i += 1
            rclpy.spin_once(node, timeout_sec=0.02)
            if k < len(SAMPLES) and rel() >= SAMPLES[k][0]:
                s = status[-1]
                st = (Time.from_msg(s.header.stamp) - t0).nanoseconds / 1e9
                results.append(dict(t=SAMPLES[k][0], status_t=round(st, 4), label=SAMPLES[k][1],
                                    state=STATE.get(s.state, str(s.state)), source=SRC.get(s.active_source),
                                    reason=s.reason))
                log(f"  t={SAMPLES[k][0]:5.1f} s  real: {results[-1]['state']:12s} "
                    f"{str(results[-1]['source']):6s} {s.reason}")
                k += 1
        history = []
        for s in status:
            st = (Time.from_msg(s.header.stamp) - t0).nanoseconds / 1e9
            if st >= 0.0:
                history.append([round(st, 4), STATE.get(s.state, str(s.state)), SRC.get(s.active_source)])
        history.sort(key=lambda h: h[0])
        return results, history
    finally:
        try:
            os.killpg(proc.pid, signal.SIGINT)
            proc.wait(timeout=8)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
        node.destroy_node()
        rclpy.try_shutdown()


def compare(arb, real):
    """Decisions at the 11 moments: real vs yours."""
    mine, _ = run_timeline(arb, events(), [r["status_t"] for r in real])
    rows = []
    for r in real:
        d = mine[r["status_t"]]
        rows.append(dict(r, mine_state=d.get("state"), mine_source=d.get("source"), mine_reason=d.get("reason"),
                         same=(d.get("state") == r["state"] and d.get("source") == r["source"]),
                         same_reason=same_words(d.get("reason"), r["reason"])))
    return rows


def compare_switches(arb, history):
    """Switch instants: real (from the recorded nav_status) vs yours. Returns rows
    (real_t, mine_t, old, new, ok) and a list of problems (empty = identical)."""
    real = switches_of([tuple(h) for h in history])
    _, a = run_timeline(arb, events(), [], end_s=END_S)
    mine = [tuple(s) for s in getattr(a, "switches", [])]
    rows, problems = [], []
    for k in range(max(len(real), len(mine))):
        r = real[k] if k < len(real) else None
        m = mine[k] if k < len(mine) else None
        ok = (r is not None and m is not None and r[1:] == tuple(m[1:])
              and abs(r[0] - m[0]) <= SWITCH_TOLERANCE_S)
        rows.append(dict(real_t=r and r[0], mine_t=m and m[0], real=r and f"{r[1]}->{r[2]}",
                         mine=m and f"{m[1]}->{m[2]}", ok=ok))
        if not ok:
            problems.append(f"switch {k + 1}: real {r and f'{r[1]}->{r[2]} at {r[0]:.2f} s'}, "
                            f"yours {m and f'{m[1]}->{m[2]} at {m[0]:.2f} s'}")
    return rows, problems


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    quiet = "--quiet" in sys.argv
    if "--replay" in sys.argv:
        with open("real_run.json") as f:
            data = json.load(f)
        real, history = data["samples"], data["history"]
    else:
        real, history = play_real(log=(lambda *a: None) if quiet else print)
        with open("real_run.json", "w") as f:
            json.dump({"samples": real, "history": history,
                       "scenario": [[t, s, {k: (None if isinstance(v, float) and math.isnan(v) else v)
                                            for k, v in kw.items()}] for t, s, kw in SCENARIO]},
                      f, indent=1)
    import arbiter
    rows = compare(arbiter, real)
    print("\n  t (s)  moment                          REAL arbiter            YOUR arbiter")
    for r in rows:
        mark = "✔" if r["same"] else "✘"
        print(f"  {r['t']:5.1f}  {r['label']:30s}  {r['state']:12s} {str(r['source']):6s}  "
              f"{str(r['mine_state']):12s} {str(r['mine_source']):6s} {mark}")
        if not r["same_reason"]:
            print(f"         real reason: {r['reason']}\n         your reason: {r['mine_reason']}")
    n = sum(r["same"] for r in rows)
    print(f"\n{n} of {len(rows)} decisions identical.")
    srows, problems = compare_switches(arbiter, history)
    print("\n  source switches     REAL t (s)   YOUR t (s)")
    for s in srows:
        rt = f"{s['real_t']:.2f}" if s["real_t"] is not None else "-"
        mt = f"{s['mine_t']:.2f}" if s["mine_t"] is not None else "-"
        print(f"  {str(s['real'] or s['mine']):16s}  {rt:>10s}   {mt:>10s}  {'✔' if s['ok'] else '✘'}")
    print(f"\n{sum(s['ok'] for s in srows)} of {len(srows)} switches identical "
          f"(same order, within {SWITCH_TOLERANCE_S} s). Saved: real_run.json")


if __name__ == "__main__":
    main()

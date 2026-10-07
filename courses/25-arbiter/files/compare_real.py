#!/usr/bin/env python3
"""compare_real.py — play a scripted scenario to NAVERA's REAL arbiter, then to yours.

    python3 compare_real.py            # ~35 s: starts the real estimator_node, plays, compares

What it does:
  1. starts the real `estimator_node.py` from YOUR NAVERA copy (~/navera), with the
     product's own settings file estimator_params.yaml, on your private ROS domain;
  2. publishes scripted navera_msgs/PositionEstimate messages on /navera/estimate/gps,
     /day, /night, /cn (the same contract every NAVERA source uses — lesson 12);
  3. at 10 chosen moments, writes down what the real arbiter said on /navera/nav_status;
  4. replays exactly the same inputs through YOUR arbiter.py and prints both side by side.

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
BASE = dict(valid=True, mode="MEASURED", lat=35.8256, lon=10.6385, sigma=None, age=0.0)


def events():
    """The scenario as estimate dicts (arbiter.py format) with their publication time."""
    out = []
    for t, src, kw in SCENARIO:
        e = dict(BASE, **kw)
        e["source"] = src
        e["stamp"] = round(t - e.pop("age"), 6)
        out.append((t, e))
    return out


# ---------------------------------------------------------------- your arbiter, replayed
def run_timeline(arb, evs, sample_times, step=0.05):
    """Feed timed estimates to arbiter.py like the real node does: keep the latest
    estimate of each source, re-decide every `step` s, remember `active` and
    `eligible_since`. Returns the decision at each sample time."""
    latest, since, active = {}, {}, None
    out, i, k = {}, 0, 0
    ts = sorted(sample_times)
    t = 0.0
    end = max(ts + [e[0] for e in evs]) + step
    while t <= end + 1e-9:
        while i < len(evs) and evs[i][0] <= t + 1e-9:
            e = evs[i][1]
            old = latest.get(e["source"])
            if not (e["source"] == "gps" and old is not None and e["stamp"] < old["stamp"]):
                latest[e["source"]] = e
            i += 1
        while k < len(ts) and ts[k] <= t + 1e-9:
            out[ts[k]] = _decide(arb, latest, since, active, ts[k])
            k += 1
        for src in arb.PRIORITY:
            if src in latest and arb.is_eligible(latest[src], t):
                since.setdefault(src, t)
            else:
                since.pop(src, None)
        d = _decide(arb, latest, since, active, t)
        active = d.get("source") if isinstance(d, dict) else None
        t = round(t + step, 6)
    return out


def _decide(arb, latest, since, active, t):
    ests = [latest[s] for s in arb.PRIORITY if s in latest]
    try:
        d = arb.decide(ests, t, active, dict(since))
    except Exception as e:                      # your code crashed: show it, keep going
        return {"state": "ERROR", "source": None, "reason": f"{type(e).__name__}: {e}"}
    return d if isinstance(d, dict) else {"state": None, "source": None, "reason": repr(d)}


SRC = {0: None, 1: "gps", 2: "day", 3: "night", 4: "cn"}
STATE = {0: "INITIALIZING", 1: "NO_FIX", 2: "FIX", 3: "DEGRADED"}


def same_words(a, b):
    """Reasons compared without their numbers (ages differ by a few ms between runs)."""
    strip = lambda s: re.sub(r"[-0-9.]+", "#", s or "")      # noqa: E731
    return strip(a) == strip(b)


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
    node.create_subscription(NavStatus, "/navera/nav_status", status.append, 10)
    srcconst = {"gps": PositionEstimate.SOURCE_GPS, "day": PositionEstimate.SOURCE_DAY_VISION,
                "night": PositionEstimate.SOURCE_NIGHT_VISION, "cn": PositionEstimate.SOURCE_CELESTIAL}
    modeconst = {"MEASURED": 0, "PROPAGATED": 1, "HELD": 2, "REPLAYED": 3}
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
                if e["sigma"] is None:
                    m.position_covariance = [0.0] * 9
                    m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
                else:
                    v = float(e["sigma"]) ** 2
                    m.position_covariance = [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4 * v]
                    m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
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
        return results
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
    mine = run_timeline(arb, events(), [r["status_t"] for r in real])
    rows = []
    for r in real:
        d = mine[r["status_t"]]
        rows.append(dict(r, mine_state=d.get("state"), mine_source=d.get("source"), mine_reason=d.get("reason"),
                         same=(d.get("state") == r["state"] and d.get("source") == r["source"]),
                         same_reason=same_words(d.get("reason"), r["reason"])))
    return rows


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    quiet = "--quiet" in sys.argv
    real = play_real(log=(lambda *a: None) if quiet else print)
    with open("real_run.json", "w") as f:
        json.dump({"samples": real, "scenario": [[t, s, {k: (None if isinstance(v, float) and math.isnan(v) else v)
                                                         for k, v in kw.items()}] for t, s, kw in SCENARIO]},
                  f, indent=1)
    import arbiter
    rows = compare(arbiter, real)
    print("\n  t (s)  moment                          REAL arbiter                 YOUR arbiter")
    for r in rows:
        mark = "✔" if r["same"] else "✘"
        print(f"  {r['t']:5.1f}  {r['label']:30s}  {r['state']:12s} {str(r['source']):6s}  "
              f"{str(r['mine_state']):12s} {str(r['mine_source']):6s} {mark}")
        if not r["same_reason"]:
            print(f"         real reason: {r['reason']}\n         your reason: {r['mine_reason']}")
    n = sum(r["same"] for r in rows)
    print(f"\n{n} of {len(rows)} decisions identical. Saved: real_run.json")


if __name__ == "__main__":
    main()

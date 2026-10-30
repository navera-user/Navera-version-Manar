#!/usr/bin/env python3
"""Teacher only — makes datasets/32-measuring/ (deterministic). Run from the academy root, ROS 2 sourced
(the bag is written with rosbag2_py):

    source /opt/ros/humble/setup.bash && python3 solutions/32-measuring/make_dataset.py

Everything is synthetic and made with NAVERA Lite only (the course reference in solutions/_navera_lite):
the decisions in the flight tables are those of the reference judge (navera_lite.arbiter, mission 29) fed
with simulated sources. No NAVERA code, output or file is used.

  flight_target.csv     240 s over the Sousse test area at 15 m/s; GPS jammed 90–149 s; day vision with the
                        "target" error profile (AR(1) per axis, σ 12 m, ρ 0.9 per s, stated σ 30 m); no match
                        for 14 s over a lake (115–128 s) and 5 % of single frames missed.
  flight_retrieval.csv  the same truth, GPS and jam; day vision with a retrieval-like error profile
                        (AR(1), σ 370 m per axis — a median near 440 m —, ρ 0.8, stated σ 300 m), every frame.
  flight_selective.csv  flight_retrieval with every vision position more than 300 m from the truth WITHHELD
                        (as if a perfect "am I wrong?" test existed): the availability trap.
  shadow_bag/           a ROS 2 bag (sqlite3): /navera_lite/fix/gps (1 Hz, true error 1.5 m per axis, states
                        2 m) and /navera_lite/fix/day (1 Hz at half seconds, STATES 15 m while its true error
                        is 22 m per axis; 10 % "no match" messages) — 300 s of shadow mode with GPS good.
  shadow_truth.csv      the truth of the bag's flight at 10 Hz (stamp_s on the bag's clock).

Columns of the flight tables: t_s, gps (ok / jammed), state, source, sigma_m, lat, lon, truth_lat, truth_lon.
"""
import csv
import math
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite.arbiter import Arbiter                      # noqa: E402
from navera_lite.estimate import COV_APPROXIMATED, Estimate   # noqa: E402
from navera_lite.geo import offset                            # noqa: E402
from navera_lite.logbook import haversine_m                   # noqa: E402
from navera_lite.settings import DEFAULTS                     # noqa: E402

OUT = os.path.join(ACADEMY, "datasets", "32-measuring")
LAT0, LON0 = 35.8256, 10.6084            # start of the route, Sousse test area
SPEED = 15.0                             # m/s
WAYPOINTS = [(0.0, 0.0), (1500.0, 900.0), (2200.0, 2600.0), (1400.0, 3600.0)]   # east, north (m)
DURATION = 240                           # s, one row per second
JAM = (90, 150)                          # GPS jammed for 90 <= t < 150
LAKE = (115, 129)                        # target vision: no match for 115 <= t < 129
T0 = 1_791_000_000.0                     # the bag's clock (an arbitrary epoch)


def track_en(t):
    """East, north (m) of the truth at time t (s): the route at constant speed."""
    d = SPEED * t
    for (e0, n0), (e1, n1) in zip(WAYPOINTS, WAYPOINTS[1:]):
        seg = math.hypot(e1 - e0, n1 - n0)
        if d <= seg:
            return e0 + (e1 - e0) * d / seg, n0 + (n1 - n0) * d / seg
        d -= seg
    return WAYPOINTS[-1]


def ar1(rng, n, rho, sigma):
    """n × 2 AR(1) errors (east, north), stationary σ per axis."""
    k = math.sqrt(1 - rho * rho)
    e = np.empty((n, 2))
    e[0] = rng.normal(0, sigma, 2)
    for i in range(1, n):
        e[i] = rho * e[i - 1] + k * rng.normal(0, sigma, 2)
    return e


def cov(sigma):
    v = sigma * sigma
    return (v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4 * v)


def fly(vision_err, vision_sigma, vision_ok):
    """The flight table: the reference judge at every second, fed with GPS and day-vision fixes."""
    rng_gps = np.random.default_rng(3201)
    gps_err = ar1(rng_gps, DURATION, 0.95, 1.5)
    judge = Arbiter(DEFAULTS)
    rows = []
    for t in range(DURATION):
        te, tn = track_en(t)
        tlat, tlon = offset(LAT0, LON0, te, tn)
        jammed = JAM[0] <= t < JAM[1]
        if jammed:
            g = Estimate("gps", math.nan, math.nan, float(t), valid=False, reason="no fix")
        else:
            glat, glon = offset(LAT0, LON0, te + gps_err[t, 0], tn + gps_err[t, 1])
            g = Estimate("gps", glat, glon, float(t), cov=cov(2.0), cov_type=COV_APPROXIMATED)
        judge.receive(g, float(t))
        if vision_ok[t]:
            vlat, vlon = offset(LAT0, LON0, te + vision_err[t, 0], tn + vision_err[t, 1])
            judge.receive(Estimate("day", vlat, vlon, float(t), cov=cov(vision_sigma), cov_type=COV_APPROXIMATED),
                          float(t))
        d = judge.step(float(t))
        has = d.estimate is not None
        rows.append({"t_s": t, "gps": "jammed" if jammed else "ok", "state": d.state, "source": d.source or "",
                     "sigma_m": f"{d.sigma_m:.1f}" if d.sigma_m is not None else "",
                     "lat": f"{d.estimate.lat:.7f}" if has else "", "lon": f"{d.estimate.lon:.7f}" if has else "",
                     "truth_lat": f"{tlat:.7f}", "truth_lon": f"{tlon:.7f}"})
    return rows


def write(name, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def selective(rows, limit_m=300.0):
    out, n = [], 0
    for r in rows:
        r = dict(r)
        if r["source"] == "day":
            e = haversine_m(float(r["truth_lat"]), float(r["truth_lon"]), float(r["lat"]), float(r["lon"]))
            if e > limit_m:
                r.update(state="NO_FIX", source="", sigma_m="", lat="", lon="")
                n += 1
        out.append(r)
    return out, n


def make_bag(path):
    import rosbag2_py
    from rclpy.serialization import serialize_message
    from navera_lite.ros.convert import to_navsatfix

    rng = np.random.default_rng(3203)
    if os.path.exists(path):
        shutil.rmtree(path)
    w = rosbag2_py.SequentialWriter()
    w.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"), rosbag2_py.ConverterOptions("cdr", "cdr"))
    for src in ("gps", "day"):
        w.create_topic(rosbag2_py.TopicMetadata(name=f"/navera_lite/fix/{src}", type="sensor_msgs/msg/NavSatFix",
                                                serialization_format="cdr"))
    truth = []
    n = 300
    for k in range(10 * n + 1):
        t = k / 10.0
        lat, lon = offset(LAT0, LON0, *track_en(t))
        truth.append({"stamp_s": f"{T0 + t:.1f}", "truth_lat": f"{lat:.7f}", "truth_lon": f"{lon:.7f}"})
    for i in range(n):
        for src, t, sig_true, sig_stated in (("gps", float(i), 1.5, 2.0), ("day", i + 0.5, 22.0, 15.0)):
            te, tn = track_en(t)
            de, dn = rng.normal(0, sig_true, 2)
            if src == "day" and rng.random() < 0.10:
                est = Estimate("day", math.nan, math.nan, T0 + t, valid=False, reason="no match")
            else:
                lat, lon = offset(LAT0, LON0, te + de, tn + dn)
                est = Estimate(src, lat, lon, T0 + t, cov=cov(sig_stated), cov_type=COV_APPROXIMATED)
            w.write(f"/navera_lite/fix/{src}", serialize_message(to_navsatfix(est)), int(round((T0 + t + 0.05) * 1e9)))
    del w
    return truth


README = """# Mission 32 — measuring

Synthetic data in NAVERA's test area, Sousse (Tunisia). Every number is synthetic.

- `flight_target.csv`, `flight_retrieval.csv`, `flight_selective.csv`: three versions of one 240 s drone
  flight, one row per second, with the decisions of NAVERA Lite's judge and the true position.
  Columns: `t_s, gps, state, source, sigma_m, lat, lon, truth_lat, truth_lon` (degrees; empty = no position).
- `shadow_bag/`: a ROS 2 bag of `sensor_msgs/NavSatFix` on `/navera_lite/fix/gps` and `/navera_lite/fix/day`
  (300 s, GPS working, both sources recorded).
- `shadow_truth.csv`: the true position of the bag's flight, 10 per second (`stamp_s` on the bag's clock).
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    for old in ("flight_measured.csv", "make_dataset.py"):
        if os.path.exists(os.path.join(OUT, old)):
            os.remove(os.path.join(OUT, old))
    rng = np.random.default_rng(3202)
    target_err = ar1(rng, DURATION, 0.9, 12.0)
    target_ok = rng.random(DURATION) >= 0.05
    target_ok[LAKE[0]:LAKE[1]] = False
    # its own seed, chosen (teacher note) so that the jam median lands near NAVERA's documented situation:
    # a little better than repeating the last GPS position, by a margin the confidence interval cannot confirm
    retr_err = ar1(np.random.default_rng(3310), DURATION, 0.8, 370.0)
    target = fly(target_err, 30.0, target_ok)
    retrieval = fly(retr_err, 300.0, np.ones(DURATION, bool))
    sel, n = selective(retrieval)
    write("flight_target.csv", target)
    write("flight_retrieval.csv", retrieval)
    write("flight_selective.csv", sel)
    truth = make_bag(os.path.join(OUT, "shadow_bag"))
    with open(os.path.join(OUT, "shadow_truth.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(truth[0]))
        w.writeheader()
        w.writerows(truth)
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write(README)
    print(f"written to {OUT}: {sorted(os.listdir(OUT))}; selective: {n} vision positions withheld")


if __name__ == "__main__":
    main()

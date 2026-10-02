#!/usr/bin/env python3
"""Measure each NAVERA source against GPS in a recorded session.

    python3 navera_tools/evaluate_session.py <bag_dir> [--max-gap 2.0] [--csv out.csv]

Ground truth is the GPS estimate (/navera/estimate/gps, valid fixes only),
interpolated at each vision/celestial estimate's measurement instant
(sensor_stamp). Estimates further than --max-gap seconds from a GPS fix are
not scored. Reports, per source and per mode (measured / dead-reckoned):
number of estimates, median / p90 / max error, share within 50 / 100 / 300 m,
and how many frames produced no position. Then, for estimates that STATE an
accuracy (vision matches, dead-reckoning): how often the true error is within 1, 2
and 3 x that stated sigma (an honest Gaussian sigma: ~39 / 86 / 99 % for a 2-D error),
and the sigma that WOULD be honest (p86 of error / 2) — the value to set as
NAVERA_DEGRADED_SIGMA_M / the day matcher's local_sigma_m. This is how accuracy claims
in docs/VALIDATION_STATUS.md must be produced from real data.
"""
import argparse
import bisect
import csv
import math
import sys

import rosbag2_py
from rclpy.serialization import deserialize_message

from navera_msgs.msg import PositionEstimate

SOURCES = {"/navera/estimate/day": "day", "/navera/estimate/night": "night",
           "/navera/estimate/cn": "celestial"}
MODES = {PositionEstimate.MODE_MEASURED: "measured", PositionEstimate.MODE_PROPAGATED: "dead-reckoned"}


def stamp_s(t) -> float:
    return t.sec + t.nanosec * 1e-9


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))


def read(bag_dir):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag_dir, storage_id=""),
                rosbag2_py.ConverterOptions("cdr", "cdr"))
    reader.set_filter(rosbag2_py.StorageFilter(topics=["/navera/estimate/gps", *SOURCES]))
    gps, est = [], []
    while reader.has_next():
        topic, data, _ = reader.read_next()
        m = deserialize_message(data, PositionEstimate)
        t = stamp_s(m.sensor_stamp) if (m.sensor_stamp.sec or m.sensor_stamp.nanosec) \
            else stamp_s(m.header.stamp)
        if topic == "/navera/estimate/gps":
            if m.valid and math.isfinite(m.latitude):
                gps.append((t, m.latitude, m.longitude))
        else:
            est.append((topic, t, m))
    gps.sort()
    return gps, est


def truth_at(gps, t, max_gap):
    """GPS position interpolated at t, or None if no fix within max_gap."""
    times = [g[0] for g in gps]
    i = bisect.bisect_left(times, t)
    if 0 < i < len(gps):
        (t0, la0, lo0), (t1, la1, lo1) = gps[i - 1], gps[i]
        if t - t0 <= max_gap and t1 - t <= max_gap:
            w = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return la0 + w * (la1 - la0), lo0 + w * (lo1 - lo0)
    for j in (i - 1, i):
        if 0 <= j < len(gps) and abs(gps[j][0] - t) <= max_gap:
            return gps[j][1], gps[j][2]
    return None


def pct(v, q):
    s = sorted(v)
    return s[min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bag")
    ap.add_argument("--max-gap", type=float, default=2.0)
    ap.add_argument("--csv")
    a = ap.parse_args()
    gps, est = read(a.bag)
    if len(gps) < 2:
        print("not enough valid GPS fixes in the session to use as ground truth")
        return 1
    rows, groups, invalid, stated = [], {}, {}, {}
    for topic, t, m in est:
        src = SOURCES[topic]
        if not m.valid:
            invalid[src] = invalid.get(src, 0) + 1
            continue
        truth = truth_at(gps, t, a.max_gap)
        if truth is None:
            continue
        err = haversine_m(truth[0], truth[1], m.latitude, m.longitude)
        mode = MODES.get(m.mode, str(m.mode))
        groups.setdefault((src, mode), []).append(err)
        sig = (math.sqrt(max(m.position_covariance[0], m.position_covariance[4]))
               if m.position_covariance_type != PositionEstimate.COVARIANCE_TYPE_UNKNOWN else None)
        if sig:
            stated.setdefault((src, mode), []).append((err, sig))
        rows.append((src, mode, m.frame_index, f"{t:.3f}", f"{err:.1f}", f"{sig:.1f}" if sig else ""))

    print(f"ground truth: {len(gps)} GPS fixes over {gps[-1][0] - gps[0][0]:.0f} s")
    print(f"{'source':10s} {'mode':14s} {'n':>5s} {'median':>8s} {'p90':>8s} {'max':>8s} "
          f"{'<50m':>6s} {'<100m':>6s} {'<300m':>6s}")
    for (src, mode), errs in sorted(groups.items()):
        within = [100.0 * sum(e < d for e in errs) / len(errs) for d in (50, 100, 300)]
        print(f"{src:10s} {mode:14s} {len(errs):5d} {pct(errs, 50):7.0f}m {pct(errs, 90):7.0f}m "
              f"{max(errs):7.0f}m {within[0]:5.0f}% {within[1]:5.0f}% {within[2]:5.0f}%")
    for src, n in sorted(invalid.items()):
        print(f"{src:10s} no position  {n:5d}")
    if stated:
        print("\nstated accuracy vs truth (honest 2-D sigma: ~39 / 86 / 99 %)")
        print(f"{'source':10s} {'mode':14s} {'n':>5s} {'stated':>8s} {'<1s':>6s} {'<2s':>6s} {'<3s':>6s} "
              f"{'honest sigma':>13s}")
        for (src, mode), es in sorted(stated.items()):
            within = [100.0 * sum(e <= k * s for e, s in es) / len(es) for k in (1, 2, 3)]
            honest = pct([e for e, _ in es], 86) / 2.0
            print(f"{src:10s} {mode:14s} {len(es):5d} {pct([s for _, s in es], 50):7.0f}m "
                  f"{within[0]:5.0f}% {within[1]:5.0f}% {within[2]:5.0f}% {honest:12.0f}m"
                  + ("   <- stated sigma too optimistic" if within[1] < 80 else ""))
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["source", "mode", "frame_index", "sensor_time_s", "error_m", "stated_sigma_m"])
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())

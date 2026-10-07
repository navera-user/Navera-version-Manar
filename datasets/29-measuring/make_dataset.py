#!/usr/bin/env python3
"""Make the lesson-29 dataset from the two flights recorded with the mission simulator.

    python3 make_dataset.py <flight_target.csv> <flight_measured.csv> <out_dir>

1. flight_target.csv / flight_measured.csv: the flights recorded by lesson 28's
   `sim_ctl.py record` (record_sample.sh in /data/academy/28-simulator), copied WITHOUT the
   simulator's own error columns (navera_err_m, ap_err_m): the students compute the errors.
   - target:   simulated vision "target" profile (stated sigma 15 m — not a measured performance)
   - measured: simulated vision "former day vision" profile (~440 m median, uncertainty unknown)
   Both: drone over Sousse, GPS jammed 60 s then spoofed (2 km jump) 30 s. SIMULATION ONLY.
2. shadow_bag/: a small ROS 2 bag for navera_tools/evaluate_session.py, SYNTHESISED from the
   true track of the target flight (en route part): /navera/estimate/gps (valid, sigma 1.5 m,
   noise 1.5 m per axis) and /navera/estimate/day (1 per second, STATING sigma 15 m while its
   real errors are drawn with 22 m per axis — an over-optimistic source, on purpose).
Needs a sourced ROS 2 + NAVERA workspace (run it in a sandbox).
"""
import csv
import math
import os
import random
import sys

DROP = ("navera_err_m", "ap_err_m")


def copy_flight(src, dst):
    with open(src, newline="") as f:
        rows = list(csv.DictReader(f))
    cols = [c for c in rows[0].keys() if c not in DROP]
    with open(dst, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return rows


def make_bag(rows, out):
    import rosbag2_py
    from rclpy.serialization import serialize_message
    from builtin_interfaces.msg import Time
    from navera_msgs.msg import PositionEstimate

    rng = random.Random(29)
    w = rosbag2_py.SequentialWriter()
    w.open(rosbag2_py.StorageOptions(uri=out, storage_id="sqlite3"),
           rosbag2_py.ConverterOptions("cdr", "cdr"))
    for name in ("/navera/estimate/gps", "/navera/estimate/day"):
        w.create_topic(rosbag2_py.TopicMetadata(name=name, type="navera_msgs/msg/PositionEstimate",
                                                serialization_format="cdr"))
    t0 = 1_791_000_000.0                               # an arbitrary epoch for the stamps
    m_lat = 111_195.0
    for r in rows:
        if r["phase"] != "enroute" or not r["truth_lat"]:
            continue
        t = t0 + float(r["t_s"])
        lat, lon = float(r["truth_lat"]), float(r["truth_lon"])
        m_lon = m_lat * math.cos(math.radians(lat))
        for topic, src, sig_true, sig_stated, dt in (("/navera/estimate/gps", PositionEstimate.SOURCE_GPS, 1.5, 1.5, 0.0),
                                                     ("/navera/estimate/day", PositionEstimate.SOURCE_DAY_VISION, 22.0, 15.0, 0.5)):
            m = PositionEstimate()
            ts = t + dt
            st = Time(sec=int(ts), nanosec=int((ts % 1) * 1e9))
            m.header.stamp, m.sensor_stamp = st, st
            m.latitude = lat + rng.gauss(0, sig_true) / m_lat
            m.longitude = lon + rng.gauss(0, sig_true) / m_lon
            m.altitude = math.nan
            v = sig_stated ** 2
            m.position_covariance = [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4 * v]
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
            m.source, m.mode, m.valid = src, PositionEstimate.MODE_MEASURED, True
            m.producer = "academy_synthetic"
            m.frame_index = -1
            w.write(topic, serialize_message(m), int(ts * 1e9))
    del w


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    target, measured, out = sys.argv[1:]
    os.makedirs(out, exist_ok=True)
    rows = copy_flight(target, os.path.join(out, "flight_target.csv"))
    copy_flight(measured, os.path.join(out, "flight_measured.csv"))
    make_bag(rows, os.path.join(out, "shadow_bag"))
    print("written:", sorted(os.listdir(out)))


if __name__ == "__main__":
    main()

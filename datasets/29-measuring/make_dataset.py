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
3. flight_selective.csv: SYNTHETIC, derived from flight_measured.csv (no simulator needed):
   every DAY VISION position more than 300 m from the truth is removed (state "NO FIX", no
   position), as if a perfect "am I wrong?" test existed. It shows the availability trap:
   a smaller error, computed on fewer seconds.
       python3 make_dataset.py --derive <out_dir>      (re-makes only this file)
Steps 1-2 need a sourced ROS 2 + NAVERA workspace (run them in a sandbox).
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


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))


def derive_selective(out, limit_m=300.0):
    src, dst = os.path.join(out, "flight_measured.csv"), os.path.join(out, "flight_selective.csv")
    with open(src, newline="") as f:
        rows = list(csv.DictReader(f))
    n = 0
    for r in rows:
        if r["navera_source"] == "DAY VISION" and r["navera_lat"] and r["truth_lat"]:
            e = haversine_m(float(r["truth_lat"]), float(r["truth_lon"]),
                            float(r["navera_lat"]), float(r["navera_lon"]))
            if e > limit_m:
                r.update(navera_state="NO FIX", navera_source="\u2014", navera_lat="", navera_lon="",
                         reason="synthetic: vision position withheld (more than 300 m from the truth)")
                n += 1
    with open(dst, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"flight_selective.csv: {n} vision positions withheld")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--derive":
        derive_selective(sys.argv[2])
        return
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    target, measured, out = sys.argv[1:]
    os.makedirs(out, exist_ok=True)
    rows = copy_flight(target, os.path.join(out, "flight_target.csv"))
    copy_flight(measured, os.path.join(out, "flight_measured.csv"))
    make_bag(rows, os.path.join(out, "shadow_bag"))
    derive_selective(out)
    print("written:", sorted(os.listdir(out)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""evaluate_session.py on a recording with known errors: GPS truth, day-vision fixes 20 m
off stating 30 m (honest) and dead-reckoned ones 300 m off stating 50 m (optimistic).
Exit code 0 = pass."""
import math
import os
import subprocess
import sys
import tempfile

import rosbag2_py
from builtin_interfaces.msg import Time
from rclpy.serialization import serialize_message

from navera_msgs.msg import PositionEstimate

HERE = os.path.dirname(os.path.abspath(__file__))
M = 1.0 / 111195.0


def est(t, lat, lon, source, mode, sigma=None):
    m = PositionEstimate()
    m.header.stamp = m.sensor_stamp = Time(sec=int(t), nanosec=int((t % 1) * 1e9))
    m.latitude, m.longitude, m.altitude, m.valid = lat, lon, math.nan, True
    m.source, m.mode = source, mode
    if sigma:
        v = sigma ** 2
        m.position_covariance = [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 0.0]
        m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
    return m


def main():
    bag = os.path.join(tempfile.mkdtemp(prefix="navera_eval_"), "bag")
    w = rosbag2_py.SequentialWriter()
    w.open(rosbag2_py.StorageOptions(uri=bag, storage_id="sqlite3"), rosbag2_py.ConverterOptions("cdr", "cdr"))
    for name in ("/navera/estimate/gps", "/navera/estimate/day"):
        w.create_topic(rosbag2_py.TopicMetadata(name=name, type="navera_msgs/msg/PositionEstimate",
                                                serialization_format="cdr"))
    t0 = 1_790_000_000.0
    for i in range(200):
        t = t0 + i * 0.5
        lat = 35.8 + 5.0 * i * 0.5 * M                    # flying north at 5 m/s
        w.write("/navera/estimate/gps", serialize_message(
            est(t, lat, 10.6, PositionEstimate.SOURCE_GPS, PositionEstimate.MODE_MEASURED, 2.0)), int(t * 1e9))
        if i % 2 == 0 and i < 120:
            w.write("/navera/estimate/day", serialize_message(est(
                t, lat + 20.0 * M, 10.6, PositionEstimate.SOURCE_DAY_VISION, PositionEstimate.MODE_MEASURED, 30.0)),
                int(t * 1e9))
        elif i % 2 == 0:
            w.write("/navera/estimate/day", serialize_message(est(
                t, lat + 300.0 * M, 10.6, PositionEstimate.SOURCE_DAY_VISION, PositionEstimate.MODE_PROPAGATED, 50.0)),
                int(t * 1e9))
    del w
    r = subprocess.run([sys.executable, os.path.join(HERE, "..", "evaluate_session.py"), bag],
                       capture_output=True, text=True)
    out = r.stdout
    fails = []
    meas = [l for l in out.splitlines() if l.startswith("day") and "measured" in l]
    dr = [l for l in out.splitlines() if l.startswith("day") and "dead-reckoned" in l]
    if len(meas) != 2 or " 20m" not in meas[0]:
        fails.append(f"measured error not 20 m: {meas}")
    if not meas or "too optimistic" in meas[-1] or "100%" not in meas[-1]:
        fails.append(f"honest 30 m sigma judged wrong: {meas}")
    if len(dr) != 2 or "too optimistic" not in dr[-1] or " 150m" not in dr[-1]:
        fails.append(f"optimistic 50 m sigma not flagged with an honest 150 m: {dr}")
    for f in fails:
        print("FAIL", f)
    if fails:
        print(out, r.stderr[-500:])
    print("evaluate_session:", "PASS" if not fails else f"{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

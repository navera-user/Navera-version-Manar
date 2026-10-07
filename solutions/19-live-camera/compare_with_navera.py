#!/usr/bin/env python3
# Lesson 19 — is YOUR attitude_at() the same as NAVERA's?
# NAVERA's live camera reads the attitude of every frame with
#     self.att = History(maxlen=4000, max_gap_s=0.2, interp=slerp)      (live_camera.py)
#     self.att.at(t)                                                      t = exposure time
# from navera_common/sensor_history.py in your NAVERA copy. This script feeds the same IMU
# log to both and compares them at every exposure of turn_frames.csv.
#
#     python3 compare_with_navera.py
# Careful: NAVERA (like ROS) stores quaternions as (x, y, z, w); we use (w, x, y, z).
# You don't need to change this file.
import json
import os
import sys

import numpy as np

import camera_tools as ct

sys.path.insert(0, os.path.expanduser("~/navera/navera_common"))
from navera_common.sensor_history import History, slerp as navera_slerp   # noqa: E402

imu = ct.read_csv(ct.DATA + "/turn_imu.csv")
it = [float(r["t_s"]) for r in imu]
iq = [np.array([float(r["qw"]), float(r["qx"]), float(r["qy"]), float(r["qz"])]) for r in imu]

hist = History(maxlen=4000, max_gap_s=0.2, interp=navera_slerp)
for t, q in zip(it, iq):
    w, x, y, z = q
    hist.add(t, (x, y, z, w))                          # NAVERA's order

lat = ct.load_latency(ct.CALIB)
if lat is None or ct.exposure_time(1.0, 0.1) is None or ct.quat_angle_deg(iq[0], iq[0]) is None:
    sys.exit("finish TODO 3, 4 and 6 of camera_tools.py first")
both_none, mismatch, diffs = 0, 0, []
for r in ct.read_csv(ct.DATA + "/turn_frames.csv"):
    e = ct.exposure_time(float(r["grab_time_s"]), lat)
    mine = ct.attitude_at(e, it, iq, 0.2)
    theirs = hist.at(e)
    if mine is None and theirs is None:
        both_none += 1
        continue
    if (mine is None) != (theirs is None):
        mismatch += 1
        print(f"t={e:.3f}: yours {'None' if mine is None else 'a value'}, NAVERA "
              f"{'None' if theirs is None else 'a value'}")
        continue
    x, y, z, w = theirs
    diffs.append(ct.quat_angle_deg(mine, np.array([w, x, y, z])))

out = {"frames_compared": len(diffs), "both_unusable": both_none, "disagree_on_unusable": mismatch,
       "max_diff_deg": max(diffs) if diffs else None}
print(json.dumps(out, indent=1))
os.makedirs("out", exist_ok=True)
with open("out/navera_compare.json", "w") as f:
    json.dump(out, f, indent=1)
if mismatch == 0 and diffs and max(diffs) < 1e-4:
    print("✔ your attitude_at() gives NAVERA's attitude at every exposure")
else:
    print("✘ not the same as NAVERA yet — compare your rules with History.at()")

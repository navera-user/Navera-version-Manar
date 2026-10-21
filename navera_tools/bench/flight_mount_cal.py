#!/usr/bin/env python3
"""Camera mount (boresight) of a recorded flight, measured against the map with the GPS truth.

    python3 navera_tools/bench/flight_mount_cal.py FLIGHT_DIR --area AREA_IMAGES_DIR --site am|hk \
        [--from-s 0 --to-s 120 --step-s 3] [--mount r,p,y]

What an installer does once per vehicle (NAVERA's camera node takes mount_roll/pitch/yaw_deg):
frames of the first minutes are matched around the RTK position (DISK + LightGlue, heading
searched every 30 deg, so the fitted rotation is the frame top's true azimuth) and compared with
what FrameBuilder computes from the attitude for the given mount:
  yaw   = median(fitted azimuth - FrameBuilder heading)
  pitch/roll: the straightened frame's centre (frame centre, no pose) must be the point under
        the camera; the median offset of the match from the RTK position, expressed along / across
        the image top, divided by the height, is the remaining tilt of the camera (atan).
Run it again with --mount set to the result to check the residuals vanish.
"""
import argparse
import csv
import json
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common"), HERE):
    sys.path.insert(0, p)

from replay_flight_dataset import MARS_CAMERAS, MARS_SIZE, Interp  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("flight")
    ap.add_argument("--area", required=True)
    ap.add_argument("--site", required=True, choices=sorted(MARS_CAMERAS))
    ap.add_argument("--mount", default="0,0,0")
    ap.add_argument("--from-s", type=float, default=0.0)
    ap.add_argument("--to-s", type=float, default=120.0)
    ap.add_argument("--step-s", type=float, default=3.0)
    ap.add_argument("--min-height", type=float, default=30.0, help="m above take-off: frames below are skipped")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    from day_pkg.learned_matcher import LearnedMatcher
    from navera_common.camera_model import CameraModel
    from navera_common.frame_builder import FrameBuilder
    from navera_common.sensor_history import History, slerp

    rows = list(csv.DictReader(open(os.path.join(a.flight, "frames.csv"))))
    S = np.load(os.path.join(a.flight, "sensors.npz"))
    info = json.load(open(os.path.join(a.flight, "info.json")))
    ft = np.array([float(r["t"]) for r in rows])
    rtk = Interp(S["rtk"], [1, 2, 3])
    # height above take-off: the RTK altitude minus its first sample (on the ground); the DJI
    # height_above_takeoff topic of MARS-LVIG reads 0 in flight
    rel = Interp(np.column_stack([S["rtk"][:, 0], S["rtk"][:, 3] - S["rtk"][0, 3]]), [1])
    att = History(maxlen=10 ** 6, max_gap_s=0.2, interp=slerp)
    for r in S["att"]:
        att.add(float(r[0]), tuple(r[1:5]))
    c = MARS_CAMERAS[a.site]
    w, h = info["image_size"]
    sc = w / MARS_SIZE[0]
    cam = CameraModel([[c["fx"] * sc, 0, c["cx"] * sc], [0, c["fy"] * sc, c["cy"] * sc], [0, 0, 1]], c["d"],
                      (w, h), "pinhole")
    mount = tuple(float(v) for v in a.mount.split(","))
    fb = FrameBuilder(cam, mount, max_tilt_deg=45.0)
    m = LearnedMatcher(a.area, min_inliers=8, scale_tol=0.25, pose_tilt_guard_deg=4.0)
    out = []
    t = ft[0] + a.from_s
    while t <= ft[0] + a.to_s:
        i = int(np.searchsorted(ft, t))
        t += a.step_s
        if i >= len(ft):
            break
        te = ft[i]
        q, tr, hh = att.at(te), rtk.at(te), rel.at(te)
        if q is None or tr is None or hh is None or hh[0] < a.min_height:
            continue
        img = cv2.imread(os.path.join(a.flight, "frames", rows[i]["file"]))
        out_img, meta = fb.build(img, i, int(te * 1e9), q, "imu", (float(hh[0]), 3.0, "rel"))
        if not meta["usable"]:
            continue
        mpp = m.frame_m_per_px(w, float(hh[0]), meta["camera_hfov_deg"])
        res = m.locate(out_img, (float(tr[0]), float(tr[1])), 150.0, mpp, scale_tol=0.3, heading_deg=None,
                       heading_search=True)
        if not res.get("accepted"):
            print(f"t {te - ft[0]:6.1f} no match: {str(res.get('reason'))[:80]}", flush=True)
            continue
        dn = (res["predicted_lat"] - tr[0]) * 111320.0
        de = (res["predicted_lon"] - tr[1]) * 111320.0 * math.cos(math.radians(tr[0]))
        hdg = meta["heading_deg"]
        a_rad = math.radians(hdg)
        along = de * math.sin(a_rad) + dn * math.cos(a_rad)            # towards the image top
        across = de * math.cos(a_rad) - dn * math.sin(a_rad)           # towards the image right
        dyaw = (res["rotation_deg"] - hdg + 180.0) % 360.0 - 180.0
        rec = dict(t=round(te - ft[0], 1), height=round(float(hh[0]), 1), tilt=meta["tilt_deg"], heading=hdg,
                   rot=res["rotation_deg"], dyaw=round(dyaw, 2), along=round(along, 2), across=round(across, 2),
                   err=round(math.hypot(de, dn), 2), inliers=res.get("inliers"), scale=res.get("scale_residual"),
                   along_deg=round(math.degrees(math.atan2(along, float(hh[0]))), 2),
                   across_deg=round(math.degrees(math.atan2(across, float(hh[0]))), 2))
        out.append(rec)
        print(json.dumps(rec), flush=True)
    if out:
        med = lambda k: float(np.median([r[k] for r in out]))    # noqa: E731
        summ = dict(n=len(out), dyaw=med("dyaw"), along_deg=med("along_deg"), across_deg=med("across_deg"),
                    err_median=med("err"), scale_median=med("scale"), mount=mount)
        print("SUMMARY", json.dumps(summ), flush=True)
        if a.json:
            json.dump(dict(summary=summ, frames=out), open(a.json, "w"), indent=1)
    os._exit(0)


if __name__ == "__main__":
    main()

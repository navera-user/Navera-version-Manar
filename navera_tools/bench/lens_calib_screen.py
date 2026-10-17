#!/usr/bin/env python3
"""Calibrate the 360 camera's lens facing the screen: a grid of dots at known screen positions, found in
the raw fisheye frame, fits the lens (focal length, radial term, centre) and the screen's pose together.

    python3 navera_tools/bench/lens_calib_screen.py [--screen-mm 527x296.5] [--save]

The screen's real size gives the scale, so focal length and distance separate. A coarse grid
(8x5) is paired with the model's prediction first (dots ~8 degrees apart, safe to pair), then a fine
grid (16x9) refines it. Room dark helps (the dots are the only bright things). --save writes the lens
into ~/.navera_sim/insta360_usb_lens.json (sky360.default_lenses() reads it). Only the part of the
lens that sees the screen (~64 x 37 degrees) is measured: the radial term beyond it is extrapolated.
"""
import argparse
import json
import math
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    sys.path.insert(0, p)

from navera_tools.bench.view360 import Bench360  # noqa: E402
from navera_tools.field import sky360  # noqa: E402
from navera_tools.field.reprocess360 import rotvec  # noqa: E402

W, SW, SH = "NAVERA lens", 1920, 1080
LENS_FILE = os.path.expanduser("~/.navera_sim/insta360_usb_lens.json")
POSE_FILE = os.path.expanduser("~/.navera_sim/insta360_screen_pose.json")


def grid(nx, ny, margin=90):
    xs = np.linspace(margin, SW - margin, nx)
    ys = np.linspace(margin, SH - margin, ny)
    return np.array([(x, y) for y in ys for x in xs])


def show_dots(cam, pts, secs=3.5):
    img = np.zeros((SH, SW), np.uint8)
    for x, y in pts:
        cv2.circle(img, (int(x), int(y)), 7, 255, -1, cv2.LINE_AA)
    end = time.time() + secs                      # the stream is ~1.7 s behind
    while time.time() < end:
        cv2.imshow(W, img)
        cv2.waitKey(40)
    f, _ = cam.cam.latest()
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return g


def blobs(g, lens, near_px):
    """Bright compact spots near the screen's position in the fisheye frame."""
    bg = cv2.GaussianBlur(g, (0, 0), 15)
    r = g - bg
    thr = max(25.0, 0.4 * float(np.percentile(r, 99.97)))
    m = (r > thr).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    out = []
    for k in range(1, n):
        if 2 <= st[k, cv2.CC_STAT_AREA] <= 400 and math.hypot(cen[k][0] - near_px[0], cen[k][1] - near_px[1]) < 700:
            w = np.clip(r[lab == k], 0, None)
            ys, xs = np.nonzero(lab == k)
            out.append((float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum())))
    return np.array(out)


def model_pts(params, lens0, P):
    f, k1, cx, cy = params[:4]
    R = rotvec(params[4:7])
    T = params[7:10]
    lens = sky360.Lens(lens0.name, cx, cy, f, lens0.R_lens_imu, k1=k1, radius=lens0.radius)
    X = (R @ np.c_[P, np.zeros(len(P))].T).T + T          # screen mm → IMU frame
    x, y, _ = lens.project(X @ lens.R_lens_imu.T)
    return np.c_[x, y]


def pair(pred, det, max_px):
    from scipy.spatial import cKDTree
    if len(det) == 0:
        return np.array([], int), np.array([], int)
    d, k = cKDTree(det).query(pred, distance_upper_bound=max_px)
    ok = np.isfinite(d)
    # one detection for one dot only
    kk = k[ok]
    uniq = np.array([np.sum(kk == v) == 1 for v in kk])
    return np.nonzero(ok)[0][uniq], kk[uniq]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen-mm", default="527x296.5")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    sw_mm, sh_mm = (float(v) for v in a.screen_mm.split("x"))
    mm = sw_mm / SW
    cv2.namedWindow(W, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(W, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cam = Bench360(W)
    info = cam.find_screen(100.0, 1200, 900, screen_mm=sw_mm, distance_mm=400.0)
    print("screen:", info, flush=True)
    lens0 = cam.view.lens
    R_view = cam.view.R_view_imu                            # rows: right, down, forward (IMU frame)
    # initial pose: square-on, centred on the screen direction, distance from the screen's angular width
    dist = (sw_mm / 2) / math.tan(math.radians(info["screen_width_deg"]) / 2)
    T0 = R_view[2] * dist
    Rs0 = np.stack([R_view[0], R_view[1], R_view[2]], axis=1)  # screen x→right, y→down, z→away
    from scipy.spatial.transform import Rotation
    params = np.r_[lens0.f, 0.0, lens0.cx, lens0.cy, Rotation.from_matrix(Rs0).as_rotvec(), T0]
    from scipy.optimize import least_squares
    report = {"screen": info}
    for name, (nx, ny), tol in (("coarse", (8, 5), 60.0), ("fine", (16, 9), 18.0)):
        G = grid(nx, ny)
        P = (G - [SW / 2, SH / 2]) * mm                         # screen mm, centre origin
        g = show_dots(cam, G)
        det = blobs(g, lens0, info["screen_centre_px"])
        pi, di = pair(model_pts(params, lens0, P), det, tol)
        if len(pi) < 12:
            raise SystemExit(f"{name}: only {len(pi)} dots paired of {len(G)} ({len(det)} spots) — darker room? camera facing the screen?")

        def res(x):
            return (model_pts(x, lens0, P[pi]) - det[di]).ravel()
        fit = least_squares(res, params, x_scale="jac", loss="soft_l1", f_scale=2.0)
        params = fit.x
        r = res(params).reshape(-1, 2)
        rms = float(np.sqrt(np.mean(np.sum(r ** 2, axis=1))))
        report[name] = {"dots": len(G), "spots": int(len(det)), "paired": int(len(pi)), "rms_px": round(rms, 2),
                        "rms_deg": round(math.degrees(rms / params[0]), 4)}
        print(name, report[name], flush=True)
    f, k1, cx, cy = params[:4]
    report["lens"] = {"name": lens0.name, "f": round(float(f), 2), "k1": round(float(k1), 5), "cx": round(float(cx), 2),
                      "cy": round(float(cy), 2), "f_guess": round(lens0.f, 2), "f_ratio": round(float(f) / lens0.f, 4)}
    report["screen_distance_mm"] = round(float(np.linalg.norm(params[7:10])), 1)
    print(json.dumps(report, indent=1), flush=True)
    if a.save:
        d = {}
        if os.path.exists(LENS_FILE):
            d = json.load(open(LENS_FILE))
        d[lens0.name] = {k: report["lens"][k] for k in ("f", "k1", "cx", "cy")}
        d[lens0.name].update(measured="screen dot grid " + time.strftime("%Y-%m-%d"), rms_deg=report["fine"]["rms_deg"])
        json.dump(d, open(LENS_FILE, "w"), indent=1)
        # the screen's pose in the camera's IMU frame, for the star bench (stars drawn at their true angles)
        json.dump({"lens": lens0.name, "rotvec": [float(v) for v in params[4:7]], "T_mm": [float(v) for v in params[7:10]],
                   "mm_per_px": mm, "screen_px": [SW, SH], "measured": time.strftime("%Y-%m-%d %H:%M")},
                  open(POSE_FILE, "w"), indent=1)
        print("saved", LENS_FILE, POSE_FILE)
    cam.close()
    cv2.destroyAllWindows()
    os._exit(0)


if __name__ == "__main__":
    main()

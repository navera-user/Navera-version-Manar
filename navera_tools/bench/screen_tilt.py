#!/usr/bin/env python3
"""The real camera tilted by hand: does NAVERA's straightening (FrameBuilder, tilt from the
attitude) still find the right place on its map?

The screen shows one still terrain view (north up); the camera films it at whatever angle
it is held. The bench has no IMU, so each frame's true attitude is MEASURED from the image:
the frame matched against the exact picture on the screen gives the screen->image
homography, decomposed with the lens model into the camera's rotation and position
relative to the screen (the screen = the ground, its normal = straight down). That
attitude goes into NAVERA's own FrameBuilder (as an IMU would), the straightened frame is
matched against NAVERA's map (other imagery, 2-3 years apart), and the result compared
with the truth: the point of the screen straight below the camera (the nadir), not where
the camera axis points. Each frame is also matched without straightening (what a tilted
camera gives with no attitude) and with the attitude off by --imu-err deg (a real IMU).

    python3 navera_tools/bench/screen_tilt.py --calib insta360_top.yaml --terrain <tiles> \
        --map <area>/images --lat 35.869 --lon 10.535 --seconds 180

Bench only: the screen is flat and 30 cm away, the attitude comes from the picture itself.
"""
import argparse
import csv
import math
import os
import time

import cv2
import numpy as np
import yaml

from navera_common.camera_model import CameraModel, rpy_to_matrix, R_BODY_NADIR_CAM
from navera_common.frame_builder import FrameBuilder
from day_pkg.local_matcher import LocalMatcher

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--calib", required=True)
ap.add_argument("--terrain", required=True, help="tiles shown on the screen (tile_<z>_<x>_<y>.jpg)")
ap.add_argument("--terrain-zoom", type=int, default=18)
ap.add_argument("--map", required=True, help="NAVERA's map tiles")
ap.add_argument("--lat", type=float, required=True)
ap.add_argument("--lon", type=float, required=True)
ap.add_argument("--seconds", type=float, default=180.0)
ap.add_argument("--imu-err", type=float, default=2.0, help="deg, attitude error added in the 'imu' case")
ap.add_argument("--device", default="/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0")
ap.add_argument("--matcher", default="learned", choices=["learned", "sift"])
ap.add_argument("--screen-cm-per-px", type=float, default=52.3 / 1920, help="the screen's pixel size (24 in 16:9)")
ap.add_argument("--out", default="screen_tilt.csv")
a = ap.parse_args()

Z, SW, SH = a.terrain_zoom, 1920, 1080

# ---- the screen: one still north-up terrain view, 1 screen px = 1 terrain px ----
def latlon_to_px(lat, lon, z=Z):
    n = 256 * 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


gx, gy = latlon_to_px(a.lat, a.lon)
X0, Y0 = int(gx - SW / 2), int(gy - SH / 2)
screen = np.zeros((SH, SW, 3), np.uint8)
for ty in range(Y0 // 256, (Y0 + SH) // 256 + 1):
    for tx in range(X0 // 256, (X0 + SW) // 256 + 1):
        f = cv2.imread(os.path.join(a.terrain, f"tile_{Z}_{tx}_{ty}.jpg"))
        if f is None:
            continue
        f = cv2.resize(f, (256, 256))
        x, y = tx * 256 - X0, ty * 256 - Y0
        xs, ys = max(0, -x), max(0, -y)
        xe, ye = min(256, SW - x), min(256, SH - y)
        screen[y + ys:y + ye, x + xs:x + xe] = f[ys:ye, xs:xe]
if (screen.sum(axis=2) == 0).mean() > 0.2:
    raise SystemExit(f"terrain tiles missing around {a.lat},{a.lon} in {a.terrain}")
MPP = 156543.03392 * math.cos(math.radians(a.lat)) / 2 ** Z          # m per screen px (k=1)

# ---- camera, NAVERA's own lens model and straightening ----
cal = yaml.safe_load(open(a.calib))
cx0, cy0, cw, ch = cal.get("crop") or (0, 0, cal["image_width"], cal["image_height"])
cam = CameraModel.from_calibration(cal)
K = cam.K_out
fb = FrameBuilder(cam, max_tilt_deg=45.0)
cap = cv2.VideoCapture(a.device, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)


def grab():
    for _ in range(6):
        cap.grab()
    ok, f = cap.retrieve()
    return f[cy0:cy0 + ch, cx0:cx0 + cw] if ok and f is not None else None


# ---- the true attitude from the picture ----
sift = cv2.SIFT_create(4000)
sg = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
skp, sdes = sift.detectAndCompute(sg, None)
flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=64))


def pose(und):
    """(R_world_cam, camera position (east, north, up) m in the k=1 world, inliers) from an
    undistorted frame, or None. World: east, north, up; the screen is the ground (z=0)."""
    kp, des = sift.detectAndCompute(cv2.cvtColor(und, cv2.COLOR_BGR2GRAY), None)
    if des is None or len(kp) < 30:
        return None
    m = [p[0] for p in flann.knnMatch(des, sdes, k=2) if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(m) < 30:
        return None
    img = np.float32([kp[x.queryIdx].pt for x in m])
    scr = np.float32([skp[x.trainIdx].pt for x in m])
    # screen px -> world metres (east, north, 0)
    obj = np.c_[(scr[:, 0] - SW / 2) * MPP, -(scr[:, 1] - SH / 2) * MPP, np.zeros(len(scr))].astype(np.float64)
    ok, rvec, tvec, inl = cv2.solvePnPRansac(obj, img.astype(np.float64), K, None, reprojectionError=4.0,
                                             iterationsCount=500)
    if not ok or inl is None or len(inl) < 30:
        return None
    Rcw, _ = cv2.Rodrigues(rvec)                       # world -> camera
    C = (-Rcw.T @ tvec).ravel()                        # camera centre in the world
    if C[2] < 0:
        return None
    return Rcw.T, C, len(inl)


def q_from_R(R):
    """Quaternion (x, y, z, w) of a rotation matrix."""
    w = math.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
    y = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
    z = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
    return x, y, z, w


def body_q(R_world_cam, err_deg=0.0, rng=np.random.default_rng(1)):
    """The body attitude an IMU would give (camera mounted straight down), optionally with
    a roll/pitch error of err_deg in a random direction."""
    R_wb = R_world_cam @ R_BODY_NADIR_CAM.T
    if err_deg:
        d = rng.uniform(0, 2 * math.pi)
        R_wb = R_wb @ rpy_to_matrix(math.radians(err_deg * math.cos(d)), math.radians(err_deg * math.sin(d)), 0.0)
    return q_from_R(R_wb)


# ---- NAVERA's map ----
if a.matcher == "learned":
    from day_pkg.learned_matcher import LearnedMatcher
    M = LearnedMatcher(a.map, zoom=17, cache_dir=os.path.join(os.path.dirname(a.map.rstrip("/")), "learned_features"))
    M.warm(a.lat, a.lon, 1500)
else:
    M = LocalMatcher(a.map, zoom=17)
    M.tiles.around(a.lat, a.lon, 1500)
HF = cam.out_hfov_deg


def locate(img, height, heading):
    mpp = 2.0 * height * math.tan(math.radians(HF / 2)) / img.shape[1]
    r = M.locate(img, (a.lat, a.lon), 300.0, mpp, scale_tol=0.15, heading_deg=heading)
    if not r["accepted"]:
        return None, r.get("inliers")
    return (r["predicted_lat"], r["predicted_lon"]), r.get("inliers")


def en(q):
    return ((q[1] - a.lon) * 111320.0 * math.cos(math.radians(a.lat)), (q[0] - a.lat) * 111320.0)


# ---- run ----
cv2.namedWindow("tilt", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("tilt", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.imshow("tilt", screen)
cv2.waitKey(2500)
rows, t0 = [], time.time()
w = csv.writer(open(a.out, "w"))
w.writerow(["t", "tilt_deg", "roll_deg", "pitch_deg", "height_m", "pnp_inliers", "black_pct",
            "err_straight_m", "err_imu_m", "err_raw_m", "inl_straight", "inl_raw"])
while time.time() - t0 < a.seconds:
    cv2.waitKey(1)
    raw = grab()
    if raw is None:
        print("no frame", flush=True)
        continue
    t = time.time() - t0
    und = cam.undistort(raw)
    P = pose(und)
    if P is None:
        print(f"{t:5.0f} s  screen not seen well enough to measure the tilt", flush=True)
        continue
    Rwc, C, ninl = P
    truth = (C[0], C[1])                               # nadir: the ground straight below the camera
    height = float(C[2])
    q = body_q(Rwc)
    out, meta = fb.build(raw, len(rows), int(time.time() * 1e9), q)
    tilt = meta.get("tilt_deg", float("nan"))
    if not meta["usable"]:
        print(f"{t:5.0f} s  tilt {tilt:4.1f} deg: {meta.get('reason')}", flush=True)
        continue
    black = float((out.max(axis=2) < 8).mean()) * 100
    d = Rwc @ np.array([0.0, 0.0, 1.0])                # where the lens axis meets the screen, from the nadir
    off = (d[:2] * (C[2] / -d[2])) / MPP * a.screen_cm_per_px if d[2] < 0 else np.zeros(2)
    lean = " ".join(f"{abs(v):.0f} cm {w}" for v, w in ((off[0], "right" if off[0] > 0 else "left"),
                                                       (off[1], "up" if off[1] > 0 else "down")) if abs(v) >= 1)
    hdg = meta["heading_deg"]

    def err(img, hd):
        p, n = locate(img, height, hd)
        return (math.dist(en(p), truth) if p else None), n

    e_s, n_s = err(out, hdg)
    out_i, meta_i = fb.build(raw, len(rows), int(time.time() * 1e9), body_q(Rwc, a.imu_err))
    e_i, _ = err(out_i, meta_i["heading_deg"]) if meta_i["usable"] else (None, None)
    # no straightening: the frame as if the camera looked straight down (heading still known)
    e_r, n_r = err(und, hdg)
    f = lambda v: "lost" if v is None else f"{v:5.1f} m"
    print(f"{t:5.0f} s  tilt {tilt:4.1f} deg (roll {meta['roll_deg']:+5.1f}, pitch {meta['pitch_deg']:+5.1f}), "
          f"height {height:4.0f} m, black {black:3.0f} %  |  straightened {f(e_s)}  imu±{a.imu_err:g} {f(e_i)}  "
          f"not straightened {f(e_r)}  [axis hits the screen {lean or 'at the nadir'}]", flush=True)
    rows.append((tilt, e_s, e_i, e_r))
    w.writerow([round(t, 1), tilt, meta["roll_deg"], meta["pitch_deg"], round(height, 1), ninl, round(black, 1),
                e_s, e_i, e_r, n_s, n_r])
cv2.destroyAllWindows()

print("\nby tilt (found / frames, median error, max error):")
for lo, hi in ((0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 46)):
    sel = [r for r in rows if lo <= r[0] < hi]
    if not sel:
        continue
    parts = []
    for k, name in ((1, "straightened"), (2, f"imu±{a.imu_err:g}"), (3, "not straightened")):
        e = [r[k] for r in sel if r[k] is not None]
        parts.append(f"{name} {len(e)}/{len(sel)}" + (f" {np.median(e):.1f}/{max(e):.1f} m" if e else ""))
    print(f"  tilt {lo:2d}-{hi:2d} deg: " + ",  ".join(parts))

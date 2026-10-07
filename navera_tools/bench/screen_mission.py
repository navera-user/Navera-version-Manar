#!/usr/bin/env python3
"""A drone mission flown by the real camera over other-date imagery scrolling on the screen.

Harder than screen_flight.py: the view turns with the drone (a camera fixed to the body:
the image top is the heading), the height changes (the view zooms), the route is a
racetrack (straights and turns) flown for as long as asked; NAVERA gets the heading as an
IMU gives it (true heading + noise) and follows the height from the image alone.

    python3 navera_tools/bench/screen_mission.py --calib camera.yaml --terrain <z18 tiles> \
        --map <NAVERA map tiles dir (z17)> --lat .. --lon .. --minutes 30

Before the flight the camera axis is calibrated against the TERRAIN imagery itself (the
screen still): where the axis points on the screen and the height the screen distance
stands for — independent of NAVERA's map. Then GPS is good for --gps-s (NAVERA's position
and, as GPS - ground, its height; NAVERA learns the map bias), then lost (--baro: a
barometer keeps the height). NAVERA = the product's modules: the matcher for each frame,
day_pkg.vision_nav.VisionNavigator between frames (carried position and sigma, search
window, gates, height retries, map bias, "no position" past its limits) and
day_pkg.frame_odometry.FrameOdometry. Truth: the ground under the camera axis at the
frame's instant. Prints a line per frame and, at the end, over the GPS-lost part: fixes,
position availability, error (and how often within 3 stated sigma), per minute.
"""
import argparse
import csv
import math
import os
import threading
import time

import cv2
import numpy as np
import yaml

from day_pkg.frame_odometry import FrameOdometry
from day_pkg.local_matcher import LocalMatcher, map_m_per_px, tile_px_to_latlon
from day_pkg.vision_nav import VisionNavigator

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--calib", required=True)
ap.add_argument("--terrain", required=True, help="tile_<z>_<x>_<y>.jpg shown on the screen (another date)")
ap.add_argument("--terrain-zoom", type=int, default=18)
ap.add_argument("--map", required=True, help="NAVERA's map tiles (tile_17_x_y.jpg)")
ap.add_argument("--matcher", choices=["learned", "sift"], default="learned")
ap.add_argument("--device", default="/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0")
ap.add_argument("--lat", type=float, required=True)
ap.add_argument("--lon", type=float, required=True)
ap.add_argument("--speed", type=float, default=25.0)
ap.add_argument("--leg", type=float, default=900.0, help="m, racetrack straight")
ap.add_argument("--turn-radius", type=float, default=250.0)
ap.add_argument("--track-deg", type=float, default=30.0, help="the straights' bearing")
ap.add_argument("--height-swing", type=float, default=0.2, help="height +- this fraction")
ap.add_argument("--height-period", type=float, default=150.0, help="s, one climb + descent")
ap.add_argument("--heading-noise", type=float, default=5.0, help="deg, the simulated IMU's error")
ap.add_argument("--minutes", type=float, default=5.0)
ap.add_argument("--gps-s", type=float, default=30.0)
ap.add_argument("--latency", type=float, default=0.14)
ap.add_argument("--hfov", type=float, default=111.0)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--baro", action="store_true", help="a barometer gives the height after the GPS loss (+-1 %%)")
ap.add_argument("--out", default="screen_mission.csv")
a = ap.parse_args()
rng = np.random.default_rng(a.seed)
Z = a.terrain_zoom
MPP = map_m_per_px(a.lat, Z)
SW, SH = 1920, 1080

# ---- the terrain mosaic ----
n = 2 ** Z
r_ = math.radians(a.lat)
CX = (a.lon + 180) / 360 * n * 256
CY = (1 - math.log(math.tan(r_) + 1 / math.cos(r_)) / math.pi) / 2 * n * 256
names = [f for f in os.listdir(a.terrain) if f.startswith(f"tile_{Z}_")]
xs = [int(f.split("_")[2]) for f in names]
ys = [int(f.split("_")[3].split(".")[0]) for f in names]
X0, Y0 = min(xs), min(ys)
mosaic = np.zeros(((max(ys) - Y0 + 1) * 256, (max(xs) - X0 + 1) * 256, 3), np.uint8)
for f, x, y in zip(names, xs, ys):
    t = cv2.imread(os.path.join(a.terrain, f))
    if t is not None:
        mosaic[(y - Y0) * 256:(y - Y0 + 1) * 256, (x - X0) * 256:(x - X0 + 1) * 256] = cv2.resize(t, (256, 256))

# ---- the route: a racetrack around the area centre ----
L, R = a.leg, a.turn_radius
PERIM = 2 * L + 2 * math.pi * R
B = math.radians(a.track_deg)
U = np.array([math.sin(B), math.cos(B)])                       # along the straights (east, north)
V = np.array([math.cos(B), -math.sin(B)])                      # across, to the right


def route(t):
    """(east, north) metres from the centre, heading deg, zoom k (screen px per terrain px)."""
    s = (a.speed * t) % PERIM
    if s < L:                                                  # straight 1, along U
        p, h = -L / 2 * U + s * U - R * V, U
    elif s < L + math.pi * R:                                  # turn 1 (to the right)
        ang = (s - L) / R
        c = L / 2 * U
        p = c + R * (math.sin(ang) * U - math.cos(ang) * V)
        h = math.cos(ang) * U + math.sin(ang) * V
    elif s < 2 * L + math.pi * R:                              # straight 2, back
        p, h = L / 2 * U - (s - L - math.pi * R) * U + R * V, -U
    else:                                                      # turn 2
        ang = (s - 2 * L - math.pi * R) / R
        c = -L / 2 * U
        p = c + R * (-math.sin(ang) * U + math.cos(ang) * V)
        h = -math.cos(ang) * U - math.sin(ang) * V
    hdg = math.degrees(math.atan2(h[0], h[1])) % 360
    k = 1.0 / (1.0 + a.height_swing * math.sin(2 * math.pi * t / a.height_period))   # higher = smaller
    return p, hdg, k


def view(p, hdg, k):
    """The screen: the terrain around p, the heading up, k screen px per terrain px."""
    gx, gy = CX + p[0] / MPP - X0 * 256, CY - p[1] / MPP - Y0 * 256          # mosaic px
    th = math.radians(hdg)
    # screen (u, v) -> mosaic: centre + R(heading) * ((u, v) - screen centre) / k
    c, s = math.cos(th), math.sin(th)
    A = np.array([[c / k, -s / k, 0.0], [s / k, c / k, 0.0]])
    A[:, 2] = [gx, gy] - A[:, :2] @ [SW / 2, SH / 2]
    return cv2.warpAffine(mosaic, A, (SW, SH), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)


def to_latlon(p):
    return tile_px_to_latlon(CX + p[0] / MPP, CY - p[1] / MPP, Z)


def en(q, ref):
    """(east, north) m of lat/lon q from lat/lon ref."""
    return np.array([(q[1] - ref[1]) * 111320.0 * math.cos(math.radians(ref[0])), (q[0] - ref[0]) * 111320.0])


# ---- camera ----
cal = yaml.safe_load(open(a.calib))
K = np.array(cal["camera_matrix"]).reshape(3, 3)
D = np.array(cal["distortion"]).reshape(4, 1)
cx0, cy0, cw, ch = cal.get("crop") or (0, 0, cal["image_width"], cal["image_height"])
FO = (cw / 2) / math.tan(math.radians(a.hfov / 2))
m1, m2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), np.array([[FO, 0, cw / 2], [0, FO, ch / 2], [0, 0, 1]]),
                                             (cw, ch), cv2.CV_16SC2)
cap = cv2.VideoCapture(a.device, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if a.matcher == "learned":
    from day_pkg.learned_matcher import LearnedMatcher
    M = LearnedMatcher(a.map, zoom=17, cache_dir=os.path.join(os.path.dirname(a.map.rstrip("/")), "learned_features"))
    M.warm(a.lat, a.lon, L / 2 + R + 1500)
else:
    M = LocalMatcher(a.map, zoom=17)
    M.tiles.around(a.lat, a.lon, L / 2 + R + 1500)
shown, rows, hud = [], [], {}
stop = threading.Event()
T0 = [None]


def grab():
    for _ in range(200):                                       # drain: a fresh frame
        t0 = time.time()
        if not cap.grab():
            break
        if time.time() - t0 > 0.02:
            break
    ok, f = cap.retrieve()
    if not ok or f is None:
        grab.dead = getattr(grab, "dead", 0) + 1
        if grab.dead > 20:                                     # the camera stopped answering: stop
            stop.set()
            raise SystemExit("the camera stopped giving frames (unplug / replug it)")
        return None, time.time() - T0[0]
    grab.dead = 0
    t = time.time() - T0[0] - a.latency
    return (cv2.remap(f[cy0:cy0 + ch, cx0:cx0 + cw], m1, m2, cv2.INTER_LINEAR) if ok else None), t


def frame_mpp(height_m, width):
    return 2.0 * height_m * math.tan(math.radians(a.hfov / 2)) / width


def calibrate_axis():
    """Before the flight (independent of NAVERA's map): the screen still at the start, the
    camera's frames matched against the TERRAIN shown (the same imagery: exact) — where the
    camera axis points on the screen and the height the screen distance stands for."""
    p, hdg, k = route(0.0)
    v = view(p, hdg, k)
    cv2.putText(v, "calibrating the camera axis...", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    cv2.imshow("NAVERA mission", v)
    cv2.waitKey(1500)
    T = LocalMatcher(a.terrain, zoom=Z)
    offs, hs = [], []
    th = math.radians(hdg)
    rot = np.array([[math.cos(th), math.sin(th)], [-math.sin(th), math.cos(th)]])
    for _ in range(4):
        cv2.waitKey(300)
        T0[0] = time.time()
        img, _t = grab()
        r = T.locate_any_height(img, to_latlon(p), 300.0, a.hfov, min_alt_m=100, max_alt_m=1500, heading_deg=hdg)
        if r["accepted"]:
            off = en((r["predicted_lat"], r["predicted_lon"]), to_latlon(p))
            offs.append(rot.T @ off / MPP * k)
            hs.append(r["altitude_m"] * k)
    if len(offs) < 2:
        raise SystemExit("camera axis calibration failed: is the camera facing the screen?")
    w, h0 = np.median(offs, axis=0), float(np.median(hs))
    print(f"camera axis: {np.hypot(*w) * MPP:.1f} m from the screen centre (at k=1), "
          f"height at k=1: {h0:.0f} m ({len(offs)} frames)", flush=True)
    return w, h0


def worker(axis_w, h0):
    """NAVERA's day vision: the matcher for one frame, VisionNavigator between frames
    (prediction, search window, gates, height, map bias), FrameOdometry for the velocity."""
    nav, vo = VisionNavigator(), FrameOdometry()
    while not stop.is_set():
        img, t = grab()
        past = [x for x in list(shown) if x[0] <= t]
        if img is None or not past:
            continue
        _, p, hdg, k = past[-1]
        th = math.radians(hdg)
        rot = np.array([[math.cos(th), math.sin(th)], [-math.sin(th), math.cos(th)]])
        truth = to_latlon(p + rot @ (axis_w / k) * MPP)
        h_true = h0 / k
        gps_on = t < a.gps_s
        imu = (hdg + rng.normal(0, a.heading_noise)) % 360
        if gps_on:                                             # GPS: the position and (GPS - ground) the height
            nav.gps(t, *truth, heading_deg=imu)
            nav.set_height(t, h_true * (1 + rng.normal(0, 0.02)), 0.03 * h_true, "gps")
        elif a.baro:
            nav.set_height(t, h_true * (1 + rng.normal(0, 0.01)), 0.02 * h_true, "baro")
        h, extra, tol = nav.heights_to_try(t)
        if gps_on:
            centre, R = truth, 150.0
        else:
            centre, R = nav.search(t, imu)
        t1 = time.time()
        if centre is None:
            r, used = {"accepted": False, "reason": "no prior"}, None
        elif h is None:
            r = M.locate_any_height(img, centre, R, a.hfov, min_alt_m=100, max_alt_m=1500, heading_deg=imu)
            used = r.get("height_tried_m")
        else:
            for hh in [h] + extra:
                r = M.locate(img, centre, R, frame_mpp(hh, img.shape[1]), scale_tol=tol, heading_deg=imu,
                             heading_tol_deg=20.0)
                used = hh
                if r["accepted"]:
                    break
            sc = float(r.get("scale_residual") or 1.0)
            if r.get("accepted") and abs(sc - 1.0) > 0.10:
                # the fitted scale answers ~half of a height error: match again at the corrected height
                again = M.locate(img, centre, R, frame_mpp(used * sc, img.shape[1]), scale_tol=tol,
                                 heading_deg=imu, heading_tol_deg=20.0)
                if again.get("accepted") and int(again.get("inliers") or 0) >= int(r.get("inliers") or 0) // 2:
                    r, used = again, used * sc
        ms = (time.time() - t1) * 1000
        vis = (r["predicted_lat"], r["predicted_lon"]) if r.get("accepted") else None
        if vis and gps_on:
            nav.bias_sample(vis, truth, imu)
        ok = nav.update(t, r, used, imu, gps_valid=gps_on)
        if nav.height is not None:
            pred = None
            if nav.vel is not None and vo._prev is not None:
                pred = (nav.vel[0] * (t - vo._prev[3]), nav.vel[1] * (t - vo._prev[3]))
            d = vo.step(img, imu, frame_mpp(nav.height[0], img.shape[1]), t, pred)
            if d is not None and not gps_on and not ok:
                nav.odometry(t, *d)
        lat, lon, sig, mode = nav.output(t, imu)
        if gps_on:
            mode = "gps"
        out = (lat, lon) if lat is not None else None
        ve = en(vis, truth) if vis else None
        oe = en(out, truth) if out else None
        hud.update(t=t, gps=gps_on, src=mode, height=nav.height[0] if nav.height else None, h_true=h_true,
                   err=float(np.hypot(*oe)) if oe is not None else None, hdg=hdg, sigma=sig)
        rows.append(dict(t=round(t, 2), gps=int(gps_on), matched=int(bool(vis)), accepted=int(ok),
                         vision_err_m=None if ve is None else round(float(np.hypot(*ve)), 1),
                         vision_e=None if ve is None else round(float(ve[0]), 1),
                         vision_n=None if ve is None else round(float(ve[1]), 1),
                         navera_err_m=None if oe is None else round(float(np.hypot(*oe)), 1),
                         navera_e=None if oe is None else round(float(oe[0]), 1),
                         navera_n=None if oe is None else round(float(oe[1]), 1),
                         sigma_m=None if sig is None else round(sig, 1), mode=mode, heading=round(hdg), k=round(k, 3),
                         height=None if nav.height is None else round(nav.height[0]), height_true=round(h_true),
                         inliers=r.get("inliers"), spread=r.get("spread"), scale=r.get("scale_residual"),
                         height_used=None if used is None else round(used), features=r.get("features", "sift"),
                         search_m=None if R is None else round(R), ms=round(ms), reason=None if ok else nav.last_reason[:80]))
        print(f"{t:7.1f}s {'GPS ' if gps_on else 'LOST'} hdg {hdg:5.0f} k {k:.2f}  vision "
              f"{'%6.1f m' % np.hypot(*ve) if ve is not None else '   -    '} {'ok ' if ok else 'no '} "
              f"NAVERA={mode:11s} err {'%6.1f' % np.hypot(*oe) if oe is not None else '   -  '} m "
              f"sigma {sig or 0:5.0f}  R {R or 0:5.0f}  height {nav.height[0] if nav.height else 0:5.0f}/{h_true:5.0f} "
              f"{r.get('inliers') or 0:4d} pts {ms:5.0f} ms", flush=True)


def draw_hud(img, t):
    """The operator line: a thin strip at the bottom edge (the camera sees the whole screen:
    a big fixed box pulls the visual odometry toward zero motion)."""
    h = dict(hud)
    src = {"gps": "GPS", "measured": "VISION", "propagated": "carried", "unavailable": "NO POSITION"}.get(h.get("src"), "-")
    txt = (f"t {t / 60:4.1f} min | {'GPS ON' if t < a.gps_s else 'GPS OFF'} | NAVERA {src}"
           + (f" +-{h['sigma']:.0f} m" if h.get("sigma") and h.get("src") != "gps" else "")
           + (f" | err {h['err']:.0f} m" if h.get("err") is not None else "")
           + (f" | height {h['height']:.0f}/{h['h_true']:.0f} m" if h.get("height") and h.get("h_true") else ""))
    cv2.rectangle(img, (0, SH - 26), (SW, SH), (20, 20, 20), -1)
    cv2.putText(img, txt, (10, SH - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)


cv2.namedWindow("NAVERA mission", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("NAVERA mission", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
axis_w, h0 = calibrate_axis()
T0[0] = time.time()
th_ = threading.Thread(target=worker, args=(axis_w, h0), daemon=True)
th_.start()
while True:
    t = time.time() - T0[0]
    if t > a.minutes * 60 or stop.is_set():
        break
    p, hdg, k = route(t)
    v = view(p, hdg, k)
    draw_hud(v, t)
    cv2.imshow("NAVERA mission", v)
    key = cv2.waitKey(1)
    shown.append((time.time() - T0[0], p, hdg, k))
    del shown[:-400]
    if key in (27, ord("q")):
        break
stop.set()
th_.join(15)
cv2.destroyAllWindows()
with open(a.out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
lost = [x for x in rows if not x["gps"]]
avail = [x for x in lost if x["navera_err_m"] is not None]
ne = [x["navera_err_m"] for x in avail]
ve = [x["vision_err_m"] for x in lost if x["accepted"] and x["vision_err_m"] is not None]
honest = [x for x in avail if x["sigma_m"] and x["navera_err_m"] <= 3 * x["sigma_m"]]
he = [abs(x["height"] / x["height_true"] - 1) * 100 for x in lost if x["height"] and x["height_true"]]
print()
print(f"GPS lost {len(lost)} frames: map fixes accepted {sum(x['accepted'] for x in lost)}/{len(lost)}"
      + (f" (vision error median {np.median(ve):.1f} m, 95% {np.percentile(ve, 95):.1f} m, max {max(ve):.1f} m)" if ve else "")
      + f"; position available {len(avail)}/{len(lost)}"
      + (f", NAVERA error median {np.median(ne):.1f} m, 95% {np.percentile(ne, 95):.1f} m, max {max(ne):.1f} m, "
         f"within 3 sigma {len(honest)}/{len(avail)}" if ne else "")
      + (f"; height error median {np.median(he):.1f} %, max {max(he):.1f} %" if he else "")
      + f"; {np.median([x['ms'] for x in rows]):.0f} ms/frame")
for m0 in range(0, int(a.minutes) + 1):
    seg = [x for x in lost if m0 * 60 <= x["t"] < (m0 + 1) * 60]
    if seg:
        e = [x["navera_err_m"] for x in seg if x["navera_err_m"] is not None]
        print(f"  minute {m0:2d}: fixes {sum(x['accepted'] for x in seg)}/{len(seg)}, available {len(e)}/{len(seg)}"
              + (f", NAVERA error median {np.median(e):.1f} m max {max(e):.1f} m" if e else ""))

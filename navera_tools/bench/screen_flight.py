#!/usr/bin/env python3
"""Bench flight with the real camera: the map scrolls on the screen as a vehicle would fly
over it, the camera (fixed, facing the screen) takes successive frames, and NAVERA's day
matcher locates each one. GPS phases: good, then drifting (spoofed), then lost.

    python3 navera_tools/bench/screen_flight.py --calib camera.yaml --area <tiles dir> \
        --lat 35.82227 --lon 10.61691 --speed 20 --seconds 150

The truth at each frame is the map point under the screen centre at the frame's time plus
the camera axis offset, measured during the good-GPS phase (with the height and the
rotation). Afterwards nothing from the truth is used: the prior is NAVERA's own position.
Limits: with --area = NAVERA's own map tiles the screen shows the map itself (no season,
shadow or sensor differences): show other imagery (another date) for a real test. The
flight is north-up (no rotation) at one height.
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

from day_pkg.local_matcher import LocalMatcher, map_m_per_px, tile_px_to_latlon
from day_pkg.vision_nav import VisionNavigator
from navera_tools.bench.screen_overlays import KINDS as OVERLAYS, Overlays

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--calib", help="strip source: the webcam lens calibration (not used with --source 360)")
ap.add_argument("--source", choices=["strip", "360"], default="strip",
                help="strip: webcam mode (top lens, cropped); 360: full 360 over USB (Android mode), straight view on the screen")
ap.add_argument("--area", required=True, help="tile_<z>_<x>_<y>.jpg directory around the start")
ap.add_argument("--device", default="/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0")
ap.add_argument("--lat", type=float, required=True)
ap.add_argument("--lon", type=float, required=True)
ap.add_argument("--speed", type=float, default=20.0, help="ground speed, m/s")
ap.add_argument("--radius", type=float, default=900.0, help="circuit radius, m")
ap.add_argument("--seconds", type=float, default=150.0)
ap.add_argument("--gps-drift-at", type=float, default=40.0, help="s: GPS starts drifting")
ap.add_argument("--gps-drift-rate", type=float, default=3.0, help="m/s of drift")
ap.add_argument("--gps-lost-at", type=float, default=75.0, help="s: GPS lost")
ap.add_argument("--screen-mm", type=float, default=527.0)
ap.add_argument("--hfov", type=float, default=100.0, help="undistorted view width, deg")
ap.add_argument("--latency", type=float, default=None,
                help="s, the camera delay: a frame is dated arrival - latency (strip 0.14 measured, 360 1.71 measured)")
ap.add_argument("--match-area", help="tiles NAVERA matches against (default --area)")
ap.add_argument("--match-zoom", type=int, default=17)
ap.add_argument("--matcher", choices=["sift", "learned"], default="learned",
                help="NAVERA's day matcher: learned (DISK + LightGlue, SIFT fallback) or sift")
ap.add_argument("--display-zoom", type=int, default=17,
                help="zoom of the --area tiles shown on the screen (18: twice the detail, a lower flight)")
ap.add_argument("--min-alt", type=float, default=300.0, help="m: the no-height search's lowest height")
ap.add_argument("--max-alt", type=float, default=2000.0)
ap.add_argument("--height", type=float,
                help="m: the height is known from the start (GPS altitude while it works): no search")
ap.add_argument("--save-frame", help="write the latest camera frame (undistorted) here, for checks")
ap.add_argument("--overlay", default="none",
                help="conditions drawn over the map on the screen, comma-separated: " + ", ".join(OVERLAYS))
ap.add_argument("--overlay-amount", type=float, default=0.3,
                help="strength 0-1 (clouds: sky fraction covered; wind: shake 0.5-3 deg equivalent)")
ap.add_argument("--max-speed", type=float, default=None,
                help="m/s, the vehicle's top speed for the track gate (default 1.5 x --speed)")
ap.add_argument("--no-gate", action="store_true",
                help="forward every accepted match as NAVERA's output (the rule before 2026-10-19: "
                     "a wrong-but-confident match 100-650 m off was output)")
ap.add_argument("--out", default="screen_flight.csv")
a = ap.parse_args()
_bad = set(a.overlay.split(",")) - set(OVERLAYS) - {"none", ""}
if _bad:
    ap.error(f"unknown --overlay {sorted(_bad)}; known: {', '.join(OVERLAYS)}")
if a.latency is None:
    a.latency = 1.71 if a.source == "360" else 0.14            # 360: fitted on 54 bench frames at 20-80 m/s
if a.source == "strip" and not a.calib:
    ap.error("--calib is needed with --source strip")

Z = a.display_zoom
MPP = map_m_per_px(a.lat, Z)                                  # ground metres per map/screen pixel
SW, SH = 1920, 1080

# ---- the map mosaic: the screen shows it one map pixel per screen pixel ----
n = 2 ** Z
cx = (a.lon + 180) / 360 * n * 256
r = math.radians(a.lat)
cy = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n * 256
names = [f for f in os.listdir(a.area) if f.startswith(f"tile_{Z}_")]
xs = [int(f.split("_")[2]) for f in names]
ys = [int(f.split("_")[3].split(".")[0]) for f in names]
x0, y0 = min(xs), min(ys)
mosaic = np.zeros(((max(ys) - y0 + 1) * 256, (max(xs) - x0 + 1) * 256, 3), np.uint8)
for f, x, y in zip(names, xs, ys):
    t = cv2.imread(os.path.join(a.area, f))
    if t is not None:
        mosaic[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = cv2.resize(t, (256, 256))


def route(t):
    """Screen-centre ground point at time t (global map pixels) and the velocity (m/s e, n)."""
    w = a.speed / a.radius
    ang = w * t
    px = cx + (a.radius * math.sin(ang)) / MPP
    py = cy - (a.radius * (1 - math.cos(ang))) / MPP          # north = up = -y
    return px, py, (a.speed * math.cos(ang), a.speed * math.sin(ang))


def latlon(px, py):
    return tile_px_to_latlon(px, py, Z)


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(a.lat))
    return math.hypot(de, dn), de, dn


def offset(p, de, dn):
    return (p[0] + dn / 111320.0, p[1] + de / (111320.0 * math.cos(math.radians(a.lat))))


cv2.namedWindow("NAVERA flight", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("NAVERA flight", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
if a.source == "360":
    # ---- the camera: full 360 over USB, a straight view centred on the screen it finds ----
    from navera_tools.bench.view360 import Bench360
    OW, OH = 1200, 900
    cam360 = Bench360("NAVERA flight")
    print("360 camera, screen found:", cam360.find_screen(a.hfov, OW, OH, screen_mm=a.screen_mm), flush=True)
    last_frame_t = [0.0]
else:
    # ---- the camera: top lens, undistorted to a straight view ----
    cal = yaml.safe_load(open(a.calib))
    K = np.array(cal["camera_matrix"]).reshape(3, 3)
    D = np.array(cal["distortion"]).reshape(4, 1)
    cx0, cy0, cw, ch = cal.get("crop") or (0, 0, cal["image_width"], cal["image_height"])
    OW, OH = 1200, ch
    fo = (OW / 2) / math.tan(math.radians(a.hfov / 2))
    m1, m2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), np.array([[fo, 0, OW / 2], [0, fo, OH / 2], [0, 0, 1]]),
                                                 (OW, OH), cv2.CV_16SC2)
    cap = cv2.VideoCapture(a.device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if a.matcher == "learned":
    from day_pkg.learned_matcher import LearnedMatcher
    M = LearnedMatcher(a.match_area or a.area, zoom=a.match_zoom)
    M.warm(a.lat, a.lon, a.radius * 2 + 1000)                 # the mission area, before the flight
else:
    M = LocalMatcher(a.match_area or a.area, zoom=a.match_zoom)
shown = []                                 # (time shown, map px, map py): what the screen showed
M.tiles.around(a.lat, a.lon, a.radius + 1500)                  # warm the map features
stop = threading.Event()
hud = {}


# weather, traffic, lens and camera-shake conditions over the map (navera_tools/bench/screen_overlays.py;
# check them offline with render_overlays.py)
overlays = Overlays(SW, SH)
OVERLAY_KINDS = [k for k in a.overlay.split(",") if k not in ("", "none")]


def draw_hud(img, t):
    """The operator panel, top-left corner (small: the camera sees the whole screen)."""
    h = dict(hud)
    x0_, y0_, w_, h_ = 20, 20, 470, 230
    cv2.rectangle(img, (x0_, y0_), (x0_ + w_, y0_ + h_), (30, 30, 30), -1)
    gps = ("GPS: ON", (0, 200, 0)) if t < a.gps_drift_at else \
          (("GPS: DRIFTING +%.0f m" % (a.gps_drift_rate * (t - a.gps_drift_at)), (0, 165, 255)) if t < a.gps_lost_at
           else ("GPS: OFF (jammed)", (0, 0, 255)))
    if h.get("refused") and t < a.gps_lost_at:
        gps = (gps[0] + " - REFUSED", (0, 0, 255))
    src = h.get("src", "-")
    lines = [(f"t {t:5.1f} s   speed {a.speed:.0f} m/s", (255, 255, 255)), gps,
             ("altitude (image): " + ("searching..." if h.get("height") is None else f"{h['height']:.0f} m"),
              (255, 255, 255)),
             ("NAVERA source: " + {"gps": "GPS", "vision": "VISION (matching)", "carried": "carried (no match)"}.get(src, src),
              (0, 200, 0) if src == "gps" else ((255, 200, 0) if src == "vision" else (0, 0, 255))),
             ("match: " + ("yes, %s points" % h.get("inliers") if h.get("matched") else "no"), (255, 255, 255)),
             ("error vs truth: " + ("-" if h.get("err") is None else f"{h['err']:.1f} m"), (255, 255, 255))]
    for i, (txt, col) in enumerate(lines):
        cv2.putText(img, txt, (x0_ + 12, y0_ + 34 + i * 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)
t_start = [None]
rows = []


def grab():
    """The newest camera frame, undistorted, with its capture time (since the start)."""
    if a.source == "360":
        while not stop.is_set():                               # wait for a frame not used yet
            img, t_arr = cam360.grab()
            if img is not None and t_arr > last_frame_t[0]:
                last_frame_t[0] = t_arr
                return img, t_arr - t_start[0] - a.latency
            time.sleep(0.02)
        return None, 0.0
    # the driver queues frames while NAVERA works: drain the queue (a frame that waited
    # is late), the time is taken when the fresh one arrives
    while True:
        t0 = time.time()
        cap.grab()
        if time.time() - t0 > 0.02:                            # waited for a new frame: fresh
            break
    ok, f = cap.retrieve()
    t = time.time() - t_start[0] - a.latency                   # when the frame was taken
    if not ok:
        return None, t
    img = f[cy0:cy0 + ch, cx0:cx0 + cw]
    return cv2.remap(img, m1, m2, cv2.INTER_LINEAR), t


def worker():
    """NAVERA's day localisation, frame after frame (the estimator's choice in between)."""
    cal_off, cal_h, cal_rot = [], [], []
    pos, pos_t, sigma = None, None, 30.0                       # NAVERA's position (output)
    vis_last, vis_vel = None, (0.0, 0.0)
    doubt, gps_refused, refused_at = 0, False, None
    height, axis, rot = a.height, None, 0.0
    src_prev = "gps"
    first = []                                                 # unconfirmed no-height matches
    # the product's track gate (day_pkg.vision_nav): with GPS trusted it follows GPS; after,
    # a match is output only if consistent with the carried track and the vehicle's speed
    nav = None if a.no_gate else VisionNavigator(max_speed_mps=a.max_speed or 1.5 * a.speed)
    while not stop.is_set():
        img, t = grab()
        if img is None:
            continue
        # the truth: what the screen showed when the frame was taken (not the route at t:
        # the display falls behind while NAVERA computes)
        past = [x for x in list(shown) if x[0] <= t]
        if not past:
            continue
        _, tpx, tpy = past[-1]
        centre = latlon(tpx, tpy)
        phase = "gps" if t < a.gps_drift_at else ("drift" if t < a.gps_lost_at else "lost")
        drift = 0.0 if phase == "gps" else a.gps_drift_rate * (t - a.gps_drift_at)
        gps = None if phase == "lost" else offset(centre if axis is None else offset(centre, *axis), drift, 0.0)
        if a.save_frame:
            cv2.imwrite(a.save_frame, img)
        t0 = time.time()
        if height is None:
            # no height known (no GPS altitude, no barometer): the multi-height search
            r = M.locate_any_height(img, gps or centre, 600.0, a.hfov, min_alt_m=a.min_alt, max_alt_m=a.max_alt,
                                    heading_deg=0.0)   # north-up display: the IMU heading
            used_h = r.get("height_tried_m")
            if r["accepted"]:
                # a match found with no height known can be an accident (blur, repeated
                # texture): kept only when a second frame agrees (height within 5 %, the same
                # place within 50 m once the motion is removed)
                _, de, dn = metres((r["predicted_lat"], r["predicted_lon"]), centre)
                cand = (r["altitude_m"], de, dn)
                agree = [c for c in first if abs(c[0] / cand[0] - 1) < 0.05 and math.hypot(c[1] - de, c[2] - dn) < 50]
                first.append(cand)
                if not agree:
                    r = dict(r, accepted=False, reason="first match, waiting for a second frame to confirm it")
        else:
            use_gps = src_prev == "gps" and gps is not None
            prior = gps if use_gps else pos
            if prior is not None and not use_gps and pos_t is not None:   # carried along the velocity
                dt = t - pos_t
                prior = offset(prior, vis_vel[0] * dt, vis_vel[1] * dt)
            mpp = 2 * height * math.tan(math.radians(a.hfov / 2)) / OW
            r = M.locate(img, prior, min(300.0 + sigma, 1500.0), mpp, scale_tol=0.15,
                         heading_deg=rot, heading_tol_deg=15.0)
            used_h = height
        if r["accepted"] and phase == "gps":
            # while GPS is good: the camera axis offset, the height and the rotation, measured
            _, de, dn = metres((r["predicted_lat"], r["predicted_lon"]), centre)
            cal_off.append((de, dn)); cal_h.append(used_h * float(r["scale_residual"])); cal_rot.append(r["rotation_deg"])
            height = float(np.median(cal_h)); rot = float(np.median(cal_rot))
            axis = (float(np.median([o[0] for o in cal_off])), float(np.median([o[1] for o in cal_off])))
        elif r["accepted"] and height is None:
            height = r["altitude_m"]
        truth = offset(centre, *axis) if axis else centre
        ms = (time.time() - t0) * 1000
        vis = (r["predicted_lat"], r["predicted_lon"]) if r["accepted"] else None
        vis_err = metres(vis, truth)[0] if vis else None
        # the estimator: GPS while it agrees with vision, else vision, else carried
        if gps is not None and vis is not None and axis is not None and height is not None:
            gap = metres(gps, vis)[0]
            if len(cal_off) >= 5:                              # the camera axis is measured
                doubt = doubt + 1 if gap > 3 * math.hypot(5.0, 10.0) else 0
            if doubt >= 2 and not gps_refused:
                gps_refused, refused_at = True, (t, drift)
                if nav is not None:                            # hand over from vision, not the drifted GPS
                    nav.gps(t, *vis, sigma_m=10.0)
        gate_why = None
        if nav is not None:
            if gps is not None and not gps_refused:
                nav.gps(t, *gps)
            elif vis is not None and not (refused_at and refused_at[0] == t) and \
                    not nav.update(t, dict(r, sigma_m=r.get("sigma_m") or 10.0), None, None, gps_valid=False):
                gate_why, vis = nav.last_reason, None
        if vis:
            if vis_last is not None and t - vis_last[2] > 0.2:
                _, de, dn = metres(vis, vis_last[:2])
                k = 0.5                                        # smoothed ground velocity
                vis_vel = (k * de / (t - vis_last[2]) + (1 - k) * vis_vel[0],
                           k * dn / (t - vis_last[2]) + (1 - k) * vis_vel[1])
            vis_last = (vis[0], vis[1], t)
        src = "gps" if gps is not None and not gps_refused else ("vision" if vis else "carried")
        if src == "gps":
            pos, pos_t, sigma = gps, t, 5.0
        elif src == "vision":
            pos, pos_t, sigma = vis, t, 10.0
        else:
            if pos is not None:
                dt = t - pos_t
                pos = offset(pos, vis_vel[0] * dt, vis_vel[1] * dt); pos_t = t
            sigma += 5.0
        src_prev = src
        out_err = metres(pos, truth)[0] if pos else None
        hud.update(t=t, phase=phase, drift=drift, height=height, src=src, matched=bool(vis),
                   err=out_err, refused=gps_refused, inliers=r.get("inliers"))
        rows.append(dict(t=round(t, 2), phase=phase, gps_drift_m=round(drift, 1), matched=int(bool(vis)),
                         vision_err_m=None if vis_err is None else round(vis_err, 1), source=src,
                         navera_err_m=None if out_err is None else round(out_err, 1), ms=round(ms),
                         inliers=r.get("inliers"), height_m=None if height is None else round(height),
                         vis_de=None if not vis else round(metres(vis, centre)[1], 1),
                         vis_dn=None if not vis else round(metres(vis, centre)[2], 1),
                         gated=int(gate_why is not None),
                         turned_deg=round(getattr(cam360, "turned_deg", 0.0), 1) if a.source == "360" else None,
                         imu_ok=int(cam360.cam.imu_age() < 1.5) if a.source == "360" else None))
        print(f"{t:6.1f}s {phase:5s} gps+{drift:5.0f}m  vision "
              f"{'%5.1f m' % vis_err if vis_err is not None else '  -   '}  NAVERA={src:7s} "
              f"err {'%5.1f' % out_err if out_err is not None else '  -  '} m  {ms:4.0f} ms"
              + (f"  camera turned {cam360.turned_deg:5.1f} deg" if a.source == "360" else "")
              + ("  IMU SILENT" if a.source == "360" and cam360.cam.imu_age() > 1.5 else "")
              + (f"  GATED: {gate_why[:70]}" if gate_why else ""), flush=True)
    stop.refused_at = refused_at


t_start[0] = time.time()
th = threading.Thread(target=worker, daemon=True)
th.start()
while True:
    t = time.time() - t_start[0]
    if t > a.seconds:
        break
    px, py, _ = route(t)
    mx, my = int(round(px - x0 * 256 - SW / 2)), int(round(py - y0 * 256 - SH / 2))
    view = mosaic[my:my + SH, mx:mx + SW].copy()
    shift = (0.0, 0.0)
    if OVERLAY_KINDS:
        view, shift = overlays.draw(view, t, OVERLAY_KINDS, a.overlay_amount)
    draw_hud(view, t)
    cv2.imshow("NAVERA flight", view)
    key = cv2.waitKey(1)
    shown.append((time.time() - t_start[0], px - shift[0], py - shift[1]))   # wind moves the scene
    del shown[:-400]
    if key in (27, ord("q")):
        break
stop.set()
th.join(10)
cv2.destroyAllWindows()
with open(a.out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
print()
for ph in ("gps", "drift", "lost"):
    rr = [x for x in rows if x["phase"] == ph]
    if not rr:
        continue
    ve = [x["vision_err_m"] for x in rr if x["vision_err_m"] is not None]
    ne = [x["navera_err_m"] for x in rr if x["navera_err_m"] is not None]
    print(f"{ph:5s}: {len(rr)} frames, vision matched {len(ve)}/{len(rr)}"
          + (f", vision error median {np.median(ve):.1f} m max {max(ve):.1f} m" if ve else "")
          + (f"; NAVERA output error median {np.median(ne):.1f} m max {max(ne):.1f} m" if ne else "")
          + f"; {np.median([x['ms'] for x in rr]):.0f} ms/frame")
ra = getattr(stop, "refused_at", None)
print(f"GPS drift refused at t={ra[0]:.1f} s, after {ra[1]:.0f} m of drift" if ra else "GPS drift never refused")
print(f"height measured from the image: {rows[-1]['height_m']} m; speed {a.speed} m/s; overlay {a.overlay}; log {a.out}")
if a.source == "360":
    cam360.close()
    os._exit(0)                                                # camera threads must not abort the exit

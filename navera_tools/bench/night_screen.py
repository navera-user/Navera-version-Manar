#!/usr/bin/env python3
"""Night bench with the real camera: a PSEUDO-THERMAL map flight on the screen, filmed by the
Insta360 (full 360 over USB, Bench360), located by night_pkg's STHN localizer.

The pattern of screen_flight.py: the map scrolls on the screen along a circle as a vehicle
would fly over it, the camera (fixed, facing the screen) takes frames, NAVERA locates each
one. Here the map is turned into a thermal-LIKE image (grey levels, sensor effects and the
--condition: crossover, polarity, NUC drift, fog, clouds, hot spots, wind...) and the night
chain locates the frame: the screen part of the camera view is cut square, its ground size
comes from the screen's measured width in the view, STHN (NightLocalizer, with its wrong-fix
checks and stated sigma) matches it against the z17 map, and NightTracker (the night node's
motion gate / re-acquisition / dead reckoning) carries the track once GPS is lost.

    # real bench (the lead runs it: opens the camera and a full-screen window on DISPLAY :1)
    python3 navera_tools/bench/night_screen.py --source 360 --condition clean \
        --area ~/.navera_sim/bench_2026-10-06/wb2022 --lat 35.8685 --lon 10.5352 \
        --seconds 90 --out night_clean.csv
    # offline check (no camera, no window): the screen image is fed as the camera frame,
    # shrunk to the bench's scale and placed in a dark "room" frame
    python3 navera_tools/bench/night_screen.py --source offline --condition fog ...

Truth: the map point under the screen centre when the frame was taken (360 stream delay 1.71 s
compensated), plus the camera-axis offset measured during the GPS phase. GPS phases: good
until --gps-lost-at, then lost (the prior is the night track's own position).
Limits: the screen shows a VISIBLE map turned grey (or another date's imagery with --area
wb2022): real LWIR contrast follows materials and temperature, not albedo; the camera is a
visible camera filming an emissive screen. This tests the chain (scale, orientation, checks,
track) and the conditions' photometry, not a thermal sensor.
"""
import argparse
import csv
import math
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "night_pkg", ROOT / "navera_common", ROOT / "cn_pkg", ROOT / "navera_tools" / "sim",
          ROOT / "navera_tools" / "bench"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import night_conditions as nc  # noqa: E402

EQUATOR_M = 40075016.686
SW, SH = 1920, 1080
CONDITIONS = ("clean", "crossover", "polarity", "fpn_nuc", "dead_pixels", "agc_jumps", "fog", "rain",
              "clouds", "hot_vehicles", "fires", "lights_drones", "birds", "wind", "worst", "lowlight")


def mpp(lat, z):
    return EQUATOR_M * math.cos(math.radians(lat)) / 2 ** z / 256.0


def latlon_to_px(lat, lon, z):
    n = 2 ** z
    r = math.radians(lat)
    return ((lon + 180) / 360 * n * 256,
            (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n * 256)


def px_to_latlon(px, py, z):
    n = 2 ** z
    return (math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * py / 256.0 / n)))), px / 256.0 / n * 360.0 - 180.0)


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(p[0]))
    return math.hypot(de, dn), de, dn


def shift(p, de, dn):
    return (p[0] + dn / 111320.0, p[1] + de / (111320.0 * math.cos(math.radians(p[0]))))


def load_mosaic(a, z, half_m):
    """BGR mosaic (one map pixel per screen pixel at zoom z) covering the route, and its origin
    in global pixels. From an --area directory of tile_<z>_<x>_<y>.jpg, else from the MBTiles."""
    cx, cy = latlon_to_px(a.lat, a.lon, z)
    r = half_m / mpp(a.lat, z)
    tx0, ty0 = int((cx - r) // 256), int((cy - r) // 256)
    tx1, ty1 = int((cx + r) // 256), int((cy + r) // 256)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), np.uint8)
    conn = None if a.area else sqlite3.connect(f"file:{a.mbtiles}?mode=ro", uri=True)
    missing = 0
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            t = None
            if a.area:
                p = os.path.join(os.path.expanduser(a.area), f"tile_{z}_{tx}_{ty}.jpg")
                t = cv2.imread(p) if os.path.exists(p) else None
            else:
                row = conn.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                                   (z, tx, 2 ** z - 1 - ty)).fetchone()
                if row:
                    t = cv2.imdecode(np.frombuffer(row[0], np.uint8), cv2.IMREAD_COLOR)
            if t is None:
                missing += 1
                continue
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = cv2.resize(t, (256, 256))
    if missing:
        print(f"warning: {missing} display tiles missing (black on the screen)", flush=True)
    return mosaic, tx0 * 256, ty0 * 256


class Renderer:
    """Screen image of the pseudo-thermal scene under one condition at time t (s)."""

    def __init__(self, condition, gsd_m, seed=7):
        self.c, self.gsd = condition, gsd_m
        self.rng = np.random.default_rng(seed)
        h, w = SH, SW
        n = nc._smooth_noise(self.rng, 2 * h, 2 * w, 96) + 0.5 * nc._smooth_noise(self.rng, 2 * h, 2 * w, 24)
        self.cloud_field = n
        self.cloud_thr = float(np.quantile(n, 1 - 0.3))
        self.vehicles = [(self.rng.uniform(0, w), self.rng.uniform(0, h), self.rng.uniform(0, 2 * math.pi),
                          self.rng.uniform(5, 15)) for _ in range(60)]
        self.fires = [(self.rng.uniform(0.2, 0.8) * w, self.rng.uniform(0.2, 0.8) * h) for _ in range(2)]

    def _ctx(self, k):
        pose = nc.Pose("screen", 0, 0, 400.0, 0, 0, 0, 0.0, 400.0, 12.0, (0, 0, 0), (0, 0))
        return nc.Ctx(pose, self.gsd, np.random.default_rng(10_000 + k))

    def render(self, bgr, t, k):
        """bgr: the map view (SH x SW); returns (screen BGR uint8, (jx, jy) scene jitter in screen px)."""
        c, ctx = self.c, self._ctx(k)
        jx = jy = 0.0
        if c in ("wind", "worst"):
            # wind: the vehicle shakes; the scene jitters (2-10 Hz) and blurs along the shake
            jx = 14 * math.sin(2 * math.pi * 2.3 * t) + 6 * math.sin(2 * math.pi * 7.1 * t + 1)
            jy = 10 * math.sin(2 * math.pi * 3.7 * t + 2) + 5 * math.sin(2 * math.pi * 9.7 * t)
            M = np.float32([[1, 0, jx], [0, 1, jy]])
            bgr = cv2.warpAffine(bgr, M, (SW, SH), borderMode=cv2.BORDER_REFLECT)
            # blur along the shake: its speed x a 30 ms integration (microbolometer lag)
            vx = 2 * math.pi * (14 * 2.3 * math.cos(2 * math.pi * 2.3 * t) + 6 * 7.1 * math.cos(2 * math.pi * 7.1 * t + 1))
            vy = 2 * math.pi * (10 * 3.7 * math.cos(2 * math.pi * 3.7 * t + 2) + 5 * 9.7 * math.cos(2 * math.pi * 9.7 * t))
            L = int(min(40, math.hypot(vx, vy) * 0.03))
            if L >= 2:
                ker = np.zeros((2 * L + 1, 2 * L + 1), np.float32)
                ex, ey = vx / math.hypot(vx, vy), vy / math.hypot(vx, vy)
                cv2.line(ker, (int(L - ex * L), int(L - ey * L)), (int(L + ex * L), int(L + ey * L)), 1.0, 1)
                bgr = cv2.filter2D(bgr, -1, ker / ker.sum())
        if c == "lowlight":
            g = nc._lowlight_visible(30.0)(nc.to_thermal(bgr), ctx, bgr)
            return self._out(g), (jx, jy)
        t0 = nc.to_thermal(bgr)
        if c in ("clean", "wind"):
            g = nc.finish(cv2.GaussianBlur(t0, (0, 0), 1.0), ctx)
        elif c == "crossover":
            g = nc.c_low_contrast(t0, ctx, bgr, k=0.12)
        elif c == "polarity":
            g = 1.0 - nc.finish(cv2.GaussianBlur(t0, (0, 0), 1.0), ctx)
        elif c == "fpn_nuc":
            g = nc.c_nuc_drift(t0, ctx, bgr)
        elif c == "dead_pixels":
            g = nc.c_dead_pixels(t0, ctx, bgr)
        elif c == "agc_jumps":
            g = nc.finish(cv2.GaussianBlur(t0, (0, 0), 1.0), ctx)
            a_, b_ = (1.8, 0.2) if int(t / 6) % 3 == 1 else ((0.5, -0.2) if int(t / 6) % 3 == 2 else (1.0, 0.0))
            g = np.clip((g - 0.5) * a_ + 0.5 + b_, 0, 1)
        elif c == "fog":
            g = nc.c_fog(t0, ctx, bgr, trans=0.3)
        elif c == "rain":
            g = nc.c_rain(t0, ctx, bgr)
        elif c in ("clouds", "worst"):
            g = self._clouds(t0, t, ctx)
        elif c == "hot_vehicles":
            g = self._hot(t0, t, ctx, vehicles=True)
        elif c == "fires":
            g = self._hot(t0, t, ctx, fires=True)
        elif c == "lights_drones":
            g = self._lights(nc.finish(cv2.GaussianBlur(t0, (0, 0), 1.0), ctx), t, drones=True)
        elif c == "birds":
            g = self._lights(nc.finish(cv2.GaussianBlur(t0, (0, 0), 1.0), ctx), t, birds=True)
        else:
            raise ValueError(c)
        if c == "worst":
            # crossover + stale NUC stripes + cloud patches (above) + hot vehicles + wind (above)
            g = 0.5 + (g - 0.5) * 0.35
            col = np.random.default_rng(13).normal(0, 0.04, (1, SW)).astype(np.float32)
            g = self._hot(g, t, ctx, vehicles=True, finish=False) + col
            g = nc.finish(g, ctx)
        return self._out(g), (jx, jy)

    @staticmethod
    def _out(g):
        return cv2.cvtColor((np.clip(g, 0, 1) * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)

    def _clouds(self, t0, t, ctx):
        """Low cloud patches (cold, dark in white-hot) drifting over the ground, ~30 % cover."""
        ox, oy = int(t * 25) % SW, int(t * 9) % SH
        fld = self.cloud_field[oy:oy + SH, ox:ox + SW]
        m = np.clip((fld - self.cloud_thr) / 0.4, 0, 1).astype(np.float32)
        g = cv2.GaussianBlur(t0, (0, 0), 1.0)
        return nc.finish(g * (1 - m) + 0.05 * m, ctx)

    def _hot(self, g, t, ctx, vehicles=False, fires=False, finish=True):
        g = g.copy()
        if vehicles:                                 # cars / trucks moving along their own headings
            for x, y, hdg, v in self.vehicles:
                px = (x + math.cos(hdg) * v * t / self.gsd) % SW
                py = (y + math.sin(hdg) * v * t / self.gsd) % SH
                cv2.ellipse(g, (int(px), int(py)), (max(2, int(2.5 / self.gsd)), max(1, int(1.2 / self.gsd))),
                            math.degrees(hdg), 0, 360, 1.6, -1)
        if fires:                                    # two fires, flickering, saturated
            for x, y in self.fires:
                r = (12 + 3 * math.sin(7 * t + x)) / self.gsd
                cv2.circle(g, (int(x), int(y)), int(r), 5.0, -1, lineType=cv2.LINE_AA)
        return nc.finish(cv2.GaussianBlur(g, (0, 0), 1.0), ctx) if finish else g

    def _lights(self, g, t, drones=False, birds=False):
        g = g.copy()
        if drones:
            for k in range(4):                       # hot drones (small crosses) and blinking aircraft lights
                x = SW * (0.5 + 0.42 * math.sin(t * (0.31 + 0.07 * k) + k))
                y = SH * (0.5 + 0.40 * math.cos(t * (0.23 + 0.05 * k) + 2 * k))
                s = (10, 16, 24, 34)[k]
                cv2.line(g, (int(x - s), int(y - s)), (int(x + s), int(y + s)), 1.0, max(2, s // 5))
                cv2.line(g, (int(x - s), int(y + s)), (int(x + s), int(y - s)), 1.0, max(2, s // 5))
            for k in range(3):
                if int(t * 2 + k) % 2:
                    x = (t * (150 + 70 * k) + 500 * k) % SW
                    cv2.circle(g, (int(x), int(SH * (0.25 + 0.25 * k))), 6, 1.0, -1)
        if birds:
            for k in range(25):                      # warm birds crossing fast
                x = (t * (200 + 15 * k) + k * 333) % (SW + 100) - 50
                y = (k * 173 + 40 * math.sin(t * 2 + k)) % SH
                cv2.circle(g, (int(x), int(y)), 3, 0.95, -1)
        return g


# ── the screen part of the camera view → the night localizer's input ───────────

def screen_geometry(mask):
    """From the screen's mask in the camera view: (centre x, y, width px, height px, rotation deg CCW)."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 1000:
        raise RuntimeError("screen mask too small")
    rect = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    (cx, cy), _, _ = rect
    box = cv2.boxPoints(rect)
    edges = [box[(i + 1) % 4] - box[i] for i in range(4)]
    lens = [float(np.hypot(*e)) for e in edges]
    long_e = edges[int(np.argmax(lens))]             # landscape screen: the long side is the width
    ang = math.degrees(math.atan2(float(long_e[1]), float(long_e[0])))
    ang = ((ang + 90.0) % 180.0) - 90.0              # -90..90, image coords (y down: + = clockwise)
    return cx, cy, max(lens), min(lens), -ang        # rotation counter-clockwise on screen


def camera_to_query(img, geom, display_mpp, crop_frac=0.9):
    """Straighten and cut the screen square; returns (square BGR, ground width m)."""
    cx, cy, w, h, rot = geom
    side = crop_frac * min(w, h)
    M = cv2.getRotationMatrix2D((cx, cy), -rot, 1.0)     # undo the screen's rotation in the view
    M[0, 2] += side / 2 - cx
    M[1, 2] += side / 2 - cy
    n = int(round(side))
    sq = cv2.warpAffine(img, M, (n, n), flags=cv2.INTER_LINEAR)
    ground_w = side * (SW / w) * display_mpp             # view px -> screen px -> metres
    return sq, ground_w


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["360", "offline"], default="360")
    ap.add_argument("--condition", choices=CONDITIONS, default="clean")
    ap.add_argument("--area", default="", help="display tiles tile_<z>_<x>_<y>.jpg (e.g. the Wayback 2022 z18 "
                                               "set: another date than the map); default: the MBTiles")
    ap.add_argument("--mbtiles", default=os.environ.get("NAVERA_MBTILES", os.path.expanduser("~/navera_data_map.mbtiles")))
    ap.add_argument("--lat", type=float, default=35.8685)
    ap.add_argument("--lon", type=float, default=10.5352)
    ap.add_argument("--display-zoom", type=int, default=18, help="18: 0.48 m per screen pixel, ~920 m shown")
    ap.add_argument("--speed", type=float, default=20.0)
    ap.add_argument("--radius", type=float, default=600.0)
    ap.add_argument("--seconds", type=float, default=90.0)
    ap.add_argument("--gps-lost-at", type=float, default=25.0)
    ap.add_argument("--latency", type=float, default=1.71, help="s, the 360 stream delay (measured)")
    ap.add_argument("--hfov", type=float, default=100.0, help="straight view on the screen, deg")
    ap.add_argument("--screen-mm", type=float, default=527.0)
    ap.add_argument("--offline-scale", type=float, default=0.337,
                    help="offline: view px per screen px (0.337 = 527 mm screen at 41 cm, 100 deg view)")
    ap.add_argument("--offline-rot", type=float, default=1.5, help="offline: screen rotation in the view, deg")
    ap.add_argument("--offline-dt", type=float, default=1.0, help="offline: simulated seconds between frames")
    ap.add_argument("--save-frames", default="", help="directory: save some screen images and queries")
    ap.add_argument("--render-only", action="store_true",
                    help="write the screen images (--save-frames, every --offline-dt s) and exit")
    ap.add_argument("--out", default="night_screen.csv")
    a = ap.parse_args()

    if a.source == "360" and not a.render_only:
        # the window first: created after torch / the STHN imports, cv2.namedWindow hung at 100 % CPU (2026-10-19)
        cv2.namedWindow("NAVERA night", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("NAVERA night", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.waitKey(1)
    from navera_common.geo import haversine_m
    from night_pkg.nodes.night_localizer import NightLocalizer
    from night_pkg.nodes.night_tracker import NightTracker
    import torch

    z = a.display_zoom
    dmpp = mpp(a.lat, z)
    half = a.radius + 0.6 * SW * dmpp + 100
    mosaic, ox, oy = load_mosaic(a, z, half)
    cx0, cy0 = latlon_to_px(a.lat, a.lon, z)
    rend = Renderer(a.condition, dmpp)
    save = Path(a.save_frames) if a.save_frames else None
    if save:
        save.mkdir(parents=True, exist_ok=True)

    def route(t):
        """Screen-centre ground point (global px) and ground velocity (m/s east, north)."""
        ang = a.speed / a.radius * t
        px = cx0 + a.radius * math.sin(ang) / dmpp
        py = cy0 - a.radius * (1 - math.cos(ang)) / dmpp
        return px, py, (a.speed * math.cos(ang), a.speed * math.sin(ang))

    def view_at(t, k):
        px, py, _ = route(t)
        mx, my = int(round(px - ox - SW / 2)), int(round(py - oy - SH / 2))
        img, (jx, jy) = rend.render(mosaic[my:my + SH, mx:mx + SW].copy(), t, k)
        # the scene moved by the jitter: the ground under the screen centre is shifted back
        return img, px - jx, py - jy

    if a.render_only:                                # check the screen images, nothing else
        out = save or Path(".")
        for k, t in enumerate(np.arange(0.0, a.seconds + 1e-6, a.offline_dt)):
            img, _, _ = view_at(float(t), k)
            cv2.imwrite(str(out / f"{a.condition}_screen_{k:04d}.jpg"), img)
        print(f"{k + 1} screen images written to {out}")
        return
    sthn = os.environ.get("NAVERA_STHN_DIR", os.path.expanduser("~/navera_data/night_pkg/STHN"))
    weights = os.environ.get("NAVERA_STHN_WEIGHTS", os.path.join(sthn, "weights/one_stage/model.safetensors"))
    loc = NightLocalizer(sthn, weights, a.mbtiles)
    track = NightTracker()
    rows, shown, stop = [], [], threading.Event()

    if a.source == "360":
        from navera_tools.bench.view360 import Bench360
        win = "NAVERA night"
        OW, OH = 1200, 900
        cam = Bench360(win)
        print("360 camera, screen found:", cam.find_screen(a.hfov, OW, OH, screen_mm=a.screen_mm), flush=True)
        m = cv2.dilate(cam.screen_mask, np.ones((15, 15), np.uint8))   # undo find_screen's erosion
        geom = screen_geometry(m)
        print(f"screen in the view: {geom[2]:.0f} x {geom[3]:.0f} px, rotated {geom[4]:+.1f} deg", flush=True)
    else:
        geom = None

    axis = []                                        # camera axis offset vs the screen centre (m e, n)
    t_start = time.time()
    last_t = [0.0]

    def localize_frame(img, t, truth_c, k):
        """One camera frame at time t (s since start), truth = ground under the screen centre."""
        q, ground_w = camera_to_query(img, geom, dmpp)
        hfov_q = 60.0
        alt = ground_w / (2 * math.tan(math.radians(hfov_q / 2)))
        phase = "gps" if t < a.gps_lost_at else "lost"
        ax = (float(np.median([v[0] for v in axis])), float(np.median([v[1] for v in axis]))) if axis else (0.0, 0.0)
        truth = shift(truth_c, *ax)
        _, _, vel = route(t)
        hdg, spd = math.degrees(math.atan2(vel[0], vel[1])) % 360, math.hypot(*vel)
        if phase == "gps":
            track.set_known(truth[0], truth[1], t)
            prior = truth
        else:
            track.note_gps_lost(t)
            prior = track.search_centre(t, hdg, spd)
        t0 = time.time()
        r = loc.localize(q, prior[0], prior[1], altitude_m=alt, hfov_deg=hfov_q, heading_deg=0.0)
        ms = (time.time() - t0) * 1000
        acc = bool(r.get("success"))
        fix = (r["lat"], r["lon"]) if acc else None
        fix_err = metres(fix, truth)[0] if fix else None
        if acc and phase == "gps":
            _, de, dn = metres(fix, truth_c)
            axis.append((de, dn))
        src, pub, why = ("gps", truth, "") if phase == "gps" else ("none", None, r.get("reason", ""))
        if phase == "lost":
            if acc:
                why = track.offer(fix[0], fix[1], t, hdg, spd)
                if why is None:
                    src, pub = "night", fix
            if pub is None:
                p = track.coast(t, hdg, spd)
                if p is not None:
                    src, pub = "dead_reckon", p
        sig = r.get("sigma_m")
        rows.append(dict(t=round(t, 2), phase=phase, condition=a.condition, accepted=int(acc),
                         err_m=None if fix_err is None else round(fix_err, 1),
                         sigma_m=None if sig is None else round(float(sig), 1),
                         recheck_m=None if r.get("recheck_m") is None else round(float(r["recheck_m"]), 1),
                         ncc=None if not r.get("verify") else round(float(r["verify"]["ncc"]), 3),
                         ground_w_m=round(ground_w), source=src,
                         navera_err_m=None if pub is None else round(haversine_m(*pub, *truth), 1),
                         ms=round(ms), reason=(why or r.get("reason") or "")[:90]))
        if save and k % 10 == 0:
            cv2.imwrite(str(save / f"{a.condition}_query_{k:04d}.png"), q)
        print(f"{t:6.1f}s {phase:4s} {'FIX ' if acc else 'none'} err "
              f"{'%6.1f' % fix_err if fix_err is not None else '   -  '} m  sigma "
              f"{'%5.1f' % sig if sig else '  -  '}  out={src:11s} {ms:5.0f} ms  {(why or r.get('reason') or '')[:60]}",
              flush=True)

    try:
        if a.source == "offline":
            t, k = 0.0, 0
            room = np.full((900, 1200, 3), 2, np.uint8)
            while t <= a.seconds:
                img, px, py = view_at(t, k)
                if save and k % 10 == 0:
                    cv2.imwrite(str(save / f"{a.condition}_screen_{k:04d}.jpg"), img)
                small = cv2.resize(img, None, fx=a.offline_scale, fy=a.offline_scale, interpolation=cv2.INTER_AREA)
                frame = room.copy()
                h, w = small.shape[:2]
                y0, x0 = (900 - h) // 2, (1200 - w) // 2
                frame[y0:y0 + h, x0:x0 + w] = np.maximum(small, 3)
                M = cv2.getRotationMatrix2D((600, 450), a.offline_rot, 1.0)
                frame = cv2.warpAffine(frame, M, (1200, 900), borderValue=(2, 2, 2))
                if geom is None:                      # the screen's mask, as find_screen gives it
                    m = np.zeros((900, 1200), np.uint8)
                    m[y0:y0 + h, x0:x0 + w] = 1
                    geom = screen_geometry(cv2.warpAffine(m, M, (1200, 900), flags=cv2.INTER_NEAREST))
                frame = np.clip(frame.astype(np.float32) + np.random.default_rng(k).normal(0, 1.5, frame.shape),
                                0, 255).astype(np.uint8)      # the camera's own noise
                localize_frame(frame, t, px_to_latlon(px, py, z), k)
                t += a.offline_dt
                k += 1
        else:
            def worker():
                k = 0
                while not stop.is_set():
                    img, t_arr = cam.grab()
                    if img is None or t_arr <= last_t[0]:
                        time.sleep(0.02)
                        continue
                    last_t[0] = t_arr
                    t = t_arr - t_start - a.latency
                    past = [x for x in list(shown) if x[0] <= t]
                    if not past:
                        continue
                    _, tpx, tpy = past[-1]
                    localize_frame(img, t, px_to_latlon(tpx, tpy, z), k)
                    k += 1
            th = threading.Thread(target=worker, daemon=True)
            th.start()
            k = 0
            while time.time() - t_start <= a.seconds:
                t = time.time() - t_start
                img, px, py = view_at(t, k)
                if save and k % 50 == 0:
                    cv2.imwrite(str(save / f"{a.condition}_screen_{k:05d}.jpg"), img)
                cv2.imshow(win, img)
                key = cv2.waitKey(1)
                shown.append((time.time() - t_start, px, py))
                del shown[:-600]
                k += 1
                if key in (27, ord("q")):
                    break
            stop.set()
            th.join(15)
            cv2.destroyAllWindows()
    finally:
        loc = None                                   # free the model (GPU shared)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    if rows:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    from night_screen_summary import summarize_rows
    print(summarize_rows(a.condition, rows))
    if a.source == "360":
        cam.close()
        os._exit(0)


if __name__ == "__main__":
    main()

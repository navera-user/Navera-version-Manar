#!/usr/bin/env python3
"""Celestial bench with the real 360 camera: a patch of the real star catalogue is drawn on the screen
so that, seen from the camera, every star sits at its true angle; the camera's own optics, exposure
and the all-sky identifier must recognise it, and the field's quality gate (allsky.accept) must
accept only right answers.

    python3 navera_tools/bench/celestial_screen.py [--limits 4,3,2.5] [--fields "88,7;200,-20"]
        [--conditions none,glow,cirrus:1.5,wind:0.5,...,worst] [--out results.json]
    python3 navera_tools/bench/celestial_screen.py --render-only DIR ...   # draw the screens to PNGs, no camera

Run navera_tools/bench/lens_calib_screen.py --save first (dark room, camera not moved since): it
measures the lens and the screen's pose in the camera's frame, and each star is drawn where the
camera's ray towards it meets the screen plane. A sky orientation is chosen so that the star field's
centre (ra, dec) lies along the camera's ray to the screen centre; the identification is right when
its rotation puts that ray back on (ra, dec) — the error is the system's (detection, lens model,
identification), not the drawing's. Only spots on the screen are used. One lens, ~65 degrees: the
full-sky geometry and gravity stay a simulation test (selftest360). Dark room, as at night.

Conditions (name[:amount], amount 1 = the typical strength, 0 = off; see CONDITIONS):
every row logs identified / correct / accepted (allsky.accept with the p_chance allsky.locate computes,
and its retry on the 25 brightest spots) and the gate's reason, so a campaign measures the WRONG-ACCEPT
rate (must be 0) and the false-reject rate per condition.

Spots: the product's detector (allsky.detect_spots_view: the field's local-noise threshold and star-shape blob
filters, F18) on the pinhole view, so the bench judges the stars as the field does; --peak-finder legacy
keeps the bench's former bare local-maximum finder for comparison (~60 spurious spots in clouds and rain).
--save-frames DIR keeps every grabbed view (PNG) so a campaign can be re-analysed offline.
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
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg"), os.path.join(ROOT, "navera_tools", "sim")):
    sys.path.insert(0, p)

from navera_tools.field import allsky  # noqa: E402
from navera_tools.field.reprocess360 import rotvec  # noqa: E402

W = "NAVERA stars"
SW, SH = 1920, 1080
POSE_FILE = os.path.expanduser("~/.navera_sim/insta360_screen_pose.json")
RETRY_SPOTS = 25                     # allsky.locate's retry on the brightest spots when junk crowded the first try
MAX_SPOTS = 60                       # allsky.LOCATE_MAX_SPOTS: the brightest spots given to the identification


def find_spots(g: np.ndarray, mask=None, how: str = "product"):
    """(xs, ys, stats) of the brightest star-like spots of a grey view, brightest first.

    product: allsky.detect_spots_view (the field's detector: local noise per block, one spot per blob, extended /
    saturated / hot-pixel blobs dropped, centroids). legacy: the bench's former finder (a local maximum 6 global
    sigmas above a 12 px background, no blob test), kept to measure what F18 changed.
    """
    if how == "legacy":
        g = g.astype(np.float32)
        res = g - cv2.GaussianBlur(g, (0, 0), 12)
        noise = 1.4826 * float(np.median(np.abs(res - np.median(res)))) + 1e-3
        peak = (res == cv2.dilate(res, np.ones((7, 7), np.uint8))) & (res > 6 * noise)
        if mask is not None:
            peak &= mask > 0
        ys, xs = np.nonzero(peak)
        order = np.argsort(-res[ys, xs])[:MAX_SPOTS]
        return xs[order].astype(float), ys[order].astype(float), {}
    st: dict = {}
    sp = allsky.detect_spots_view(np.clip(g, 0, 255).astype(np.uint8) if g.dtype != np.uint8 else g, mask=mask,
                                  max_spots=MAX_SPOTS, stats=st)
    xs = np.array([x for x, _, _ in sp], float)
    ys = np.array([y for _, y, _ in sp], float)
    return xs, ys, {k: v for k, v in st.items() if v}


# name: what amount 1 means (the default strength); every condition scales with its amount
CONDITIONS = {
    "glow": "city light glow: background ramp 0..70 towards one edge",
    "twilight": "twilight: strong ramp 0..120 from one side + 25 everywhere, stars 30% dimmer",
    "haze": "thin haze: every star 55% dimmer",
    "fog": "fog: stars 70% dimmer, +45 uniform glow, halo around bright stars",
    "cirrus": "thin cirrus: drifting patches dimming stars 0..1.5 mag",
    "clouds": "moving clouds: opaque patches over ~40% of the screen, drifting",
    "moon": "full moon in the field: bright disc (0.5 deg) + scattered glow; amount = phase brightness",
    "moon_out": "full moon just out of the field: glow from one edge only",
    "rain": "rain: drops on the lens (blurred blobs) + falling streaks",
    "dew": "dew/condensation: whole picture blurred (sigma 3 px) + halo",
    "satellites": "satellites: 5 slow steady points (~0.3 deg/s)",
    "planes": "planes: 4 moving blinking lights",
    "drones": "drones: 6 erratic blinking pairs",
    "birds": "birds: 8 dark V shapes crossing",
    "insects": "insects: 10 fast blurred bright blobs",
    "trees": "trees/buildings: opaque silhouettes up to 25% of the screen height from the bottom edge",
    "noise": "noise: 900 flickering speckles + 120 hot pixels",
    "wind": "wind: the whole star field shakes 2-10 Hz with amount deg amplitude, streaked in 1/30 s",
    "reflections": "car-roof reflections: ghosts of bright stars (10%, offset), 8 LED points, a smear band",
}
WORST = {"glow": 1.0, "cirrus": 1.0, "clouds": 0.7, "moon_out": 1.0, "planes": 1.0, "drones": 1.0, "birds": 1.0,
         "insects": 1.0, "trees": 1.0, "noise": 1.0, "wind": 0.3, "reflections": 1.0}


def parse_condition(spec: str) -> dict:
    """'none' / 'worst' / 'all' / 'a:1.5+b' → {name: amount}."""
    spec = spec.strip()
    if spec in ("none", ""):
        return {}
    if spec == "worst":
        return dict(WORST)
    if spec == "all":                                    # the 2026-10-17 'all' row: every old condition at once
        return {k: 1.0 for k in ("glow", "haze", "noise", "planes", "drones", "birds", "clouds")}
    out = {}
    for part in spec.split("+"):
        name, _, amt = part.partition(":")
        if name not in CONDITIONS:
            raise SystemExit(f"unknown condition {name!r}; known: {', '.join(CONDITIONS)}, worst, all, none")
        out[name] = float(amt) if amt else 1.0
    return out


class Sky:
    """Catalogue stars to screen pixels through the measured screen pose."""

    def __init__(self, pose, ra0, dec0, limit):
        from sky_view import load_bsc5
        self.Rs, self.T = rotvec(np.array(pose["rotvec"])), np.array(pose["T_mm"])
        self.mm = pose["mm_per_px"]
        self.px_per_deg = math.radians(1.0) * float(np.linalg.norm(self.T)) / self.mm   # near the screen centre
        self.c_imu = self.T / np.linalg.norm(self.T)                    # camera ray to the screen centre
        up_imu = -self.Rs[:, 1]                                         # screen 'up' in the IMU frame
        # sky frame: the field centre along c_imu, north towards the screen's up
        c = allsky.radec_to_vec(ra0, dec0)
        north = np.array([0, 0, 1.0]) - c[2] * c
        north /= np.linalg.norm(north)
        u = up_imu - (up_imu @ self.c_imu) * self.c_imu
        u /= np.linalg.norm(u)
        A = np.stack([self.c_imu, u, np.cross(self.c_imu, u)], axis=1)  # IMU-frame basis
        B = np.stack([c, north, np.cross(c, north)], axis=1)            # the same basis on the sky
        self.R_icrs_imu = B @ A.T
        ra, dec, mag = load_bsc5(os.path.expanduser("~/.navera_sim"))
        keep = mag <= limit
        d = allsky.radec_to_vec(ra[keep], dec[keep]) @ self.R_icrs_imu   # star rays in the IMU frame
        q_d = d @ self.Rs                                               # in screen axes
        q_T = self.Rs.T @ self.T
        with np.errstate(divide="ignore", invalid="ignore"):
            s = q_T[2] / q_d[:, 2]
        ok = (s > 0) & (d @ self.c_imu > 0.3)
        pts = s[ok, None] * q_d[ok] - q_T
        self.px = pts[:, 0] / self.mm + SW / 2
        self.py = pts[:, 1] / self.mm + SH / 2
        self.mag = mag[keep][ok]
        on = (self.px >= 0) & (self.px < SW) & (self.py >= 0) & (self.py < SH)
        self.n_on_screen = int(on.sum())

    # ── layers ──────────────────────────────────────────────────────────
    def _stars(self, factor, dx=0.0, dy=0.0):
        """The star layer: brightness x factor(x, y) (per star), shifted by (dx, dy) px."""
        img = np.zeros((SH, SW), np.float32)
        for x, y, m in zip(self.px + dx, self.py + dy, self.mag):
            if 0 <= x < SW and 0 <= y < SH:
                b = float(np.clip(255 * 10 ** (-0.4 * m) * 3, 70, 255)) * factor(x, y)
                if b > 1:
                    cv2.circle(img, (int(round(x)), int(round(y))), max(2, int(round(5 - m))), b, -1, cv2.LINE_AA)
        return img

    def draw(self, conds: dict, t: float, rng) -> np.ndarray:
        """The screen picture at time t (s) for the conditions {name: amount}."""
        a = conds.get
        fixed = np.random.default_rng(7)                               # placements that must not jump between frames
        yy, xx = np.mgrid[0:SH, 0:SW].astype(np.float32)

        # star brightness factor (haze, fog, twilight, drifting cirrus)
        dim = 1.0
        dim *= 1 - 0.55 * min(1.0, a("haze", 0))
        dim *= 1 - 0.7 * min(1.0, a("fog", 0))
        dim *= 1 - 0.3 * min(1.0, a("twilight", 0))
        cir = None
        if a("cirrus"):
            lo = fixed.random((SH // 60 + 3, SW // 60 + 3)).astype(np.float32)
            cir = cv2.resize(cv2.GaussianBlur(lo, (0, 0), 1.5), (SW + 180, SH + 180))
            cir = (cir - cir.min()) / (np.ptp(cir) + 1e-6)
            off = int(t * 25) % 180                                     # drifting
            cir = cir[off // 2:off // 2 + SH, off:off + SW]
        def factor(x, y):  # noqa: E306
            f = dim
            if cir is not None:
                f *= 10 ** (-0.4 * 1.5 * a("cirrus") * float(cir[int(y), int(x)]))
            return f

        # wind: the whole field shakes (2-10 Hz), each camera exposure (1/30 s) sees a streak
        if a("wind"):
            amp = a("wind") * self.px_per_deg
            freqs = (2.3, 4.7, 9.1)

            def shake(tt):
                return (amp * sum(math.sin(2 * math.pi * f * tt + k) for k, f in enumerate(freqs)) / 2.2,
                        amp * sum(math.cos(2 * math.pi * f * tt + 2 * k) for k, f in enumerate(freqs)) / 2.2)
            img = np.zeros((SH, SW), np.float32)
            K = 6
            for k in range(K):
                dx, dy = shake(t + k / (30.0 * K))
                img += self._stars(factor, dx, dy) / K
        else:
            img = self._stars(factor)

        # background light
        if a("glow"):
            img += a("glow") * np.linspace(0, 70, SH, dtype=np.float32)[:, None]
        if a("twilight"):
            img += a("twilight") * (25 + 120 * (xx / SW) ** 2)
        if a("fog"):
            img += 45 * a("fog")
            halo = cv2.GaussianBlur(np.where(img > 150, img, 0).astype(np.float32), (0, 0), 12)
            img += 3.0 * a("fog") * halo
        if a("moon"):
            mx, my = SW * 0.68, SH * 0.35
            r = max(3, int(0.25 * self.px_per_deg))                     # 0.5 deg disc
            d = np.hypot(xx - mx, yy - my) / self.px_per_deg
            img += a("moon") * 120 * np.exp(-d / 8.0)
            cv2.circle(img, (int(mx), int(my)), r, 255, -1, cv2.LINE_AA)
        if a("moon_out"):
            d = np.hypot(xx - SW * 1.15, yy - SH * 0.3) / self.px_per_deg
            img += a("moon_out") * 120 * np.exp(-d / 8.0)

        # moving lights and objects
        if a("satellites"):
            for k in range(int(round(5 * a("satellites")))):
                v = 0.3 * self.px_per_deg
                ang = fixed.uniform(0, 2 * math.pi)
                x0, y0 = fixed.uniform(0, SW), fixed.uniform(0, SH)
                cv2.circle(img, (int(x0 + v * t * math.cos(ang)) % SW, int(y0 + v * t * math.sin(ang)) % SH), 3, 200, -1)
        if a("planes"):
            for k in range(int(round(4 * a("planes")))):
                px, py = (t * 90 + k * 480) % SW, (k * 260 + 120) % SH
                cv2.circle(img, (int(px), int(py)), 4, 255, -1)
                if int(t * 2 + k) % 2:
                    cv2.circle(img, (int(px) + 20, int(py)), 3, 200, -1)
        if a("drones"):
            for k in range(int(round(6 * a("drones")))):
                px = SW * (0.5 + 0.45 * math.sin(t * (0.5 + 0.1 * k) + k)) + 30 * math.sin(t * 4 + k)
                py = SH * (0.5 + 0.42 * math.cos(t * (0.4 + 0.1 * k) + 2 * k))
                if int(t * 3 + k) % 2:
                    cv2.circle(img, (int(px), int(py)), 3, 255, -1)
                    cv2.circle(img, (int(px) + 14, int(py)), 3, 180, -1)
        if a("insects"):
            ins = np.zeros((SH, SW), np.float32)
            for k in range(int(round(10 * a("insects")))):
                x = (t * (700 + 90 * k) + k * 333) % (SW + 300) - 150
                y = (k * 211 + 120 * math.sin(t * 3 + k)) % SH
                cv2.line(ins, (int(x), int(y)), (int(x + 40), int(y + 12)), float(fixed.uniform(80, 220)), 9, cv2.LINE_AA)
            img += cv2.GaussianBlur(ins, (0, 0), 6)
        if a("noise"):
            n = rng.integers(0, SW * SH, int(900 * a("noise")))
            img.ravel()[n] = np.maximum(img.ravel()[n], rng.uniform(60, 255, len(n)))
            hot = np.random.default_rng(99).integers(0, SW * SH, int(120 * a("noise")))
            img.ravel()[hot] = 230
        if a("reflections"):
            ghost = np.roll(np.roll(np.where(img > 120, img, 0), 9, axis=1), 6, axis=0) * 0.10 * a("reflections")
            img += ghost
            for k in range(int(round(8 * a("reflections")))):
                cv2.circle(img, (int(fixed.uniform(0, SW)), int(fixed.uniform(SH * 0.5, SH))), 2, 255, -1)
            band = np.exp(-((yy - SH * 0.82) / 40.0) ** 2) * 35 * a("reflections")
            img += band

        # things in front of the sky
        if a("clouds"):
            lo = cv2.GaussianBlur(fixed.random((SH // 8, SW // 8 + 60)).astype(np.float32), (0, 0), 6)
            lo = cv2.resize(lo, (SW + 480, SH))
            off = int(t * 60) % 480
            cl = lo[:, off:off + SW]
            img[cl > np.quantile(cl, 1 - 0.4 * min(1.5, a("clouds")))] = 25
        if a("birds"):
            for k in range(int(round(8 * a("birds")))):
                x = (t * (220 + 30 * k) + k * 260) % (SW + 200) - 100
                y = (k * 131 + 30 * math.sin(t * 2 + k)) % SH
                pts = np.array([[x - 22, y - 9], [x, y], [x + 22, y - 9]], np.int32)
                cv2.polylines(img, [pts], False, 0, 9)
        if a("trees"):
            top = SH * (1 - 0.25 * a("trees"))
            prof = np.full(SW, SH, np.float32)
            x = 0
            while x < SW:
                w = int(fixed.uniform(60, 260))
                if fixed.random() < 0.5:                                   # a building: flat top
                    prof[x:x + w] = fixed.uniform(top, SH)
                else:                                                      # a tree: round crown
                    h = fixed.uniform(top, SH)
                    xs = np.arange(x, min(SW, x + w))
                    prof[xs] = h + (SH - h) * ((xs - x - w / 2) / (w / 2)) ** 2 * 0.6
                x += w
            img[yy >= prof[None, :]] = 0
        if a("rain"):
            drops = np.zeros((SH, SW), np.float32)
            for k in range(int(round(25 * a("rain")))):
                cx, cy, r = fixed.uniform(0, SW), fixed.uniform(0, SH), fixed.uniform(15, 60)
                cv2.circle(drops, (int(cx), int(cy)), int(r), 1.0, -1)
            drops = cv2.GaussianBlur(drops, (0, 0), 8)
            blurred = cv2.GaussianBlur(img, (0, 0), 10)
            img = img * (1 - np.clip(drops, 0, 1)) + blurred * np.clip(drops, 0, 1) + 20 * drops
            for k in range(int(round(30 * a("rain")))):
                x = fixed.uniform(0, SW)
                y = (fixed.uniform(0, SH) + t * 1500) % SH
                cv2.line(img, (int(x), int(y)), (int(x + 8), int(y + 70)), 90.0, 2, cv2.LINE_AA)
        if a("dew"):
            s = 3.0 * a("dew")
            img = cv2.GaussianBlur(img, (0, 0), s) + 0.6 * cv2.GaussianBlur(img, (0, 0), 6 * s)
        return np.clip(img, 0, 255).astype(np.uint8)


def gate(rays, cat):
    """identify + allsky.accept as allsky.locate applies them (one lens: no lens-disagreement test).
    Returns (R or None, row fields)."""
    out = {}
    r = allsky.identify(rays, cat, n_seed=12, with_p=True) if len(rays) >= 6 else None
    why = None
    if r is None:
        out.update(identified=False, accepted=False, gate_why="no star pattern identified")
        return None, out
    R, idx, kidx, rms, p = r
    why = allsky.accept(len(idx), rms, p)
    out.update(identified=True, matched=int(len(idx)), rms_deg=round(rms, 3), p_chance=float(f"{p:.3g}"))
    if why and len(rays) > RETRY_SPOTS:                                # locate's retry on the brightest spots
        r2 = allsky.identify(rays[:RETRY_SPOTS], cat, n_seed=12, with_p=True)
        if r2 is not None and allsky.accept(len(r2[1]), r2[3], r2[4]) is None:
            R, idx, kidx, rms, p = r2
            why = None
            out.update(matched=int(len(idx)), rms_deg=round(rms, 3), p_chance=float(f"{p:.3g}"), retried_with=RETRY_SPOTS)
    out.update(accepted=why is None, gate_why=why)
    return R, out


def render_only(a, pose):
    """Draw every (field, condition, limit) screen at t = 1.3 s to PNGs: checks the drawing without the camera."""
    os.makedirs(a.render_only, exist_ok=True)
    rng = np.random.default_rng(3)
    for field in a.fields.split(";"):
        ra0, dec0 = (float(v) for v in field.split(","))
        for cond in a.conditions.split(","):
            for lim in (float(v) for v in a.limits.split(",")):
                sky = Sky(pose, ra0, dec0, lim)
                img = sky.draw(parse_condition(cond), 1.3, rng)
                name = f"f{ra0:g}_{dec0:g}_{cond.replace(':', '-').replace('+', '_')}_m{lim:g}.png"
                cv2.imwrite(os.path.join(a.render_only, name), img)
                print(f"{name}: {sky.n_on_screen} stars on the screen, {sky.px_per_deg:.1f} px/deg", flush=True)


def offline(a, pose):
    """An ideal camera: the drawn screen itself (+ sensor noise) is detected and turned into rays through the pose.
    It checks the drawing, the gate and the scoring without hardware, and is the baseline the real camera is
    compared with (the real one adds its optics, exposure, compression and the lens model's error)."""
    cat = allsky.Catalogue(limit_mag=4.0)
    rng = np.random.default_rng(3)
    results = []
    for field in a.fields.split(";"):
        ra0, dec0 = (float(v) for v in field.split(","))
        for cond in a.conditions.split(","):
            conds = parse_condition(cond)
            for lim in (float(v) for v in a.limits.split(",")):
                sky = Sky(pose, ra0, dec0, lim)
                g = sky.draw(conds, 1.3, rng).astype(np.float32)
                if a.noise_model == "camera":     # sensor noise, then the optics / demosaic / H.264 smoothing
                    g = cv2.GaussianBlur(g + rng.normal(0, 2.0, g.shape).astype(np.float32), (0, 0), 1.0)
                else:                             # white noise on every pixel after the optics (the original model)
                    g = cv2.GaussianBlur(g, (0, 0), 1.0) + rng.normal(0, 2.0, g.shape).astype(np.float32)
                xs, ys, rej = find_spots(g, None, a.peak_finder)
                p = np.stack([(xs - SW / 2) * sky.mm, (ys - SH / 2) * sky.mm, np.zeros(len(xs))], axis=-1) + sky.Rs.T @ sky.T
                rays = p @ sky.Rs.T
                rays = rays / np.linalg.norm(rays, axis=1, keepdims=True) if len(rays) else rays.reshape(0, 3)
                R, row = gate(rays, cat)
                row = {"field": [ra0, dec0], "condition": cond, "limit_mag": lim, "spots": int(len(rays)),
                       "stars_drawn": sky.n_on_screen, "offline": True, "peak_finder": a.peak_finder,
                       "noise_model": a.noise_model,
                       "rejected_spots": rej, **row}
                if R is not None:
                    err = math.degrees(math.acos(float(np.clip((R @ sky.c_imu) @ allsky.radec_to_vec(ra0, dec0), -1, 1))))
                    row.update(centre_err_deg=round(err, 3), correct=bool(err < 1.0 + 1.5 * conds.get("wind", 0.0)))
                    row["wrong_accept"] = bool(row["accepted"] and not row["correct"])
                print(json.dumps(row), flush=True)
                results.append(row)
    json.dump({"screen": "offline (ideal camera)", "pose": pose, "results": results}, open(a.out, "w"), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limits", default="4,3,2.5")
    ap.add_argument("--conditions", default="none,glow,haze,noise,planes,drones,birds,clouds,all",
                    help="comma-separated; each name[:amount][+name[:amount]], or none/all/worst. Known: "
                         + ", ".join(CONDITIONS))
    ap.add_argument("--fields", default="88,7;200,-20", help="sky centres ra,dec;...")
    ap.add_argument("--out", default="celestial_screen.json")
    ap.add_argument("--render-only", default="", help="folder: save the drawn screens as PNGs, no camera, no window")
    ap.add_argument("--offline", action="store_true", help="ideal camera: solve the drawn screens themselves (no hardware)")
    ap.add_argument("--peak-finder", choices=("product", "legacy"), default="product",
                    help="product: allsky.detect_spots_view, as the field (default); legacy: the former bench finder")
    ap.add_argument("--noise-model", choices=("white", "camera"), default="white",
                    help="--offline: white = 2 DN per pixel after the blur; camera = 2 DN before it (smoothed, as H.264)")
    ap.add_argument("--save-frames", default="", help="folder: keep every grabbed view as a PNG (offline re-analysis)")
    a = ap.parse_args()
    if a.save_frames:
        os.makedirs(a.save_frames, exist_ok=True)
    for c in a.conditions.split(","):
        parse_condition(c)                                             # fail before the camera starts
    pose = json.load(open(POSE_FILE))
    if a.render_only:
        return render_only(a, pose)
    if a.offline:
        return offline(a, pose)
    from navera_tools.bench.view360 import Bench360
    cv2.namedWindow(W, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(W, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cam = Bench360(W)
    info = cam.find_screen(100.0, 1200, 900)
    print("screen:", info, "| pose measured", pose.get("measured"), "lens", pose.get("lens"), flush=True)
    cat = allsky.Catalogue(limit_mag=4.0)
    view = cam.view
    rng = np.random.default_rng(3)
    results = []
    for field in a.fields.split(";"):
        ra0, dec0 = (float(v) for v in field.split(","))
        for cond in a.conditions.split(","):
            conds = parse_condition(cond)
            for lim in (float(v) for v in a.limits.split(",")):
                sky = Sky(pose, ra0, dec0, lim)
                t0 = time.time()
                while time.time() - t0 < 3.5:                          # the stream is ~1.7 s behind
                    cv2.imshow(W, sky.draw(conds, time.time() - t0, rng))
                    cv2.waitKey(30)
                img, _ = cam.grab(stabilise=False)
                if img is None:
                    continue
                g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                if a.save_frames:
                    name = f"f{ra0:g}_{dec0:g}_{cond.replace(':', '-').replace('+', '_')}_m{lim:g}.png"
                    cv2.imwrite(os.path.join(a.save_frames, name), g)
                xs, ys, rej = find_spots(g, cam.screen_mask, a.peak_finder)
                cx, cy = (view.width - 1) / 2, (view.height - 1) / 2
                rays = np.stack([(xs - cx) / view.f, (ys - cy) / view.f, np.ones(len(xs))], axis=-1)
                rays = rays / np.linalg.norm(rays, axis=1, keepdims=True) @ view.R_view_imu   # → IMU frame
                R, row = gate(rays, cat)
                row = {"field": [ra0, dec0], "condition": cond, "limit_mag": lim, "spots": int(len(rays)),
                       "stars_drawn": sky.n_on_screen, "peak_finder": a.peak_finder, "rejected_spots": rej, **row}
                if R is not None:
                    truth = allsky.radec_to_vec(ra0, dec0)
                    err = math.degrees(math.acos(float(np.clip((R @ sky.c_imu) @ truth, -1, 1))))
                    # a wrong identification is worse than none. Wind really moves the drawn field (up to ~1.5 x its
                    # amplitude, which the camera's IMU would measure in the car): a right answer may be off by that much
                    tol = 1.0 + 1.5 * conds.get("wind", 0.0)
                    row.update(centre_err_deg=round(err, 3), correct=bool(err < tol))
                    row["wrong_accept"] = bool(row["accepted"] and not row["correct"])
                row["s"] = round(time.time() - t0, 1)
                print(json.dumps(row), flush=True)
                results.append(row)
                json.dump({"screen": info, "pose": pose, "results": results}, open(a.out, "w"), indent=1)   # survives a stop
    cam.close()
    cv2.destroyAllWindows()
    os._exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Celestial bench with the real 360 camera: a patch of the real star catalogue is drawn on the screen
so that, seen from the camera, every star sits at its true angle; the camera's own optics, exposure
and the all-sky identifier must recognise it.

    python3 navera_tools/bench/celestial_screen.py [--limits 4,3,2.5]
        [--conditions none,glow,haze,noise,planes,drones,birds,clouds,all]

Run navera_tools/bench/lens_calib_screen.py --save first (dark room, camera not moved since): it
measures the lens and the screen's pose in the camera's frame, and each star is drawn where the
camera's ray towards it meets the screen plane. A sky orientation is chosen so that the star field's
centre (ra, dec) lies along the camera's ray to the screen centre; the identification is right when
its rotation puts that ray back on (ra, dec) — the error is the system's (detection, lens model,
identification), not the drawing's. Only spots on the screen are used. One lens, ~65 degrees: the
full-sky geometry and gravity stay a simulation test (selftest360). Dark room, as at night.
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

from navera_tools.bench.view360 import Bench360  # noqa: E402
from navera_tools.field import allsky  # noqa: E402
from navera_tools.field.reprocess360 import rotvec  # noqa: E402

W = "NAVERA stars"
SW, SH = 1920, 1080
POSE_FILE = os.path.expanduser("~/.navera_sim/insta360_screen_pose.json")
CONDITIONS = ("glow", "haze", "noise", "planes", "drones", "birds", "clouds")


class Sky:
    """Catalogue stars to screen pixels through the measured screen pose."""

    def __init__(self, pose, ra0, dec0, limit):
        from sky_view import load_bsc5
        self.Rs, self.T = rotvec(np.array(pose["rotvec"])), np.array(pose["T_mm"])
        self.mm = pose["mm_per_px"]
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

    def draw(self, conditions, t, rng):
        img = np.zeros((SH, SW), np.float32)
        if "glow" in conditions:                                       # city glow towards one edge
            img += np.linspace(0, 70, SH, dtype=np.float32)[:, None]
        for x, y, m in zip(self.px, self.py, self.mag):
            if 0 <= x < SW and 0 <= y < SH:
                b = float(np.clip(255 * 10 ** (-0.4 * m) * 3, 70, 255))
                if "haze" in conditions:                               # thin haze: every star dimmer
                    b *= 0.45
                cv2.circle(img, (int(round(x)), int(round(y))), max(2, int(round(5 - m))), b, -1, cv2.LINE_AA)
        if "noise" in conditions:                                      # flickering speckles + fixed hot pixels
            n = rng.integers(0, SW * SH, 900)
            img.ravel()[n] = np.maximum(img.ravel()[n], rng.uniform(60, 255, 900))
            hot = np.random.default_rng(99).integers(0, SW * SH, 120)
            img.ravel()[hot] = 230
        if "planes" in conditions:                                     # moving lights not in any catalogue
            for k in range(4):
                px, py = (t * 90 + k * 480) % SW, (k * 260 + 120) % SH
                cv2.circle(img, (int(px), int(py)), 4, 255, -1)
                if int(t * 2 + k) % 2:
                    cv2.circle(img, (int(px) + 20, int(py)), 3, 200, -1)
        if "drones" in conditions:                                     # drone lights, blinking, erratic
            for k in range(6):
                px = SW * (0.5 + 0.45 * math.sin(t * (0.5 + 0.1 * k) + k)) + 30 * math.sin(t * 4 + k)
                py = SH * (0.5 + 0.42 * math.cos(t * (0.4 + 0.1 * k) + 2 * k))
                if int(t * 3 + k) % 2:
                    cv2.circle(img, (int(px), int(py)), 3, 255, -1)
                    cv2.circle(img, (int(px) + 14, int(py)), 3, 180, -1)
        if "birds" in conditions:                                      # dark birds crossing, hiding stars
            for k in range(8):
                x = (t * (220 + 30 * k) + k * 260) % (SW + 200) - 100
                y = (k * 131 + 30 * math.sin(t * 2 + k)) % SH
                pts = np.array([[x - 22, y - 9], [x, y], [x + 22, y - 9]], np.int32)
                cv2.polylines(img, [pts], False, 0, 9)
        if "clouds" in conditions:                                     # opaque patches hiding ~40 % of the stars
            noise = cv2.GaussianBlur(np.random.default_rng(5).random((SH // 8, SW // 8)).astype(np.float32), (0, 0), 6)
            noise = cv2.resize(noise, (SW, SH))
            img[noise > np.quantile(noise, 0.6)] = 25
        return np.clip(img, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limits", default="4,3,2.5")
    ap.add_argument("--conditions", default="none,glow,haze,noise,planes,drones,birds,clouds,all")
    ap.add_argument("--fields", default="88,7;200,-20", help="sky centres ra,dec;...")
    ap.add_argument("--out", default="celestial_screen.json")
    a = ap.parse_args()
    pose = json.load(open(POSE_FILE))
    cv2.namedWindow(W, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(W, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cam = Bench360(W)
    info = cam.find_screen(100.0, 1200, 900)
    print("screen:", info, "| pose measured", pose.get("measured"), flush=True)
    cat = allsky.Catalogue(limit_mag=4.0)
    view = cam.view
    rng = np.random.default_rng(3)
    results = []
    for field in a.fields.split(";"):
        ra0, dec0 = (float(v) for v in field.split(","))
        for cond in a.conditions.split(","):
            conds = set(CONDITIONS) if cond == "all" else ({cond} - {"none"})
            for lim in (float(v) for v in a.limits.split(",")):
                sky = Sky(pose, ra0, dec0, lim)
                t0 = time.time()
                while time.time() - t0 < 3.5:                          # the stream is ~1.7 s behind
                    cv2.imshow(W, sky.draw(conds, time.time() - t0, rng))
                    cv2.waitKey(60)
                img, _ = cam.grab(stabilise=False)
                if img is None:
                    continue
                g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
                res = g - cv2.GaussianBlur(g, (0, 0), 12)
                noise = 1.4826 * float(np.median(np.abs(res - np.median(res)))) + 1e-3
                peak = (res == cv2.dilate(res, np.ones((7, 7), np.uint8))) & (res > 6 * noise) & (cam.screen_mask > 0)
                ys, xs = np.nonzero(peak)
                order = np.argsort(-res[ys, xs])[:60]
                xs, ys = xs[order], ys[order]
                cx, cy = (view.width - 1) / 2, (view.height - 1) / 2
                rays = np.stack([(xs - cx) / view.f, (ys - cy) / view.f, np.ones(len(xs))], axis=-1)
                rays = rays / np.linalg.norm(rays, axis=1, keepdims=True) @ view.R_view_imu   # → IMU frame
                r = allsky.identify(rays, cat, n_seed=12) if len(rays) >= 6 else None
                row = {"field": [ra0, dec0], "condition": cond, "limit_mag": lim, "spots": int(len(rays)),
                       "stars_drawn": int(((sky.px >= 0) & (sky.px < SW) & (sky.py >= 0) & (sky.py < SH)).sum())}
                if r is None:
                    row.update(identified=False)
                else:
                    R, idx, kidx, rms = r
                    truth = allsky.radec_to_vec(ra0, dec0)
                    err = math.degrees(math.acos(float(np.clip((R @ sky.c_imu) @ truth, -1, 1))))
                    row.update(identified=True, matched=int(len(idx)), rms_deg=round(rms, 3), centre_err_deg=round(err, 3),
                               correct=bool(err < 1.0))               # a wrong identification is worse than none
                row["s"] = round(time.time() - t0, 1)
                print(json.dumps(row), flush=True)
                results.append(row)
    json.dump({"screen": info, "pose": pose, "results": results}, open(a.out, "w"), indent=1)
    cam.close()
    cv2.destroyAllWindows()
    os._exit(0)


if __name__ == "__main__":
    main()

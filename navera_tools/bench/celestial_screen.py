#!/usr/bin/env python3
"""Celestial bench with the real 360 camera: a patch of the real star catalogue is drawn on the screen
so that, seen from the camera, every star sits at its true angle; the camera's own optics, exposure
and the all-sky identifier must recognise it.

    python3 navera_tools/bench/celestial_screen.py [--limits 4,3,2.5] [--conditions none,glow,planes,drones,clouds]

What it measures (per star-brightness limit and condition): spots found, stars identified, the
direction of the screen centre among the stars against what was drawn (angular error, degrees),
and the fit residual of the matched stars (the lens model against the real lens). The screen covers
~64 degrees of one lens only: the full-sky geometry and gravity are tested in simulation
(selftest360), not here. Assumes the camera faces the screen square-on (the drawing is a gnomonic
projection centred on the camera's view of the screen centre).
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

W = "NAVERA stars"
SW, SH = 1920, 1080


def draw_sky(ra0, dec0, hfov_deg, limit, condition, t, rng):
    """Gnomonic projection of the catalogue around (ra0, dec0), north up, the screen hfov_deg wide."""
    from sky_view import load_bsc5
    ra, dec, mag = load_bsc5(os.path.expanduser("~/.navera_sim"))
    keep = mag <= limit
    v = allsky.radec_to_vec(ra[keep], dec[keep])
    c = allsky.radec_to_vec(ra0, dec0)
    east = np.cross([0, 0, 1.0], c)
    east /= np.linalg.norm(east)
    north = np.cross(c, east)
    z = v @ c
    f = (SW / 2) / math.tan(math.radians(hfov_deg) / 2)
    ok = z > 0.2
    x = SW / 2 - f * (v[ok] @ east) / z[ok]                 # sky seen from below: east is to the left
    y = SH / 2 - f * (v[ok] @ north) / z[ok]
    m = mag[keep][ok]
    img = np.zeros((SH, SW), np.float32)
    if condition == "glow":                                  # city glow towards one edge
        img += np.linspace(0, 70, SH, dtype=np.float32)[:, None]
    for xi, yi, mi in zip(x, y, m):
        if 0 <= xi < SW and 0 <= yi < SH:
            r = max(2, int(round(5 - mi)))
            b = float(np.clip(255 * 10 ** (-0.4 * (mi - 0.0)) * 3, 70, 255))
            cv2.circle(img, (int(xi), int(yi)), r, b, -1, cv2.LINE_AA)
    if condition == "planes":                                # moving lights not in any catalogue
        for k in range(4):
            px, py = (t * 90 + k * 480) % SW, (k * 260 + 120) % SH
            cv2.circle(img, (int(px), int(py)), 4, 255, -1)
            if int(t * 2 + k) % 2:
                cv2.circle(img, (int(px) + 20, int(py)), 3, 200, -1)
    if condition == "drones":                                # drone lights: blinking red/green/white points moving erratically
        for k in range(6):
            px = SW * (0.5 + 0.45 * math.sin(t * (0.5 + 0.1 * k) + k)) + 30 * math.sin(t * 4 + k)
            py = SH * (0.5 + 0.42 * math.cos(t * (0.4 + 0.1 * k) + 2 * k))
            if int(t * 3 + k) % 2:
                cv2.circle(img, (int(px), int(py)), 3, 255, -1)
                cv2.circle(img, (int(px) + 14, int(py)), 3, 180, -1)
    if condition == "clouds":                                # opaque dark patches hiding ~40 % of the stars
        noise = cv2.GaussianBlur(rng.random((SH // 8, SW // 8)).astype(np.float32), (0, 0), 6)
        noise = cv2.resize(noise, (SW, SH))
        img[noise > np.quantile(noise, 0.6)] = 25
    return np.clip(img, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limits", default="4,3,2.5")
    ap.add_argument("--conditions", default="none,glow,planes,drones,clouds")
    ap.add_argument("--fields", default="88,7;200,-20;15,40", help="sky centres ra,dec;...")
    ap.add_argument("--out", default="celestial_screen.json")
    a = ap.parse_args()
    cv2.namedWindow(W, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(W, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cam = Bench360(W)
    info = cam.find_screen(100.0, 1200, 900)
    hfov_s = info["screen_width_deg"]
    print("screen:", info, flush=True)
    cat = allsky.Catalogue(limit_mag=4.0)
    view = cam.view
    rng = np.random.default_rng(3)
    results = []
    for field in a.fields.split(";"):
        ra0, dec0 = (float(v) for v in field.split(","))
        for cond in a.conditions.split(","):
            for lim in (float(v) for v in a.limits.split(",")):
                t0 = time.time()
                end = t0 + 3.5                               # show it; the stream is ~1.5 s behind
                while time.time() < end:
                    cv2.imshow(W, draw_sky(ra0, dec0, hfov_s, lim, cond, time.time() - t0, rng))
                    cv2.waitKey(60)
                img, _ = cam.grab()
                if img is None:
                    continue
                g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                # spots in the straight view → rays in the view frame
                bg = cv2.GaussianBlur(g.astype(np.float32), (0, 0), 12)
                res = g.astype(np.float32) - bg
                noise = 1.4826 * float(np.median(np.abs(res - np.median(res)))) + 1e-3
                peak = (res == cv2.dilate(res, np.ones((7, 7), np.uint8))) & (res > 6 * noise)
                ys, xs = np.nonzero(peak)
                flux = res[ys, xs]
                order = np.argsort(-flux)[:60]
                xs, ys = xs[order], ys[order]
                cx, cy = (view.width - 1) / 2, (view.height - 1) / 2
                rays = np.stack([(xs - cx) / view.f, (ys - cy) / view.f, np.ones(len(xs))], axis=-1)
                rays = rays / np.linalg.norm(rays, axis=1, keepdims=True)
                r = allsky.identify(rays, cat, n_seed=12) if len(rays) >= 6 else None
                row = {"field": [ra0, dec0], "condition": cond, "limit_mag": lim, "spots": int(len(rays))}
                if r is None:
                    row.update(identified=False)
                else:
                    R, idx, kidx, rms = r
                    # the screen centre: where the camera's view of it points among the stars
                    ra_c, dec_c = allsky.vec_to_radec(R @ np.array([0.0, 0.0, 1.0]))
                    err = math.degrees(math.acos(float(np.clip(allsky.radec_to_vec(ra_c, dec_c) @ allsky.radec_to_vec(ra0, dec0), -1, 1))))
                    row.update(identified=True, matched=int(len(idx)), rms_deg=round(rms, 3), centre_err_deg=round(err, 3))
                row["s"] = round(time.time() - t0, 1)
                print(json.dumps(row), flush=True)
                results.append(row)
    json.dump({"screen": info, "results": results}, open(a.out, "w"), indent=1)
    cam.close()
    cv2.destroyAllWindows()
    os._exit(0)


if __name__ == "__main__":
    main()

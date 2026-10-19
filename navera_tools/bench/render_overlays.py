#!/usr/bin/env python3
"""Render screen_flight's overlays to PNG files (no window, no camera): check them before a bench run.

    python3 navera_tools/bench/render_overlays.py --area ~/.navera_sim/bench_2026-10-06/area \
        --lat 35.82227 --lon 10.61691 --out /tmp/overlays [--kinds rain,wind] [--amounts 0.3,0.7]

Writes <out>/<kind>_<amount>_t<time>.png (half size) and prints the draw time per frame: the
screen is redrawn every display frame, a slow overlay lowers the scrolling rate.
"""
import argparse
import math
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from navera_tools.bench.screen_overlays import KINDS, Overlays  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--kinds", default=",".join(KINDS))
    ap.add_argument("--amounts", default="0.3,0.7")
    ap.add_argument("--times", default="1.0,4.3")
    a = ap.parse_args()
    z, W, H = 17, 1920, 1080
    n = 2 ** z
    cx = (a.lon + 180) / 360 * n * 256
    r = math.radians(a.lat)
    cy = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n * 256
    view = np.zeros((H, W, 3), np.uint8)
    for ty in range(int((cy - H / 2) // 256), int((cy + H / 2) // 256) + 1):
        for tx in range(int((cx - W / 2) // 256), int((cx + W / 2) // 256) + 1):
            t = cv2.imread(os.path.join(a.area, f"tile_{z}_{tx}_{ty}.jpg"))
            if t is None:
                continue
            t = cv2.resize(t, (256, 256))
            x0, y0 = int(tx * 256 - (cx - W / 2)), int(ty * 256 - (cy - H / 2))
            xs, ys = max(0, -x0), max(0, -y0)
            xe, ye = min(256, W - x0), min(256, H - y0)
            if xe > xs and ye > ys:
                view[y0 + ys:y0 + ye, x0 + xs:x0 + xe] = t[ys:ye, xs:xe]
    os.makedirs(a.out, exist_ok=True)
    ov = Overlays(W, H)
    print("| overlay | amount | draw ms (median) | scene shift px (max) |\n|---|---|---|---|")
    for kind in a.kinds.split(","):
        for amt in (float(v) for v in a.amounts.split(",")):
            ms, sh = [], []
            for tt in np.arange(0.0, 5.0, 0.25):
                t0 = time.time()
                img, shift = ov.draw(view, float(tt), [kind], amt)
                ms.append((time.time() - t0) * 1000)
                sh.append(math.hypot(*shift))
            for tt in (float(v) for v in a.times.split(",")):
                img, _ = ov.draw(view, tt, [kind], amt)
                cv2.imwrite(os.path.join(a.out, f"{kind}_{amt:g}_t{tt:g}.png"),
                            cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA))
            print(f"| {kind} | {amt:g} | {np.median(ms):.0f} | {max(sh):.0f} |", flush=True)


if __name__ == "__main__":
    main()

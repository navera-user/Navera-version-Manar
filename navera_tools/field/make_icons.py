#!/usr/bin/env python3
"""Draw the phone app's icons (navera_tools/field/static/icon-*.png): a dark sky, a ring of stars
and the zenith mark in NAVERA red. Run once; the PNGs are committed.

    python3 navera_tools/field/make_icons.py
"""
import math
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
BG, RED, STAR = (11, 13, 18), (255, 106, 77), (217, 221, 232)


def icon(n):
    s = 4 * n                                         # drawn large, scaled down: smooth edges
    im = Image.new("RGB", (s, s), BG)
    d = ImageDraw.Draw(im)
    c = s / 2
    d.ellipse([c - 0.34 * s, c - 0.34 * s, c + 0.34 * s, c + 0.34 * s], outline=(34, 39, 55), width=int(0.018 * s))
    for k, (a, r, sz) in enumerate([(20, .30, .030), (95, .24, .022), (160, .31, .026), (215, .19, .018),
                                    (260, .28, .028), (320, .22, .020), (350, .12, .016)]):
        x, y = c + r * s * math.cos(math.radians(a)), c - r * s * math.sin(math.radians(a))
        d.ellipse([x - sz * s, y - sz * s, x + sz * s, y + sz * s], fill=STAR)
    w = 0.05 * s                                       # the zenith cross
    d.rectangle([c - w / 2, c - 0.13 * s, c + w / 2, c + 0.13 * s], fill=RED)
    d.rectangle([c - 0.13 * s, c - w / 2, c + 0.13 * s, c + w / 2], fill=RED)
    return im.resize((n, n), Image.LANCZOS)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for n, name in ((192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")):
        icon(n).save(os.path.join(OUT, name), optimize=True)
        print(name, os.path.getsize(os.path.join(OUT, name)), "bytes")

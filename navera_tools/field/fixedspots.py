#!/usr/bin/env python3
"""Camera-fixed junk: spots that stay on the same pixel for half an hour are not stars. Find them, mask them.

    python3 -m navera_tools.field.fixedspots build <session> --out MASK.png [--every 10] [--min-sep-min 30]
        [--px 3] [--min-repeats 3]
    python3 -m navera_tools.field.fixedspots stats <session> --mask MASK.png [--last N]

The sky turns 0.25 deg per minute about the celestial pole, so in 30 minutes a star at angle d from the pole
moves 7.5 deg x sin(d) over the sensor, even for a camera that does not move at all (and more for one that
does). A spot found within --px pixels of the same place in >= --min-repeats frames that are each at least
--min-sep-min minutes apart is therefore fixed to the camera: a lit object in the room, a reflection on the
window or the plastic cover, a street lamp, a hot pixel cluster, an H.264 pattern. Only stars closer than
~2.5 deg to the celestial pole move less than 3 px (~0.3 deg) in 30 minutes: Polaris (0.65 deg) is lost, no
other star of the catalogue is.

The mask (PNG, 255 = fixed junk) is built from the spots alone, never from the catalogue, so removing these
spots keeps the solver's chance probability honest: it is computed from the spots that remain.
apply_mask() paints the masked discs with the local background so that allsky.detect_spots / locate see no
spot there; resolve_prior and starcheck take --junk-mask.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DISC_PX = 5          # radius of the masked disc around a fixed spot (its blob and centroid scatter)


def rows_of(folder: str):
    name = "frames.jsonl" if os.path.exists(os.path.join(folder, "frames.jsonl")) else "index.jsonl"
    with open(os.path.join(folder, name)) as fh:
        rows = [json.loads(line) for line in fh]
    return [r for r in rows if r.get("image")]


def fixed_spots(spots, min_sep_s: float, px: float, min_repeats: int):
    """spots: (N, 3) array of (t, x, y). Boolean (N,): the spot recurs within px in >= min_repeats OTHER
    frames (distinct t) each at least min_sep_s away from it in time."""
    import numpy as np
    from scipy.spatial import cKDTree
    spots = np.asarray(spots, float).reshape(-1, 3)
    if len(spots) == 0:
        return np.zeros(0, bool)
    t, xy = spots[:, 0], spots[:, 1:3]
    near = cKDTree(xy).query_ball_point(xy, px)
    out = np.zeros(len(spots), bool)
    for i, nb in enumerate(near):
        out[i] = len({t[j] for j in nb if abs(t[j] - t[i]) >= min_sep_s}) >= min_repeats
    return out


def make_mask(shape, xy, disc_px: int = DISC_PX):
    """uint8 image, 255 in a disc of disc_px around each (x, y)."""
    import cv2
    import numpy as np
    m = np.zeros(shape[:2], np.uint8)
    for x, y in xy:
        cv2.circle(m, (int(round(x)), int(round(y))), disc_px, 255, -1)
    return m


def apply_mask(gray, mask):
    """gray with the masked pixels replaced by the local background (median over 31 px): no spot left there."""
    import cv2
    if mask is None:
        return gray
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    bg = cv2.medianBlur(gray, 31)
    out = gray.copy()
    out[mask > 0] = bg[mask > 0]
    return out


def collect(folder: str, rows, k_sigma=None):
    """(t, x, y) of every spot of both lenses (no altitude cut) in the given rows."""
    import cv2
    from cn_pkg import allsky, sky360
    lenses = sky360.default_lenses()
    out, shape = [], None
    for r in rows:
        img = cv2.imread(os.path.join(folder, r["image"]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        shape = img.shape
        for L in lenses:
            out += [(r["t"], x, y) for x, y, _ in allsky.detect_spots(img, L, k_sigma=k_sigma, max_spots=300)]
    return out, shape


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("build", "stats"))
    ap.add_argument("folder")
    ap.add_argument("--out", help="build: the mask PNG to write")
    ap.add_argument("--mask", help="stats: the mask PNG to test")
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--last", type=int, default=0)
    ap.add_argument("--min-sep-min", type=float, default=30.0)
    ap.add_argument("--px", type=float, default=3.0)
    ap.add_argument("--min-repeats", type=int, default=3)
    a = ap.parse_args(argv)
    import cv2
    import numpy as np
    rows = rows_of(a.folder)[::a.every]
    if a.last:
        rows = rows[-a.last:]
    spots, shape = collect(a.folder, rows)
    if not spots:
        print("no spots")
        return 1
    sp = np.array(spots)
    if a.cmd == "build":
        fx = fixed_spots(sp, a.min_sep_min * 60.0, a.px, a.min_repeats)
        mask = make_mask(shape, sp[fx, 1:3])
        cv2.imwrite(a.out, mask)
        n = len(set(sp[:, 0]))
        print(f"{n} frames, {len(sp) / n:.1f} spots/frame, {fx.mean() * 100:.0f} % fixed to the camera; "
              f"mask {int((mask > 0).sum())} px -> {a.out}")
    else:
        m = cv2.imread(a.mask, cv2.IMREAD_GRAYSCALE)
        xi = np.clip(np.rint(sp[:, 1]).astype(int), 0, m.shape[1] - 1)
        yi = np.clip(np.rint(sp[:, 2]).astype(int), 0, m.shape[0] - 1)
        hit = m[yi, xi] > 0
        n = len(set(sp[:, 0]))
        print(f"{n} frames: {len(sp) / n:.1f} spots/frame, {(~hit).sum() / n:.1f} left outside the mask")
    return 0


if __name__ == "__main__":
    sys.exit(main())

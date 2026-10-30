#!/usr/bin/env python3
"""Forced photometry: is there ANY starlight at the catalogue's places, summed over many frames of a still camera?

    python3 -m navera_tools.field.forcedcheck <session> --at LAT,LON [--last N | --since HH:MM] [--every N]
        [--mag 3.0] [--lens right] [--min-alt 15]

starcheck compares DETECTED spots with the catalogue, so a star must first pass the 6-sigma detector in one
frame. Here nothing is detected: for each frame the local signal-to-noise map (the detector's own background and
noise, allsky._detect_blobs) is read at the predicted pixel of every bright star (+ planets) for every heading
about the true zenith, and the readings are summed over all frames. A still camera keeps one heading all night,
so faint stars add up frame after frame while they drift over the sensor (no stacking smear). The same sum at
NULL_PLACES (wrong zeniths, same frames) is the honest reference: junk (room, lamps, clouds) scores the same there.

Output: per heading the true-place score; z = (best true score - mean of the null scores) / their spread
(each null place's best heading). z >= 5 at a stable heading = real starlight that the detector misses.
This is a sensitivity diagnostic with the true place known; it makes no fix and changes nothing in the product.
Memory ~300 MB (one frame + its maps), ~2 s per frame on the Jetson.
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.field.starcheck import NULL_OFFSETS  # noqa: E402

SNR_CLIP = 8.0       # one reading counts at most this much (a lamp or a lit cloud edge cannot dominate the sum)
SEARCH_PX = 3        # the predicted pixel is read as the max over (2 * SEARCH_PX + 1)^2 (lens model error)


def snr_map(gray, k_blur: float = 12.0):
    """The detector's signal-to-noise map: residual over a Gaussian background / per-block robust noise."""
    import cv2
    import numpy as np
    from cn_pkg import allsky
    sub = gray.astype(np.float32)
    res = sub - cv2.GaussianBlur(sub, (0, 0), k_blur)
    h, w = res.shape
    B = allsky.NOISE_BLOCK
    hb, wb = h // B, w // B
    blocks = np.abs(res[:hb * B, :wb * B]).reshape(hb, B, wb, B).transpose(0, 2, 1, 3).reshape(hb, wb, B * B)
    noise_b = np.maximum(1.4826 * np.median(blocks, axis=2), allsky.NOISE_FLOOR).astype(np.float32)
    snr = res / cv2.resize(noise_b, (w, h), interpolation=cv2.INTER_LINEAR)
    k = 2 * SEARCH_PX + 1
    d = cv2.dilate(snr, np.ones((k, k), np.uint8))
    # the max over a box is biased up (~+2.5 for pure noise): standardise it over the frame (robustly) so that a
    # point on noise reads 0 +- 1 whatever the number of points in view at a heading
    sample = d[::7, ::7]
    med = float(np.median(sample))
    mad = float(np.median(np.abs(sample - med))) * 1.4826
    return (d - med) / max(mad, 1e-3)


def heading_scores(snr, lens, up, z, vec, weight, step_deg: float, min_alt: float, sky=None):
    """Score of every heading: sum over catalogue points of the clipped SNR at their predicted pixel.

    vec: (K, 3) ICRS unit vectors; weight: (K,) per point. Points below min_alt (at this zenith), outside the
    image circle or outside the sky mask (sky: bool image, optional) do not count. Returns (scores, n_points).
    """
    import numpy as np
    from cn_pkg.allsky import _align
    alt = np.degrees(np.arcsin(np.clip(vec @ z, -1, 1)))
    keep = alt > min_alt
    vec, weight = vec[keep], weight[keep]
    R0 = _align(up, z)                                        # R @ imu ray = ICRS ray
    psis = np.radians(np.arange(0.0, 360.0, step_deg))
    # rotation about z by psi (Rodrigues, all headings at once): R(psi) = I + sin K + (1 - cos) K^2
    K = np.array([[0.0, -z[2], z[1]], [z[2], 0.0, -z[0]], [-z[1], z[0], 0.0]])
    Rz = (np.eye(3)[None] + np.sin(psis)[:, None, None] * K[None]
          + (1 - np.cos(psis))[:, None, None] * (K @ K)[None])
    R = Rz @ R0                                               # (P, 3, 3)
    v_lens = np.einsum("kj,pji,li->pkl", vec, R, lens.R_lens_imu)   # ICRS -> IMU (R.T v) -> lens
    x, y, _ = lens.project(v_lens)
    h, w = snr.shape
    xi, yi = np.rint(x).astype(int), np.rint(y).astype(int)
    ok = (v_lens[..., 2] > -0.2) & (np.hypot(x - lens.cx, y - lens.cy) < lens.radius - 10)
    ok &= (xi >= 0) & (yi >= 0) & (xi < w) & (yi < h)
    xi, yi = np.where(ok, xi, 0), np.where(ok, yi, 0)
    if sky is not None:
        ok &= sky[yi, xi]
    val = np.clip(snr[yi, xi], -SNR_CLIP, SNR_CLIP) * weight[None, :]
    scores = np.where(ok, val, 0.0).sum(axis=1)
    return scores, int(keep.sum())


def inject(gray, lens, up, z, psi_deg: float, vec, amp_dn: float, sigma_px: float = 1.0):
    """gray (float32 copy) with a Gaussian spot of peak amp_dn at each point's pixel for heading psi_deg about z
    (the same geometry as heading_scores): the sensitivity test on real frames and in the tests."""
    import numpy as np
    from cn_pkg.allsky import _align
    from cn_pkg.allsky_mount import rotvec
    out = gray.astype(np.float32).copy()
    R = rotvec(z * math.radians(psi_deg)) @ _align(up, z)
    v_lens = (vec @ R) @ lens.R_lens_imu.T
    x, y, _ = lens.project(v_lens)
    h, w = out.shape
    r = int(math.ceil(4 * sigma_px))
    gy, gx = np.mgrid[-r:r + 1, -r:r + 1]
    for xx, yy, vz in zip(x, y, v_lens[:, 2]):
        if vz <= -0.2 or math.hypot(xx - lens.cx, yy - lens.cy) >= lens.radius - 10:
            continue
        xi, yi = int(round(xx)), int(round(yy))
        if r <= xi < w - r and r <= yi < h - r:
            g = amp_dn * np.exp(-((gx + xi - xx) ** 2 + (gy + yi - yy) ** 2) / (2 * sigma_px ** 2))
            out[yi - r:yi + r + 1, xi - r:xi + r + 1] += g
    return out


def points(cat, utc: str, lat: float, lon: float, max_mag: float):
    """Catalogue stars to max_mag + the bright planets above the horizon, weight 1 each (any light counts)."""
    import numpy as np
    from cn_pkg import allsky
    sel = cat.mag <= max_mag
    vec = [cat.vec[sel]]
    for v, _m in allsky.planet_vectors(utc, lat, lon).values():
        vec.append(np.asarray(v, float)[None, :])
    vec = np.vstack(vec)
    return vec, np.ones(len(vec))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session", help="a session folder (frames.jsonl) or a deepstack output (index.jsonl)")
    ap.add_argument("--at", required=True, help="LAT,LON of the camera")
    ap.add_argument("--last", type=int, default=0)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--since", help="HH:MM local time: only frames after it (today or last night)")
    ap.add_argument("--mag", type=float, default=3.0)
    ap.add_argument("--lens", default="right", choices=("left", "right", "both"))
    ap.add_argument("--min-alt", type=float, default=15.0)
    ap.add_argument("--step", type=float, default=0.5, help="heading step, deg")
    ap.add_argument("--sky-mask", help="PNG (non-zero = sky): only points over the sky count")
    ap.add_argument("--inject-dn", type=float, default=0.0,
                    help="sensitivity test: add the points at the true place with this peak (DN) first")
    ap.add_argument("--inject-heading", type=float, default=100.0)
    ap.add_argument("--save", help="save the summed scores (places x headings) to this .npy")
    a = ap.parse_args(argv)
    import cv2
    import numpy as np
    from cn_pkg import allsky, sky360
    from cn_pkg.allsky_mount import zenith_icrs
    lat, lon = (float(v) for v in a.at.split(","))
    cat = allsky.Catalogue(limit_mag=a.mag, path=allsky.BUNDLED_CATALOGUE)
    lenses = [L for L in sky360.default_lenses() if a.lens in ("both", L.name)]
    sky = None
    if a.sky_mask:
        sky = cv2.imread(a.sky_mask, cv2.IMREAD_GRAYSCALE) > 0
    name = "frames.jsonl" if os.path.exists(os.path.join(a.session, "frames.jsonl")) else "index.jsonl"
    with open(os.path.join(a.session, name)) as fh:
        rows = [json.loads(line) for line in fh]
    rows = [r for r in rows if r.get("image") and r.get("up_imu")]
    if a.since:
        hh, mm = (int(v) for v in a.since.split(":"))
        t_last = rows[-1]["t"]
        lt = datetime.fromtimestamp(t_last)
        start = lt.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if start.timestamp() > t_last:
            start = datetime.fromtimestamp(start.timestamp() - 86400)
        rows = [r for r in rows if r["t"] >= start.timestamp()]
    rows = rows[::a.every]
    if a.last:
        rows = rows[-a.last:]
    places = [(lat, lon)] + [(max(-89.0, min(89.0, lat + da)), (lon + db + 540.0) % 360.0 - 180.0)
                             for da, db in NULL_OFFSETS]
    total = None
    n_used = 0
    for r in rows:
        img = cv2.imread(os.path.join(a.session, r["image"]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        t = r.get("t_exp") or r["t"]
        utc = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        up = np.asarray(r["up_imu"], float)
        up /= np.linalg.norm(up)
        vec, wgt = points(cat, utc, lat, lon, a.mag)
        if a.inject_dn:
            z0 = zenith_icrs(lat, lon, utc)
            for L in lenses:
                img = inject(img, L, up, z0, a.inject_heading, vec, a.inject_dn)
        snr = snr_map(img)
        per = []
        for pl in places:
            z = zenith_icrs(pl[0], pl[1], utc)
            s = sum(heading_scores(snr, L, up, z, vec, wgt, a.step, a.min_alt, sky)[0] for L in lenses)
            per.append(s)
        per = np.array(per)
        total = per if total is None else total + per
        n_used += 1
        best = int(np.argmax(per[0]))
        print(f"{r.get('idx', '?'):>5} {utc}  frame best heading {best * a.step:5.1f} score {per[0][best]:6.1f}"
              f"  running best {np.argmax(total[0]) * a.step:5.1f}", flush=True)
    if total is None:
        print("no frames")
        return 1
    if a.save:
        np.save(a.save, total)
    true_best = float(total[0].max())
    psi = float(np.argmax(total[0]) * a.step)
    null_best = total[1:].max(axis=1)
    null_all = total[1:].ravel()
    z_score = (true_best - null_all.mean()) / max(null_all.std(), 1e-9)
    z_null = (null_best.max() - null_all.mean()) / max(null_all.std(), 1e-9)
    print(f"{n_used} frames: true place best heading {psi:.1f} deg score {true_best:.1f} (z {z_score:.1f}); "
          f"wrong places best z {z_null:.1f} -> "
          + ("STARLIGHT at the true place" if true_best > null_best.max() and z_score >= 5
             else "no starlight above the wrong-place level"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

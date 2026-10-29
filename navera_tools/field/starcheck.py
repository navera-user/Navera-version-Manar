#!/usr/bin/env python3
"""Are there real stars in these 360 frames at all? A solver-independent check with the true place known.

    python3 -m navera_tools.field.starcheck <session or deepstack folder> --at LAT,LON [--last N | --every N]

For a camera at a known place (a fixed test, or the phone's GPS) and 'up' from its IMU, the only unknown of the
sky's orientation is the turn about the zenith. Each frame's spots are compared with the catalogue at the true
zenith for every heading (0.2 deg steps), and the best count is set against the same scan at NULL_PLACES (wrong
zeniths, same spots): real stars give a sharp excess at one heading, stable from frame to frame for a camera
that does not turn; junk (noise, H.264 blocks, lamps, lit clouds) gives the same counts everywhere.

Light (one frame at a time, ~3 s per frame on the Jetson): fine next to a live test with nice.
Validated (2026-10-30) by injecting the catalogue into a real frame of the night: 6 DN at magnitude 3 gives
51 matches at the right heading against 7 for the null places; the night's real frames all scored at null level.
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

# wrong places for the null scan (lat, lon offsets in degrees from the true one): far away on every side
NULL_OFFSETS = ((-55.0, 30.0), (25.0, -110.0), (-25.0, 140.0), (0.0, 90.0), (0.0, -90.0), (-80.0, -60.0))
MATCH_DEG = 0.5


def heading_scan(rays, up, z, tree, step_deg: float = 0.2):
    """(best match count, its heading deg) of the rays at zenith z over all turns about it."""
    import numpy as np
    from cn_pkg.allsky import _align
    from cn_pkg.allsky_mount import rotvec
    R0 = _align(up, z)
    chord = 2 * math.sin(math.radians(MATCH_DEG) / 2)
    best = (0, 0.0)
    for psi in np.arange(0.0, 360.0, step_deg):
        R = rotvec(z * math.radians(psi)) @ R0
        n = int(np.isfinite(tree.query(rays @ R.T, distance_upper_bound=chord)[0]).sum())
        if n > best[0]:
            best = (n, float(psi))
    return best


def frame_rays(img, up, min_alt: float, k_sigma=None):
    """Refraction-corrected rays (IMU frame) of the spots above min_alt in both lenses."""
    import numpy as np
    from cn_pkg import allsky, sky360
    rays = []
    for L in sky360.default_lenses():
        sp = allsky.detect_spots(img, L, k_sigma=k_sigma, up_imu=up, min_alt=min_alt, max_spots=300)
        if sp:
            xy = np.array(sp)
            rays.append(allsky.unproject(L, xy[:, 0], xy[:, 1]))
    if not rays:
        return np.zeros((0, 3))
    rays = np.vstack(rays)
    alt = np.degrees(np.arcsin(np.clip(rays @ up, -1, 1)))
    drop = np.radians(allsky.refraction_deg(alt))
    tang = allsky._unit(up - (rays @ up)[:, None] * rays)
    return allsky._unit(rays * np.cos(drop)[:, None] - tang * np.sin(drop)[:, None])


def check(img, up, utc, lat, lon, tree, min_alt: float = 5.0, k_sigma=None) -> dict:
    import numpy as np
    from cn_pkg.allsky_mount import zenith_icrs
    up = np.asarray(up, float) / np.linalg.norm(up)
    rays = frame_rays(img, up, min_alt, k_sigma)
    if len(rays) == 0:
        return {"spots": 0, "truth": 0, "heading": None, "null_max": 0, "null_mean": 0.0, "excess": 0}
    n, psi = heading_scan(rays, up, zenith_icrs(lat, lon, utc), tree)
    nulls = []
    for a, b in NULL_OFFSETS:
        zn = zenith_icrs(max(-89.0, min(89.0, lat + a)), (lon + b + 540.0) % 360.0 - 180.0, utc)
        nulls.append(heading_scan(rays, up, zn, tree)[0])
    return {"spots": int(len(rays)), "truth": n, "heading": round(psi, 1), "null_max": int(max(nulls)),
            "null_mean": round(float(np.mean(nulls)), 1), "excess": int(n - max(nulls))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", help="a session (frames.jsonl) or a deepstack output (index.jsonl)")
    ap.add_argument("--at", required=True, help="LAT,LON of the camera")
    ap.add_argument("--last", type=int, default=0, help="only the last N frames")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--min-alt", type=float, default=5.0)
    a = ap.parse_args(argv)
    import cv2
    from scipy.spatial import cKDTree
    from cn_pkg import allsky
    lat, lon = (float(v) for v in a.at.split(","))
    cat = allsky.Catalogue(limit_mag=4.5, path=allsky.BUNDLED_CATALOGUE)
    tree = cKDTree(cat.vec)
    name = "frames.jsonl" if os.path.exists(os.path.join(a.folder, "frames.jsonl")) else "index.jsonl"
    with open(os.path.join(a.folder, name)) as fh:
        rows = [json.loads(line) for line in fh]
    rows = [r for r in rows if r.get("image") and r.get("up_imu")][::a.every]
    if a.last:
        rows = rows[-a.last:]
    excess = []
    for r in rows:
        img = cv2.imread(os.path.join(a.folder, r["image"]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        t = r.get("t_exp") or r["t"]
        utc = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        c = check(img, r["up_imu"], utc, lat, lon, tree, a.min_alt)
        excess.append(c["excess"])
        print(f"{r.get('idx', '?'):>5} {utc} spots {c['spots']:3d}  true place {c['truth']:3d} at {c['heading']} deg"
              f"  wrong places max {c['null_max']:3d} mean {c['null_mean']:5.1f}  excess {c['excess']:+d}", flush=True)
    if excess:
        stars = sum(e >= 5 for e in excess)
        print(f"{len(excess)} frames: {stars} with a clear star excess (>= 5 over the best wrong place)"
              + ("" if stars else " -> no real star pattern in these frames"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

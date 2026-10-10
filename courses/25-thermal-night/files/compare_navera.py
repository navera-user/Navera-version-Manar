"""Your query_coverage() against NAVERA's own normalize_query() (night_pkg).

Run:  python3 compare_navera.py
It builds a blank frame of each camera size, asks NAVERA's night localizer to scale it, turn
it north-up and crop it to STHN's 512 px square, and prints NAVERA's coverage next to yours.
(Importing night_localizer loads PyTorch: it takes ~10 s.)
"""
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
try:
    from night_pkg.nodes.night_localizer import MIN_QUERY_COVERAGE, normalize_query
except ImportError:
    sys.path.insert(0, os.path.expanduser("~/navera/night_pkg"))
    from night_pkg.nodes.night_localizer import MIN_QUERY_COVERAGE, normalize_query

from thermal import query_coverage

CASES = [  # width, height, hfov, heading, height above ground
    (640, 480, 84.0, 0.0, 300.0), (640, 480, 84.0, 45.0, 300.0), (640, 480, 84.0, 45.0, 350.0),
    (640, 480, 84.0, 30.0, 250.0), (640, 528, 56.7, 0.0, 400.0), (1536, 730, 84.0, 20.0, 400.0)]
print(f"NAVERA refuses a frame below {MIN_QUERY_COVERAGE:.0%} coverage.\n")
print("  camera        hfov  heading  height   NAVERA   yours    verdict")
worst = 0.0
for w, h, hfov, hdg, alt in CASES:
    _, info = normalize_query(np.full((h, w, 3), 128, np.uint8), 35.83, 17, alt, hfov, hdg)
    try:
        mine = query_coverage(w, h, alt, hfov, hdg, 35.83)
    except NotImplementedError as e:
        raise SystemExit(f"({e} is not done yet: finish TODO 10 and 11 in thermal.py first)")
    worst = max(worst, abs(mine - info["coverage"]))
    verdict = "refused: fly higher" if info["coverage"] < MIN_QUERY_COVERAGE else "accepted"
    print(f"  {w:4d} x {h:<4d}  {hfov:5.1f}  {hdg:6.0f}°  {alt:5.0f} m   {info['coverage']:.3f}   {mine:.3f}   {verdict}")
print(f"\nLargest difference: {worst:.4f}")

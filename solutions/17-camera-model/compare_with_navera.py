# Lesson 17 — compare YOUR formulas with the ones in YOUR copy of NAVERA (~/navera).
# Run:   python3 compare_with_navera.py
import math
import sys

import camera_math as mine

try:
    from navera_common.camera_model import CameraModel, altitude_from_scale, ground_m_per_px
    from day_pkg.local_matcher import LocalMatcher, map_m_per_px
except ImportError as e:
    sys.exit(f"cannot import NAVERA ({e}) — open a new terminal (it loads ~/navera) and try again")

bad = 0


def compare(label, yours, navera):
    global bad
    same = yours is not None and math.isclose(yours, navera, rel_tol=1e-6)
    bad += not same
    yv = "None" if yours is None else f"{yours:.4f}"
    print(f"{'✔' if same else '✘'} {label:<44} you {yv:>12}   NAVERA {navera:.4f}")


for h, fov, w in ((50, 111, 1920), (150, 111, 1920), (120, 90, 960), (400, 60, 1280)):
    compare(f"m/px  h={h} m fov={fov} w={w}", mine.meters_per_pixel(h, fov, w), ground_m_per_px(h, fov, w))
    compare(f"day_pkg frame_m_per_px, same", mine.meters_per_pixel(h, fov, w), LocalMatcher.frame_m_per_px(w, h, fov))
for lat, z in ((35.8, 17), (35.8, 19), (0.0, 13)):
    compare(f"map m/px lat={lat} z={z}", mine.map_meters_per_pixel(lat, z), map_m_per_px(lat, z))
cam = CameraModel.ideal(111.0, (1920, 540))
compare("focal length, ideal 111 deg lens, 1920 px", mine.focal_px(111, 1920), cam.K[0, 0])
# altitude_from_scale: a match found the ground 1.2x bigger than predicted at 150 m
yours = mine.height_from_object(12.0, 12.0 / (1.2 * mine.meters_per_pixel(150, 90, 960)), 90, 960) \
    if mine.meters_per_pixel(150, 90, 960) else None
compare("height from a 1.2 scale at 150 m", yours, altitude_from_scale(150.0, 1.2))
print("\nALL MATCH — your formulas are NAVERA's" if bad == 0 else f"\n{bad} difference(s): fix camera_math.py")
sys.exit(1 if bad else 0)

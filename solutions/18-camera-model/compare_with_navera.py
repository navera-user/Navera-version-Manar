# Lesson 18 — compare YOUR formulas with the code in YOUR copy of NAVERA (~/navera).
# Nothing to change here. Run:   python3 compare_with_navera.py
import math
import sys

import numpy as np
from scipy.spatial.transform import Rotation

import camera_math as mine

try:
    from navera_common.camera_model import (CameraModel, altitude_from_scale, camera_rotation, ground_m_per_px,
                                            nadir_homography, tilt_deg)
    from day_pkg.local_matcher import LocalMatcher, map_m_per_px
except ImportError as e:
    sys.exit(f"cannot import NAVERA ({e}) — open a new terminal (it loads ~/navera) and try again")

bad = 0


def compare(label, yours, navera, tol=1e-6):
    global bad
    try:
        same = yours is not None and math.isclose(float(yours), float(navera), rel_tol=tol, abs_tol=tol)
    except (TypeError, ValueError):
        same = False
    bad += not same
    yv = "None" if yours is None else (f"{float(yours):.4f}" if np.ndim(yours) == 0 else str(yours))
    print(f"{'✔' if same else '✘'} {label:<52} you {yv:>12}   NAVERA {float(navera):.4f}")


print("— resolution (navera_common/camera_model.py, day_pkg/local_matcher.py)")
for h, fov, w in ((50, 111, 1920), (150, 111, 1920), (120, 90, 960), (400, 60, 1280)):
    compare(f"GSD h={h} fov={fov} w={w}  vs ground_m_per_px", mine.meters_per_pixel(h, fov, w), ground_m_per_px(h, fov, w))
    compare("      same, vs LocalMatcher.frame_m_per_px", mine.meters_per_pixel(h, fov, w),
            LocalMatcher.frame_m_per_px(w, h, fov))
for lat, z in ((23.59, 17), (35.83, 17), (17.02, 19), (0.0, 13)):
    compare(f"map m/px lat={lat} z={z}", mine.map_m_per_px(lat, z), map_m_per_px(lat, z))

print("— intrinsics (CameraModel.ideal)")
for hfov, size in ((111.0, (1920, 540)), (90.0, (960, 540))):
    Kn = CameraModel.ideal(hfov, size).K
    Km = mine.intrinsic_matrix(hfov, *size)
    for (i, j), name in (((0, 0), "fx"), ((1, 1), "fy"), ((0, 2), "cx"), ((1, 2), "cy")):
        compare(f"K {name}, {hfov:.0f} deg on {size[0]}x{size[1]}", None if Km is None else np.asarray(Km)[i, j], Kn[i, j])

print("— projection vs NAVERA's straightening (nadir_homography)")
K = CameraModel.ideal(90.0, (960, 540)).K
h = 150.0
for heading, pitch, roll in ((0, -10, 0), (30, -12, 4), (250, 5, -15)):
    R_mine = mine.camera_rotation(heading, pitch, roll)
    R_wb = R_mine @ mine.R_BODY_NADIR_CAM.T
    q = Rotation.from_matrix(R_wb).as_quat()                    # (x, y, z, w), NAVERA's order
    R_nav = camera_rotation(q)
    t = tilt_deg(R_nav)
    # 1) the point under the drone, seen by the tilted camera, lands at the CENTRE of the
    #    straightened image (that is the purpose of nadir_homography)
    p = mine.project(K, R_nav, [0.0, 0.0, h], [0.0, 0.0, 0.0])
    if p is None:
        compare(f"nadir point -> straightened centre u ({heading},{pitch},{roll})", None, 480.0)
        continue
    Hm = nadir_homography(K, R_nav)
    q2 = Hm @ np.array([p[0], p[1], 1.0])
    compare(f"nadir point -> straightened centre u ({heading},{pitch},{roll})", q2[0] / q2[2], 480.0, tol=1e-3)
    compare(f"nadir point -> straightened centre v ({heading},{pitch},{roll})", q2[1] / q2[2], 270.0, tol=1e-3)
    # 2) the image centre hits the ground h*tan(tilt) away from the point under the drone
    g = mine.ground_point(K, R_nav, [0.0, 0.0, h], 480.0, 270.0)
    compare(f"centre ray distance = h tan(tilt), tilt {t:.1f} deg", None if g is None else float(np.hypot(*g)),
            h * math.tan(math.radians(t)), tol=1e-4)

print("— height from the scale of a match (altitude_from_scale)")
for hp, s in ((150.0, 1.2), (1800.0, 0.1667)):
    compare(f"believed {hp:.0f} m, fitted scale {s}", None if mine.fitted_scale(hp, hp * s) is None
            else hp * mine.fitted_scale(hp, hp * s), altitude_from_scale(hp, s))

print("\nALL MATCH — your formulas are NAVERA's" if bad == 0 else f"\n{bad} difference(s): fix camera_math.py")
sys.exit(1 if bad else 0)

# Optional — run NAVERA's OWN day-vision matcher on the same photos and compare with yours.
# Run:  python3 compare_navera.py
# It imports LocalMatcher from your NAVERA copy: ~/navera/day_pkg/day_pkg/local_matcher.py
# and reads the map tiles of the dataset (images/tile_17_x_y.jpg, the layout NAVERA uses).
import os
import sys
import time

import cv2

import navmap

DATA = "/data/academy/22-locate-on-map"
sys.path.insert(0, os.path.expanduser("~/navera/day_pkg"))      # works even without ROS sourced
from day_pkg.local_matcher import LocalMatcher  # noqa: E402

from locate import read_truth  # noqa: E402

# device="cpu": no GPU needed (NAVERA uses the GPU for the matching step when it has one)
matcher = LocalMatcher(f"{DATA}/images", zoom=17, device="cpu")

print(f"{'photo':13s} {'NAVERA':>9s} {'inliers':>8s} {'error':>8s} {'time':>7s}   reason")
errors = []
for row in read_truth():
    photo = cv2.imread(f"{DATA}/{row['file']}")
    mpp = LocalMatcher.frame_m_per_px(photo.shape[1], float(row["altitude_m"]), float(row["hfov_deg"]))
    t0 = time.time()
    res = matcher.locate(photo, (float(row["prior_lat"]), float(row["prior_lon"])), float(row["search_m"]), mpp)
    ms = (time.time() - t0) * 1000
    name = row["file"].split("/")[-1][:-4]
    if res["accepted"]:
        err = navmap.haversine_m(res["predicted_lat"], res["predicted_lon"],
                                 float(row["true_lat"]), float(row["true_lon"]))
        errors.append(err)
        print(f"{name:13s} {'ACCEPTED':>9s} {res['inliers']:8d} {err:6.1f} m {ms:5.0f} ms   "
              f"scale {res['scale_residual']}, rotation {res['rotation_deg']} deg, sigma {res['sigma_m']:.0f} m")
    else:
        print(f"{name:13s} {'no fix':>9s} {res.get('inliers', 0):8d} {'-':>8s} {ms:5.0f} ms   "
              f"{res.get('reason') or res.get('error')}")
errors.sort()
if errors:
    n = len(errors)
    med = errors[n // 2] if n % 2 else 0.5 * (errors[n // 2 - 1] + errors[n // 2])
    print(f"\nNAVERA's LocalMatcher: accepted {n} photos, median error {med:.1f} m, worst {errors[-1]:.1f} m")
print("(the first photos are slower: NAVERA computes each map tile's features once, then keeps them)")

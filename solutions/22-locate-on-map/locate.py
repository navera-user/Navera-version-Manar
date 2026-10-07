# Lesson 22 — find a drone photo on the satellite map (NAVERA's test map covers Sousse, Tunisia).
# Run the demo:  python3 locate.py            (locates photo p01 and draws locate_demo.png)
#                python3 locate.py p05_farms  (another photo of the dataset)
import math
import sys

import cv2
import numpy as np

import navmap

Z = 17                 # the zoom NAVERA's day vision matches against (about 0.97 m per pixel here)
RATIO = 0.8            # ratio test (lesson 21), NAVERA's value
MIN_INLIERS = 8        # gate 1, like NAVERA's local_min_inliers
SCALE_TOL = 0.15       # gate 2: the fitted scale must be 1 ± 15 % (NAVERA's local_scale_tol)
RANSAC_PX = 6.0        # RANSAC inlier threshold in map pixels (NAVERA's ransac_px)


def photo_m_per_px(width_px, altitude_m, hfov_deg):
    """Ground size of one photo pixel, in metres (lesson 17): footprint width / pixel width."""
    # TODO 1: footprint width W = 2 * altitude * tan(hfov / 2)   (hfov in DEGREES: convert!)
    footprint = 2.0 * altitude_m * math.tan(math.radians(hfov_deg) / 2.0)
    return footprint / width_px


def build_search_patch(prior_lat, prior_lon, search_m, margin_m, z=Z):
    """The piece of map where the photo can be: a square centred on the prior, of half-width
    search_m + margin_m (in metres). Returns (patch BGR image, (x0, y0) its top-left global
    pixel, metres per map pixel)."""
    # TODO 2: metres per map pixel at the prior, half-width in pixels (rounded UP), navmap.map_patch
    mpp = navmap.m_per_px(prior_lat, z)
    half = int(math.ceil((search_m + margin_m) / mpp))
    patch, origin = navmap.map_patch(prior_lat, prior_lon, z, 2 * half, 2 * half)
    return patch, origin, mpp


def match_features(photo_grey, patch_grey):
    """SIFT keypoints of both pictures, matched with the ratio test.
    Returns two float32 arrays of shape (N, 2): points in the photo, the same points in the patch."""
    kp1, d1 = cv2.SIFT_create(nfeatures=1500, contrastThreshold=0.02).detectAndCompute(photo_grey, None)
    # the patch is much bigger than the photo: no limit on its number of keypoints
    kp2, d2 = cv2.SIFT_create(nfeatures=0, contrastThreshold=0.02).detectAndCompute(patch_grey, None)
    if d1 is None or d2 is None or len(kp1) < 2 or len(kp2) < 2:
        return np.zeros((0, 2), np.float32), np.zeros((0, 2), np.float32)
    # TODO 3: the ratio test (lesson 21)
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < RATIO * p[1].distance]
    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 2)
    return src, dst


def locate(photo, prior_lat, prior_lon, alt_m, hfov_deg, search_m=300.0):
    """Where was this photo taken? Returns a dict:
       accepted (True/False), lat, lon (None when not accepted), inliers, scale, rotation_deg, reason."""
    res = dict(accepted=False, lat=None, lon=None, inliers=0, scale=None, rotation_deg=None, reason="")
    grey = photo if photo.ndim == 2 else cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)
    # 1. the photo at the map's resolution: one photo pixel becomes one map pixel
    mpp_photo = photo_m_per_px(grey.shape[1], alt_m, hfov_deg)
    mpp_map = navmap.m_per_px(prior_lat, Z)
    s = mpp_photo / mpp_map
    small = cv2.resize(grey, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    # 2. the map around the prior: the search circle + half the photo's diagonal on the ground
    margin = 0.5 * math.hypot(*grey.shape[:2]) * mpp_photo
    patch, (x0, y0), _ = build_search_patch(prior_lat, prior_lon, search_m, margin)
    patch_grey = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    # 3. features and matches
    src, dst = match_features(small, patch_grey)
    if len(src) < MIN_INLIERS:
        res["reason"] = f"only {len(src)} feature matches (min {MIN_INLIERS})"
        return res
    # TODO 4: similarity with RANSAC, scale and rotation, the two gates, centre -> lat/lon
    A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PX,
                                         maxIters=5000, confidence=0.999)
    if A is None:
        res["reason"] = "no consistent geometry"
        return res
    n_in = int(inl.sum())
    scale = math.hypot(A[0, 0], A[1, 0])
    rot = math.degrees(math.atan2(A[1, 0], A[0, 0]))
    res.update(inliers=n_in, scale=round(scale, 3), rotation_deg=round(rot, 1))
    if n_in < MIN_INLIERS:
        res["reason"] = f"{n_in} inliers (min {MIN_INLIERS})"
        return res
    if abs(scale - 1.0) > SCALE_TOL:
        res["reason"] = f"fitted scale {scale:.2f}, expected 1 ± {SCALE_TOL}: wrong place or wrong height"
        return res
    u, v = A @ np.array([small.shape[1] / 2.0, small.shape[0] / 2.0, 1.0])
    lat, lon = navmap.pixel_to_latlon(x0 + u, y0 + v, Z)
    res.update(accepted=True, lat=lat, lon=lon, reason="ok", _A=A, _small=small)
    return res


# ---- you don't need to change anything below this line ----
DATA = "/data/academy/22-locate-on-map"


def read_truth():
    import csv
    with open(f"{DATA}/truth.csv") as f:
        return list(csv.DictReader(f))


def draw_result(res, row, path):
    """The search patch with the prior (blue), the truth (green) and the answer (red)."""
    patch, (x0, y0), _ = build_search_patch(float(row["prior_lat"]), float(row["prior_lon"]),
                                            float(row["search_m"]), 250.0)
    img = patch.copy()

    def to_px(lat, lon):
        gx, gy = navmap.latlon_to_pixel(lat, lon, Z)
        return int(round(gx - x0)), int(round(gy - y0))
    mpp = navmap.m_per_px(float(row["prior_lat"]), Z)
    pc = to_px(float(row["prior_lat"]), float(row["prior_lon"]))
    cv2.circle(img, pc, int(float(row["search_m"]) / mpp), (255, 160, 0), 2)
    cv2.drawMarker(img, pc, (255, 160, 0), cv2.MARKER_CROSS, 30, 3)
    cv2.circle(img, to_px(float(row["true_lat"]), float(row["true_lon"])), 12, (0, 200, 0), 3)
    if res.get("accepted") and res.get("_A") is not None:
        A = res["_A"]
        h, w = res["_small"].shape[:2]
        corners = np.float32([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]]) @ A.T
        # the photo's outline, shifted from the search patch it was matched in to this one
        gx, gy = navmap.latlon_to_pixel(res["lat"], res["lon"], Z)
        cu, cv_ = A @ np.array([w / 2.0, h / 2.0, 1.0])
        corners += np.float32([gx - x0 - cu, gy - y0 - cv_])
        cv2.polylines(img, [corners.astype(np.int32)], True, (0, 0, 255), 2)
        cv2.drawMarker(img, to_px(res["lat"], res["lon"]), (0, 0, 255), cv2.MARKER_TILTED_CROSS, 24, 3)
    cv2.imwrite(path, img)


def demo(name):
    rows = [r for r in read_truth() if name in r["file"]]
    if not rows:
        sys.exit(f"no photo called {name} in {DATA}/truth.csv")
    row = rows[0]
    photo = cv2.imread(f"{DATA}/{row['file']}")
    print(f"photo {row['file']}: {photo.shape[1]}x{photo.shape[0]} px, altitude {row['altitude_m']} m, "
          f"camera {row['hfov_deg']} deg, heading {row['heading_deg']} deg")
    print("photo_m_per_px:", photo_m_per_px(photo.shape[1], float(row["altitude_m"]), float(row["hfov_deg"])))
    res = locate(photo, float(row["prior_lat"]), float(row["prior_lon"]), float(row["altitude_m"]),
                 float(row["hfov_deg"]), float(row["search_m"]))
    print("result:", {k: v for k, v in res.items() if not k.startswith("_")})
    if res.get("accepted"):
        err = navmap.haversine_m(res["lat"], res["lon"], float(row["true_lat"]), float(row["true_lon"]))
        print(f"error: {err:.1f} m from the truth")
    draw_result(res, row, "locate_demo.png")
    print("drawn: locate_demo.png (blue = prior and search circle, green = truth, red = your answer)")


if __name__ == "__main__":
    try:
        demo(sys.argv[1] if len(sys.argv) > 1 else "p01_medina")
    except NotImplementedError as e:
        print(f"Not written yet: {e} — open locate.py, fill in that TODO, save and run again.")

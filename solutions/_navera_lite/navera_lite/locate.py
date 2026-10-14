"""navera_lite/locate.py — from one downward photo to latitude and longitude: the search circle from the prior, the
coarse step (retrieval, retrieval.py) when the circle is large, the fine step (local feature matching with OpenCV),
the gates, the error budget, and an honest evaluation.
Part of NAVERA Lite, the course's teaching stack (mission 23). Written for the course; it is not NAVERA code.

Conventions: degrees at the interfaces, metres for distances; pictures are numpy uint8 (OpenCV: BGR colour, or
grey). OpenCV puts the CENTRE of pixel (i, j) at the coordinates (i, j); the map's continuous pixel coordinates
(tiles.pixel_to_latlon) put pixel i between i and i + 1, so its centre at i + 0.5. Percentiles are linear
(numpy's default, CONVENTIONS.md §6). Map data © OpenStreetMap contributors.
"""
import math

import cv2
import numpy as np

from navera_lite.camera import gsd
from navera_lite.estimate import COV_APPROXIMATED, Estimate
from navera_lite.geo import haversine_m
from navera_lite.image import like_map, to_gray
from navera_lite.retrieval import ZOOM, north_up
from navera_lite.tiles import m_per_px, map_patch, patch_origin, pixel_to_latlon

# @part 23
DEFAULTS = {
    "z": ZOOM,                 # map zoom (≈ 0.97 m per map pixel at Sousse)
    "k_sigma": 3.0,            # search radius = k_sigma × σ of the prior …
    "r_min_m": 80.0,           # … but at least r_min_m …
    "r_max_m": 1500.0,         # … and at most r_max_m (NAVERA uses 3, 80 m and 1 500 m)
    "direct_max_r_m": 300.0,   # YOUR decision (lab Step 12): above this radius, retrieval chooses where to look
    "top_k": 3,                # how many retrieved tiles the fine step tries, best first
    "tile_r_m": 180.0,         # the fine step's radius around a retrieved tile's centre (a tile's half-diagonal ≈ 175 m)
    "ratio": 0.9,              # ratio test (mission 22)
    "min_inliers": 6,          # gate 1: at least this many RANSAC inliers
    "scale_tol": 0.15,         # gate 2: the fitted scale within 1 ± scale_tol
    "max_patch_px": 2000,      # the largest map patch the fine step may cut (memory: SIFT works on a 2× enlarged copy)
}
# @part 23
SIGMA_DAY_M = 30.0             # the σ a day-vision fix states (NAVERA's conservative value until measured in flight)


# ====================================================================== measuring (session 1)

# @part 23 todo 3
def evaluate(errors_m, wrong_m=50.0):
    """The four numbers of an honest evaluation (lesson §4), plus one more for retrieval. errors_m: one entry per
    test photo, the error in metres of the position given for it, or None when the method refused to give one.

    Returns a dict: "n" (photos), "accepted" (positions given), "availability" (accepted / n), "median_m" and
    "p90_m" (linear percentiles of the accepted errors; None if nothing was accepted), "within_300" (share of the
    ACCEPTED errors ≤ 300 m; None if nothing was accepted) and "wrong" (accepted errors > wrong_m). n = 0 → ValueError.
    Example: evaluate([4.0, None, 12.0, 80.0, 2.0]) → {"n": 5, "accepted": 4, "availability": 0.8, "median_m": 8.0,
             "p90_m": 59.6, "within_300": 1.0, "wrong": 1}
    """
    if len(errors_m) == 0:
        raise ValueError("errors_m must hold at least one photo, got an empty list")
    acc = np.array([float(e) for e in errors_m if e is not None])
    n = len(errors_m)
    out = {"n": n, "accepted": int(len(acc)), "availability": len(acc) / n, "median_m": None, "p90_m": None,
           "within_300": None, "wrong": int((acc > wrong_m).sum())}
    if len(acc):
        out.update(median_m=float(np.percentile(acc, 50)), p90_m=float(np.percentile(acc, 90)),
                   within_300=float((acc <= 300.0).mean()))
    return out


# ====================================================================== the search circle (session 2)

# @part 23 todo 6
def search_radius(sigma_m, k=3.0, r_min_m=80.0, r_max_m=1500.0):
    """The radius of the search circle around the prior (lesson §5): k times the prior's σ, but never below r_min_m
    (the prior's own error is never quite zero) nor above r_max_m (a larger circle costs too much and finds too many
    look-alikes). sigma_m < 0, or not a finite number → ValueError.

    Example: search_radius(120.0) → 360.0; search_radius(10.0) → 80.0; search_radius(900.0) → 1500.0
    """
    if not math.isfinite(sigma_m) or sigma_m < 0:
        raise ValueError(f"sigma_m must be a finite number ≥ 0, got {sigma_m}")
    return float(min(max(k * sigma_m, r_min_m), r_max_m))


# ====================================================================== the fine step (session 2)

# @part 23
def match_similarity(view, patch, ratio=0.9, thr_px=3.0, n_features=4000):
    """Mission 22's chain with OpenCV: CLAHE (clip 2.0, 8 × 8 tiles) on both pictures, then SIFT keypoints (contrast
    threshold 0.02 for pale map pictures, mission 21) of the view (not on its black border) and of the map patch,
    the two nearest map descriptors of each view descriptor, the ratio test, one match per map keypoint (the
    closest), then a similarity (turn + uniform scale + shift) fitted by RANSAC (cv2.estimateAffinePartial2D).

    view, patch: grey uint8. Returns (A, n_inliers): A = float (2, 3) carrying view pixels to patch pixels
    (OpenCV pixel centres), or None when fewer than 3 matches survive; n_inliers = the RANSAC inliers (or the
    surviving matches when A is None).
    Example: match_similarity(view, patch) → (array([[0.99, -0.02, 312.4], [0.02, 0.99, 280.9]]), 57)
    """
    # given — read it and use it, no need to change it
    sift = cv2.SIFT_create(nfeatures=n_features, contrastThreshold=0.02)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    border = cv2.erode((view > 0).astype(np.uint8) * 255, np.ones((15, 15), np.uint8))
    k1, d1 = sift.detectAndCompute(clahe.apply(view), border)
    k2, d2 = sift.detectAndCompute(clahe.apply(patch), None)
    if d1 is None or d2 is None or len(k1) < 2 or len(k2) < 2:
        return None, 0
    best = {}
    for pair in cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2):
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance:
            m = pair[0]
            if m.trainIdx not in best or m.distance < best[m.trainIdx].distance:
                best[m.trainIdx] = m
    good = list(best.values())
    if len(good) < 3:
        return None, len(good)
    src = np.float32([k1[m.queryIdx].pt for m in good])
    dst = np.float32([k2[m.trainIdx].pt for m in good])
    cv2.setRNGSeed(0)
    A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=thr_px, maxIters=2000,
                                         confidence=0.99)
    if A is None:
        return None, len(good)
    return A, int(inl.sum())


# @part 23 todo 7
def place(A, n_inliers, view_shape, x0, y0, z=ZOOM, min_inliers=6, scale_tol=0.15):
    """Apply the gates to a fitted similarity, then carry the view's centre to latitude and longitude (lesson §7).
    A: (2, 3) view pixels → patch pixels (OpenCV pixel centres), or None; view_shape: the view's (h, w) (or (h, w,
    3)); (x0, y0): the patch's top-left corner in tile coordinates (tiles.patch_origin), zoom z.

    Gate 1: A is None or n_inliers < min_inliers → (None, None, "<n> inliers (min <min_inliers>)").
    Gate 2: the fitted scale (the length of A's first column) outside 1 ± scale_tol → (None, None,
            "scale <s, 2 decimals> (expected 1 ± <scale_tol>)").
    Otherwise the centre of the view ((w − 1)/2, (h − 1)/2) goes through A into the patch, then to (lat, lon) with
    tiles.pixel_to_latlon — mind the half pixel between OpenCV's pixel centres and the map's coordinates (module
    docstring) — and the result is (lat, lon, "ok: <n> inliers, scale <s, 2 decimals>").
    Example: place(np.array([[1.0, 0.0, 100.0], [0.0, 1.0, 50.0]]), 20, (101, 101), 69408.0, 51546.0)
             → (35.83030…, 10.63638…, "ok: 20 inliers, scale 1.00")
    """
    if A is None or n_inliers < min_inliers:
        return None, None, f"{n_inliers} inliers (min {min_inliers})"
    A = np.asarray(A, dtype=float)
    s = math.hypot(A[0, 0], A[1, 0])
    if abs(s - 1.0) > scale_tol:
        return None, None, f"scale {s:.2f} (expected 1 ± {scale_tol})"
    h, w = view_shape[:2]
    u, v = A @ np.array([(w - 1) / 2.0, (h - 1) / 2.0, 1.0])
    lat, lon = pixel_to_latlon(u + 0.5, v + 0.5, z, x0, y0)
    return lat, lon, f"ok: {n_inliers} inliers, scale {s:.2f}"


# @part 23
def local_match(photo, meta, lat, lon, r_m, cfg=DEFAULTS, path=None):
    """The fine step around one point: the photo made like the map (mission 08's like_map, with the photo's height
    and heading), a map patch that holds a circle of r_m metres around (lat, lon) plus the view's half side, the
    match, then YOUR place(). meta: {"alt_m", "heading_deg", "hfov_deg"}. Returns (lat, lon, reason) like place().

    Example: local_match(photo, {"alt_m": 350.0, "heading_deg": 40.0, "hfov_deg": 60.0}, 35.82, 10.62, 150.0)
             → (35.8191…, 10.6213…, "ok: 41 inliers, scale 1.01")
    """
    # given — read it and use it, no need to change it
    z = int(cfg["z"])
    gm = m_per_px(lat, z)
    view = like_map(photo, float(meta["heading_deg"]), gsd(float(meta["alt_m"]), float(meta["hfov_deg"]),
                                                           photo.shape[1]), gm)
    side = 2 * int(math.ceil(r_m / gm + view.shape[0] / 2.0))
    if side > int(cfg.get("max_patch_px", 2000)):
        return None, None, f"circle too large for one patch ({side} px > {int(cfg.get('max_patch_px', 2000))} px)"
    patch = to_gray(map_patch(lat, lon, z, side, side, path=path))
    x0, y0 = patch_origin(lat, lon, z, side, side)
    A, n = match_similarity(view, patch, ratio=float(cfg["ratio"]))
    return place(A, n, view.shape, x0, y0, z, int(cfg["min_inliers"]), float(cfg["scale_tol"]))


# ====================================================================== the whole chain (session 2)

# @part 23 todo 8
def locate(photo, meta, prior, finder, cfg=DEFAULTS):
    """Where was this photo taken? (lesson §8). photo: BGR uint8; meta: {"alt_m", "heading_deg", "hfov_deg"};
    prior: (lat, lon, sigma_m), where the drone believes it is and the σ of that belief; finder: the coarse step,
    called as finder(view, lat, lon, r_m, k) with a north-up colour view (retrieval.north_up, map scale at the
    prior's latitude) → a list of up to k candidates (x, y, lat, lon, similarity), best first (a TileIndex's search,
    or the check's own); cfg: the settings of DEFAULTS.

    The search radius comes from the prior (search_radius with cfg's k_sigma, r_min_m, r_max_m). Up to
    cfg["direct_max_r_m"], the fine step searches the whole circle at once (local_match around the prior) and the
    finder is NOT called. Above it, the finder is called once, then the fine step tries the candidates in order,
    each within cfg["tile_r_m"], and keeps the first position the gates accept. A position farther from the prior
    than the search radius is refused too: the drone cannot be there if the prior's σ is honest.
    Returns (lat, lon, reason): (lat, lon, "ok: …") or (None, None, reason) — the reason says why: the last gate's
    reason, "no candidate in the circle", or "outside the search circle (<d> m > <r> m)".
    Example: locate(photo, meta, (35.8201, 10.6197, 40.0), finder) → (35.8192…, 10.6213…, "ok: 37 inliers, scale 0.99")
             (r = 120 m: no retrieval); with a σ of 400 m (r = 1 200 m) the finder chooses where to look
    """
    plat, plon, sigma = float(prior[0]), float(prior[1]), float(prior[2])
    r = search_radius(sigma, cfg["k_sigma"], cfg["r_min_m"], cfg["r_max_m"])
    if r <= cfg["direct_max_r_m"]:
        lat, lon, reason = local_match(photo, meta, plat, plon, r, cfg)
    else:
        gm = m_per_px(plat, int(cfg["z"]))
        view = north_up(photo, float(meta["heading_deg"]),
                        gsd(float(meta["alt_m"]), float(meta["hfov_deg"]), photo.shape[1]), gm)
        lat, lon, reason = None, None, "no candidate in the circle"
        for cand in finder(view, plat, plon, r, int(cfg["top_k"])):
            lat, lon, reason = local_match(photo, meta, float(cand[2]), float(cand[3]), cfg["tile_r_m"], cfg)
            if lat is not None:
                break
    if lat is None:
        return None, None, reason
    d = haversine_m(plat, plon, lat, lon)
    if d > r:
        return None, None, f"outside the search circle ({d:.0f} m > {r:.0f} m)"
    return lat, lon, reason


# ====================================================================== the error budget (session 2)

# @part 23 todo 9
def budget(terms):
    """The total 1-σ error of independent error sources (lesson §9): the root of the sum of their squares.
    terms: a dict {name: σ in metres} (or any iterable of σ). Empty → 0.0; a negative or non-finite σ → ValueError.

    Example: budget({"tilt": 3.0, "matcher": 4.0}) → 5.0
    """
    values = list(terms.values()) if isinstance(terms, dict) else list(terms)
    total = 0.0
    for v in values:
        v = float(v)
        if not math.isfinite(v) or v < 0:
            raise ValueError(f"every σ must be a finite number ≥ 0, got {v}")
        total += v * v
    return math.sqrt(total)


# @part 23
def to_estimate(lat, lon, t_s, sigma_m=SIGMA_DAY_M):
    """A day-vision position as the judge receives it (mission 12's Estimate): source "day", the σ stated on both
    axes (covariance type "approximated"), or an invalid Estimate when lat is None.

    Example: to_estimate(35.8192, 10.6213, 12.5).cov[0] → 900.0
    """
    # given — read it and use it, no need to change it
    if lat is None:
        return Estimate("day", math.nan, math.nan, float(t_s), valid=False, reason="no fix")
    v = float(sigma_m) ** 2
    return Estimate("day", float(lat), float(lon), float(t_s), cov=(v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, v),
                    cov_type=COV_APPROXIMATED)

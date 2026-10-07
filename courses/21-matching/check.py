import json
import os

import cv2
import numpy as np

from academy_check import Checker, load_student, need

c = Checker()
DATA = "/data/academy/21-matching"
TRUTH = json.load(open(os.path.join(DATA, "truth.json")))
_cache = {}


def pair(name):
    return (cv2.imread(os.path.join(DATA, f"view_{name}.jpg")), cv2.imread(os.path.join(DATA, f"patch_{name}.jpg")))


def matched(name):
    """match_views() of the student on one pair (computed once)."""
    if name not in _cache:
        (match_views,) = need(load_student("matching.py"), "match_views")
        r = match_views(*pair(name))
        c.ok(isinstance(r, tuple) and len(r) == 3, f"match_views() should return (H, inliers, details), got {r!r}")
        _cache[name] = r
    return _cache[name]


def angle_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def check_pair(name, rot_tol, scale_tol, min_inl, centre_tol):
    H, inl, _ = matched(name)
    c.ok(H is not None, f"no homography found for the '{name}' pair — is TODO 3 complete?")
    c.ok(int(inl) >= min_inl, f"only {inl} inliers on the '{name}' pair (expected at least {min_inl})")
    m = load_student("matching.py")
    rotation_and_scale, where_is_centre = need(m, "rotation_and_scale", "where_is_centre")
    rs = rotation_and_scale(H)
    c.ok(rs is not None and len(rs) == 2, "rotation_and_scale() should return (rotation, scale)")
    t = TRUTH[name]
    c.ok(angle_diff(float(rs[0]), t["rotation_deg"]) <= rot_tol,
         f"rotation {float(rs[0]):.1f}° but the view was turned by {t['rotation_deg']:.0f}° (± {rot_tol}°)")
    c.near(rs[1], t["scale"], tol=scale_tol * t["scale"], what=f"the scale of '{name}'")
    p = where_is_centre(H, pair(name)[0])
    c.ok(p is not None and len(p) == 2, "where_is_centre() should return (x, y)")
    d = float(np.hypot(p[0] - t["centre"][0], p[1] - t["centre"][1]))
    c.ok(d <= centre_tol, f"the centre lands {d:.1f} px from the truth (max {centre_tol} px)")


@c.test("ransac_line.py: fit_line_ransac() finds the true line (slope 0.6, intercept 12) despite the outliers",
        hint="Each try: the line through 2 random points, count the points closer than `threshold`, keep the "
             "best try, then refit on its inliers with least_squares_line(). Run `python3 ransac_line.py`.")
def _():
    (fit,) = need(load_student("ransac_line.py"), "fit_line_ransac")
    pts = np.loadtxt(os.path.join(DATA, "points.csv"), delimiter=",", skiprows=1)
    r = fit(pts)
    c.ok(r is not None and len(r) == 3, f"fit_line_ransac() should return (slope, intercept, inlier_mask), got {r!r}")
    c.near(r[0], 0.6, tol=0.05, what="the slope")
    c.near(r[1], 12.0, tol=2.0, what="the intercept")


@c.test("fit_line_ransac(): the inlier mask marks the ~70 good points and leaves the outliers out",
        hint="The mask is a numpy array of True/False, one per point: True when the point is close to the line.")
def _():
    (fit,) = need(load_student("ransac_line.py"), "fit_line_ransac")
    pts = np.loadtxt(os.path.join(DATA, "points.csv"), delimiter=",", skiprows=1)
    r = fit(pts)
    c.ok(r is not None and len(r) == 3, "fit_line_ransac() returns nothing yet")
    mask = np.asarray(r[2]).astype(bool)
    c.ok(mask.shape == (len(pts),), f"the mask should have one value per point ({len(pts)}), it has shape {mask.shape}")
    c.ok(65 <= mask.sum() <= 76, f"{mask.sum()} inliers — the data has 70 points on the line (+ a few outliers "
                                 "that happen to fall close to it)")


@c.test("ratio_test() keeps a clear match and drops an ambiguous one",
        hint="Keep `best` only when best.distance < ratio * second.distance.")
def _():
    (ratio_test,) = need(load_student("matching.py"), "ratio_test")
    clear = [cv2.DMatch(0, 5, 100.0), cv2.DMatch(0, 9, 300.0)]      # 100 < 0.8 x 300 → keep
    ambiguous = [cv2.DMatch(1, 2, 200.0), cv2.DMatch(1, 3, 210.0)]  # 200 > 0.8 x 210 → drop
    alone = [cv2.DMatch(2, 4, 50.0)]                                # no second candidate → drop
    out = ratio_test([clear, ambiguous, alone], 0.8)
    c.ok(isinstance(out, list), f"ratio_test() should return a list, got {out!r}")
    c.eq(len(out), 1, "the number of matches kept")
    c.eq((out[0].queryIdx, out[0].trainIdx), (0, 5), "the match kept (queryIdx, trainIdx)")


@c.test("ratio_test() on the real 'city' pair keeps a few hundred matches",
        hint="Use the `ratio` argument, not a fixed number; a match passes when it is clearly better than the second.")
def _():
    m = load_student("matching.py")
    ratio_test, features = need(m, "ratio_test", "features")
    v, p = pair("city")
    _, dv = features(v)
    _, dp = features(p)
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(dv, dp, k=2)
    n8, n6 = len(ratio_test(pairs, 0.8)), len(ratio_test(pairs, 0.6))
    c.ok(150 <= n8 <= 400, f"{n8} matches kept with ratio 0.8 (expected about 250)")
    c.ok(n6 < n8, f"a stricter ratio (0.6) should keep fewer matches: {n6} vs {n8}")


@c.test("rotation_and_scale() and where_is_centre() on a known matrix",
        hint="rotation = atan2(H[1,0], H[0,0]) in degrees, scale = the length of (H[0,0], H[1,0]); "
             "the centre: cv2.perspectiveTransform on an array of shape (1, 1, 2).")
def _():
    m = load_student("matching.py")
    rotation_and_scale, where_is_centre = need(m, "rotation_and_scale", "where_is_centre")
    a = np.radians(40.0)
    H = np.array([[2 * np.cos(a), -2 * np.sin(a), 100.0], [2 * np.sin(a), 2 * np.cos(a), 50.0], [0, 0, 1.0]])
    rs = rotation_and_scale(H)
    c.ok(rs is not None and len(rs) == 2, f"rotation_and_scale() should return (rotation, scale), got {rs!r}")
    c.near(rs[0], 40.0, tol=0.01, what="the rotation (degrees)")
    c.near(rs[1], 2.0, tol=0.001, what="the scale")
    p = where_is_centre(H, np.zeros((100, 200, 3), np.uint8))    # centre (100, 50)
    want = H[:2, :2] @ np.array([100.0, 50.0]) + H[:2, 2]
    c.ok(p is not None and len(p) == 2, f"where_is_centre() should return (x, y), got {p!r}")
    c.near(p[0], want[0], tol=0.01, what="x of the centre")
    c.near(p[1], want[1], tol=0.01, what="y of the centre")


@c.test("match_views() on the 'city' pair: rotation 30° (±1°), scale 0.80 (±2 %), centre within 3 px",
        hint="TODO 3: ratio_test → the (x, y) of each good match in both pictures → cv2.findHomography with "
             "cv2.RANSAC and 5.0 → count the 1s in the mask.")
def _():
    check_pair("city", 1.0, 0.02, 100, 3.0)


@c.test("match_views() on the 'olives' pair: rotation −60° (±1°), scale 1.20 (±2 %), centre within 3 px",
        hint="Same function as for the city: if the city works, look at how you count the inliers.")
def _():
    check_pair("olives", 1.0, 0.02, 100, 3.0)


@c.test("match_views() on the 'otherdate' pair (2022 photo vs today's map): rotation 120° (±4°), scale 1.5 (±6 %)",
        hint="Keep the ratio 0.8 and the RANSAC threshold 5.0: a different date leaves far fewer good matches.")
def _():
    check_pair("otherdate", 4.0, 0.06, 10, 8.0)


@c.test("match_views() on the 'sea' pair finds nothing — and does not crash",
        hint="Open water has no keypoints: match_views() must return (None, 0, details) instead of failing.")
def _():
    H, inl, _ = matched("sea")
    c.ok(H is None or int(inl) < 8, f"a match on open water with {inl} inliers? It cannot be right")


@c.test("trust(): believes the city match, refuses the sea and a wrong scale",
        hint="False when H is None, when inliers < min_inliers, or when |scale / expected_scale − 1| > scale_tol.")
def _():
    (trust,) = need(load_student("matching.py"), "trust")
    H, inl, _ = matched("city")
    c.ok(H is not None, "match_views() finds no homography on the city pair yet")
    c.ok(trust(H, inl, 0.8) is True, "trust() should say True for the city match (expected scale 0.8)")
    c.ok(trust(H, inl, 1.2) is False, "trust() should say False when the scale is 0.8 but 1.2 was expected")
    c.ok(trust(H, 5, 0.8) is False, "trust() should say False with only 5 inliers")
    c.ok(trust(None, 0, 1.0) is False, "trust() should say False when there is no homography")


@c.test("draw_inlier_matches() saves a picture with the inlier matches only",
        hint="Keep the matches whose mask value is True, cv2.drawMatches(...), cv2.imwrite(path, img), return path.")
def _():
    (draw,) = need(load_student("matching.py"), "draw_inlier_matches")
    H, inl, details = matched("city")
    c.ok(H is not None, "match_views() finds no homography on the city pair yet")
    path = "_check_matches.png"
    if os.path.exists(path):
        os.remove(path)
    draw(*pair("city"), details, path)
    c.file_exists(path)
    img = cv2.imread(path)
    os.remove(path)
    c.ok(img is not None and img.shape[1] == 480 + 800, "the picture should hold the view and the patch side by side")


c.run()

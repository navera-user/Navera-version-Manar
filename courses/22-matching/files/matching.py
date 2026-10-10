"""Lesson 22 — matching a drone view to a piece of the satellite map, and deciding whether to trust it.

Run the demo:   python3 matching.py              (all four pairs, OpenCV's RANSAC and yours)
                python3 matching.py olives       (one pair)
"""
import json
import math
import os
import sys
import time

import cv2
import numpy as np

import geometry

DATA = "/data/academy/22-matching"           # the lesson's pictures (read only)


# ---------------------------------------------------------------- TODO 7
def ratio_test(knn_pairs, ratio=0.8):
    """Lowe's ratio test.  knn_pairs: what BFMatcher.knnMatch(..., k=2) returns — a list of
    [best, second] cv2.DMatch pairs.  Returns the list of the `best` matches with
    best.distance < ratio * second.distance (a pair without a second candidate is dropped)."""
    good = []
    for pair in knn_pairs:
        if len(pair) < 2:             # no second candidate: we cannot judge, drop it
            continue
        best, second = pair[0], pair[1]
        # TODO 7: append `best` to `good` only when it is clearly better than `second`
        raise NotImplementedError("TODO 7")
    return good


# ---------------------------------------------------------------- TODO 8
def match_views(view, patch, ratio=0.8, method="opencv", threshold=5.0):
    """Find the homography H (view pixels -> patch pixels).

    method: "opencv" (cv2.findHomography with cv2.RANSAC) or "mine" (geometry.ransac_homography).
    Returns (H, inliers, details): H is 3x3 (None when not found), inliers the number of
    RANSAC inliers, details a dict with the keypoints, the good matches, src / dst (N, 2)
    arrays and the boolean inlier mask."""
    kv, dv = features(view)
    kp, dp = features(patch)
    details = {"kp_view": kv, "kp_patch": kp, "good": [], "mask": None,
               "src": np.zeros((0, 2), np.float32), "dst": np.zeros((0, 2), np.float32)}
    if dv is None or dp is None or len(kv) < 4 or len(kp) < 4:
        return None, 0, details                  # a picture without texture (sea...)
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(dv, dp, k=2)
    # TODO 8a: good = the matches that pass your ratio_test (with the `ratio` argument)
    # TODO 8b: src, dst = (N, 2) float32 arrays of the (x, y) of each good match in the view
    #          (kv[m.queryIdx].pt) and in the patch (kp[m.trainIdx].pt); store them in details
    # TODO 8c: method "opencv": cv2.findHomography(src.reshape(-1, 1, 2), dst..., cv2.RANSAC, threshold)
    #          (its mask is (N, 1) of 0/1: make it a boolean (N,) array);
    #          method "mine": geometry.ransac_homography(src, dst, threshold);
    #          any other method: ValueError.  No H -> return None, 0, details.
    #          Put the boolean mask in details["mask"]; return H, number of inliers, details.
    raise NotImplementedError("TODO 8")


# ---------------------------------------------------------------- TODO 9
def trust(H, src_inliers, view_shape, expected_scale, expected_rotation_deg=None,
          min_inliers=8, scale_tol=0.15, rotation_tol_deg=20.0, min_spread=0.25):
    """NAVERA's trust gates.  Returns (ok, reason): ok is True or False, reason a short text.

    Refuse, in this order:  no H  ->  "no homography";
    fewer than min_inliers inliers  ->  a reason containing "inliers";
    expected_rotation_deg given and the fitted rotation further than rotation_tol_deg from it
    (difference wrapped to -180..180)  ->  a reason containing "rotation";
    |scale / expected_scale - 1| > scale_tol  ->  a reason containing "scale";
    fewer than 30 inliers AND inlier_spread(src_inliers, view_shape) < min_spread  ->  a reason
    containing "spread" (vision_nav.py: a weak fix on one strip of the frame is not believed).
    Otherwise (True, "ok")."""
    # TODO 9: the five refusals of the docstring, in that order; use geometry.similarity_params(H)
    #         for the rotation and the scale, and inlier_spread() (below) for the spread.
    raise NotImplementedError("TODO 9")


# ---- you don't need to change anything below this line ----
_sift = None


def features(img):
    """SIFT keypoints and descriptors of a picture (lesson 21). Always the same settings."""
    global _sift
    if _sift is None:
        _sift = cv2.SIFT_create(nfeatures=2000)
    grey = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return _sift.detectAndCompute(grey, None)


def inlier_spread(pts, shape):
    """NAVERA's local_matcher.inlier_spread: the share of a 4 x 2 grid of the frame whose
    cells hold at least 3 of the points."""
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    h, w = shape[:2]
    if len(pts) == 0:
        return 0.0
    cx = np.clip((pts[:, 0] / max(w, 1) * 4).astype(int), 0, 3)
    cy = np.clip((pts[:, 1] / max(h, 1) * 2).astype(int), 0, 1)
    counts = np.bincount(cy * 4 + cx, minlength=8)
    return float((counts >= 3).sum()) / 8.0


def where_is_centre(H, view):
    """The patch pixel (x, y) where the centre of the view lands."""
    h, w = view.shape[:2]
    p = cv2.perspectiveTransform(np.float32([[[w / 2.0, h / 2.0]]]), np.asarray(H, np.float64))
    return float(p[0, 0, 0]), float(p[0, 0, 1])


def draw_inlier_matches(view, patch, details, path):
    """Save a picture of the INLIER matches only to `path`."""
    good, mask = details["good"], details["mask"]
    inl = [m for m, ok in zip(good, mask) if ok] if mask is not None else []
    img = cv2.drawMatches(view, details["kp_view"], patch, details["kp_patch"], inl, None,
                          matchColor=(0, 200, 0), flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    cv2.imwrite(path, img)
    return path


def save_overlay(view, patch, H, path):
    """Lay the view onto the patch with H and save both mixed: if H is right, the roads of
    the view continue the roads of the map."""
    h, w = patch.shape[:2]
    warped = cv2.warpPerspective(view, H, (w, h))
    inside = cv2.warpPerspective(np.ones(view.shape[:2], np.uint8), H, (w, h)) > 0
    out = patch.copy()
    out[inside] = (0.5 * patch[inside] + 0.5 * warped[inside]).astype(np.uint8)
    corners = cv2.perspectiveTransform(np.float32([[[0, 0]], [[view.shape[1], 0]],
                                                   [[view.shape[1], view.shape[0]]], [[0, view.shape[0]]]]), H)
    cv2.polylines(out, [np.int32(corners)], True, (0, 165, 255), 3)
    cv2.imwrite(path, out)
    return path


def load_pair(name):
    return (cv2.imread(os.path.join(DATA, f"view_{name}.jpg")), cv2.imread(os.path.join(DATA, f"patch_{name}.jpg")))


def load_truth():
    with open(os.path.join(DATA, "truth.json")) as f:
        return json.load(f)


def demo(name, truth):
    view, patch = load_pair(name)
    t = truth[name]
    print(f"\n=== pair '{name}' (view made from: {t['view_source']}; truth: rotation {t['rotation_deg']:.0f} deg, "
          f"scale {t['scale']:.2f}, centre ({t['centre'][0]:.1f}, {t['centre'][1]:.1f}))")
    for method in ("opencv", "mine"):
        t0 = time.time()
        try:
            H, inliers, details = match_views(view, patch, method=method)
        except NotImplementedError as e:
            print(f"  {method:6s}: ({e} is not done yet)")
            continue
        ms = (time.time() - t0) * 1000.0
        print(f"  {method:6s}: {len(details['good'])} good matches, {inliers} inliers, {ms:.0f} ms", end="")
        if H is None:
            print("  — no homography")
            continue
        try:
            sp = geometry.similarity_params(H)
            c = where_is_centre(H, view)
            err = math.hypot(c[0] - t["centre"][0], c[1] - t["centre"][1])
            print(f"  rot {sp['rotation_deg']:7.2f}  scale {sp['scale']:.3f}  centre error {err:.2f} px")
        except NotImplementedError as e:
            print(f"  ({e} is not done yet)")
            continue
        if method == "opencv":
            save_overlay(view, patch, H, f"overlay_{name}.png")
            draw_inlier_matches(view, patch, details, f"matches_{name}.png")
            try:
                ok, why = trust(H, details["src"][details["mask"]], view.shape, t["scale"], t["rotation_deg"])
                print(f"          trust: {ok} ({why}) — saved overlay_{name}.png, matches_{name}.png")
            except NotImplementedError as e:
                print(f"          ({e} is not done yet)")


if __name__ == "__main__":
    truth = load_truth()
    for n in sys.argv[1:] or ["city", "olives", "otherdate", "sea"]:
        demo(n, truth)

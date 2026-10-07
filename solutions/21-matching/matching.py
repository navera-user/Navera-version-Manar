"""Lesson 21 — matching two pictures: a drone view and a piece of the satellite map.

Run the demo:   python3 matching.py            (all four pairs)
                python3 matching.py olives     (one pair)
"""
import json
import math
import os
import sys

import cv2
import numpy as np

DATA = "/data/academy/21-matching"           # the lesson's pictures (read only)


# ---------------------------------------------------------------- TODO 2
def ratio_test(knn_pairs, ratio=0.8):
    """Keep only the matches whose best candidate is clearly better than the second best.

    knn_pairs: what BFMatcher.knnMatch(..., k=2) returns — a list of [best, second] pairs,
    each a cv2.DMatch with a .distance. Returns the list of the 'best' matches for which
    best.distance < ratio * second.distance.
    """
    good = []
    for pair in knn_pairs:
        if len(pair) < 2:             # no second candidate: we cannot judge, skip it
            continue
        best, second = pair[0], pair[1]
        if best.distance < ratio * second.distance:
            good.append(best)
    return good


# ---------------------------------------------------------------- TODO 3
def match_views(view, patch, ratio=0.8):
    """Find the homography H that lays `view` onto `patch`.

    Returns (H, inliers, details): H is the 3x3 matrix (None when not found), inliers the
    number of RANSAC inliers, details a dict used to draw the matches.
    """
    kv, dv = features(view)
    kp, dp = features(patch)
    details = {"kp_view": kv, "kp_patch": kp, "good": [], "mask": None}
    if dv is None or dp is None or len(kv) < 4 or len(kp) < 4:
        return None, 0, details                  # a picture without texture (sea…)
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(dv, dp, k=2)

    # TODO 3a: keep the good matches with your ratio_test
    good = ratio_test(pairs, ratio)
    details["good"] = good
    if len(good) < 4:                            # a homography needs at least 4 pairs
        return None, 0, details

    # TODO 3b: the pixel positions of each good match, in the view (src) and in the patch (dst)
    src = np.float32([kv[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    # TODO 3c: the homography with RANSAC (5 px threshold); count the inliers in the mask
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None:
        return None, 0, details
    details["mask"] = mask.ravel().astype(bool)
    return H, int(mask.sum()), details


# ---------------------------------------------------------------- TODO 4
def rotation_and_scale(H):
    """(rotation in degrees, scale) of the homography, read from its top-left 2 x 2 block."""
    rotation = math.degrees(math.atan2(H[1, 0], H[0, 0]))
    scale = math.hypot(H[0, 0], H[1, 0])
    return rotation, scale


def where_is_centre(H, view):
    """The patch pixel (x, y) where the centre of the view lands."""
    h, w = view.shape[:2]
    p = cv2.perspectiveTransform(np.float32([[[w / 2.0, h / 2.0]]]), H)
    return float(p[0, 0, 0]), float(p[0, 0, 1])


# ---------------------------------------------------------------- TODO 5
def trust(H, inliers, expected_scale, min_inliers=8, scale_tol=0.15):
    """True when the match can be believed: a homography exists, it has at least
    min_inliers inliers, and its scale is within scale_tol (0.15 = 15 %) of expected_scale."""
    if H is None or inliers < min_inliers:
        return False
    _, scale = rotation_and_scale(H)
    return abs(scale / expected_scale - 1.0) <= scale_tol


# ---------------------------------------------------------------- TODO 6
def draw_inlier_matches(view, patch, details, path):
    """Save a picture of the INLIER matches only (cv2.drawMatches) to `path`."""
    good, mask = details["good"], details["mask"]
    inl = [m for m, ok in zip(good, mask) if ok] if mask is not None else []
    img = cv2.drawMatches(view, details["kp_view"], patch, details["kp_patch"], inl, None,
                          matchColor=(0, 255, 0), flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    cv2.imwrite(path, img)
    return path


# ---- you don't need to change anything below this line ----
_sift = None


def features(img):
    """SIFT keypoints and descriptors of a picture (lesson 20). Always the same settings."""
    global _sift
    if _sift is None:
        _sift = cv2.SIFT_create(nfeatures=2000)
    grey = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return _sift.detectAndCompute(grey, None)


def save_overlay(view, patch, H, path):
    """Lay the view onto the patch with H (cv2.warpPerspective) and save both mixed:
    if H is right, the roads of the view continue the roads of the map."""
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
    view = cv2.imread(os.path.join(DATA, f"view_{name}.jpg"))
    patch = cv2.imread(os.path.join(DATA, f"patch_{name}.jpg"))
    return view, patch


def load_truth():
    with open(os.path.join(DATA, "truth.json")) as f:
        return json.load(f)


def demo(name, truth):
    view, patch = load_pair(name)
    t = truth[name]
    print(f"\n=== pair '{name}' (view made from: {t['view_source']})")
    result = match_views(view, patch)
    if result is None:
        print("  match_views() returns nothing yet (TODO 3)")
        return
    H, inliers, details = result
    print(f"  good matches after the ratio test: {len(details['good'])}")
    print(f"  RANSAC inliers: {inliers}")
    if H is None:
        print("  no homography found — nothing to lay onto the map")
        return
    rs = rotation_and_scale(H)
    if rs is None:
        print("  rotation_and_scale() returns nothing yet (TODO 4)")
    else:
        print(f"  rotation : {rs[0]:7.1f} deg   (truth {t['rotation_deg']:.1f})")
        print(f"  scale    : {rs[1]:7.3f}       (truth {t['scale']:.3f})")
    c = where_is_centre(H, view)
    if c is not None:
        print(f"  centre   : ({c[0]:.1f}, {c[1]:.1f}) px   (truth ({t['centre'][0]:.1f}, {t['centre'][1]:.1f}))")
    ok = trust(H, inliers, t["scale"])
    print(f"  trust it?: {ok if ok is not None else 'TODO 5'}")
    print(f"  overlay  : {save_overlay(view, patch, H, f'overlay_{name}.png')}  (the view laid onto the map)")
    out = draw_inlier_matches(view, patch, details, f"matches_{name}.png")
    if out:
        print(f"  matches  : {out}  (open it in the editor)")


if __name__ == "__main__":
    truth = load_truth()
    names = sys.argv[1:] or ["city", "olives", "otherdate", "sea"]
    for n in names:
        demo(n, truth)

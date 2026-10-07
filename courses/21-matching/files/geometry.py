"""Lesson 21 — the geometry of matching, written by hand with numpy.

    python3 geometry.py          # a self-test on synthetic points with a known homography

You implement: applying a homography, Hartley normalisation, the DLT (with numpy's SVD),
the RANSAC iteration formula, RANSAC itself, and reading rotation / scale out of H.
matching.py then uses these functions on real pictures and compares them with OpenCV.
"""
import math

import numpy as np


# ---------------------------------------------------------------- TODO 1
def apply_homography(H, pts):
    """Carry points through H.  pts: (N, 2) array of (x, y).  Returns an (N, 2) array.

    In homogeneous coordinates: [x', y', w']^T = H [x, y, 1]^T, then divide by w'."""
    # TODO 1a: add a column of 1s (np.hstack), multiply by H transposed,
    #          divide the first two columns by the third
    raise NotImplementedError("TODO 1a")


def reprojection_errors(H, src, dst):
    """Distance in pixels between H(src_i) and dst_i, for every pair i.  Returns (N,)."""
    # TODO 1b: apply_homography(H, src) minus dst, then the length of each row
    #          (np.linalg.norm(..., axis=1))
    raise NotImplementedError("TODO 1b")


# ---------------------------------------------------------------- TODO 2
def normalise_points(pts):
    """Hartley normalisation.  Returns (pts_n, T): T is the 3x3 similarity that moves the
    centroid of pts to (0, 0) and scales them so that their mean distance to it is sqrt(2);
    pts_n = T applied to pts, shape (N, 2)."""
    # TODO 2: centroid c = mean of the points; d = mean distance of the points to c;
    #         s = sqrt(2) / d; T = [[s, 0, -s*cx], [0, s, -s*cy], [0, 0, 1]];
    #         pts_n = (pts - c) * s.  Return pts_n, T
    raise NotImplementedError("TODO 2")


# ---------------------------------------------------------------- TODO 3
def build_dlt_matrix(src, dst):
    """The 2N x 9 matrix A of the DLT (A h = 0) for pairs (x, y) -> (u, v)."""
    # TODO 3a: for each pair (x, y) -> (u, v) append the two rows of the course
    #          (section 4) to a list, return np.array(rows) of shape (2N, 9)
    raise NotImplementedError("TODO 3a")


def dlt_homography(src, dst, normalise=True):
    """The homography H (3x3, H[2, 2] = 1) with H(src_i) ~ dst_i, from N >= 4 pairs, by the
    Direct Linear Transform: two rows of A per pair, h = the right singular vector of A for
    its smallest singular value.  With normalise=True both point sets are normalised first
    (Hartley) and H is de-normalised at the end: H = inv(T_dst) @ Hn @ T_src."""
    # TODO 3b: (normalise both sets) -> A = build_dlt_matrix -> np.linalg.svd(A) ->
    #          h = last row of Vt -> 3x3 -> de-normalise -> divide by H[2, 2]
    #          (raise ValueError for fewer than 4 pairs)
    raise NotImplementedError("TODO 3b")


# ---------------------------------------------------------------- TODO 4
def ransac_iterations(p, w, s):
    """How many random samples RANSAC needs so that, with probability p, at least one of
    them holds only inliers: N = log(1 - p) / log(1 - w**s), rounded UP to an integer.
    w: inlier ratio (0..1], s: sample size.  w = 1 → 1 sample.  w = 0 → ValueError."""
    # TODO 4: the formula of the course (section 5); math.log, math.ceil.
    #         Do not forget the special cases of the docstring.
    raise NotImplementedError("TODO 4")


# ---------------------------------------------------------------- TODO 5
def ransac_homography(src, dst, threshold=5.0, p=0.999, max_iters=5000, seed=0):
    """RANSAC around dlt_homography.  Returns (H, mask): mask is a boolean array (N,), True
    for the inliers (reprojection error < threshold px).  (None, all-False mask) when no
    model is found.  Adaptive: after each better model, the number of samples still needed
    is recomputed with ransac_iterations(p, inlier_ratio, 4)."""
    # TODO 5: loop: 4 random indices (rng.choice(n, 4, replace=False)); skip degenerate
    #         samples (_degenerate); H = dlt_homography of the sample; mask = errors < threshold;
    #         keep the best mask and update the number of samples still needed;
    #         at the end refit on all the inliers and recompute the mask.
    #         rng = np.random.default_rng(seed) makes the result repeatable.
    raise NotImplementedError("TODO 5")


def _degenerate(q):  # (given: used by TODO 5)
    """True when 3 of the 4 points are (nearly) on one line: no homography is defined."""
    for a, b, c in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)):
        area = abs((q[b, 0] - q[a, 0]) * (q[c, 1] - q[a, 1]) - (q[b, 1] - q[a, 1]) * (q[c, 0] - q[a, 0]))
        if area < 1e-6 * (1.0 + np.abs(q).max()) ** 2:
            return True
    return False


# ---------------------------------------------------------------- TODO 6
def similarity_params(H):
    """Read the motion out of H (normalised to H[2, 2] = 1).  Returns a dict:
      rotation_deg  the rotation of the 2x2 block A = H[:2, :2] (closest rotation: U @ Vt of its SVD)
      scale         sqrt(|det A|): the mean zoom
      anisotropy    sigma_max / sigma_min of A: 1.0 for a pure rotation + scale
      perspective   |(H[2, 0], H[2, 1])|: 0 for a straight-down view
      tx, ty        the translation H[0, 2], H[1, 2]"""
    # TODO 6: A = H[:2, :2] (after dividing H by H[2, 2]); U, S, Vt = np.linalg.svd(A);
    #         R = U @ Vt; rotation = atan2(R[1, 0], R[0, 0]) in degrees; ... (see the course)
    raise NotImplementedError("TODO 6")


# ---- you don't need to change anything below this line ----

def synthetic_pairs(n=200, outlier_ratio=0.3, noise_px=0.5, seed=1):
    """Pairs (src, dst) of a known homography H_true, with noise and outliers, for tests.
    Returns (src, dst, H_true, is_inlier)."""
    rng = np.random.default_rng(seed)
    a = math.radians(35.0)
    H_true = np.array([[1.2 * math.cos(a), -1.2 * math.sin(a), 310.0],
                       [1.2 * math.sin(a), 1.2 * math.cos(a), 140.0],
                       [2e-5, -1e-5, 1.0]])
    src = rng.uniform([0, 0], [640, 480], (n, 2))
    ph = np.hstack([src, np.ones((n, 1))]) @ H_true.T
    dst = ph[:, :2] / ph[:, 2:3] + rng.normal(0, noise_px, (n, 2))
    is_in = rng.random(n) >= outlier_ratio
    dst[~is_in] = rng.uniform([0, 0], [1000, 1000], ((~is_in).sum(), 2))
    return src, dst, H_true, is_in


def _try(step, fn, *a, **k):
    try:
        return fn(*a, **k)
    except NotImplementedError:
        print(f"  ({step} is not done yet)")
    except Exception as e:  # show the problem, keep the demo going
        print(f"  {step} raised {type(e).__name__}: {e}")
    return None


if __name__ == "__main__":
    np.set_printoptions(precision=4, suppress=True)
    src, dst, H_true, is_in = synthetic_pairs()
    print(f"{len(src)} synthetic pairs, {is_in.sum()} inliers (noise 0.5 px), {(~is_in).sum()} outliers")
    print("H_true =\n", H_true)
    m = _try("TODO 1", apply_homography, H_true, src[:3])
    if m is not None:
        print("TODO 1  H_true carries the first point", src[0].round(1), "to", np.round(m[0], 1))
    r = _try("TODO 2", normalise_points, src)
    if r is not None:
        pn, T = r
        print(f"TODO 2  normalised: centroid {pn.mean(0).round(6)}, mean distance "
              f"{np.linalg.norm(pn, axis=1).mean():.4f} (sqrt 2 = 1.4142)")
    H = _try("TODO 3", dlt_homography, src[is_in], dst[is_in])
    if H is not None:
        print("TODO 3  DLT on the inliers only:\n", H)
    for w in (0.9, 0.7, 0.5, 0.3):
        n = _try("TODO 4", ransac_iterations, 0.99, w, 4)
        if n is None:
            break
        print(f"TODO 4  p=0.99, w={w}, s=4  ->  N = {n}")
    res = _try("TODO 5", ransac_homography, src, dst, 3.0)
    if res is not None and res[0] is not None:
        Hr, mask = res
        print(f"TODO 5  RANSAC: {mask.sum()} inliers, {np.sum(mask & is_in)} of them true inliers")
        sp = _try("TODO 6", similarity_params, Hr)
        if sp:
            print("TODO 6  ", {k: round(v, 4) for k, v in sp.items()}, "(truth: rotation 35, scale ~1.2)")

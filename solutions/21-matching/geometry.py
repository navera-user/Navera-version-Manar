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
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    ph = np.hstack([pts, np.ones((len(pts), 1))]) @ np.asarray(H, dtype=np.float64).T
    return ph[:, :2] / ph[:, 2:3]


def reprojection_errors(H, src, dst):
    """Distance in pixels between H(src_i) and dst_i, for every pair i.  Returns (N,)."""
    return np.linalg.norm(apply_homography(H, src) - np.asarray(dst, dtype=np.float64).reshape(-1, 2), axis=1)


# ---------------------------------------------------------------- TODO 2
def normalise_points(pts):
    """Hartley normalisation.  Returns (pts_n, T): T is the 3x3 similarity that moves the
    centroid of pts to (0, 0) and scales them so that their mean distance to it is sqrt(2);
    pts_n = T applied to pts, shape (N, 2)."""
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    c = pts.mean(axis=0)
    d = np.linalg.norm(pts - c, axis=1).mean()
    s = math.sqrt(2.0) / d if d > 0 else 1.0
    T = np.array([[s, 0.0, -s * c[0]], [0.0, s, -s * c[1]], [0.0, 0.0, 1.0]])
    return (pts - c) * s, T


# ---------------------------------------------------------------- TODO 3
def build_dlt_matrix(src, dst):
    """The 2N x 9 matrix A of the DLT (A h = 0) for pairs (x, y) -> (u, v)."""
    rows = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])
    return np.array(rows)


def dlt_homography(src, dst, normalise=True):
    """The homography H (3x3, H[2, 2] = 1) with H(src_i) ~ dst_i, from N >= 4 pairs, by the
    Direct Linear Transform: two rows of A per pair, h = the right singular vector of A for
    its smallest singular value.  With normalise=True both point sets are normalised first
    (Hartley) and H is de-normalised at the end: H = inv(T_dst) @ Hn @ T_src."""
    src = np.asarray(src, dtype=np.float64).reshape(-1, 2)
    dst = np.asarray(dst, dtype=np.float64).reshape(-1, 2)
    if len(src) < 4 or len(src) != len(dst):
        raise ValueError("dlt_homography needs at least 4 pairs, as many src as dst")
    if normalise:
        s, Ts = normalise_points(src)
        d, Td = normalise_points(dst)
    else:
        s, d, Ts, Td = src, dst, np.eye(3), np.eye(3)
    A = build_dlt_matrix(s, d)
    _, _, Vt = np.linalg.svd(A)
    Hn = Vt[-1].reshape(3, 3)
    H = np.linalg.inv(Td) @ Hn @ Ts
    return H / H[2, 2]


# ---------------------------------------------------------------- TODO 4
def ransac_iterations(p, w, s):
    """How many random samples RANSAC needs so that, with probability p, at least one of
    them holds only inliers: N = log(1 - p) / log(1 - w**s), rounded UP to an integer.
    w: inlier ratio (0..1], s: sample size.  w = 1 → 1 sample.  w = 0 → ValueError."""
    if not 0.0 < w <= 1.0 or not 0.0 < p < 1.0:
        raise ValueError("need 0 < w <= 1 and 0 < p < 1")
    ws = w ** s
    if ws >= 1.0:
        return 1
    return int(math.ceil(math.log(1.0 - p) / math.log(1.0 - ws)))


# ---------------------------------------------------------------- TODO 5
def ransac_homography(src, dst, threshold=5.0, p=0.999, max_iters=5000, seed=0):
    """RANSAC around dlt_homography.  Returns (H, mask): mask is a boolean array (N,), True
    for the inliers (reprojection error < threshold px).  (None, all-False mask) when no
    model is found.  Adaptive: after each better model, the number of samples still needed
    is recomputed with ransac_iterations(p, inlier_ratio, 4)."""
    src = np.asarray(src, dtype=np.float64).reshape(-1, 2)
    dst = np.asarray(dst, dtype=np.float64).reshape(-1, 2)
    n = len(src)
    best_mask = np.zeros(n, bool)
    if n < 4:
        return None, best_mask
    rng = np.random.default_rng(seed)
    best_count, needed, it = 0, max_iters, 0
    while it < min(needed, max_iters):
        it += 1
        idx = rng.choice(n, 4, replace=False)
        if _degenerate(src[idx]) or _degenerate(dst[idx]):
            continue
        try:
            H = dlt_homography(src[idx], dst[idx])
        except (np.linalg.LinAlgError, ValueError):
            continue
        if not np.all(np.isfinite(H)):
            continue
        with np.errstate(all="ignore"):
            mask = reprojection_errors(H, src, dst) < threshold
        c = int(mask.sum())
        if c > best_count:
            best_count, best_mask = c, mask
            needed = ransac_iterations(p, c / n, 4)
    if best_count < 4:
        return None, np.zeros(n, bool)
    H = dlt_homography(src[best_mask], dst[best_mask])            # refit on all the inliers
    with np.errstate(all="ignore"):
        mask = reprojection_errors(H, src, dst) < threshold
    return H, mask


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
    H = np.asarray(H, dtype=np.float64)
    H = H / H[2, 2]
    A = H[:2, :2]
    U, S, Vt = np.linalg.svd(A)
    R = U @ Vt
    return {"rotation_deg": math.degrees(math.atan2(R[1, 0], R[0, 0])),
            "scale": math.sqrt(abs(np.linalg.det(A))),
            "anisotropy": float(S[0] / S[1]) if S[1] > 0 else float("inf"),
            "perspective": float(math.hypot(H[2, 0], H[2, 1])),
            "tx": float(H[0, 2]), "ty": float(H[1, 2])}


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

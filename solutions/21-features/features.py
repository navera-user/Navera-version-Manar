"""Lesson 21 — Local features: corners, scale and descriptors.

Run the demo:   python3 features.py
Each TODO is one function. Save (Ctrl+S), run again, then press ✔ Check my work.
The units: x = column (to the right), y = row (down), as in OpenCV; points are (x, y).
"""
import csv
import os

import cv2
import numpy as np
from scipy.spatial import cKDTree

DATA = "/data/academy/21-features"           # the lesson's pictures (read only)

# TODO 0 (Step 5 of the lab): write here what you measured on real descriptors.
ORB_BYTES = 32         # how many bytes (numbers 0-255) in ONE ORB descriptor?   des.shape[1]
SIFT_LENGTH = 128      # how many numbers in ONE SIFT descriptor?                des.shape[1]

SOBEL_NORM = 8.0       # cv2.Sobel(ksize=3) gives 8x the change per pixel: divide by this


# ───────────────────────── Part A — Harris, from the maths ─────────────────────────

def image_gradients(grey):
    """(Ix, Iy): brightness change per pixel to the right (x) and down (y), float32 arrays.
    3x3 Sobel derivative divided by SOBEL_NORM, so that a ramp I = a*x gives Ix = a."""
    g = grey.astype(np.float32)
    ix = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3) / SOBEL_NORM
    iy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3) / SOBEL_NORM
    return ix, iy


def harris_response(grey, sigma=1.5, k=0.05):
    """Harris corner response R = det(M) - k * trace(M)^2 at every pixel (float32 array).
    M = [[Sxx, Sxy], [Sxy, Syy]] is the structure tensor: Ix*Ix, Iy*Iy and Ix*Iy, each
    averaged by a Gaussian window of standard deviation sigma (cv2.GaussianBlur)."""
    ix, iy = image_gradients(grey)
    sxx = cv2.GaussianBlur(ix * ix, (0, 0), sigma)
    syy = cv2.GaussianBlur(iy * iy, (0, 0), sigma)
    sxy = cv2.GaussianBlur(ix * iy, (0, 0), sigma)
    return (sxx * syy - sxy * sxy - k * (sxx + syy) ** 2).astype(np.float32)


def harris_corners(grey, n=500, sigma=1.5, k=0.05, nms_radius=4, rel_threshold=0.01):
    """The n strongest Harris corners as a float32 array (m, 2) of (x, y), strongest first.
    A pixel is kept when (1) R is the maximum of its (2r+1) x (2r+1) neighbourhood
    (non-maximum suppression, r = nms_radius) and (2) R > rel_threshold * R.max()."""
    r = harris_response(grey, sigma, k)
    size = 2 * nms_radius + 1
    local_max = r == cv2.dilate(r, np.ones((size, size), np.uint8))
    keep = local_max & (r > rel_threshold * r.max())
    ys, xs = np.nonzero(keep)
    order = np.argsort(-r[ys, xs])[:n]
    return np.float32(np.column_stack([xs[order], ys[order]])).reshape(-1, 2)


def characteristic_scale(grey, x, y, sigmas):
    """The sigma (one of `sigmas`) where the scale-normalised Laplacian
    |sigma^2 * Laplacian(Gaussian_sigma * I)| is largest at pixel (x, y)."""
    g = grey.astype(np.float32)
    best, best_v = None, -1.0
    for s in sigmas:
        lap = cv2.Laplacian(cv2.GaussianBlur(g, (0, 0), s), cv2.CV_32F, ksize=1)
        v = abs(s * s * float(lap[int(y), int(x)]))
        if v > best_v:
            best, best_v = s, v
    return float(best)


# ───────────────────────── Part B — OpenCV detectors and descriptors ─────────────────────────

def detect_keypoints(img, method="ORB", max_points=10000):
    """(keypoints, descriptors) of a picture (colour BGR or grey) with ORB or SIFT.
    keypoints: a list of cv2.KeyPoint; descriptors: one row per keypoint (None when none).
    Any other method → ValueError."""
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if method == "ORB":
        det = cv2.ORB_create(nfeatures=max_points)
    elif method == "SIFT":
        det = cv2.SIFT_create(nfeatures=max_points)
    else:
        raise ValueError(f"unknown method {method!r} (use 'ORB' or 'SIFT')")
    kps, des = det.detectAndCompute(grey, None)
    return list(kps), des


def hamming(a, b):
    """Number of different bits between two binary descriptors (uint8 arrays of equal length)."""
    return int(np.unpackbits(np.bitwise_xor(np.asarray(a, np.uint8), np.asarray(b, np.uint8))).sum())


# ───────────────────────── Part C — repeatability ─────────────────────────

def project(points, H):
    """Points (N, 2) mapped by the 3x3 matrix H: [x', y', w'] = H [x, y, 1], then (x'/w', y'/w')."""
    p = np.asarray(points, np.float64).reshape(-1, 2)
    hom = np.column_stack([p, np.ones(len(p))]) @ np.asarray(H, np.float64).T
    return hom[:, :2] / hom[:, 2:3]


def repeatability(pts_a, pts_b, H, shape_b, eps=3.0):
    """Share of the points of picture A that are found again in picture B.
    pts_a, pts_b: arrays (N, 2) of (x, y). H maps A to B. shape_b: B's shape (h, w, ...).
    Only A points whose projection falls inside B count; one is 'repeated' when a B point
    lies within eps pixels of its projection. Returns a number 0-1 (0 when none falls inside)."""
    h, w = shape_b[:2]
    pa = project(pts_a, H)
    inside = (pa[:, 0] >= 0) & (pa[:, 0] < w) & (pa[:, 1] >= 0) & (pa[:, 1] < h)
    pa = pa[inside]
    pb = np.asarray(pts_b, np.float64).reshape(-1, 2)
    if len(pa) == 0 or len(pb) == 0:
        return 0.0
    d, _ = cKDTree(pb).query(pa)
    return float((d <= eps).mean())


# ───────────────────────── Part D — texture and matchability ─────────────────────────

def count_keypoints(path, method="SIFT"):
    """(given — read it) Number of keypoints found in the picture file `path`."""
    return len(detect_keypoints(cv2.imread(path), method)[0])


def keypoints_per_terrain(method="SIFT"):
    """(given — read it) {terrain name: number of keypoints} for every row of terrain.csv."""
    out = {}
    with open(os.path.join(DATA, "terrain.csv"), newline="") as f:
        for row in csv.DictReader(f):
            out[row["terrain"]] = count_keypoints(os.path.join(DATA, row["file"]), method)
    return out


def spread(keypoints, shape, grid=(4, 4), min_per_cell=3):
    """Share (0 to 1) of the cells of a grid cut of the picture that hold at least
    min_per_cell keypoints. shape: img.shape (height, width, ...). grid: (columns, rows)."""
    cols, rows = grid
    h, w = shape[:2]
    counts = np.zeros((rows, cols), int)
    for kp in keypoints:
        x, y = kp.pt
        counts[min(rows - 1, max(0, int(y / h * rows))), min(cols - 1, max(0, int(x / w * cols)))] += 1
    return float((counts >= min_per_cell).sum()) / (rows * cols)


def matchability(img, enough=300):
    """How easy this picture will be to match on a map: 0 (hopeless) to 1 (great).
    = min(1, number of ORB keypoints / enough) x spread of those keypoints."""
    kps, _ = detect_keypoints(img, "ORB", max_points=500)
    return min(1.0, len(kps) / enough) * spread(kps, img.shape)


# ---- you don't need to change anything below this line (but read it!) ----

def draw_keypoints(img, keypoints, out_path):
    """Save a copy of img with every keypoint drawn as a circle (size = its scale, line = its angle)."""
    drawn = cv2.drawKeypoints(img, keypoints, None, color=(0, 0, 255),
                              flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    cv2.imwrite(out_path, drawn)
    return out_path


def draw_points(img, pts, out_path, color=(0, 255, 255)):
    """Save a copy of img with small crosses on the points (N, 2)."""
    out = img.copy() if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    for x, y in np.asarray(pts).reshape(-1, 2):
        cv2.drawMarker(out, (int(round(x)), int(round(y))), color, cv2.MARKER_CROSS, 7, 1)
    cv2.imwrite(out_path, out)
    return out_path


def _try(step, fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except NotImplementedError:
        print(f"  ({step} is not done yet)")
    except Exception as e:  # show the problem, keep the demo going
        print(f"  {step} raised {type(e).__name__}: {e}")
    return None


if __name__ == "__main__":
    city = cv2.imread(os.path.join(DATA, "terrain_city.jpg"))
    grey = cv2.cvtColor(city, cv2.COLOR_BGR2GRAY)
    print("The city patch is", city.shape[1], "x", city.shape[0], "pixels")

    ramp = np.tile(np.arange(20, dtype=np.float32) * 3.0, (20, 1))          # I = 3 x
    g = _try("TODO 1", image_gradients, ramp)
    if g is not None:
        print(f"TODO 1  ramp I = 3x: Ix = {g[0][10, 10]:.2f} (expect 3.00), Iy = {g[1][10, 10]:.2f} (expect 0.00)")
    r = _try("TODO 2", harris_response, grey)
    if r is not None:
        print(f"TODO 2  Harris R on the city: min {r.min():.1f}, max {r.max():.1f}")
    pts = _try("TODO 3", harris_corners, grey, 300)
    if pts is not None:
        draw_points(city, pts, "harris_city.png")
        print(f"TODO 3  {len(pts)} Harris corners → saved harris_city.png")
    res = _try("TODO 5", detect_keypoints, city, "ORB")
    if res:
        kps, des = res
        print(f"TODO 5  ORB found {len(kps)} keypoints; descriptors array: {des.shape} {des.dtype}")
        draw_keypoints(city, kps[:300], "keypoints_city.png")
        print("        → saved keypoints_city.png (the 300 strongest) — open it in the editor")
        d = _try("TODO 6", hamming, des[0], des[1])
        if d is not None:
            print(f"TODO 6  Hamming distance between descriptors 0 and 1: {d} bits of {8 * des.shape[1]}")
    print("\nMatchability (0 = hopeless, 1 = great):")
    for name in ("terrain_city.jpg", "terrain_olives.jpg", "terrain_coast_water.jpg", "terrain_sea.jpg",
                 "drone_city.jpg", "drone_city_blurry_dark.jpg"):
        s = _try("TODO 8", matchability, cv2.imread(os.path.join(DATA, name)))
        if s is None:
            break
        print(f"  {name:28s} {s:.2f}")
    print("\nNext: python3 measure.py   (repeatability and the numbers for your report)")

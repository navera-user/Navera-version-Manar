"""Lesson 21 — warm-up: fit a line through points when some points are wrong (RANSAC).

Run:   python3 ransac_line.py        → prints both fits and saves line_fit.png
"""
import os
import warnings

import matplotlib
matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Unable to import Axes3D")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

DATA = "/data/academy/21-matching"           # the lesson's pictures (read only)


def least_squares_line(points):
    """The ordinary 'best line' through ALL points (numpy's polyfit). Outliers pull it away."""
    pts = np.asarray(points, dtype=float)
    slope, intercept = np.polyfit(pts[:, 0], pts[:, 1], 1)
    return float(slope), float(intercept)


# ---------------------------------------------------------------- TODO 1
def fit_line_ransac(points, iterations=200, threshold=3.0, seed=0):
    """Fit y = slope * x + intercept despite outliers. Returns (slope, intercept, inlier_mask)."""
    rng = np.random.default_rng(seed)
    pts = np.asarray(points, dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    best_mask, best_count = None, -1
    for _ in range(iterations):
        # 1. pick two different points at random
        i, j = rng.choice(len(pts), 2, replace=False)
        if x[i] == x[j]:
            continue                      # a vertical line: skip this try
        # TODO 1a: the slope and the intercept of the line through points i and j
        # TODO 1b: mask = a boolean array, True for the points whose vertical distance
        #          |y - (slope * x + intercept)| is smaller than threshold
        # TODO 1c: if this mask has more True values than best_count, remember it
        #          (best_mask, best_count)
    # TODO 1d: refit with least_squares_line(...) on the inliers of the best mask only,
    #          and return slope, intercept, best_mask
    return None


# ---- you don't need to change anything below this line ----
def load_points():
    return np.loadtxt(os.path.join(DATA, "points.csv"), delimiter=",", skiprows=1)


if __name__ == "__main__":
    pts = load_points()
    s1, b1 = least_squares_line(pts)
    print(f"{len(pts)} points")
    print(f"least squares on ALL points : y = {s1:.3f} x + {b1:.2f}")
    res = fit_line_ransac(pts)
    fig, ax = plt.subplots(figsize=(7, 5))
    xs = np.array([0, 100])
    if res is None or res[0] is None:
        print("RANSAC                      : not written yet (TODO 1)")
        ax.scatter(pts[:, 0], pts[:, 1], s=14, color="#888888", label="points")
    else:
        s2, b2, mask = res
        mask = np.asarray(mask, dtype=bool)
        print(f"RANSAC                      : y = {s2:.3f} x + {b2:.2f}   ({mask.sum()} inliers, "
              f"{(~mask).sum()} outliers)")
        ax.scatter(pts[mask, 0], pts[mask, 1], s=14, color="#0b6e8a", label="inliers")
        ax.scatter(pts[~mask, 0], pts[~mask, 1], s=14, color="#d64545", marker="x", label="outliers")
        ax.plot(xs, s2 * xs + b2, color="#0b6e8a", lw=2, label="RANSAC line")
    ax.plot(xs, s1 * xs + b1, color="#f2a33a", lw=2, ls="--", label="least squares (all points)")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend()
    ax.set_title("Fitting a line when 30 % of the points are wrong")
    fig.savefig("line_fit.png", dpi=90, bbox_inches="tight")
    print("saved line_fit.png — open it in the editor")

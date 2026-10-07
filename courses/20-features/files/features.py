"""Lesson 20 — Finding interesting points (keypoints) in map pictures.

Run the demo:   python3 features.py
Each TODO is one small function. Save (Ctrl+S), run again, then press ✔ Check my work.
"""
import csv
import os

import cv2
import numpy as np

DATA = "/data/academy/20-features"           # the lesson's pictures (read only)

# TODO 6 (after Step 3 of the lab): write here what you measured on a real descriptor.
ORB_BYTES = 0          # how many bytes (numbers 0-255) in ONE ORB descriptor?   des.shape[1]
SIFT_LENGTH = 0        # how many numbers in ONE SIFT descriptor?                des.shape[1]


def detect_keypoints(img, method="ORB", max_points=10000):
    """Find the keypoints of a picture and compute their descriptors.

    img: a picture (colour BGR or grey). method: "ORB" or "SIFT".
    Returns (keypoints, descriptors): a list of cv2.KeyPoint and a numpy array with one row
    per keypoint (None when there is no keypoint). Any other method → ValueError.
    """
    # TODO 1: grey picture, then ORB or SIFT detector with nfeatures=max_points, then detectAndCompute
    raise NotImplementedError("TODO 1")


def count_keypoints(path, method="SIFT"):
    """Number of keypoints found in the picture file `path`."""
    # TODO 2: read the picture with cv2.imread, then use detect_keypoints
    raise NotImplementedError("TODO 2")


def keypoints_per_terrain(method="SIFT"):
    """{terrain name: number of keypoints} for every row of terrain.csv."""
    # TODO 3: read DATA/terrain.csv (columns file, terrain, ...) and count the keypoints of each file
    raise NotImplementedError("TODO 3")


def spread(keypoints, shape, grid=(4, 4), min_per_cell=3):
    """Share (0 to 1) of the cells of a grid x grid cut of the picture that hold at least
    min_per_cell keypoints. shape: img.shape (height, width, ...). grid: (columns, rows)."""
    # TODO 4: count the keypoints falling in each cell, then the share of "full enough" cells
    raise NotImplementedError("TODO 4")


def matchability(img, enough=300):
    """How easy this picture will be to match on a map: a score from 0 (hopeless) to 1 (great).
    = min(1, number of ORB keypoints / enough) x spread of those keypoints."""
    # TODO 5: ORB keypoints (max_points=500), then combine their number and their spread
    raise NotImplementedError("TODO 5")


# ---- you don't need to change anything below this line (but read it!) ----

def draw_keypoints(img, keypoints, out_path):
    """Save a copy of img with every keypoint drawn as a circle (size = its scale, line = its angle)."""
    drawn = cv2.drawKeypoints(img, keypoints, None, color=(0, 0, 255),
                              flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    cv2.imwrite(out_path, drawn)
    return out_path


def _try(step, fn, *a):
    try:
        return fn(*a)
    except NotImplementedError:
        print(f"  ({step} is not done yet)")
    except Exception as e:  # show the problem, keep the demo going
        print(f"  {step} raised {type(e).__name__}: {e}")
    return None


if __name__ == "__main__":
    city = cv2.imread(os.path.join(DATA, "terrain_city.jpg"))
    print("The city patch is", city.shape[1], "x", city.shape[0], "pixels")
    res = _try("TODO 1", detect_keypoints, city, "ORB")
    if res:
        kps, des = res
        print(f"ORB found {len(kps)} keypoints; descriptors array: {des.shape} {des.dtype}")
        print("first keypoint: x=%.1f y=%.1f size=%.1f angle=%.0f°" % (kps[0].pt + (kps[0].size, kps[0].angle)))
        draw_keypoints(city, kps[:300], "keypoints_city.png")
        print("→ saved keypoints_city.png (the 300 strongest) — open it in the editor")
    table = _try("TODO 3", keypoints_per_terrain, "SIFT")
    if table:
        print("\nSIFT keypoints per terrain:")
        for name, n in sorted(table.items(), key=lambda t: -t[1]):
            print(f"  {name:12s} {n:6d}  " + "#" * min(60, n // 100))
    print("\nMatchability (0 = hopeless, 1 = great):")
    for name in ("terrain_city.jpg", "terrain_olives.jpg", "terrain_coast_water.jpg", "terrain_sea.jpg",
                 "drone_city.jpg", "drone_city_blurry_dark.jpg"):
        s = _try("TODO 5", matchability, cv2.imread(os.path.join(DATA, name)))
        if s is None:
            break
        print(f"  {name:28s} {s:.2f}")

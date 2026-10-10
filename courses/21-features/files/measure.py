"""Measure your detectors on the lesson's pictures and save results.json.   python3 measure.py

Uses YOUR functions from features.py (TODOs 1-8 must be done). It measures:
  1. repeatability of Harris, ORB and SIFT on 5 picture pairs with a known transform H,
     with the same number of points per detector (1000), and the chance level;
  2. Hamming distances of ORB descriptors: the same ground point vs two random points;
  3. SIFT keypoints per terrain and the matchability of 6 pictures.
Read results.json, then write report.md (Step 8 of the lab).
"""
import json
import os

import cv2
import numpy as np

from features import (DATA, detect_keypoints, hamming, harris_corners, keypoints_per_terrain, matchability,
                      project, repeatability)

N_POINTS = 1000          # the same number of points for every detector: a fair comparison
EPS = 3.0                # a point is "found again" within 3 pixels


def grey(path):
    return cv2.imread(os.path.join(DATA, path), cv2.IMREAD_GRAYSCALE)


def points(img, method):
    if method == "harris":
        return harris_corners(img, n=N_POINTS)
    kps, _ = detect_keypoints(img, method.upper(), max_points=N_POINTS)
    return np.float32([k.pt for k in kps[:N_POINTS]]).reshape(-1, 2)


def chance_level(n_b, shape_b, eps=EPS, trials=2000, seed=0):
    """Repeatability of RANDOM points: the share of random positions with one of n_b random
    points within eps — what a useless detector would score."""
    rng = np.random.default_rng(seed)
    h, w = shape_b[:2]
    a = rng.uniform([0, 0], [w, h], (trials, 2))
    b = rng.uniform([0, 0], [w, h], (n_b, 2))
    return repeatability(a, b, np.eye(3), shape_b, eps)


def main():
    pairs = json.load(open(os.path.join(DATA, "pairs.json")))
    out = {"n_points": N_POINTS, "eps_px": EPS, "repeatability": {}, "pairs": {}}
    print(f"Repeatability ({N_POINTS} points per detector, found again within {EPS:.0f} px):")
    print(f"  {'pair':20s} {'scale':>5s} {'harris':>7s} {'orb':>7s} {'sift':>7s} {'chance':>7s}")
    for p in pairs:
        a, b, H = grey(p["map"]), grey(p["photo"]), np.array(p["H"])
        row = {}
        for m in ("harris", "orb", "sift"):
            row[m] = round(repeatability(points(a, m), points(b, m), H, b.shape, EPS), 3)
        row["chance"] = round(chance_level(N_POINTS, b.shape), 3)
        out["repeatability"][p["name"]] = row
        out["pairs"][p["name"]] = {"scale": p["scale"], "heading_deg": p["heading_deg"], "what": p["what"]}
        print(f"  {p['name']:20s} {p['scale']:5.2f} {row['harris']:7.2f} {row['orb']:7.2f} {row['sift']:7.2f} "
              f"{row['chance']:7.2f}")

    # Hamming: ORB descriptors of the same ground point in the map patch and the photo
    p = next(q for q in pairs if q["name"] == "city_rot35")
    a, b, H = grey(p["map"]), grey(p["photo"]), np.array(p["H"])
    ka, da = detect_keypoints(a, "ORB", 2000)
    kb, db = detect_keypoints(b, "ORB", 2000)
    pa = project(np.float32([k.pt for k in ka]), H)
    pb = np.float32([k.pt for k in kb])
    same = []
    for i, q in enumerate(pa):
        d = np.hypot(*(pb - q).T)
        j = int(np.argmin(d))
        if d[j] < 1.5 and abs(ka[i].size * 1.0 - kb[j].size) < 0.5 * ka[i].size:
            same.append(hamming(da[i], db[j]))
    rng = np.random.default_rng(1)
    rnd = [hamming(da[i], db[j]) for i, j in zip(rng.integers(0, len(da), 2000), rng.integers(0, len(db), 2000))]
    out["hamming_orb"] = {"pairs_same_point": len(same), "median_same_point": float(np.median(same)),
                          "median_random": float(np.median(rnd)), "bits": int(8 * da.shape[1])}
    print(f"\nORB Hamming distance (of {8 * da.shape[1]} bits): same ground point median "
          f"{np.median(same):.0f} ({len(same)} pairs), random pairs median {np.median(rnd):.0f}")

    out["sift_per_terrain"] = keypoints_per_terrain("SIFT")
    print("\nSIFT keypoints per terrain:", out["sift_per_terrain"])
    out["matchability"] = {}
    for name in ("terrain_city.jpg", "terrain_olives.jpg", "terrain_farms.jpg", "terrain_hills.jpg",
                 "terrain_coast_water.jpg", "terrain_sea.jpg", "drone_city.jpg", "drone_city_blurry_dark.jpg"):
        out["matchability"][name] = round(float(matchability(cv2.imread(os.path.join(DATA, name)))), 3)
    print("Matchability:", out["matchability"])
    with open("results.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\n→ saved results.json — now write report.md (Step 9)")


if __name__ == "__main__":
    try:
        main()
    except NotImplementedError as e:
        print(f"measure.py needs all the TODOs of features.py: {e} is not done yet.")

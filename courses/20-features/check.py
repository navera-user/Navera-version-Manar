import os

import cv2
import numpy as np

from academy_check import Checker, load_student, need, sh

c = Checker()
DATA = "/data/academy/20-features"
# SIFT keypoints per terrain (OpenCV 4.11, these exact pictures, nfeatures=10000)
EXPECTED = {"city": 6626, "olives": 5852, "farms": 3983, "hills": 2571, "coast_water": 5, "sea": 0}


def img(name):
    return cv2.imread(os.path.join(DATA, name))


def F():
    return load_student("features.py")


@c.test("features.py runs without errors",
        hint="Run `python3 features.py` in the terminal and read the last lines of the error.")
def _():
    code, out = sh("python3 features.py", timeout=60)
    c.ok(code == 0, "the program stopped with an error:\n" + out[-600:])


@c.test("TODO 1 — detect_keypoints(img, 'ORB') gives keypoints and 32-byte descriptors",
        hint="Three steps: a grey picture, an ORB detector that keeps max_points, then detectAndCompute. "
             "Return both of its results.")
def _():
    (det,) = need(F(), "detect_keypoints")
    res = det(img("terrain_city.jpg"), "ORB")
    c.ok(isinstance(res, tuple) and len(res) == 2, f"it should return (keypoints, descriptors), got {type(res).__name__}")
    kps, des = res
    c.ok(len(kps) > 1000, f"only {len(kps)} ORB keypoints on the city — expected thousands")
    c.ok(des is not None and des.shape == (len(kps), 32) and des.dtype == np.uint8,
         f"ORB descriptors should be an array ({len(kps)}, 32) of uint8, got "
         f"{None if des is None else (des.shape, des.dtype)}")


@c.test("TODO 1 — detect_keypoints(img, 'SIFT') gives 128-number descriptors; another name → ValueError",
        hint="Use cv2.SIFT_create(nfeatures=max_points) for 'SIFT'. For any other method, "
             "`raise ValueError(...)`.")
def _():
    (det,) = need(F(), "detect_keypoints")
    kps, des = det(cv2.cvtColor(img("terrain_farms.jpg"), cv2.COLOR_BGR2GRAY), "SIFT")
    c.ok(len(kps) > 1000, f"only {len(kps)} SIFT keypoints on the farms (grey picture) — expected thousands")
    c.ok(des is not None and des.shape == (len(kps), 128), f"SIFT descriptors shape is "
         f"{None if des is None else des.shape}, expected ({len(kps)}, 128)")
    try:
        det(img("terrain_city.jpg"), "HARRIS-ROCKET")
    except ValueError:
        return
    c.ok(False, "detect_keypoints(img, 'HARRIS-ROCKET') did not raise ValueError")


@c.test("TODO 2 — count_keypoints() counts 0 on the open sea and thousands on the city",
        hint="cv2.imread(path), then len() of the keypoints returned by detect_keypoints(img, method).")
def _():
    (cnt,) = need(F(), "count_keypoints")
    sea, city = cnt(os.path.join(DATA, "terrain_sea.jpg"), "SIFT"), cnt(os.path.join(DATA, "terrain_city.jpg"), "SIFT")
    c.eq(sea, 0, "count_keypoints(sea, 'SIFT')")
    c.near(city, EXPECTED["city"], tol=EXPECTED["city"] * 0.05, what="count_keypoints(city, 'SIFT')")


@c.test("TODO 3 — keypoints_per_terrain() gives the 6 terrains with the right counts",
        hint="Read terrain.csv (in the DATA folder) with csv.DictReader. Each row gives a file name and a terrain "
             "name; the file is inside DATA. Use your count_keypoints for each one.")
def _():
    (kpt,) = need(F(), "keypoints_per_terrain")
    t = kpt("SIFT")
    c.ok(isinstance(t, dict), f"it should return a dict, got {type(t).__name__}")
    c.eq(sorted(t), sorted(EXPECTED), "the terrain names")
    for k, v in EXPECTED.items():
        c.near(t[k], v, tol=max(3, v * 0.05), what=f"keypoints of {k}")


@c.test("TODO 4 — spread() of keypoints all in one corner is 1/16; spread evenly it is 1",
        hint="Cell column = int(x / width * columns), row = int(y / height * rows) (keep them inside the grid). "
             "Count per cell, then (number of cells with >= min_per_cell) / (rows * columns).")
def _():
    (spread,) = need(F(), "spread")
    corner = [cv2.KeyPoint(float(5 + i), float(5 + i), 3) for i in range(20)]
    c.near(spread(corner, (400, 400, 3)), 1 / 16, tol=1e-6, what="spread(20 points in the top-left corner)")
    even = [cv2.KeyPoint(float(x), float(y), 3) for x in range(10, 400, 25) for y in range(10, 300, 25)]
    c.near(spread(even, (300, 400)), 1.0, tol=1e-6, what="spread(points everywhere on a 400 x 300 picture)")
    edge = [cv2.KeyPoint(399.9, 299.9, 3)] * 3            # on the very last pixel: must not crash
    c.near(spread(edge, (300, 400), grid=(2, 2)), 0.25, tol=1e-6, what="spread(3 points at the bottom-right, 2x2 grid)")
    c.near(spread(corner, (400, 400), min_per_cell=30), 0.0, tol=1e-6, what="spread(20 points, min_per_cell=30)")


@c.test("TODO 5 — matchability(): city near 1, open sea 0, always between 0 and 1",
        hint="Two factors multiplied: how many ORB keypoints (max_points=500) compared with `enough`, capped at 1, "
             "and how spread they are (your TODO 4).")
def _():
    (m,) = need(F(), "matchability")
    for name in ("terrain_city.jpg", "terrain_sea.jpg", "terrain_coast_water.jpg", "drone_city.jpg"):
        s = m(img(name))
        c.ok(isinstance(s, (int, float, np.floating)) and 0.0 <= float(s) <= 1.0, f"matchability({name}) = {s!r}")
    c.ok(m(img("terrain_city.jpg")) > 0.8, f"matchability(city) = {m(img('terrain_city.jpg')):.2f}, expected > 0.8")
    c.ok(m(img("terrain_sea.jpg")) < 0.01, f"matchability(sea) = {m(img('terrain_sea.jpg')):.2f}, expected 0")


@c.test("TODO 5 — matchability() ranks: textured land > coast water; clear drone photo > blurry dark one",
        hint="Both parts matter: few keypoints (water) must give a low score, and a dark blurry photo has almost none.")
def _():
    (m,) = need(F(), "matchability")
    land = min(m(img(f"terrain_{k}.jpg")) for k in ("city", "olives", "farms", "hills"))
    water = m(img("terrain_coast_water.jpg"))
    c.ok(land > 0.8 and water < 0.1, f"lowest land score {land:.2f} (expected > 0.8), coast water {water:.2f} (expected < 0.1)")
    clear, bad = m(img("drone_city.jpg")), m(img("drone_city_blurry_dark.jpg"))
    c.ok(clear > 0.8 and bad < 0.1, f"drone_city {clear:.2f} (expected > 0.8), blurry dark {bad:.2f} (expected < 0.1)")


@c.test("TODO 5 — half city, half sea scores about one half (the spread counts)",
        hint="Plenty of keypoints but only on one half: min(1, n/enough) is 1, the spread must bring it down to ~0.5.")
def _():
    (m,) = need(F(), "matchability")
    a = img("terrain_city.jpg").copy()
    a[:, 256:] = img("terrain_sea.jpg")[:, 256:]
    s = m(a)
    c.ok(0.3 <= s <= 0.65, f"matchability(half city / half sea) = {s:.2f}, expected about 0.5")


@c.test("keypoints_city.png was drawn by the demo",
        hint="Run `python3 features.py` once TODO 1 works: it saves keypoints_city.png.")
def _():
    c.file_exists("keypoints_city.png")
    p = cv2.imread("keypoints_city.png")
    c.ok(p is not None and p.shape == (512, 512, 3), "keypoints_city.png is not a 512 x 512 picture")
    c.ok(np.abs(p.astype(int) - img("terrain_city.jpg").astype(int)).mean() > 1.0, "no keypoints are drawn on it")


@c.test("TODO 6 — ORB_BYTES and SIFT_LENGTH are what you measured",
        hint="Run `python3 peek.py` and read the descriptor array shapes: (number of keypoints, length).")
def _():
    o, s = need(F(), "ORB_BYTES", "SIFT_LENGTH")
    c.eq(o, 32, "ORB_BYTES")
    c.eq(s, 128, "SIFT_LENGTH")


c.run()

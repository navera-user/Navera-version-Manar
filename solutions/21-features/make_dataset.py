#!/usr/bin/env python3
"""Mission 21 dataset (teacher only — never copy this file into datasets/: students read everything there).

    PYTHONPATH= python3 solutions/21-features/make_dataset.py [NAVERA_DAY_FRAMES_DIR]      # ~40 s on the Jetson

NAVERA_DAY_FRAMES_DIR: the folder of NAVERA's recorded day frames (staff data, frame_0013.jpeg and
frame_0018.jpeg are copied as DATA). Without it, existing real_*.jpg files are kept as they are.

Writes datasets/21-features/ (students: /data/academy/21-features/):
  terrain_<name>.png   six 512 × 512 "map patches", north up, at the zoom-17 resolution of the place
                       (≈ 0.97 m/px, ≈ 495 m of ground): aerial-style renders of OpenStreetMap data
                       (render_view, style 'pseudo', no effects): city, olives, fields, saltpans, coast, sea
  terrain.csv          file, terrain, lat, lon, m_per_px (no counts, no ranking: the scout predicts them)
  pair_<name>.jpg      640 × 480 "drone photos" of a map patch's centre: a chosen heading and resolution,
  pairs.json           with mild camera effects (noise, blur, brightness, JPEG) and the EXACT 3 × 3 H that maps
                       a pixel of terrain_<map>.png to the photo (pixel-centre convention, below)
  drone_city.jpg       a clear 640 × 480 drone view of the city (heading 20°, 0.6 m/px)
  drone_city_dark.jpg  the same view, blurred and very dark (dusk, motion)
  house.png            a 200 × 160 synthetic top view of one house (roof, courtyard, wall, water tank, road)
                       on flat ground: corners you can judge by eye
  real_coast.jpg       real aerial frames from NAVERA's day test data (1536 × 730), copied as DATA. Their place
  real_town.jpg        and the imagery's source are not established: never name a place (owner decision §7.2)
  patches_train.npz    a, b: uint8 (12 288, 32, 32) — pairs of patches showing the SAME ground point: a from a
                       map-like nadir view, b from a "drone photo" of the place (heading error ±20°, scale 0.8–1.25,
                       tilt ±8°, blur, gamma, brightness gradient, noise, JPEG); 48 places
  patches_val.npz      a, b: uint8 (2 048, 48, 48), 8 other places (48 × 48 so OpenCV's ORB/SIFT can describe them
                       too; the network uses the central 32 × 32)
  README.md            neutral description + © OpenStreetMap contributors
and courses/21-features/hidden/patches_test.npz (check only): 1 024 pairs, 48 × 48, from 4 more places.
Places sit on a 1.4 km grid over the land of the map (a view covers ≈ 0.5 km), each assigned to ONE set: no
ground is shared between train, validation and test. Patch centres: half SIFT keypoints, half random textured
points (std > 6 grey levels), ≥ 6 px apart. --skip-patches keeps existing patch files (they take ≈ 10 min).

How the truth is made exact. For each terrain ONE fine north-up orthophoto is rendered (render_view, pseudo, no
effects) at a quarter of the zoom-17 pixel size; the map patch AND every photo of that terrain are then resampled
from it with cv2.warpAffine (Gaussian pre-filter against aliasing), each through a known "ground metres → pixel"
matrix. So H = photo matrix · inverse(map matrix) is exact up to interpolation (checked below with SIFT + RANSAC:
residual medians ≈ 0.1–0.3 px). (Rendering each picture separately with render_view left a ≈ 0.2 map-pixel offset
inside render_view, i.e. ≈ 1 px in a 4× closer photo.) Pixel-centre convention: a picture's centre point is
((w − 1)/2, (h − 1)/2); the ortho is rendered one pixel larger and its first row and column dropped (mission 08's
trick) so that (lat, lon) sits exactly there.
Deterministic (fixed seeds).
"""
import csv
import json
import math
import os
import shutil
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "datasets", "21-features")
sys.path.insert(0, os.path.join(REPO, "datasets", "_map"))
from render_view import render_view  # noqa: E402

ATTRIBUTION = "© OpenStreetMap contributors (ODbL), https://www.openstreetmap.org/copyright"
MAP_PX = 512
PHOTO_W, PHOTO_H = 640, 480
TERRAINS = [   # name, lat, lon
    ("city", 35.8277, 10.6388),
    ("olives", 35.7409, 10.7377),
    ("fields", 35.7373, 10.7235),
    ("saltpans", 35.7607, 10.7176),
    ("coast", 35.8563, 10.6191),
    ("sea", 35.8300, 10.7000),
]
PAIRS = [      # name, map terrain, heading of the photo's top (deg, clockwise from north), zoom = map m/px ÷ photo m/px
    ("city_rot35", "city", 35.0, 1.0),
    ("city_zoom2", "city", 0.0, 2.0),
    ("city_zoom4", "city", 0.0, 4.0),
    ("city_rot35_zoom", "city", 35.0, 1.6),
    ("olives_rot35_zoom", "olives", 35.0, 1.6),
    ("fields_rot35_zoom", "fields", 35.0, 1.6),
]
PHOTO_FX = {"blur": 0.6, "noise": 3.0, "brightness": 0.95, "gamma": 1.05}
FINE = 4                       # the orthophoto has FINE × the map's resolution
ORTHO_PX = 3200                # its side: covers the 35° turned 1× photo (diagonal 800 map px) with margin


def zoom17_m_per_px(lat):
    return 40075016.686 * math.cos(math.radians(lat)) / 2 ** 17 / 256


def centred(lat, lon, heading, w, h, gsd, **kw):
    """render_view with (lat, lon) on the course centre point ((w − 1)/2, (h − 1)/2) (see the module doc)."""
    img = render_view(lat, lon, heading, ground_size_m=(w + 1) * gsd, out_px=(w + 1, h + 1), style="pseudo", **kw)
    return img[1:, 1:]


def pixel_from_enu(heading_deg, gsd, w, h):
    """3 × 3 matrix: ground (east, north) metres from the centre point → pixel (x, y) of a nadir view whose top
    looks towards heading_deg."""
    p = math.radians(heading_deg)
    s, c = math.sin(p), math.cos(p)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    return np.array([[c / gsd, -s / gsd, cx],
                     [-s / gsd, -c / gsd, cy],
                     [0.0, 0.0, 1.0]])


def house():
    """A top view of one house on flat ground, 200 × 160 px: an L-shaped roof with a courtyard, a garden wall,
    a round water tank and a road edge, mild noise. Corners where a roof corner is, straight edges elsewhere."""
    img = np.full((160, 200), 150, np.uint8)                          # flat sandy ground
    cv2.rectangle(img, (0, 128), (199, 159), 70, -1)                  # a road along the bottom (one long edge)
    pts = np.array([[40, 30], [130, 30], [130, 70], [90, 70], [90, 105], [40, 105]], np.int32)
    cv2.fillPoly(img, [pts], 225)                                     # L-shaped white roof
    cv2.rectangle(img, (55, 45), (75, 60), 110, -1)                   # a small dark courtyard in the roof
    cv2.line(img, (145, 20), (145, 110), 60, 3)                       # a garden wall (a thin line: two edges)
    cv2.circle(img, (170, 60), 12, 235, -1)                           # a round water tank (no corner)
    rng = np.random.default_rng(21)
    img = np.clip(img.astype(np.float64) + rng.normal(0, 2.0, img.shape), 0, 255)
    return cv2.GaussianBlur(img, (0, 0), 0.8).round().astype(np.uint8)


def ortho(lat, lon, mpp, side):
    """The fine north-up orthophoto (side × side px, mpp / FINE m/px) and its ground → pixel matrix."""
    img = centred(lat, lon, 0.0, side, side, mpp / FINE, seed=0)
    return img, pixel_from_enu(0.0, mpp / FINE, side, side)


def resample(src, P_src, P_dst, w, h):
    """The picture whose ground → pixel matrix is P_dst, read from src (matrix P_src): one warpAffine, after a
    Gaussian pre-filter that removes the detail the coarser result cannot hold (no aliasing)."""
    M = P_src @ np.linalg.inv(P_dst)                                  # destination pixel → source pixel
    f = math.sqrt(abs(np.linalg.det(M[:2, :2])))                      # source pixels per destination pixel
    if f > 1.0:
        src = cv2.GaussianBlur(src, (0, 0), 0.45 * math.sqrt(f * f - 1.0))
    return cv2.warpAffine(src, M[:2], (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REFLECT)


def camera_effects(img, fx, seed, jpeg=92):
    """Mild camera effects: blur, brightness/gamma, sensor noise, then a JPEG round trip."""
    rng = np.random.default_rng(seed)
    f = img.astype(np.float64)
    if fx.get("blur"):
        f = cv2.GaussianBlur(f, (0, 0), fx["blur"])
    if fx.get("motion_blur"):
        k = np.zeros((fx["motion_blur"], fx["motion_blur"]))
        k[fx["motion_blur"] // 2, :] = 1.0 / fx["motion_blur"]
        f = cv2.filter2D(f, -1, k)
    f = 255.0 * (np.clip(f, 0, 255) / 255.0) ** fx.get("gamma", 1.0) * fx.get("brightness", 1.0)
    f = f + rng.normal(0, fx.get("noise", 0.0), f.shape)
    out = np.clip(np.rint(f), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def tilt_h(pitch_deg, roll_deg, w, h, f):
    """Homography of a camera turned by (pitch, roll) about its centre, focal f px (mission 18: K·R·K⁻¹)."""
    K = np.array([[f, 0, (w - 1) / 2.0], [0, f, (h - 1) / 2.0], [0, 0, 1.0]])
    p, r = math.radians(pitch_deg), math.radians(roll_deg)
    Rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    Ry = np.array([[math.cos(r), 0, math.sin(r)], [0, 1, 0], [-math.sin(r), 0, math.cos(r)]])
    return K @ Rx @ Ry @ np.linalg.inv(K)


def hard_effects(img, rng):
    """A drone camera far from the map: blur, gamma, gain, a brightness gradient, lower contrast, noise, JPEG."""
    f = cv2.GaussianBlur(img.astype(np.float64), (0, 0), rng.uniform(0.3, 2.0))
    h, w = f.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w] / max(h, w)
    ang = rng.uniform(0, 2 * np.pi)
    grad = 1 + rng.uniform(0, 0.5) * ((xx * np.cos(ang) + yy * np.sin(ang)) - 0.5)
    f = 255 * (np.clip(f, 0, 255) / 255) ** rng.uniform(0.6, 1.6) * rng.uniform(0.5, 1.2) * grad[..., None]
    f = (f - f.mean()) * rng.uniform(0.6, 1.0) + f.mean()
    f = f + rng.normal(0, rng.uniform(3, 10), f.shape)
    out = np.clip(np.rint(f), 0, 255).astype(np.uint8)
    _, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(35, 90))])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


PATCH = 48
VIEW = 512


def place_patches(lat, lon, rng, n_max=256):
    """Pairs of 48 × 48 patches (map view, drone view) of the same ground points around (lat, lon), or None."""
    mpp = zoom17_m_per_px(lat)
    side = 1700
    o, P_o = (centred(lat, lon, 0.0, side, side, mpp / 2, seed=0), pixel_from_enu(0.0, mpp / 2, side, side))
    P_a = pixel_from_enu(0.0, mpp, VIEW, VIEW)
    a = resample(o, P_o, P_a, VIEW, VIEW)
    P_b = pixel_from_enu(rng.uniform(-20, 20), mpp * rng.uniform(0.8, 1.25), VIEW, VIEW)
    T = tilt_h(rng.uniform(-8, 8), rng.uniform(-8, 8), VIEW, VIEW, VIEW / 2 / math.tan(math.radians(30)))
    b = hard_effects(cv2.warpPerspective(resample(o, P_o, P_b, VIEW, VIEW), T, (VIEW, VIEW),
                                         flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT), rng)
    H = T @ P_b @ np.linalg.inv(P_a)
    ga, gb = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    pts = np.float32([k.pt for k in cv2.SIFT_create(n_max).detect(ga, None)]).reshape(-1, 2)
    pts = np.vstack([pts, rng.uniform(PATCH / 2, VIEW - PATCH / 2, (3 * max(len(pts), 64), 2)).astype(np.float32)])
    q = np.column_stack([pts, np.ones(len(pts))]) @ H.T
    q = q[:, :2] / q[:, 2:]
    m = PATCH // 2
    ok = (pts.min(1) >= m) & (pts.max(1) < VIEW - m) & (q.min(1) >= m) & (q.max(1) < VIEW - m)
    pts, q = pts[ok], q[ok]
    A = np.stack([cv2.getRectSubPix(ga, (PATCH, PATCH), (float(x), float(y))) for x, y in pts])
    good = A[:, 8:40, 8:40].std(axis=(1, 2)) > 6                       # a flat patch has nothing to describe
    pts, q, A = pts[good], q[good], A[good]
    keep = []
    for i, p in enumerate(pts):
        if all(np.hypot(*(p - pts[j])) >= 6 for j in keep):
            keep.append(i)
        if len(keep) >= n_max:
            break
    if len(keep) < n_max:                                             # sea, empty fields: not a full place
        return None
    B = np.stack([cv2.getRectSubPix(gb, (PATCH, PATCH), (float(x), float(y))) for x, y in q[keep]])
    return A[keep], B


def make_patches():
    rng = np.random.default_rng(2021)
    grid = [(la, lo) for la in np.arange(35.715, 35.955, 0.0126) for lo in np.arange(10.48, 10.74, 0.0155)]
    order = rng.permutation(len(grid))
    want = {"train": 48, "val": 8, "test": 4}
    got = {k: [] for k in want}
    for i in order:
        need = [k for k in ("test", "val", "train") if len(got[k]) < want[k]]
        if not need:
            break
        lat, lon = grid[i]
        r = place_patches(float(lat), float(lon), rng)
        if r is None:
            continue
        got[need[0]].append(r)
        print(f"patches {need[0]} {len(got[need[0]])}/{want[need[0]]} at {lat:.4f}, {lon:.4f}", flush=True)
    cat = {k: (np.concatenate([x[0] for x in v]), np.concatenate([x[1] for x in v])) for k, v in got.items()}
    a, b = cat["train"]
    np.savez_compressed(os.path.join(OUT, "patches_train.npz"), a=a[:, 8:40, 8:40], b=b[:, 8:40, 8:40])
    np.savez_compressed(os.path.join(OUT, "patches_val.npz"), a=cat["val"][0], b=cat["val"][1])
    hid = os.path.join(REPO, "courses", "21-features", "hidden")
    os.makedirs(hid, exist_ok=True)
    np.savez_compressed(os.path.join(hid, "patches_test.npz"), a=cat["test"][0], b=cat["test"][1])


def check_h(a, b, H):
    """Median and 90th-percentile residual (px) of SIFT+RANSAC inliers under the stated H."""
    s = cv2.SIFT_create(4000)
    ka, da = s.detectAndCompute(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), None)
    kb, db = s.detectAndCompute(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), None)
    m = [p for p, q in cv2.BFMatcher().knnMatch(da, db, k=2) if p.distance < 0.75 * q.distance]
    pa = np.float32([ka[x.queryIdx].pt for x in m])
    pb = np.float32([kb[x.trainIdx].pt for x in m])
    _, inl = cv2.findHomography(pa, pb, cv2.RANSAC, 3.0)
    pa, pb = pa[inl.ravel() > 0], pb[inl.ravel() > 0]
    hom = np.column_stack([pa, np.ones(len(pa))]) @ H.T
    r = np.hypot(*(hom[:, :2] / hom[:, 2:3] - pb).T)
    return len(pa), float(np.median(r)), float(np.percentile(r, 90))


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    skip_patches = "--skip-patches" in sys.argv
    frames = args[0] if args else None
    os.makedirs(OUT, exist_ok=True)
    keep = ("README.md", "real_coast.jpg", "real_town.jpg") + (("patches_train.npz", "patches_val.npz")
                                                               if skip_patches else ())
    for old in os.listdir(OUT):                                       # the old (satellite-map) dataset goes
        if old not in keep:
            os.remove(os.path.join(OUT, old))
    where = {}
    rows = []
    for name, lat, lon in TERRAINS:
        mpp = zoom17_m_per_px(lat)
        side = ORTHO_PX if any(src == name for _, src, _, _ in PAIRS) else MAP_PX * FINE
        o, P_o = ortho(lat, lon, mpp, side)
        P_map = pixel_from_enu(0.0, mpp, MAP_PX, MAP_PX)
        img = resample(o, P_o, P_map, MAP_PX, MAP_PX)
        cv2.imwrite(os.path.join(OUT, f"terrain_{name}.png"), img)
        where[name] = (lat, lon, mpp, img, o, P_o, P_map)
        rows.append({"file": f"terrain_{name}.png", "terrain": name, "lat": lat, "lon": lon, "m_per_px": round(mpp, 4)})
        print(f"terrain {name} done")
    with open(os.path.join(OUT, "terrain.csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, ["file", "terrain", "lat", "lon", "m_per_px"])
        wr.writeheader()
        wr.writerows(rows)

    pairs = []
    for i, (name, src, heading, zoom) in enumerate(PAIRS):
        lat, lon, mpp, a, o, P_o, P_map = where[src]
        gsd = mpp / zoom
        P_b = pixel_from_enu(heading, gsd, PHOTO_W, PHOTO_H)
        b = camera_effects(resample(o, P_o, P_b, PHOTO_W, PHOTO_H), PHOTO_FX, 100 + i)
        cv2.imwrite(os.path.join(OUT, f"pair_{name}.jpg"), b, [cv2.IMWRITE_JPEG_QUALITY, 95])
        b = cv2.imread(os.path.join(OUT, f"pair_{name}.jpg"))
        H = P_b @ np.linalg.inv(P_map)
        H /= H[2, 2]
        n, med, p90 = check_h(a, b, H)
        print(f"{name:20s} H check: {n} SIFT inliers, residual median {med:.2f} px, p90 {p90:.2f} px")
        pairs.append({"name": name, "map": f"terrain_{src}.png", "photo": f"pair_{name}.jpg",
                      "heading_deg": heading, "zoom": zoom, "photo_m_per_px": round(gsd, 4),
                      "H": [[round(v, 9) for v in row] for row in H.tolist()]})
    with open(os.path.join(OUT, "pairs.json"), "w") as fh:
        json.dump(pairs, fh, indent=1)

    lat, lon, mpp, _, o, P_o, _ = where["city"]
    view = resample(o, P_o, pixel_from_enu(20.0, 0.6, PHOTO_W, PHOTO_H), PHOTO_W, PHOTO_H)
    cv2.imwrite(os.path.join(OUT, "drone_city.jpg"), camera_effects(view, PHOTO_FX, 7), [cv2.IMWRITE_JPEG_QUALITY, 95])
    dark = camera_effects(view, {"blur": 2.0, "motion_blur": 9, "noise": 2.0, "brightness": 0.22, "gamma": 1.6}, 8, 80)
    cv2.imwrite(os.path.join(OUT, "drone_city_dark.jpg"), dark, [cv2.IMWRITE_JPEG_QUALITY, 95])
    cv2.imwrite(os.path.join(OUT, "house.png"), house())

    if frames:
        for src, dst in (("frame_0013.jpeg", "real_coast.jpg"), ("frame_0018.jpeg", "real_town.jpg")):
            shutil.copyfile(os.path.join(os.path.expanduser(frames), src), os.path.join(OUT, dst))
    for dst in ("real_coast.jpg", "real_town.jpg"):
        if not os.path.exists(os.path.join(OUT, dst)):
            sys.exit(f"{dst} is missing: give the folder of NAVERA's day frames as the first argument")
    if not skip_patches:
        make_patches()
    with open(os.path.join(OUT, "README.md"), "w") as fh:
        fh.write(README)
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print("written:", sorted(os.listdir(OUT)), f"{total / 1e6:.1f} MB")


README = """# Mission 21 data (read only)

| File | What |
|---|---|
| `terrain_*.png` | six 512 × 512 px map patches of the Sousse area (Tunisia), north up, about 0.97 m per pixel (about 500 m of ground): an aerial-style drawing rendered from OpenStreetMap data |
| `terrain.csv` | one line per patch: file, terrain, lat, lon, m_per_px |
| `pair_*.jpg` | 640 × 480 px simulated drone photos of the centre of a map patch, turned and/or closer, with camera effects |
| `pairs.json` | for each photo: its map patch, the photo's heading and zoom, and the exact 3 × 3 matrix `H` that maps a pixel (x, y) of the map patch to the photo |
| `drone_city.jpg`, `drone_city_dark.jpg` | a simulated drone view of the city, clear and at dusk with motion blur |
| `house.png` | a synthetic top view of one house on flat ground |
| `real_coast.jpg`, `real_town.jpg` | two real aerial frames from NAVERA's day-camera test data, 1536 × 730 px |
| `patches_train.npz` | arrays `a`, `b`: 12 288 pairs of 32 × 32 grey patches (uint8); `a[i]` and `b[i]` show the same ground point, `a` in a map-like view, `b` in a simulated drone photo (turned, scaled, tilted, blurred, darker or brighter, noisy) |
| `patches_val.npz` | arrays `a`, `b`: 2 048 more pairs, 48 × 48, from other places (no ground shared with the training pairs) |

Pixels: (x, y) = (column, row), the centre of the top-left pixel is (0, 0); the centre point of a picture w px wide
and h px high is ((w − 1)/2, (h − 1)/2).

Map data © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright.
The renders are a produced work of that data.
"""

if __name__ == "__main__":
    main()

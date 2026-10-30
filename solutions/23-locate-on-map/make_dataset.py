#!/usr/bin/env python3
"""make_dataset.py — mission 23's data (teacher only; run on the host, ≈ 6 min with the GPU free).

    python3 solutions/23-locate-on-map/make_dataset.py              # everything
    python3 solutions/23-locate-on-map/make_dataset.py --skip-index # keep dino_index.npz (photos only)

Writes datasets/23-locate-on-map/ (students see it read-only at /data/academy/23-locate-on-map/):
  photos/p01.jpg … p80.jpg  640 × 480 synthetic downward photos rendered from the OpenStreetMap map of Sousse
                            (datasets/_map/render_view.py, style "map" = the tiles' own style) with camera effects:
                            residual tilt σ 0.5° (what is left after straightening with the IMU), heading error σ 2°,
                            height error ±5 %, blur, noise, gamma, colour, light gradient, vignette, JPEG, sometimes a
                            cloud or a dark blob at the border.
  photos.csv                id, alt_m (the height the drone believes), heading_deg (the IMU's heading of the photo's
                            top), hfov_deg (60), terrain (textured / sparse / sea, from the map around the point),
                            prior_lat, prior_lon, prior_sigma_m (200 m: the truth moved by a 2-D Gaussian draw)
  truth.csv                 id, lat, lon — the true position of each photo's centre (the lab evaluates with it)
  dino_index.npz            the DINOv2 ViT-S/14 embeddings of the 2 208 zoom-17 tiles of the test area: xy (M, 2)
                            int32, emb (M, 384) float16, z — made with the reference preprocess (the student's must
                            give the same numbers)
  README.md                 neutral description + attribution
and courses/23-locate-on-map/hidden/ (check only, never mounted):
  h01.jpg … h40.jpg, queries.json (truth, meta, priors at σ 100/400 m, DINOv2 top-5 candidates at σ 400 m, the
  candidate tiles of each σ-400 circle), views64.npz (the 64 × 64 north-up views TileNet's check embeds).

Truth: render_view puts (lat, lon) at OpenCV pixel (w/2, h/2); each photo is rendered 641 × 481 with the same metres
per pixel and its first row and column are dropped, so the true point is the course's centre ((w − 1)/2, (h − 1)/2)
(datasets/_map/README.md). Points: stratified by terrain (sea / sparse / textured, measured on the map) at least
400 m apart, 1.1 km inside the test area. Deterministic (fixed seeds), except DINOv2 on the GPU (float16 storage).
"""
import argparse
import csv
import json
import math
import os
import shutil
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "datasets", "23-locate-on-map")
HID = os.path.join(REPO, "courses", "23-locate-on-map", "hidden")
MAP = os.path.expanduser("~/academy-data/osm_sousse.mbtiles")
os.environ.setdefault("NAVERA_LITE_MAP", MAP)
os.environ.setdefault("NAVERA_LITE_MODELS", os.path.expanduser("~/academy-data/models"))
sys.path.insert(0, os.path.join(REPO, "solutions", "_navera_lite"))
sys.path.insert(0, os.path.join(REPO, "datasets", "_map"))
from navera_lite import geo, retrieval as R, tiles  # noqa: E402
from render_view import render_view  # noqa: E402

ATTRIBUTION = "© OpenStreetMap contributors (ODbL), https://www.openstreetmap.org/copyright"
W, H, HFOV = 640, 480, 60.0
N_LAB = {"textured": 52, "sparse": 18, "sea": 10}
N_HID = {"textured": 28, "sparse": 8, "sea": 4}
SIGMA_LAB = 200.0
MARGIN_LAT, MARGIN_LON = 0.010, 0.012          # ≈ 1.1 km inside TEST_AREA


def effects(rng):
    u = rng.uniform
    e = dict(pitch_deg=float(rng.normal(0, 0.5)), roll_deg=float(rng.normal(0, 0.5)),
             yaw_err_deg=float(rng.normal(0, 2.0)), scale_err=float(u(-0.05, 0.05)), blur=float(u(0.3, 1.2)),
             noise=float(u(1, 5)), gamma=float(u(0.85, 1.2)), color=0.05, brightness=float(u(0.8, 1.1)),
             illum=float(u(0, 0.2)), vignette=float(u(0, 0.25)), jpeg=int(u(70, 93)))
    if u() < 0.25:
        e["clouds"] = float(u(0.05, 0.25))
    if u() < 0.15:
        e["occlusion"] = 1
    return e


def terrain(lat, lon):
    """sea / sparse / textured, from the 248 m of map around the point (shrunk 4 times)."""
    p = cv2.resize(tiles.map_patch(lat, lon, 17, 256, 256, path=MAP), (64, 64), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY)
    b, _, r = (float(p[..., i].mean()) for i in range(3))
    if g.std() < 3.0 and b > r + 10:
        return "sea"
    return "textured" if g.std() >= 7.0 else "sparse"


def draw_points(rng, want, avoid, min_d=400.0):
    a = R.TEST_AREA
    got = {k: [] for k in want}
    tries = 0
    while any(len(got[k]) < want[k] for k in want):
        tries += 1
        lat = rng.uniform(a[0] + MARGIN_LAT, a[1] - MARGIN_LAT)
        lon = rng.uniform(a[2] + MARGIN_LON, a[3] - MARGIN_LON)
        k = terrain(lat, lon)
        if len(got[k]) >= want[k]:
            continue
        if any(geo.haversine_m(lat, lon, p[0], p[1]) < min_d for p in avoid + sum(got.values(), [])):
            continue
        got[k].append((lat, lon, k))
    print(f"  {sum(want.values())} points in {tries} draws")
    pts = sum(got.values(), [])
    order = rng.permutation(len(pts))
    return [pts[i] for i in order]


def photo(lat, lon, alt, heading, seed, rng):
    gsd = 2 * alt * math.tan(math.radians(HFOV / 2)) / W
    img = render_view(lat, lon, heading_deg=heading, ground_size_m=(W + 1) * gsd, out_px=(W + 1, H + 1), seed=seed,
                      style="map", effects=effects(rng))
    return img[1:, 1:]


def prior(rng, lat, lon, sigma):
    """The truth moved by a 2-D Gaussian draw of σ sigma on each axis (east, north)."""
    e, n = rng.normal(0, sigma, 2)
    return geo.offset(lat, lon, float(e), float(n))


def view_of(img, meta):
    gm = tiles.m_per_px(35.82, 17)
    return R.north_up(img, meta["heading_deg"], 2 * meta["alt_m"] * math.tan(math.radians(HFOV / 2)) / W, gm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-index", action="store_true")
    args = ap.parse_args()
    import torch
    torch.set_num_threads(2)
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    for old in ("images", "photos", "overview.jpg", "truth.csv", "make_dataset.py", "photos.csv"):
        p = os.path.join(OUT, old)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    os.makedirs(os.path.join(OUT, "photos"))
    if os.path.isdir(HID):
        shutil.rmtree(HID)
    os.makedirs(HID)

    rng = np.random.default_rng(2323)
    print("points")
    lab = draw_points(rng, N_LAB, [])
    hid = draw_points(rng, N_HID, [(p[0], p[1]) for p in lab])

    print("photos")
    rows, truth = [], []
    for i, (lat, lon, k) in enumerate(lab, 1):
        alt, hd = float(rng.uniform(300, 420)), float(rng.uniform(0, 360))
        img = photo(lat, lon, alt, hd, 1000 + i, rng)
        cv2.imwrite(os.path.join(OUT, "photos", f"p{i:02d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        plat, plon = prior(rng, lat, lon, SIGMA_LAB)
        rows.append({"id": f"p{i:02d}", "alt_m": round(alt, 1), "heading_deg": round(hd, 1), "hfov_deg": HFOV,
                     "terrain": k, "prior_lat": round(plat, 6), "prior_lon": round(plon, 6),
                     "prior_sigma_m": SIGMA_LAB})
        truth.append({"id": f"p{i:02d}", "lat": round(lat, 6), "lon": round(lon, 6)})
    for name, data in (("photos.csv", rows), ("truth.csv", truth)):
        with open(os.path.join(OUT, name), "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(data[0]))
            wr.writeheader()
            wr.writerows(data)

    queries, views = [], []
    for i, (lat, lon, k) in enumerate(hid, 1):
        alt, hd = float(rng.uniform(300, 420)), float(rng.uniform(0, 360))
        img = photo(lat, lon, alt, hd, 5000 + i, rng)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        with open(os.path.join(HID, f"h{i:02d}.jpg"), "wb") as f:
            f.write(buf.tobytes())
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)                  # what the check will read
        q = {"id": f"h{i:02d}", "lat": round(lat, 6), "lon": round(lon, 6), "alt_m": round(alt, 1),
             "heading_deg": round(hd, 1), "hfov_deg": HFOV, "terrain": k, "priors": {}}
        for s in (40.0, 100.0, 400.0):
            q["priors"][str(int(s))] = [round(v, 6) for v in prior(rng, lat, lon, s)]
        queries.append(q)
        views.append(view_of(img, {"alt_m": round(alt, 1), "heading_deg": round(hd, 1)}))
    views = np.stack(views)

    print("DINOv2 index", f"{time.time() - t0:.0f} s")
    from academy_gpu_shim import torch_device
    xy = R.area_tiles(R.TEST_AREA)
    idx_path = os.path.join(OUT, "dino_index.npz")
    with torch_device() as dev:
        model = R.load_dino(dev)
        if not args.skip_index or not os.path.exists(idx_path):
            db = tiles.open_map(MAP)
            emb = []
            for s in range(0, len(xy), 128):
                imgs = np.stack([tiles.decode_tile(tiles.read_tile(db, 17, x, y)) for x, y in xy[s:s + 128]])
                emb.append(R.embed_dino(model, imgs, dev))
            np.savez_compressed(idx_path, xy=np.array(xy, np.int32), emb=np.concatenate(emb).astype(np.float16),
                                z=np.int32(17))
        index = R.TileIndex.load(idx_path)
        qe = R.embed_dino(model, views, dev)
    for q, e in zip(queries, qe):
        plat, plon = q["priors"]["400"]
        q["dino400"] = [list(c) for c in index.search(e, plat, plon, 1200.0, 5)]
        q["cand400"] = [[int(index.xy[r][0]), int(index.xy[r][1])] for r in index.candidates(plat, plon, 1200.0)]
    small = np.stack([cv2.resize(v, (64, 64), interpolation=cv2.INTER_AREA) for v in views])
    np.savez_compressed(os.path.join(HID, "views64.npz"), views=small)
    with open(os.path.join(HID, "queries.json"), "w") as f:
        json.dump(queries, f, indent=0)

    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write(f"""# Mission 23 — locate a photo on the map

Synthetic downward photos (640 × 480, horizontal field of view 60°) rendered from the course's OpenStreetMap map of
Sousse, Tunisia (NAVERA's test area), with camera effects; their metadata and a prior position for each; the true
positions; and the DINOv2 ViT-S/14 embeddings of the zoom-17 map tiles of the test area
(lat {R.TEST_AREA[0]}–{R.TEST_AREA[1]}, lon {R.TEST_AREA[2]}–{R.TEST_AREA[3]}).

| File | What |
|---|---|
| `photos/pNN.jpg` | the photos |
| `photos.csv` | id, alt_m, heading_deg, hfov_deg, terrain, prior_lat, prior_lon, prior_sigma_m |
| `truth.csv` | id, lat, lon of each photo's centre |
| `dino_index.npz` | xy (tile numbers), emb (unit rows, float16), z |

Map data {ATTRIBUTION}. DINOv2: Meta AI, Apache-2.0 (/data/models/dinov2).
""")
    mb = sum(os.path.getsize(os.path.join(dp, fn)) for dp, _, fns in os.walk(OUT) for fn in fns) / 1e6
    hb = sum(os.path.getsize(os.path.join(HID, fn)) for fn in os.listdir(HID)) / 1e6
    print(f"done in {time.time() - t0:.0f} s: datasets {mb:.1f} MB, hidden {hb:.1f} MB")


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(REPO, "courses", "_lib"))
    import academy_gpu as academy_gpu_shim  # noqa: E402
    sys.modules["academy_gpu_shim"] = academy_gpu_shim
    main()

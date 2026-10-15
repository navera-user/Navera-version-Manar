#!/usr/bin/env python3
"""Mission 25 dataset (teacher only — never copy this file into datasets/: students read everything there).

    PYTHONPATH= python3 solutions/25-thermal-night/make_dataset.py [--workers 3] [--replay DIR]
    (≈ 25 min on a quiet Jetson with 3 workers: ≈ 520 scenes, two renders each)

--replay DIR: NAVERA's replay folder that holds `thermal/` and `day/` (staff data, in the camera package's data
folder of the NAVERA data disk). Its 30 + 30 frames are copied as DATA (downscaled). Without it, existing replay/
files are kept.

Writes datasets/25-thermal-night/ (students: /data/academy/25-thermal-night/):
  scenes_train.npz  ref, night: uint8 (N, 160, 160); lat, lon: the scenes' centres; m_per_px
  scenes_val.npz    ref, night, day, crossover (+ the same keys); other places (no ground shared with train/test)
  scenes_coast.npz  ref, night: coastal scenes, half or more of them sea (a failure case, never trained on)
  flight/           a simulated night flight: frame_01.png … (640 × 512 grey thermal-like frames), frames.csv
                    (t_s, prior_lat, prior_lon, alt_m, heading_deg, true_lat, true_lon), ref_area.png (the day
                    reference of the flight's area, north-up, 7.75 m/px) + ref_area.json (its corner and m/px)
  night_fixes.csv   a night matcher's output on another flight (t_s, lat, lon, score) for the motion gate
  replay/           NAVERA's replay frames, copied as data: night_NN.jpg, day_NN.jpg (downscaled, 768 px wide),
                    night_labels.csv, day_labels.csv (the labels the replay set carries)
  README.md         neutral description + © OpenStreetMap contributors
and courses/25-thermal-night/hidden/test_pairs.npz (check only): 512 night pairs from test places, with offsets,
and courses/25-thermal-night/assets/look.jpg (lesson figure).

What a scene is. A square of ground ≈ 1.24 km wide (160 px at 8 × the zoom-17 pixel, ≈ 7.75 m/px), north-up,
rendered twice from OpenStreetMap data with render_view ('pseudo' style): the DAY REFERENCE (an aerial-style
drawing, sun shadows to the north-west) and a no-shadow render that is turned into a 'temperature' picture by a
material model (below). Both come from the same Mapnik box, so they are aligned exactly (no pixel-centre issue:
same geometry, same function). The student's training pairs are cut from these scenes with random 4-point offsets.

The material model ("thermal-like", NOT thermal): each pixel of the no-shadow render gets soft weights for water,
vegetation, asphalt, light roofs and metal roofs from its colour (blue excess, green excess, dark and grey, bright,
bright grey-blue); everything else is bare soil, darker soil a little warmer. Temperatures (0 cold – 1 hot):
                 soil   veg   asphalt water  roof   metal
    night        0.18   0.40  0.80    0.66   0.58   0.10     (soil cools fast, water and asphalt keep their heat,
                                                              metal reflects the cold sky)
    day          0.88   0.38  0.97    0.30   0.72   0.92     (sun-heated soil and metal, cool water and plants)
    crossover    0.50   0.50  0.51    0.50   0.505  0.49     (dawn/dusk: everything at almost the same temperature)
Water is smoothed (uniform surface temperature), then the optics blur (σ = 1 fine px) and the 4 × area resize.
The camera part (noise, column pattern, automatic gain) is applied per pair by navera_lite.homography_net.thermal_camera.

Splits: scene centres on two 1.3 km grids (the second shifted by half a step); 3.9 km cells are assigned to train /
val / test by a fixed hash; a scene closer than 1.3 km to a scene of a later split (val, test, coast, flight) is
dropped, so no ground is shared. Deterministic (fixed seeds; the renders are deterministic).
"""
import argparse
import csv
import glob
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
OUT = os.path.join(REPO, "datasets", "25-thermal-night")
HIDDEN = os.path.join(REPO, "courses", "25-thermal-night", "hidden")
ASSETS = os.path.join(REPO, "courses", "25-thermal-night", "assets")
sys.path.insert(0, os.path.join(REPO, "datasets", "_map"))
sys.path.insert(0, os.path.join(REPO, "solutions", "_navera_lite"))

ATTRIBUTION = "© OpenStreetMap contributors (ODbL), https://www.openstreetmap.org/copyright"
S = 160                         # scene side, px
FINE = 4                        # renders are made FINE × finer, then resized with INTER_AREA
BBOX = (35.71, 35.96, 10.48, 10.74)
STEP_M = 1300.0
CELL_M = 3900.0
CAM_HFOV, CAM_VFOV, CAM_W, CAM_H = 75.0, 63.0, 640, 512     # the flight's thermal camera
MODES = {        # soil   veg   asphalt water  roof   metal  texture
    "night":     (0.18, 0.40, 0.80, 0.66, 0.58, 0.10, 0.0015),
    "day":       (0.88, 0.38, 0.97, 0.30, 0.72, 0.92, 0.0015),
    "crossover": (0.50, 0.50, 0.51, 0.50, 0.505, 0.49, 0.0001),
}


def m_per_px(lat):
    """8 × the zoom-17 map pixel at this latitude (≈ 7.75 m at Sousse)."""
    return 8 * 40075016.686 * math.cos(math.radians(lat)) / 2 ** 17 / 256


def _s(x):
    return 1.0 / (1.0 + np.exp(-x))


def temperature(bgr, mode):
    """Material 'temperature' (0–1) of a no-shadow pseudo render (see the module docstring)."""
    f = bgr.astype(np.float32)
    B, G, R = f[..., 0], f[..., 1], f[..., 2]
    V = (B + G + R) / 3
    green, blue, sat = G - (R + B) / 2, B - (R + G) / 2, f.max(-1) - f.min(-1)
    wwat = _s((blue - 10) / 4)
    wveg = _s((green - 5) / 3) * (1 - wwat)
    wasph = _s((105 - V) / 10) * _s((16 - sat) / 4) * (1 - wwat) * (1 - wveg)
    wroof = _s((V - 195) / 8) * (1 - wveg) * (1 - wwat)
    wmetal = _s((V - 160) / 8) * _s((12 - sat) / 3) * _s((B - R) / 3) * (1 - wwat)
    soil, veg, asph, wat, roof, metal, tex = MODES[mode]
    T = soil + tex * (150 - V)
    T = T * (1 - wveg) + veg * wveg
    T = T * (1 - wasph) + asph * wasph
    T = T * (1 - wroof) + (roof + (0.08 if mode != "crossover" else 0.0) * (R - B) / 60) * wroof
    T = T * (1 - wmetal) + metal * wmetal
    smooth = cv2.GaussianBlur(np.full_like(T, wat), (0, 0), 6)
    T = T * (1 - wwat) + smooth * wwat
    return np.clip(cv2.GaussianBlur(T, (0, 0), 1.0), 0, 1)


def to_u8(t, side_w, side_h=None):
    side_h = side_h or side_w
    return np.clip(cv2.resize(t, (side_w, side_h), interpolation=cv2.INTER_AREA) * 255, 0, 255).astype(np.uint8)


def render_pair(lat, lon, heading=0.0, ground_m=None, alt_m=None, out=(S * FINE, S * FINE), fov=60.0, modes=("night",)):
    """(day reference BGR, {mode: temperature float}) of one view, from the same render box."""
    import render_view as rv
    kw = dict(ground_size_m=ground_m) if ground_m else dict(alt_m=alt_m)
    day = rv.render_view(lat, lon, heading, out_px=out, style="pseudo", fov_deg=fov, **kw)
    keep = rv.SUN_SHADOW
    rv.SUN_SHADOW = (0.0, 0.0)               # a thermal camera sees no sun shadows: no shadow offset
    try:
        nos = rv.render_view(lat, lon, heading, out_px=out, style="pseudo", fov_deg=fov, **kw)
    finally:
        rv.SUN_SHADOW = keep
    return day, {m: temperature(nos, m) for m in modes}


def scene_job(args):
    key, lat, lon, modes = args
    day, temps = render_pair(lat, lon, ground_m=m_per_px(lat) * S, modes=modes)
    out = {"ref": cv2.cvtColor(cv2.resize(day, (S, S), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY),
           "colour": cv2.resize(day, (S, S), interpolation=cv2.INTER_AREA)}
    for m, t in temps.items():
        out[m] = to_u8(t, S)
    return key, out


def grid():
    pts = []
    for off in (0.0, 0.5):
        lat = BBOX[0] + off * STEP_M / 111320.0
        while lat < BBOX[1]:
            dlon = STEP_M / (111320.0 * math.cos(math.radians(lat)))
            lon = BBOX[2] + off * dlon
            while lon < BBOX[3]:
                pts.append((round(lat, 5), round(lon, 5)))
                lon += dlon
            lat += STEP_M / 111320.0
    return pts


def sea_share(lat, lon):
    """Share of sea/water in the course map (zoom 14, 160 px ≈ 3.9 km) around a point, and of missing tiles."""
    from navera_lite import tiles
    m = tiles.map_patch(lat, lon, 14, S, S, path=os.path.expanduser("~/academy-data/osm_sousse.mbtiles"))
    return float(((m[..., 0].astype(int) - m[..., 2]) > 30).mean()), float((m == 40).all(-1).mean())


def split_of(lat, lon):
    cy = math.floor((lat - 35.70) * 111320 / CELL_M)
    cx = math.floor((lon - 10.47) * 90300 / CELL_M)
    h = (cy * 7919 + cx * 104729 + 7 * 31) % 100
    return "test" if h < 13 else "val" if h < 26 else "train"


def dist_m(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))


# ---------------------------------------------------------------------------------------------- the flight
def flight_plan(val_pts):
    """A 12-frame night flight inside a validation cell: 20 m/s, 3 s apart, camera heading = track; frame 7 low."""
    # the val point with the most varied neighbourhood is chosen by the caller; here: geometry only
    lat0, lon0 = val_pts
    track = 62.0
    rng = np.random.default_rng(2525)
    rows = []
    for k in range(12):
        d = 20.0 * 3.0 * k - 330.0
        e, n = d * math.sin(math.radians(track)), d * math.cos(math.radians(track))
        lat = lat0 + n / 111320.0
        lon = lon0 + e / (111320.0 * math.cos(math.radians(lat0)))
        alt = 300.0 if k == 6 else 430.0 + 10.0 * math.sin(k)
        pe, pn = rng.uniform(-60, 60), rng.uniform(-60, 60)          # the prior's error (dead reckoning)
        plat = lat + pn / 111320.0
        plon = lon + pe / (111320.0 * math.cos(math.radians(lat0)))
        rows.append(dict(frame=k + 1, t_s=3.0 * k, prior_lat=round(plat, 7), prior_lon=round(plon, 7), alt_m=round(alt, 1),
                         heading_deg=track + float(rng.uniform(-3, 3)), true_lat=round(lat, 7), true_lon=round(lon, 7)))
    return rows


def flight_job(row):
    import render_view as rv
    _, temps = render_pair(row["true_lat"], row["true_lon"], heading=row["heading_deg"], alt_m=row["alt_m"],
                           out=(CAM_W, CAM_H), fov=CAM_HFOV)
    # render_view's camera has square pixels: 640 × 512 at 75° horizontal gives 2·atan(tan(37.5°)·0.8) = 63.1°
    rng = np.random.default_rng(int(row["frame"]))
    t = np.clip(temps["night"] * 255, 0, 255).astype(np.float32)
    from navera_lite.homography_net import thermal_camera
    return row["frame"], thermal_camera(t, rng, noise=1.5)


def night_fixes():
    """A matcher's output on another night flight: 25 m/s heading 40°, a fix every 2 s, ±8 m noise; at t = 8 s a wrong
    match 238 m off with score 0.93; frames refused from 20 to 30 s; at t = 32 s a wrong match 300 m off (score 0.91)."""
    lat0, lon0 = 35.8050, 10.6150
    rng = np.random.default_rng(30)
    rows = []
    for t in list(range(0, 20, 2)) + list(range(32, 42, 2)):
        d = 25.0 * t
        e, n = d * math.sin(math.radians(40)), d * math.cos(math.radians(40))
        e, n = e + rng.normal(0, 5), n + rng.normal(0, 5)
        score = round(float(rng.uniform(0.86, 0.95)), 2)
        if t == 8:
            e, n, score = e + 238.0 * math.cos(math.radians(20)), n - 238.0 * math.sin(math.radians(20)), 0.93
        if t == 32:
            e, n, score = e - 300.0, n + 10.0, 0.91
        rows.append(dict(t_s=float(t), lat=round(lat0 + n / 111320.0, 7),
                         lon=round(lon0 + e / (111320.0 * math.cos(math.radians(lat0))), 7), score=score))
    return rows


# ---------------------------------------------------------------------------------------------- replay data
def copy_replay(src):
    dst = os.path.join(OUT, "replay")
    os.makedirs(dst, exist_ok=True)
    night = sorted(glob.glob(os.path.join(src, "thermal", "frame_*.jpg")))
    day = sorted(glob.glob(os.path.join(src, "day", "frame_*.jpeg")))
    if len(night) != 30 or len(day) != 30:
        raise SystemExit(f"replay: expected 30 + 30 frames in {src}, found {len(night)} + {len(day)}")
    for i, p in enumerate(night, 1):
        img = cv2.imread(p)
        cv2.imwrite(os.path.join(dst, f"night_{i:02d}.jpg"), cv2.resize(img, (768, 365), interpolation=cv2.INTER_AREA),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
    for i, p in enumerate(day, 1):
        img = cv2.imread(p)
        cv2.imwrite(os.path.join(dst, f"day_{i:02d}.jpg"), cv2.resize(img, (768, 365), interpolation=cv2.INTER_AREA),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])
    with open(os.path.join(src, "thermal", "flight_ready.csv")) as f:
        rows = list(csv.DictReader(f))
    with open(os.path.join(dst, "night_labels.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "lat", "lon", "altitude_m", "heading_deg"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["lat"], r["lon"], r["altitude_m"], r["heading_deg"]])
    with open(os.path.join(src, "day", "flight_log.csv")) as f:
        rows = list(csv.DictReader(f))
    with open(os.path.join(dst, "day_labels.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "lat", "lon", "altitude_m", "heading_deg"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["lat"], r["lon"], r["altitude_m"], r["heading_deg"]])


README = """# Mission 25 data (read only)

| File | What |
|---|---|
| `scenes_train.npz` | arrays `ref`, `night` (N × 160 × 160, uint8), `lat`, `lon`, `m_per_px`: squares of ground of the Sousse area (Tunisia), north up, about 7.75 m per pixel (about 1.24 km wide). `ref` is a day aerial-style view, `night` a night "temperature" picture of the same ground (0 = cold, 255 = hot), aligned pixel for pixel |
| `scenes_val.npz` | the same for other places (no ground shared with `scenes_train.npz`), plus `day` (a thermal-like picture at noon) and `crossover` (at dawn, when everything has about the same temperature) |
| `scenes_coast.npz` | `ref`, `night` of coastal places, half or more of them sea |
| `flight/frame_NN.png` | 640 × 512 thermal-like frames of a simulated night flight (camera 75° × 63°) |
| `flight/frames.csv` | per frame: time, the prior position (where the drone believed it was), height above ground, heading, and the true position |
| `flight/ref_area.png`, `ref_area.json` | the day reference of the flight's area, north up, and the latitude/longitude of its top-left corner and its metres per pixel |
| `night_fixes.csv` | positions reported by a night matcher on another flight: time, lat, lon, its score |
| `replay/night_NN.jpg`, `replay/day_NN.jpg` | NAVERA's replay frames (night and day sets), copied as data and reduced to 768 px wide |
| `replay/night_labels.csv`, `replay/day_labels.csv` | the labels the replay sets carry: frame, lat, lon, altitude_m, heading_deg |

The views are drawings made from OpenStreetMap data (they are not photographs and not real thermal images).
Pixels: (x, y) = (column, row), the centre of the top-left pixel is (0, 0).

Map data © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright.
The renders are a produced work of that data.
"""


def label_panel(img, text):
    """A white tab with the panel's letter and name in its top-left corner (in place)."""
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(img, (0, 0), (w + 12, h + 12), (255, 255, 255), -1)
    cv2.putText(img, text, (6, h + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--replay", default=None)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(HIDDEN, exist_ok=True)
    os.makedirs(ASSETS, exist_ok=True)
    import multiprocessing as mp
    t0 = time.time()

    # 1. candidate places: land (sea < 50 %) → train/val/test; coast (50–85 % sea) → coast set
    land, coast = [], []
    for lat, lon in grid():
        sea, miss = sea_share(lat, lon)
        if miss > 0.01:
            continue
        if sea < 0.5:
            land.append((lat, lon, split_of(lat, lon)))
        elif sea < 0.85 and len(coast) < 40:
            coast.append((lat, lon, "coast"))
    coast = coast[::5][:8]
    val_pts = [p for p in land if p[2] == "val"]
    # the flight: around the val point nearest the centre of the val cell with the most points
    cells = {}
    for p in val_pts:
        cells.setdefault((math.floor((p[0] - 35.70) * 111320 / CELL_M), math.floor((p[1] - 10.47) * 90300 / CELL_M)), []).append(p)
    best = max(cells.values(), key=len)
    clat = float(np.mean([p[0] for p in best]))
    clon = float(np.mean([p[1] for p in best]))
    flight_centre = (round(clat, 5), round(clon, 5))
    later = {"train": ["val", "test", "coast", "flight"], "val": ["test", "coast"], "test": ["coast"]}
    keep = []
    for p in land:
        bad = False
        for q in land + coast + [(flight_centre[0], flight_centre[1], "flight")]:
            if q[2] in later.get(p[2], []) and dist_m(p, q) < (2200.0 if q[2] == "flight" else STEP_M):
                bad = True
                break
        if not bad:
            keep.append(p)
    print(f"places: {len(keep)} land kept ({sum(p[2] == 'train' for p in keep)} train, "
          f"{sum(p[2] == 'val' for p in keep)} val, {sum(p[2] == 'test' for p in keep)} test), {len(coast)} coast", flush=True)

    # 2. render
    jobs = []
    for i, (lat, lon, sp) in enumerate(keep + coast):
        modes = ("night", "day", "crossover") if sp == "val" else ("night",)
        jobs.append(((sp, i, lat, lon), lat, lon, modes))
    res = {}
    with mp.Pool(args.workers) as pool:
        for key, out in pool.imap_unordered(scene_job, jobs):
            res[key] = out
            if len(res) % 40 == 0:
                print(f"  {len(res)}/{len(jobs)} scenes, {time.time() - t0:.0f} s", flush=True)
        plan = flight_plan(flight_centre)
        frames = dict(pool.map(flight_job, plan))
    by = {}
    for (sp, i, lat, lon), out in sorted(res.items(), key=lambda kv: kv[0][1]):
        by.setdefault(sp, []).append((lat, lon, out))

    def pack(sp, keys):
        items = by.get(sp, [])
        d = {k: np.stack([o[k] for _, _, o in items]) for k in keys}
        d["lat"] = np.array([a for a, _, _ in items])
        d["lon"] = np.array([b for _, b, _ in items])
        d["m_per_px"] = np.array([m_per_px(a) for a, _, _ in items])
        return d

    train = pack("train", ("ref", "night"))
    val = pack("val", ("ref", "night", "day", "crossover"))
    test = pack("test", ("ref", "night"))
    coastd = pack("coast", ("ref", "night"))
    np.savez_compressed(os.path.join(OUT, "scenes_train.npz"), **train)
    np.savez_compressed(os.path.join(OUT, "scenes_val.npz"), **val)
    np.savez_compressed(os.path.join(OUT, "scenes_coast.npz"), **coastd)

    # 3. hidden test pairs (night), never shown to students
    from navera_lite import homography_net as hn
    tx, ty = hn.make_pairs(test["ref"], test["night"], 512, seed=2525, augment=False)
    np.savez_compressed(os.path.join(HIDDEN, "test_pairs.npz"), x=tx, y=ty)

    # 4. the flight: frames, the reference area (day, north-up, 7.75 m/px, 2.4 km square around the route centre)
    fd = os.path.join(OUT, "flight")
    os.makedirs(fd, exist_ok=True)
    for k, img in frames.items():
        cv2.imwrite(os.path.join(fd, f"frame_{k:02d}.png"), img)
    with open(os.path.join(fd, "frames.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(plan[0]))
        w.writeheader()
        for r in plan:
            r = dict(r)
            r["heading_deg"] = round(r["heading_deg"], 2)
            w.writerow(r)
    import render_view as rv
    mpp = m_per_px(flight_centre[0])
    side = 320
    area = rv.render_view(flight_centre[0], flight_centre[1], 0.0, ground_size_m=mpp * side, out_px=side * FINE, style="pseudo")
    area = cv2.cvtColor(cv2.resize(area, (side, side), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    cv2.imwrite(os.path.join(fd, "ref_area.png"), area)
    # top-left CORNER of the picture (pixel edges), so the centre point of pixel (x, y) is at corner + (x + 0.5) px
    half = mpp * side / 2.0
    tl_lat = flight_centre[0] + half / 111320.0
    tl_lon = flight_centre[1] - half / (111320.0 * math.cos(math.radians(flight_centre[0])))
    with open(os.path.join(fd, "ref_area.json"), "w") as f:
        json.dump({"corner_lat": tl_lat, "corner_lon": tl_lon, "centre_lat": flight_centre[0],
                   "centre_lon": flight_centre[1], "m_per_px": mpp, "side_px": side,
                   "note": "north-up; the top-left CORNER of the picture is at (corner_lat, corner_lon)",
                   "attribution": ATTRIBUTION}, f, indent=1)
    with open(os.path.join(OUT, "night_fixes.csv"), "w", newline="") as f:
        rows = night_fixes()
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # 5. replay frames (data), README, lesson figure
    if args.replay:
        copy_replay(args.replay)
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write(README)
    i = int(np.argmax([float(np.std(r)) for r in val["ref"]]))
    tiles_ = [by["val"][i][2]["colour"]] + [cv2.cvtColor(val[m][i], cv2.COLOR_GRAY2BGR) for m in ("night", "day", "crossover")]
    big = [cv2.resize(t, (320, 320), interpolation=cv2.INTER_CUBIC) for t in tiles_]
    for b, text in zip(big, ("A day reference", "B night (thermal-like)", "C noon", "D dawn")):
        label_panel(b, text)
    look = np.hstack([np.pad(b, ((0, 0), (0, 8), (0, 0)), constant_values=255) for b in big])[:, :-8]
    from navera_lite.tiles import stamp_attribution
    cv2.imwrite(os.path.join(ASSETS, "look.jpg"), stamp_attribution(look), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"done in {time.time() - t0:.0f} s; look.jpg from val scene {i}; flight centre {flight_centre}")


if __name__ == "__main__":
    main()

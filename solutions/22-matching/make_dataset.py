#!/usr/bin/env python3
"""Mission 22 dataset (teacher only — never copy this file into datasets/: students read everything there).

    PYTHONPATH= python3 solutions/22-matching/make_dataset.py [--cache DIR]        # ≈ 12 min on the Jetson

--cache DIR keeps the fine orthophotos (≈ 25 MB each) between runs (rendering them is most of the time).

Writes datasets/22-matching/ (students: /data/academy/22-matching/):
  map_<place>.png        512 × 512 "map patches", north up, at the zoom-17 resolution of the place (≈ 0.97 m/px):
                         aerial-style renders of OpenStreetMap data (render_view, style 'pseudo', no effects)
  photos/*.jpg           640 × 480 "drone photos" (nadir unless said), resampled from the same fine orthophoto as
                         the map with a known heading and zoom (zoom = map m/px ÷ photo m/px), camera effects
  pairs.json             session 1: 8 named pairs {name, map, photo, prior {heading_deg, heading_sigma_deg, zoom},
                         H (map pixel → photo pixel, exact) or null for a photo of another place}
  curve.json             session 2: 12 pairs for choosing a threshold (prior heading within ±10° of the truth),
                         with their exact H
  envelope.json          session 2: base photos (one per place, heading 50°) and blurred versions, with their H
  mission.json           session 2: 10 scenarios for the matcher's policy (prior, truth H or null)
  README.md              neutral description + © OpenStreetMap contributors
courses/22-matching/files/ref_desc.pt: a copy of mission 21's reference weights (solutions/21-features/my_desc.pt),
  for students whose own my_desc.pt is missing. NOT in datasets/: /data/academy is readable from every mission, and
  mission 21's check grades a trained my_desc.pt. lp_expected.npz below is computed with it: whenever mission 21's
  reference is retrained, run this script again (with --cache it takes about 20 s).
and courses/22-matching/hidden/ (check only):
  lp_map.png, lp_photo.png, lp_expected.npz   one unseen pair and the reference learned_pairs() result on it with
                                              ref_desc.pt (prior heading 75°, zoom 1.6; ratio 0.8 and 0.9/0.6)
  scenes.npz + scenes.json                    13 unseen scenarios (town, olives, fields; sharp, blurred, shaken,
                                              heading known or not, a wrong place, a wrong altitude) with truth H

How the truth is exact (as mission 21): for each place ONE fine north-up orthophoto is rendered (render_view, pseudo,
no effects) at a quarter of the zoom-17 pixel size; the map patch and every photo of the place are resampled from it
with cv2.warpAffine (Gaussian pre-filter), each through a known "ground metres → pixel" matrix, so
H = photo matrix · inverse(map matrix) exactly (checked with SIFT + RANSAC residuals below). Tilted photos: the flat
photo is resampled on a larger canvas, then turned by K·R·K⁻¹ (mission 18) and cropped. Pixel-centre convention:
a picture's centre point is ((w − 1)/2, (h − 1)/2) (the ortho is rendered one pixel larger, first row and column
dropped, as in mission 08). A photo of ANOTHER place (wrong place) is resampled from that place's own ortho.
Places are at least ≈ 0.8 km from every place of mission 21's training/validation/test patches (centre to centre).
Deterministic (fixed seeds); the reference network runs on the CPU.
"""
import json
import math
import os
import shutil
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "datasets", "22-matching")
HID = os.path.join(REPO, "courses", "22-matching", "hidden")
REF_WEIGHTS = os.path.join(REPO, "solutions", "21-features", "my_desc.pt")
REF_COPY = os.path.join(REPO, "courses", "22-matching", "files", "ref_desc.pt")   # in the lesson folder, not datasets/
sys.path.insert(0, os.path.join(REPO, "datasets", "_map"))
from render_view import render_view  # noqa: E402

MAP_PX = 512
W, H_ = 640, 480
FINE = 4
ORTHO_PX = 2400                # 2400 × mpp/4 ≈ 580 m: covers a 1.6× photo at any heading (diagonal ≈ 485 m)
PLACES = {                     # name: (lat, lon) — public places, then hidden (check) places
    "city": (35.8277, 10.6388),
    "olives": (35.7409, 10.7377),
    "harbour": (35.7920, 10.6800),
    "sea": (35.8300, 10.7000),
    "grove": (35.7350, 10.7450),        # only photographed (the wrong place of session 1)
    "town": (35.8450, 10.6000),         # hidden
    "farm": (35.9200, 10.5200),         # hidden (olive groves and fields)
    "plain": (35.8000, 10.5500),        # hidden (fields; also a wrong place)
    "beach": (35.8600, 10.6200),        # hidden, only photographed (a wrong place)
    "grove2": (35.7380, 10.7500),       # hidden, only photographed (a wrong place)
}
MILD = {"blur": 0.6, "noise": 3.0, "brightness": 0.95, "gamma": 1.05}


def zoom17_m_per_px(lat):
    return 40075016.686 * math.cos(math.radians(lat)) / 2 ** 17 / 256


def pixel_from_enu(heading_deg, gsd, w, h):
    """3 × 3: ground (east, north) metres from the place's centre → pixel (x, y) of a nadir view whose top looks
    towards heading_deg."""
    p = math.radians(heading_deg)
    s, c = math.sin(p), math.cos(p)
    return np.array([[c / gsd, -s / gsd, (w - 1) / 2.0], [-s / gsd, -c / gsd, (h - 1) / 2.0], [0.0, 0.0, 1.0]])


def resample(src, P_src, P_dst, w, h):
    M = P_src @ np.linalg.inv(P_dst)
    f = math.sqrt(abs(np.linalg.det(M[:2, :2])))
    if f > 1.0:
        src = cv2.GaussianBlur(src, (0, 0), 0.45 * math.sqrt(f * f - 1.0))
    return cv2.warpAffine(src, M[:2], (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REFLECT)


def camera_effects(img, fx, seed, jpeg=92):
    rng = np.random.default_rng(seed)
    f = img.astype(np.float64)
    if fx.get("blur"):
        f = cv2.GaussianBlur(f, (0, 0), fx["blur"])
    if fx.get("motion_blur"):
        n = int(fx["motion_blur"])
        k = np.zeros((n, n))
        k[n // 2, :] = 1.0 / n
        if fx.get("motion_deg"):
            R = cv2.getRotationMatrix2D(((n - 1) / 2.0, (n - 1) / 2.0), fx["motion_deg"], 1.0)
            k = cv2.warpAffine(k, R, (n, n))
            k /= k.sum()
        f = cv2.filter2D(f, -1, k)
    f = 255.0 * (np.clip(f, 0, 255) / 255.0) ** fx.get("gamma", 1.0) * fx.get("brightness", 1.0)
    f = f + rng.normal(0, fx.get("noise", 0.0), f.shape)
    out = np.clip(np.rint(f), 0, 255).astype(np.uint8)
    _, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def tilt_h(pitch_deg, w, h, f):
    """Homography of a camera pitched by pitch_deg about its centre (focal f px): K·R·K⁻¹ (mission 18)."""
    K = np.array([[f, 0, (w - 1) / 2.0], [0, f, (h - 1) / 2.0], [0, 0, 1.0]])
    p = math.radians(pitch_deg)
    R = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    return K @ R @ np.linalg.inv(K)


class Place:
    def __init__(self, name, cache=None):
        self.name = name
        self.lat, self.lon = PLACES[name]
        self.mpp = zoom17_m_per_px(self.lat)
        f = os.path.join(cache, f"ortho_{name}.png") if cache else None
        if f and os.path.exists(f):
            self.o = cv2.imread(f)
        else:
            side = ORTHO_PX
            img = render_view(self.lat, self.lon, 0.0, ground_size_m=(side + 1) * self.mpp / FINE,
                              out_px=(side + 1, side + 1), style="pseudo", seed=0)
            self.o = img[1:, 1:]
            if f:
                cv2.imwrite(f, self.o)
        self.P_o = pixel_from_enu(0.0, self.mpp / FINE, ORTHO_PX, ORTHO_PX)
        self.P_map = pixel_from_enu(0.0, self.mpp, MAP_PX, MAP_PX)
        self.map = resample(self.o, self.P_o, self.P_map, MAP_PX, MAP_PX)
        print(f"place {name} ready", flush=True)

    def photo(self, heading, zoom, fx=None, seed=0, pitch=0.0, map_of=None):
        """(photo BGR, H map→photo of map_of (default: this place) or None for another place)."""
        gsd = self.mpp / zoom
        if pitch:
            cw, ch = W + 320, H_ + 240
            P_c = pixel_from_enu(heading, gsd, cw, ch)
            canvas = resample(self.o, self.P_o, P_c, cw, ch)
            T = tilt_h(pitch, W, H_, W / 2 / math.tan(math.radians(30)))
            S = np.array([[1, 0, -160.0], [0, 1, -120.0], [0, 0, 1]])           # canvas → photo pixel (flat)
            Hc = T @ S                                                         # canvas → tilted photo
            img = cv2.warpPerspective(canvas, Hc, (W, H_), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            P_b = Hc @ P_c
        else:
            P_b = pixel_from_enu(heading, gsd, W, H_)
            img = resample(self.o, self.P_o, P_b, W, H_)
        img = camera_effects(img, fx or MILD, seed)
        if map_of is not None and map_of is not self:
            return img, None
        Hm = P_b @ np.linalg.inv(self.P_map)
        return img, Hm / Hm[2, 2]


def h_check(m, p, H):
    """SIFT + RANSAC residual of the stated H (median px), or None when too few matches."""
    s = cv2.SIFT_create(3000)
    g1, g2 = cv2.cvtColor(m, cv2.COLOR_BGR2GRAY), cv2.cvtColor(p, cv2.COLOR_BGR2GRAY)
    k1, d1 = s.detectAndCompute(g1, None)
    k2, d2 = s.detectAndCompute(g2, None)
    if d1 is None or d2 is None or len(d2) < 2:
        return None
    mm = [a for a, b in cv2.BFMatcher().knnMatch(d1, d2, k=2) if a.distance < 0.7 * b.distance]
    if len(mm) < 8:
        return None
    a = np.float32([k1[x.queryIdx].pt for x in mm])
    b = np.float32([k2[x.trainIdx].pt for x in mm])
    _, inl = cv2.findHomography(a, b, cv2.RANSAC, 3.0)
    a, b = a[inl.ravel() > 0], b[inl.ravel() > 0]
    q = np.column_stack([a, np.ones(len(a))]) @ H.T
    return float(np.median(np.hypot(*(q[:, :2] / q[:, 2:3] - b).T)))


def rnd(H):
    return None if H is None else [[round(float(v), 9) for v in row] for row in H]


def save_jpg(path, img):
    cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return cv2.imread(path)


def main():
    cache = None
    if "--cache" in sys.argv:
        cache = sys.argv[sys.argv.index("--cache") + 1]
        os.makedirs(cache, exist_ok=True)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)                     # the old (satellite-map) dataset and its generator go
    os.makedirs(os.path.join(OUT, "photos"))
    os.makedirs(HID, exist_ok=True)
    for f in os.listdir(HID):
        os.remove(os.path.join(HID, f))
    P = {n: Place(n, cache) for n in PLACES}
    for n in ("city", "olives", "harbour", "sea"):
        cv2.imwrite(os.path.join(OUT, f"map_{n}.png"), P[n].map)

    # ---------------------------------------------------------------- session 1: eight named pairs
    known = lambda h, sg=5.0, z=1.6: {"heading_deg": h, "heading_sigma_deg": sg, "zoom": z}  # noqa: E731
    S1 = [  # name, map place, photo place, heading, true zoom, effects, pitch, prior
        ("city", "city", "city", 35.0, 1.6, MILD, 0.0, known(38.0)),
        ("city_tilt", "city", "city", 35.0, 1.6, MILD, 15.0, known(38.0)),
        ("olives", "olives", "olives", 35.0, 1.6, MILD, 0.0, known(31.0)),
        ("olives_shaken", "olives", "olives", 120.0, 1.6, dict(MILD, motion_blur=13), 0.0, known(126.0)),
        ("harbour", "harbour", "harbour", 300.0, 1.6, MILD, 0.0, known(296.0)),
        ("sea", "sea", "sea", 80.0, 1.6, MILD, 0.0, known(84.0)),
        ("wrong_place", "city", "grove", 200.0, 1.6, MILD, 0.0, known(200.0)),
        ("hills", "city", "city", 35.0, 2.24, MILD, 0.0, known(38.0, 5.0, 1.6)),
    ]
    pairs = []
    for i, (name, mp, pp, hd, z, fx, pitch, prior) in enumerate(S1):
        img, Hm = P[pp].photo(hd, z, fx, 100 + i, pitch, map_of=P[mp])
        img = save_jpg(os.path.join(OUT, "photos", f"{name}.jpg"), img)
        r = h_check(P[mp].map, img, Hm) if Hm is not None else None
        print(f"pair {name:14s} H check: median residual {r if r is None else round(r, 2)} px", flush=True)
        pairs.append({"name": name, "map": f"map_{mp}.png", "photo": f"photos/{name}.jpg", "prior": prior,
                      "map_m_per_px": round(P[mp].mpp, 4), "H": rnd(Hm)})
    json.dump(pairs, open(os.path.join(OUT, "pairs.json"), "w"), indent=1)

    # ---------------------------------------------------------------- session 2: threshold pairs (curve)
    rng = np.random.default_rng(2222)
    curve = []
    for i in range(12):
        place = ("city", "olives", "harbour")[i % 3]
        hd = float(rng.uniform(0, 360))
        fx = dict(MILD, blur=float(rng.uniform(0.5, 2.5)), noise=float(rng.uniform(2, 8)),
                  brightness=float(rng.uniform(0.6, 1.1)), gamma=float(rng.uniform(0.8, 1.4)))
        if i % 4 == 1:
            fx["motion_blur"] = int(rng.choice([7, 9, 11]))
            fx["motion_deg"] = float(rng.uniform(0, 180))
        img, Hm = P[place].photo(hd, float(rng.uniform(1.4, 1.8)), fx, 300 + i)
        zoom_true = float(np.sqrt(abs(np.linalg.det(Hm[:2, :2]))))
        name = f"curve_{i:02d}"
        save_jpg(os.path.join(OUT, "photos", f"{name}.jpg"), img)
        prior = {"heading_deg": round(hd + float(rng.uniform(-10, 10)), 1), "heading_sigma_deg": 10.0,
                 "zoom": round(zoom_true * float(rng.uniform(0.95, 1.05)), 3)}
        curve.append({"name": name, "map": f"map_{place}.png", "photo": f"photos/{name}.jpg", "prior": prior,
                      "map_m_per_px": round(P[place].mpp, 4), "H": rnd(Hm)})
    json.dump(curve, open(os.path.join(OUT, "curve.json"), "w"), indent=1)

    # ---------------------------------------------------------------- session 2: the envelope
    env = []
    BLURS = [("sharp", {}), ("blur2", {"blur": 2.0}), ("blur3", {"blur": 3.0}), ("blur4", {"blur": 4.0}),
             ("shake9", {"motion_blur": 9}), ("shake13", {"motion_blur": 13}), ("shake17", {"motion_blur": 17})]
    for place in ("city", "olives"):
        for j, (tag, extra) in enumerate(BLURS):
            img, Hm = P[place].photo(50.0, 1.6, dict(MILD, **extra), 500 + j)
            name = f"env_{place}_{tag}"
            save_jpg(os.path.join(OUT, "photos", f"{name}.jpg"), img)
            env.append({"name": name, "place": place, "effect": tag, "map": f"map_{place}.png",
                        "photo": f"photos/{name}.jpg", "heading_deg": 50.0, "zoom": 1.6,
                        "map_m_per_px": round(P[place].mpp, 4), "H": rnd(Hm)})
    json.dump(env, open(os.path.join(OUT, "envelope.json"), "w"), indent=1)

    # ---------------------------------------------------------------- session 2: mission scenarios (public)
    unknown = lambda z=1.6: {"heading_deg": None, "heading_sigma_deg": 180.0, "zoom": z}  # noqa: E731
    MS = [  # name, map, photo place, heading, zoom, effects, prior
        ("m01", "city", "city", 140.0, 1.6, MILD, unknown()),
        ("m02", "city", "city", 140.0, 1.6, dict(MILD, motion_blur=15), known(147.0, 8.0)),
        ("m03", "olives", "olives", 250.0, 1.6, MILD, unknown()),
        ("m04", "olives", "olives", 250.0, 1.6, dict(MILD, motion_blur=13, motion_deg=30.0), known(244.0, 8.0)),
        ("m05", "olives", "olives", 250.0, 1.6, dict(MILD, motion_blur=13, motion_deg=30.0), unknown()),
        ("m06", "olives", "olives", 10.0, 1.6, dict(MILD, blur=4.5), known(15.0, 8.0)),
        ("m07", "harbour", "harbour", 190.0, 1.6, dict(MILD, blur=2.5), known(185.0, 30.0)),
        ("m08", "sea", "sea", 0.0, 1.6, MILD, known(5.0, 8.0)),
        ("m09", "olives", "grove", 90.0, 1.6, MILD, known(90.0, 8.0)),
        ("m10", "city", "city", 300.0, 2.2, MILD, known(300.0, 8.0, 1.6)),
    ]
    mission = []
    for i, (name, mp, pp, hd, z, fx, prior) in enumerate(MS):
        img, Hm = P[pp].photo(hd, z, fx, 700 + i, map_of=P[mp])
        save_jpg(os.path.join(OUT, "photos", f"{name}.jpg"), img)
        mission.append({"name": name, "map": f"map_{mp}.png", "photo": f"photos/{name}.jpg", "prior": prior,
                        "map_m_per_px": round(P[mp].mpp, 4), "H": rnd(Hm)})
    json.dump(mission, open(os.path.join(OUT, "mission.json"), "w"), indent=1)

    # ---------------------------------------------------------------- hidden (check only)
    sys.path.insert(0, os.path.join(REPO, "solutions", "_navera_lite"))
    import torch
    torch.set_num_threads(2)
    from navera_lite.learned_desc import load_weights
    from navera_lite.learned_match import learned_pairs
    model = load_weights(REF_WEIGHTS)
    img, Hm = P["town"].photo(70.0, 1.6, dict(MILD, blur=1.2), 901)
    mg, pg = cv2.cvtColor(P["town"].map, cv2.COLOR_BGR2GRAY), cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cv2.imwrite(os.path.join(HID, "lp_map.png"), mg)            # grey PNG: the check reads exactly these pixels
    cv2.imwrite(os.path.join(HID, "lp_photo.png"), pg)
    res = {}
    for tag, ratio, md in (("r80", 0.8, None), ("r90_d60", 0.9, 0.6)):
        s, d = learned_pairs(mg, pg, 75.0, 1.6, model, ratio, md)
        res[f"{tag}_src"], res[f"{tag}_dst"] = s, d
        q = np.column_stack([s, np.ones(len(s))]) @ Hm.T
        ok = np.hypot(*(q[:, :2] / q[:, 2:3] - d).T) < 6
        print(f"hidden lp {tag}: {len(s)} pairs, {ok.mean():.3f} right", flush=True)
    np.savez_compressed(os.path.join(HID, "lp_expected.npz"), H=Hm, **res)

    HS = [  # name, map, photo place, heading, zoom, effects, prior, kind
        ("h01", "town", "town", 220.0, 1.6, MILD, unknown()),
        ("h02", "town", "town", 220.0, 1.6, dict(MILD, motion_blur=17, motion_deg=60.0), known(214.0, 6.0)),
        ("h03", "farm", "farm", 130.0, 1.6, MILD, unknown()),
        ("h04", "farm", "farm", 130.0, 1.6, dict(MILD, motion_blur=13, motion_deg=120.0), known(137.0, 8.0)),
        ("h05", "farm", "farm", 130.0, 1.6, dict(MILD, motion_blur=13, motion_deg=120.0), unknown()),
        ("h06", "plain", "plain", 330.0, 1.6, dict(MILD, motion_blur=11), known(326.0, 8.0)),
        ("h07", "town", "beach", 90.0, 1.6, MILD, known(90.0, 8.0)),
        ("h08", "farm", "farm", 60.0, 2.3, MILD, known(60.0, 8.0, 1.6)),
        ("h09", "town", "town", 100.0, 1.6, dict(MILD, blur=3.5), known(100.0, 40.0)),
        ("h10", "farm", "farm", 280.0, 1.6, dict(MILD, blur=5.0), known(284.0, 8.0)),
        ("h11", "farm", "grove2", 300.0, 1.6, MILD, known(300.0, 8.0)),
        ("h12", "plain", "plain", 30.0, 1.6, dict(MILD, motion_blur=15, motion_deg=90.0), known(36.0, 8.0)),
        ("h13", "farm", "farm", 300.0, 1.6, dict(MILD, motion_blur=11, motion_deg=10.0), known(293.0, 8.0)),
    ]
    arrays, meta = {}, []
    for i, (name, mp, pp, hd, z, fx, prior) in enumerate(HS):
        img, Hm = P[pp].photo(hd, z, fx, 950 + i, map_of=P[mp])
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        arrays[f"{name}_photo"] = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        meta.append({"name": name, "map": mp, "prior": prior, "map_m_per_px": round(P[mp].mpp, 4), "H": rnd(Hm)})
    for n in ("town", "farm", "plain"):
        arrays[f"map_{n}"] = cv2.cvtColor(P[n].map, cv2.COLOR_BGR2GRAY)
    np.savez_compressed(os.path.join(HID, "scenes.npz"), **arrays)
    json.dump(meta, open(os.path.join(HID, "scenes.json"), "w"), indent=1)

    shutil.copyfile(REF_WEIGHTS, REF_COPY)
    with open(os.path.join(OUT, "README.md"), "w") as fh:
        fh.write(README)
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
    print(f"datasets/22-matching: {total / 1e6:.1f} MB")


README = """# Mission 22 data (read only)

| File | What |
|---|---|
| `map_*.png` | 512 × 512 px map patches of the Sousse area (Tunisia), north up, about 0.97 m per pixel: an aerial-style drawing rendered from OpenStreetMap data |
| `photos/*.jpg` | 640 × 480 px simulated drone photos, with camera effects (noise, blur, shake, brightness) |
| `pairs.json` | session 1: eight named pairs: map, photo, the drone's prior (heading, its uncertainty, zoom) and the exact 3 × 3 matrix `H` from a map pixel to a photo pixel (`null` when the photo shows another place) |
| `curve.json`, `envelope.json`, `mission.json` | session 2: the pairs and scenarios of lab Steps 9–11, same fields |

zoom = map metres per pixel ÷ photo metres per pixel; heading = where the photo's top points, clockwise from north.
Pixels: (x, y) = (column, row), the centre of the top-left pixel is (0, 0).

Map data © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright.
The renders are a produced work of that data.
"""

if __name__ == "__main__":
    main()

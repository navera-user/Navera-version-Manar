#!/usr/bin/env python3
"""Mission 24 dataset (teacher only — never copy this file into datasets/: students read everything there).

    PYTHONPATH= python3 solutions/24-visual-odometry/make_dataset.py        # ≈ 4 min on the Jetson (orthos cached)

Writes datasets/24-visual-odometry/ (students: /data/academy/24-visual-odometry/):
  flight/frame_000.jpg … frame_089.jpg   90 frames, 320 × 240, one per second, of a synthetic drone flight over
                       Sousse (OpenStreetMap data, render_view 'pseudo' style): 52 s north-east across the city, out
                       over the sea, a left turn of 143° over the water, back over the coast and the city.
                       The camera is fixed under the drone, looking straight down, image TOP = the drone's heading
                       ("heading-up"); HFOV 70°; true height 120 m above flat ground; speed 20 m/s.
  flight.csv           what the drone BELIEVES: frame, file, t_s, heading_deg (IMU), baro_alt_m (barometer)
  truth.csv            frame, east_m, north_m: the true position (metres from frame 0) — for grading only
  map_fixes.csv        frame, east_m, north_m, sigma_m: map-matching fixes (mission 23) on land only
  info.json            camera and flight facts (no hidden defect named)
  pairs/a_NN.jpg, b_NN.jpg, pairs.csv   40 frame pairs from another part of the city (and the sea) for the
                       odometer comparison: group (straight, turn4, turn12, turn30, sea), turn_deg (IMU heading
                       change b − a), true_dx_px, true_dy_px (where the ground point at a's centre appears in b,
                       minus the centre: the shift phase correlation should measure after derotation)
  README.md            neutral description + © OpenStreetMap contributors
and courses/24-visual-odometry/hidden/ (check only):
  test_pairs.npz       6 straight pairs (grey uint8) from a third place, with their true centre shifts
  test_flight.npz      a 13-frame flight from that place (grey frames, IMU headings with no bias, true m/px, truth)

Hidden defects of the main flight (the lab makes the student find them; never write them into datasets/):
  * the barometer reads 3 % low (116.4 m instead of 120 m) → every VO step 3 % short (a scale bias);
  * the IMU heading is 2.0° too large (+ 0.05° noise) → every step turned by 2° (a direction bias);
  * frames 80–87: a telemetry overlay (OSD box) is burnt into the image — a static pattern that can pull phase
    correlation to "no motion" (the vo_gate experiment);
  * the sea moves: sea pixels are redrawn with new waves in every frame, so over open water nothing is fixed.

How the truth is exact. For each place ONE fine north-up orthophoto is rendered (render_view, pseudo, no effects)
at 1/3 m per pixel; every frame is resampled from it with cv2.warpAffine through a known "ground metres → pixel"
matrix (Gaussian pre-filter against aliasing), as in mission 21. A map-style render of the same box gives the sea
mask. Pixel-centre convention: a frame's centre point is ((w − 1)/2, (h − 1)/2). Deterministic (fixed seeds).
Orthos are cached in ~/.cache/navera-academy/24 (delete it after a map change).
"""
import csv
import json
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "datasets", "24-visual-odometry")
HID = os.path.join(REPO, "courses", "24-visual-odometry", "hidden")
CACHE = os.path.expanduser("~/.cache/navera-academy/24")
sys.path.insert(0, os.path.join(REPO, "datasets", "_map"))
from render_view import render_view  # noqa: E402

W, H = 320, 240
HFOV = 70.0
ALT = 120.0
GSD = 2 * ALT * math.tan(math.radians(HFOV / 2)) / W          # 0.52510 m/px
BARO_FACTOR = 0.97
HEADING_BIAS = 2.0
SPEED = 20.0
FINE = 1.0 / 3.0                                                # ortho m/px
SEA_BGR = np.array([223, 211, 170], float)                      # the map style's sea colour (#aad3df), BGR
SEA_PSEUDO_BGR = np.array([118, 92, 38], float)

# places: (name, lat, lon, ortho side px)
FLIGHT_PLACE = ("flight", 35.831593, 10.639002, 3600)           # coast north of Sousse's medina
PAIRS_PLACE = ("pairs", 35.8165, 10.6180, 1800)                 # city, south-west
SEA_PLACE = ("sea", 35.8420, 10.6640, 900)                      # open sea, east of the coast
TEST_PLACE = ("test", 35.8590, 10.6020, 1800)                   # city, north (hidden check data)


# ------------------------------------------------------------------ geometry
def centred(lat, lon, side, gsd, style):
    """render_view north-up, side × side px, with (lat, lon) at the pixel centre ((side − 1)/2, …)."""
    img = render_view(lat, lon, 0.0, ground_size_m=(side + 1) * gsd, out_px=side + 1, style=style)
    return img[1:, 1:]


def ortho(place):
    name, lat, lon, side = place
    os.makedirs(CACHE, exist_ok=True)
    f_p, f_m = os.path.join(CACHE, f"{name}_pseudo.png"), os.path.join(CACHE, f"{name}_map.png")
    if not os.path.exists(f_p):
        print(f"rendering the {name} ortho ({side} px) …", flush=True)
        cv2.imwrite(f_p, centred(lat, lon, side, FINE, "pseudo"))
        cv2.imwrite(f_m, centred(lat, lon, side, FINE, "map"))
    img, mp = cv2.imread(f_p), cv2.imread(f_m)
    sea = (np.abs(mp.astype(float) - SEA_BGR).sum(2) < 30).astype(np.float32)
    c = (side - 1) / 2.0
    P = np.array([[1 / FINE, 0, c], [0, -1 / FINE, c], [0, 0, 1.0]])   # ground (E, N, 1) → ortho pixel
    return img, sea, P


def frame_matrix(e, n, heading_deg, gsd=GSD, w=W, h=H):
    """Ground (E, N, 1) metres → pixel of a heading-up nadir frame centred on (e, n)."""
    th = math.radians(heading_deg)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    # pixel → ground: E = e + r cos + f sin, N = n − r sin + f cos, r = (x − cx) g, f = −(y − cy) g
    A = np.array([[gsd * math.cos(th), -gsd * math.sin(th), 0.0],
                  [-gsd * math.sin(th), -gsd * math.cos(th), 0.0],
                  [0, 0, 1.0]])
    A[0, 2] = e - A[0, 0] * cx - A[0, 1] * cy
    A[1, 2] = n - A[1, 0] * cx - A[1, 1] * cy
    return np.linalg.inv(A)


def resample(src, P_src, P_dst, w=W, h=H, border=cv2.BORDER_REFLECT):
    M = P_src @ np.linalg.inv(P_dst)                              # destination pixel → source pixel
    f = math.sqrt(abs(np.linalg.det(M[:2, :2])))
    if f > 1.0:
        src = cv2.GaussianBlur(src, (0, 0), 0.45 * math.sqrt(f * f - 1.0))
    return cv2.warpAffine(src, M[:2], (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=border)


# ------------------------------------------------------------------ camera
def moving_sea(img, wsea, rng):
    """Replace sea pixels by water drawn anew for this frame: nothing on the sea is fixed between frames."""
    if wsea.max() <= 0:
        return img
    n = cv2.GaussianBlur(rng.normal(0, 1, wsea.shape).astype(np.float32), (0, 0), 2.5)
    n *= 7.0 / (n.std() + 1e-6)
    caps = (rng.random(wsea.shape) < 0.0015).astype(np.float32)
    caps = cv2.GaussianBlur(caps, (0, 0), 1.0) * 120.0
    water = SEA_PSEUDO_BGR[None, None, :] + (n + caps)[..., None] * np.array([1.0, 1.1, 1.2])
    w = wsea[..., None]
    return img * (1 - w) + water * w


def camera(img, rng, jpeg=88):
    """Blur, gain, gamma, sensor noise, JPEG: a different draw for every frame."""
    f = cv2.GaussianBlur(img.astype(np.float64), (0, 0), rng.uniform(0.35, 0.9))
    f = 255.0 * (np.clip(f, 0, 255) / 255.0) ** rng.uniform(0.9, 1.1) * rng.uniform(0.9, 1.1)
    f = f + rng.normal(0, rng.uniform(1.5, 4.0), f.shape)
    out = np.clip(np.rint(f), 0, 255).astype(np.uint8)
    _, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def osd(img):
    """A telemetry overlay burnt into the picture (a static box with text), bottom left."""
    out = img.copy()
    x0, y0, x1, y1 = 8, 168, 168, 232
    roi = out[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = (roi * 0.35).astype(np.uint8)
    cv2.rectangle(out, (x0, y0), (x1, y1), (255, 255, 255), 2)
    for k, s in enumerate(("REC  CAM 1", "ALT AGL  ---", "GNSS  NO FIX")):
        cv2.putText(out, s, (x0 + 8, y0 + 19 + 19 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                    cv2.LINE_AA)
    return out


def shoot(o, sea, P_o, e, n, hdg, rng, gsd=GSD):
    P = frame_matrix(e, n, hdg, gsd)
    img = resample(o, P_o, P).astype(np.float64)
    wsea = resample(sea, P_o, P)
    return camera(moving_sea(img, wsea, rng), rng), float(wsea.mean())


# ------------------------------------------------------------------ the flight
def flight_path():
    """True (e, n, heading) of the 90 frames, metres in the flight ortho's frame."""
    e, n, hdg = -400.0, -440.0, 48.0
    pts = [(e, n, hdg)]
    for ns, rate in ((52, 0.0), (13, -11.0), (24, 0.0)):
        for _ in range(ns):
            hdg = (hdg + rate) % 360.0
            e += SPEED * math.sin(math.radians(hdg))
            n += SPEED * math.cos(math.radians(hdg))
            pts.append((e, n, hdg))
    return pts


def make_flight():
    o, sea, P_o = ortho(FLIGHT_PLACE)
    rng = np.random.default_rng(2424)
    pts = flight_path()
    os.makedirs(os.path.join(OUT, "flight"), exist_ok=True)
    rows, truth, seafrac = [], [], []
    e0, n0 = pts[0][0], pts[0][1]
    for i, (e, n, hdg) in enumerate(pts):
        img, sf = shoot(o, sea, P_o, e, n, hdg, rng)
        if 80 <= i <= 87:
            img = osd(img)
        name = f"frame_{i:03d}.jpg"
        cv2.imwrite(os.path.join(OUT, "flight", name), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        imu = (hdg + HEADING_BIAS + rng.normal(0, 0.05)) % 360.0
        baro = ALT * BARO_FACTOR + rng.normal(0, 0.15)
        rows.append([i, f"flight/{name}", f"{float(i):.1f}", f"{imu:.2f}", f"{baro:.2f}"])
        truth.append([i, f"{e - e0:.3f}", f"{n - n0:.3f}"])
        seafrac.append(sf)
    with open(os.path.join(OUT, "flight.csv"), "w", newline="") as f:
        csv.writer(f).writerows([["frame", "file", "t_s", "heading_deg", "baro_alt_m"]] + rows)
    with open(os.path.join(OUT, "truth.csv"), "w", newline="") as f:
        csv.writer(f).writerows([["frame", "east_m", "north_m"]] + truth)
    fr = np.random.default_rng(23)
    fixes = []
    for i in (10, 20, 30, 40, 50, 79, 89):                          # map matching works on land only
        fixes.append([i, f"{pts[i][0] - e0 + fr.normal(0, 3.0):.2f}", f"{pts[i][1] - n0 + fr.normal(0, 3.0):.2f}",
                      "4.0"])
    with open(os.path.join(OUT, "map_fixes.csv"), "w", newline="") as f:
        csv.writer(f).writerows([["frame", "east_m", "north_m", "sigma_m"]] + fixes)
    lat0 = FLIGHT_PLACE[1] + n0 / 111320.0
    lon0 = FLIGHT_PLACE[2] + e0 / (111320.0 * math.cos(math.radians(FLIGHT_PLACE[1])))
    info = {"frames": len(pts), "width_px": W, "height_px": H, "camera_hfov_deg": HFOV,
            "time_between_frames_s": 1.0, "start_lat": round(lat0, 6), "start_lon": round(lon0, 6),
            "camera": "fixed under the drone, looking straight down; the TOP of each frame points to the drone's "
                      "heading (heading-up)",
            "heading_deg": "from the IMU, clockwise from north", "baro_alt_m": "height above the ground from the "
            "barometer (the ground is flat)",
            "map_fixes": "map-matching positions (mission 23): only where the map could be matched",
            "attribution": "Map data © OpenStreetMap contributors"}
    with open(os.path.join(OUT, "info.json"), "w") as f:
        json.dump(info, f, indent=1)
    full = [i for i, s in enumerate(seafrac) if s > 0.97]
    print(f"flight: {len(pts)} frames, full-sea frames {full[0]}–{full[-1]} ({len(full)})")
    return seafrac


# ------------------------------------------------------------------ pairs
def centre_shift(Pa, Pb):
    """Where a's centre ground point appears in b, minus the centre (px)."""
    c = np.array([(W - 1) / 2.0, (H - 1) / 2.0, 1.0])
    q = Pb @ np.linalg.inv(Pa) @ c
    return q[0] / q[2] - c[0], q[1] / q[2] - c[1]


def pair(o, sea, P_o, rng, centre_box, turn, forward=None):
    """Two frames of one place: b flown forward 16–24 m (± 3 m sideways) and turned by `turn` degrees."""
    half = centre_box
    e, n = rng.uniform(-half, half, 2)
    hdg = rng.uniform(0, 360)
    fwd = rng.uniform(16, 24) if forward is None else forward
    side = rng.uniform(-3, 3)
    th = math.radians(hdg)
    e2 = e + fwd * math.sin(th) + side * math.cos(th)
    n2 = n + fwd * math.cos(th) - side * math.sin(th)
    hdg2 = hdg + turn
    a, sa = shoot(o, sea, P_o, e, n, hdg, rng)
    b, sb = shoot(o, sea, P_o, e2, n2, hdg2, rng)
    dx, dy = centre_shift(frame_matrix(e, n, hdg), frame_matrix(e2, n2, hdg2))
    return a, b, dx, dy, max(sa, sb)


def make_pairs():
    o, sea, P_o = ortho(PAIRS_PLACE)
    os_, ss, Ps = ortho(SEA_PLACE)
    rng = np.random.default_rng(2425)
    os.makedirs(os.path.join(OUT, "pairs"), exist_ok=True)
    rows, k = [], 0
    for group, turn in (("straight", 0.0), ("turn4", 4.0), ("turn12", 12.0), ("turn30", 30.0), ("sea", 0.0)):
        for _ in range(8):
            t = turn * rng.choice([-1.0, 1.0])
            if group == "sea":
                a, b, dx, dy, sf = pair(os_, ss, Ps, rng, 60.0, t)
                assert sf > 0.99, sf
            else:
                a, b, dx, dy, sf = pair(o, sea, P_o, rng, 180.0, t)
                assert sf < 0.01, sf
            cv2.imwrite(os.path.join(OUT, "pairs", f"a_{k:02d}.jpg"), a, [cv2.IMWRITE_JPEG_QUALITY, 92])
            cv2.imwrite(os.path.join(OUT, "pairs", f"b_{k:02d}.jpg"), b, [cv2.IMWRITE_JPEG_QUALITY, 92])
            rows.append([k, group, f"{t:.1f}", f"{dx:.3f}", f"{dy:.3f}"])
            k += 1
    with open(os.path.join(OUT, "pairs.csv"), "w", newline="") as f:
        csv.writer(f).writerows([["pair", "group", "turn_deg", "true_dx_px", "true_dy_px"]] + rows)
    print(f"pairs: {k}")


# ------------------------------------------------------------------ hidden check data
def gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def make_hidden():
    o, sea, P_o = ortho(TEST_PLACE)
    rng = np.random.default_rng(2426)
    A, B, D = [], [], []
    for fwd in (18.0, -14.0, 22.0, 9.0, 25.0, -20.0):              # negative: flying backwards (dy < 0)
        a, b, dx, dy, _ = pair(o, sea, P_o, rng, 200.0, 0.0, forward=fwd)
        A.append(gray(a))
        B.append(gray(b))
        D.append((dx, dy))
    os.makedirs(HID, exist_ok=True)
    np.savez_compressed(os.path.join(HID, "test_pairs.npz"), a=np.stack(A), b=np.stack(B), shift=np.array(D))
    # a short flight with a turn: 13 frames, 18 m/s, height 90 m (another m/px), headings exact (no bias)
    gsd = 2 * 90.0 * math.tan(math.radians(HFOV / 2)) / W
    e, n, hdg = -120.0, -150.0, 300.0
    frames, heads, pos = [], [], []
    for i in range(13):
        img, _ = shoot(o, sea, P_o, e, n, hdg, rng, gsd=gsd)
        frames.append(gray(img))
        heads.append(hdg)
        pos.append((e, n))
        hdg = (hdg + (6.0 if 4 <= i < 9 else 0.0)) % 360.0
        e += 18.0 * math.sin(math.radians(hdg))
        n += 18.0 * math.cos(math.radians(hdg))
    pos = np.array(pos) - np.array(pos[0])
    np.savez_compressed(os.path.join(HID, "test_flight.npz"), frames=np.stack(frames), heading=np.array(heads),
                        m_per_px=np.array(gsd), truth=pos)
    print("hidden: test_pairs.npz, test_flight.npz")


README = """# Mission 24 — visual odometry data

Synthetic downward camera frames drawn from OpenStreetMap data of Sousse, Tunisia (NAVERA's test area) with the
course's map renderer. Map data © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).

| File | What |
|---|---|
| `flight/frame_NNN.jpg` | 90 frames (320 × 240), one per second, of one flight. Heading-up: the top of each frame points to the drone's heading |
| `flight.csv` | frame, file, t_s, heading_deg (IMU), baro_alt_m (barometer): what the drone measured |
| `truth.csv` | frame, east_m, north_m: the true position, metres from frame 0. Use it to grade your odometry, never to compute it |
| `map_fixes.csv` | frame, east_m, north_m, sigma_m: positions from map matching (mission 23), where it worked |
| `info.json` | camera and flight facts |
| `pairs/a_NN.jpg`, `pairs/b_NN.jpg`, `pairs.csv` | 40 frame pairs for comparing odometers: group, turn_deg (heading change from a to b), true_dx_px, true_dy_px (where the ground point at a's centre appears in b, minus the centre) |
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    make_flight()
    make_pairs()
    make_hidden()
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write(README)
    total = sum(os.path.getsize(os.path.join(dp, x)) for dp, _, fs in os.walk(OUT) for x in fs)
    print(f"datasets/24-visual-odometry: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

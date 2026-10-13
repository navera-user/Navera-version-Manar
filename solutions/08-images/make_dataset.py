#!/usr/bin/env python3
"""Mission 08 dataset (teacher only — never copy this file into datasets/: it states the true values).

    PYTHONPATH= python3 solutions/08-images/make_dataset.py [REAL_FRAME]        # ~10 s on the Jetson

REAL_FRAME: path of NAVERA's recorded day frame number 5 (frame_0005.jpeg of its day data set, staff
data folder). Without it, an existing datasets/08-images/real_frame.jpg is kept as it is.

Writes datasets/08-images/ (students: /data/academy/08-images/):
  map_patch.png    512 x 512, north up, the zoom-17 resolution at the place (0.9675 m/px), centred on
                   Port El Kantaoui marina: an aerial-style render of OpenStreetMap data (render_view,
                   style 'pseudo', no effects) — the "reference map" of the lab
  drone_photo.jpg  640 x 480 "drone photo" of the same centre: TRUE heading 35.0° (top of the photo),
                   0.60 m/px, darker, warmer, blurred, noisy, vignetted, JPEG — same renderer, effects on
  thermal16.png    640 x 512 uint16 "thermal-like" frame (raw counts ~7 150–8 430): a grey render of the
                   Sousse harbour mapped to counts, plus noise. Synthetic; says so in the README
  real_frame.jpg   a real aerial frame from NAVERA's day-camera test data (frame_0005, 1536 x 730), copied as
                   DATA. Its place and the source of the imagery are not established: never name a place
                   (owner decision §7.2, 2026-10-12); never code
  info.json        what the "drone" reported: heading from its compass (IMU) = 31.0° — 4° off the truth,
                   on purpose (lab Step 8 finds it with the NCC sweep) — and the m/px values
  README.md        neutral description + © OpenStreetMap contributors

Deterministic (fixed seeds). The true heading (35.0°) appears only here, in check.py and in TEACHER.md.
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
OUT = os.path.join(REPO, "datasets", "08-images")
sys.path.insert(0, os.path.join(REPO, "datasets", "_map"))
from render_view import render_view  # noqa: E402

LAT, LON = 35.8942, 10.5979                  # Port El Kantaoui marina (north of Sousse)
TRUE_HEADING_DEG = 35.0
IMU_HEADING_DEG = 31.0                       # what info.json says: a 4° compass error
PHOTO_MPP = 0.60
PHOTO_W, PHOTO_H = 640, 480
MAP_PX = 512
REAL_FRAME = sys.argv[1] if len(sys.argv) > 1 else None
THERMAL_AT = (35.8285, 10.6440)              # Sousse harbour: sea, quays, town
ATTRIBUTION = "© OpenStreetMap contributors (ODbL), https://www.openstreetmap.org/copyright"


def zoom17_m_per_px(lat):
    return 40075016.686 * math.cos(math.radians(lat)) / 2 ** 17 / 256


def centred(lat, lon, heading, w, h, gsd, **kw):
    """render_view with (lat, lon) on the CENTRE POINT ((w − 1)/2, (h − 1)/2) of the course convention.
    render_view puts it at (w/2, h/2) in pixel-centre coordinates: render one pixel more each way and drop the
    first row and column (checked: like_map of such a photo against the map shows no heading-dependent shift)."""
    img = render_view(lat, lon, heading, ground_size_m=(w + 1) * gsd, out_px=(w + 1, h + 1), **kw)
    return img[1:, 1:]


def main():
    os.makedirs(OUT, exist_ok=True)
    for old in ("make_dataset.py",):                  # an older generator must not stay where students read
        p = os.path.join(OUT, old)
        if os.path.exists(p):
            os.remove(p)
    map_mpp = zoom17_m_per_px(LAT)
    ref = centred(LAT, LON, 0.0, MAP_PX, MAP_PX, map_mpp, style="pseudo", seed=0)
    cv2.imwrite(os.path.join(OUT, "map_patch.png"), ref)

    fx = {"blur": 1.3, "noise": 5.0, "gamma": 1.35, "brightness": 0.72, "color": 0.0, "illum": 0.25,
          "vignette": 0.3, "jpeg": 85}
    photo = centred(LAT, LON, TRUE_HEADING_DEG, PHOTO_W, PHOTO_H, PHOTO_MPP,
                        style="pseudo", seed=8, effects=fx)
    f = photo.astype(np.float32)
    f[..., 0] *= 0.82                                   # warmer: less blue, more red
    f[..., 2] = f[..., 2] * 1.08 + 6
    photo = np.clip(np.rint(f), 0, 255).astype(np.uint8)
    cv2.imwrite(os.path.join(OUT, "drone_photo.jpg"), photo, [cv2.IMWRITE_JPEG_QUALITY, 88])

    t = render_view(*THERMAL_AT, 0.0, ground_size_m=640 * 0.9, out_px=(640, 512), style="pseudo", seed=0)
    g = cv2.cvtColor(t, cv2.COLOR_BGR2GRAY).astype(np.float64)
    g = cv2.GaussianBlur(g, (0, 0), 1.5)               # thermal cameras are soft
    rng = np.random.default_rng(80)
    counts = 7150.0 + (g - g.min()) / (g.max() - g.min()) * 1280.0 + rng.normal(0, 6, g.shape)
    counts = np.clip(np.rint(counts), 7150, 8430).astype(np.uint16)
    cv2.imwrite(os.path.join(OUT, "thermal16.png"), counts)

    dst = os.path.join(OUT, "real_frame.jpg")
    if REAL_FRAME:
        shutil.copyfile(os.path.expanduser(REAL_FRAME), dst)
    elif not os.path.exists(dst):
        sys.exit("give the path of NAVERA's day frame 5 as the first argument (real_frame.jpg is missing)")

    info = {
        "place": "Port El Kantaoui marina, north of Sousse (Tunisia)",
        "lat": LAT, "lon": LON,
        "photo": {"file": "drone_photo.jpg", "width": PHOTO_W, "height": PHOTO_H,
                  "heading_imu_deg": IMU_HEADING_DEG,
                  "heading_note": "the direction of the photo's top, clockwise from north, as the drone's compass reported it",
                  "m_per_px": PHOTO_MPP,
                  "centre": "the photo's centre point is (lat, lon)"},
        "map": {"file": "map_patch.png", "size": MAP_PX, "m_per_px": round(map_mpp, 6),
                "centre": "the patch's centre point is (lat, lon); north is up"},
        "thermal": {"file": "thermal16.png", "dtype": "uint16", "width": 640, "height": 512,
                    "note": "synthetic thermal-like frame, raw sensor counts"},
        "real": {"file": "real_frame.jpg", "note": "a real aerial frame from NAVERA's day-camera test data"},
        "attribution": ATTRIBUTION,
    }
    with open(os.path.join(OUT, "info.json"), "w") as fh:
        json.dump(info, fh, indent=1)
    with open(os.path.join(OUT, "README.md"), "w") as fh:
        fh.write(README)
    print("written:", sorted(os.listdir(OUT)))


README = """# Mission 08 data (read only)

| File | What |
|---|---|
| `map_patch.png` | 512 × 512 px reference map, north up, about 0.97 m per pixel, centred on Port El Kantaoui marina (Sousse, Tunisia). An aerial-style drawing rendered from OpenStreetMap data |
| `drone_photo.jpg` | 640 × 480 px simulated downward drone photo of the same place, drawn by the same renderer, with camera effects |
| `thermal16.png` | 640 × 512 px simulated thermal-like frame, 16-bit raw counts (open it with `cv2.IMREAD_UNCHANGED`) |
| `real_frame.jpg` | a real aerial frame from NAVERA's day-camera test data, 1536 × 730 px |
| `info.json` | what the drone reported with the photo, and the map's metres per pixel |

Map data © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright.
The renders are a produced work of that data.
"""

if __name__ == "__main__":
    main()

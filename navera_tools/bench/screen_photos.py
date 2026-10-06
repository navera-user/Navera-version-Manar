#!/usr/bin/env python3
"""The real camera locates real aerial photos shown on the screen, against NAVERA's map.

The 33 benchmark photos (another camera and date than the satellite map: colours, shadows,
changes) are shown one by one, turned north-up from their heading and at one fixed scale;
the camera (fixed, facing the screen) films each; NAVERA locates it with each matcher,
against its own map tiles. No height is given: it is found on the first photos (two that
agree), then kept. Truth: the photo's GPS position (its centre is the screen centre) plus
the camera axis offset — a constant ground vector, estimated as the median over the
session and reported (errors given with and without it).

    python3 navera_tools/bench/screen_photos.py --calib camera.yaml --area <area dir>
"""
import argparse
import glob
import json
import math
import os
import time

import cv2
import numpy as np

from day_pkg.local_matcher import LocalMatcher
from day_pkg.learned_matcher import LearnedMatcher, north_up

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--calib", required=True)
ap.add_argument("--area", required=True, help="area dir: images/ (and learned_features/)")
ap.add_argument("--device", default="/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0")
ap.add_argument("--frames", default=os.path.expanduser("~/navera_data/vision_pkg/vision_pkg/dataset/frames_gps"))
ap.add_argument("--hfov", type=float, default=111.0)
ap.add_argument("--show-scale", type=float, default=0.72, help="screen px per photo px")
ap.add_argument("--search-m", type=float, default=600.0)
ap.add_argument("--out", default="screen_photos.json")
a = ap.parse_args()

files = sorted(glob.glob(a.frames + "/*.jpg"))
truth = [(float(os.path.basename(f).split("_lat")[1].split("_")[0]),
          float(os.path.basename(f).split("_lon")[1].split("_")[0])) for f in files]
hd = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames_heading.json")))


def bearing(p, q):
    return math.degrees(math.atan2((q[1] - p[1]) * math.cos(math.radians(p[0])), q[0] - p[0]))


HEAD = [hd.get(os.path.basename(f), bearing(truth[i - 1], truth[i]) if i else bearing(truth[0], truth[1]))
        for i, f in enumerate(files)]


def metres(p, q):
    """(east, north) metres from q to p."""
    return ((p[1] - q[1]) * 111320.0 * math.cos(math.radians(q[0])), (p[0] - q[0]) * 111320.0)


# ---- camera ----
import yaml
cal = yaml.safe_load(open(a.calib))
K = np.array(cal["camera_matrix"]).reshape(3, 3)
D = np.array(cal["distortion"]).reshape(4, 1)
cx0, cy0, cw, ch = cal.get("crop") or (0, 0, cal["image_width"], cal["image_height"])
fo = (cw / 2) / math.tan(math.radians(a.hfov / 2))
m1, m2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), np.array([[fo, 0, cw / 2], [0, fo, ch / 2], [0, 0, 1]]),
                                             (cw, ch), cv2.CV_16SC2)
cap = cv2.VideoCapture(a.device, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)


def shoot():
    for _ in range(12):                                          # fresh frame, exposure settled
        cap.grab()
    ok, f = cap.retrieve()
    return cv2.remap(f[cy0:cy0 + ch, cx0:cx0 + cw], m1, m2, cv2.INTER_LINEAR) if ok else None


matchers = {"sift": LocalMatcher(a.area + "/images"),
            "learned": LearnedMatcher(a.area + "/images", cache_dir=a.area + "/learned_features")}
for p in truth:
    matchers["learned"].warm(p[0], p[1], 1200)

cv2.namedWindow("photos", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("photos", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
state = {m: dict(height=None, first=[], res=[]) for m in matchers}
for i, f in enumerate(files):
    photo = north_up(cv2.imread(f), HEAD[i])
    photo = cv2.resize(photo, None, fx=a.show_scale, fy=a.show_scale, interpolation=cv2.INTER_AREA)
    screen = np.zeros((1080, 1920, 3), np.uint8)
    ph, pw = photo.shape[:2]
    sy, sx = max(0, (ph - 1080) // 2), max(0, (pw - 1920) // 2)
    crop = photo[sy:sy + 1080, sx:sx + 1920]
    oy, ox = (1080 - crop.shape[0]) // 2, (1920 - crop.shape[1]) // 2
    screen[oy:oy + crop.shape[0], ox:ox + crop.shape[1]] = crop
    cv2.putText(screen, f"photo {i + 1}/{len(files)}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
    cv2.imshow("photos", screen)
    cv2.waitKey(900)
    img = shoot()
    cv2.waitKey(1)
    prior = truth[i - 1] if i else truth[0]
    if i >= 2:                                                   # carried along the velocity
        prior = (2 * truth[i - 1][0] - truth[i - 2][0], 2 * truth[i - 1][1] - truth[i - 2][1])
    for name, M in matchers.items():
        st = state[name]
        t0 = time.time()
        if st["height"] is None:
            r = M.locate_any_height(img, prior, a.search_m, a.hfov, min_alt_m=80, max_alt_m=1200, heading_deg=0.0)
            if r["accepted"]:
                e = metres((r["predicted_lat"], r["predicted_lon"]), truth[i])
                agree = [c for c in st["first"] if abs(c[0] / r["altitude_m"] - 1) < 0.05]
                st["first"].append((r["altitude_m"],) + e)
                if agree:
                    st["height"] = float(np.median([r["altitude_m"]] + [c[0] for c in agree]))
                else:
                    r = dict(r, accepted=False)
        else:
            mpp = 2 * st["height"] * math.tan(math.radians(a.hfov / 2)) / img.shape[1]
            r = M.locate(img, prior, a.search_m, mpp, scale_tol=0.15, heading_deg=0.0)
            if r["accepted"]:                                    # the height follows the measured scale
                st["height"] *= 0.8 + 0.2 * float(r["scale_residual"])
        ms = (time.time() - t0) * 1000
        e = metres((r["predicted_lat"], r["predicted_lon"]), truth[i]) if r["accepted"] else None
        st["res"].append(dict(i=i, ok=bool(r["accepted"]), e=e, ms=ms, inliers=r.get("inliers"),
                              features=r.get("features", "sift")))
        print(f"photo {i:2d} {name:7s} " + (f"found, offset {e[0]:+6.1f} E {e[1]:+6.1f} N m, {r.get('inliers')} pts, "
                                            f"{r.get('features', 'sift')}" if e else "not found")
              + f"  ({ms:.0f} ms, height {st['height'] or 0:.0f} m)", flush=True)
cv2.destroyAllWindows()
print()
for name, st in state.items():
    found = [x for x in st["res"] if x["ok"]]
    if not found:
        print(f"{name:7s}: located 0/{len(files)}")
        continue
    E = np.array([x["e"] for x in found])
    bias = np.median(E, axis=0)                                   # the camera axis offset
    raw = np.hypot(E[:, 0], E[:, 1])
    cor = np.hypot(E[:, 0] - bias[0], E[:, 1] - bias[1])
    wrong = int((cor > 50).sum())
    good = cor[cor <= 50]
    print(f"{name:7s}: located {len(found)}/{len(files)}, wrong {wrong}; error (camera axis offset "
          f"{bias[0]:+.0f} E {bias[1]:+.0f} N m removed) median {np.median(good):.1f} m, 90% "
          f"{np.percentile(good, 90):.1f} m, max {good.max():.1f} m; raw median {np.median(raw):.1f} m; "
          f"{np.median([x['ms'] for x in st['res']]):.0f} ms/photo; height found {st['height'] or 0:.0f} m")
json.dump({k: v["res"] for k, v in state.items()}, open(a.out, "w"))

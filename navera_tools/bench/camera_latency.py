#!/usr/bin/env python3
"""Camera delay for NAVERA_CAMERA_LATENCY_S: the screen flashes white, the camera (facing
the screen) sees it some time later; the median of N flashes is printed.

    python3 navera_tools/bench/camera_latency.py [--device ...] [--crop top] [--flashes 20] [--calib camera.yaml]

What is measured is screen + camera + USB + decoding: the screen's own delay (typically
10-30 ms for a desktop monitor) is included, so the camera's delay is at most the result.
"""
import argparse
import threading
import time

import cv2
import numpy as np

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--device", default="/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0")
ap.add_argument("--size", default="1920x1080")
ap.add_argument("--crop", default="top", help="top / bottom / none: the half facing the screen")
ap.add_argument("--flashes", type=int, default=20)
ap.add_argument("--calib", help="write the result into this camera calibration file (latency_s): "
                                "live_camera then uses it when NAVERA_CAMERA_LATENCY_S is not set")
a = ap.parse_args()
w, h = (int(v) for v in a.size.split("x"))
cap = cv2.VideoCapture(a.device, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
samples = []                                   # (arrival time, brightness of the view centre)
stop = threading.Event()


def reader():
    while not stop.is_set():
        if not cap.grab():
            continue
        t = time.time()
        ok, f = cap.retrieve()
        if not ok:
            continue
        if a.crop == "top":
            f = f[:f.shape[0] // 2]
        elif a.crop == "bottom":
            f = f[f.shape[0] // 2:]
        H, W = f.shape[:2]
        samples.append((t, float(f[H // 4:3 * H // 4, W // 3:2 * W // 3].mean())))


th = threading.Thread(target=reader, daemon=True)
th.start()
black = np.zeros((1080, 1920, 3), np.uint8)
white = np.full((1080, 1920, 3), 255, np.uint8)
cv2.namedWindow("latency", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("latency", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
delays = []
for i in range(a.flashes):
    cv2.imshow("latency", black)
    cv2.waitKey(700)
    lo = np.median([b for t, b in samples[-8:]]) if samples else 0.0
    cv2.imshow("latency", white)
    cv2.waitKey(1)
    t0 = time.time()
    cv2.waitKey(700)
    hi = np.median([b for t, b in samples[-5:]])
    if hi - lo < 20:
        print(f"flash {i + 1}: the camera does not see the flash (brightness {lo:.0f} -> {hi:.0f})")
        continue
    seen = [t for t, b in samples if t > t0 - 0.2 and b > (lo + hi) / 2]
    if seen:
        delays.append(seen[0] - t0)
        print(f"flash {i + 1}: {1000 * delays[-1]:.0f} ms")
stop.set()
th.join(2)
cap.release()
cv2.destroyAllWindows()
if delays:
    print(f"delay screen -> NAVERA: median {1000 * np.median(delays):.0f} ms "
          f"(min {1000 * min(delays):.0f}, max {1000 * max(delays):.0f}, {len(delays)} flashes) — "
          f"NAVERA_CAMERA_LATENCY_S={np.median(delays):.2f} (includes the screen's own delay)")
    if a.calib:
        import yaml
        with open(a.calib) as f:
            d = yaml.safe_load(f)
        d["latency_s"] = round(float(np.median(delays)), 3)
        with open(a.calib, "w") as f:
            yaml.safe_dump(d, f, sort_keys=False)
        print(f"latency_s {d['latency_s']} written to {a.calib}")

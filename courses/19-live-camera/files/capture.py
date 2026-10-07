# Lesson 19 — grab frames from the camera (or the recorded frames), measure the frame
# rate, stamp each frame with its exposure time, and save the two halves.
#
#     python3 capture.py            # 60 frames (about 2 s)
#     python3 capture.py 150        # 150 frames
#
# It writes, in out/:
#   full.jpg, top.jpg, bottom.jpg   the last frame and its two halves (open them in the editor)
#   stamps.csv                      grab time and exposure time of every frame
#   capture_info.json               where the frames came from, fps, delay
# You don't need to change this file: finish the TODOs of camera_tools.py.

import csv
import json
import os
import sys

import cv2

from camera_tools import CALIB, FrameSource, exposure_time, load_latency, measure_fps, split_halves

n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
os.makedirs("out", exist_ok=True)

src = FrameSource()
if src.kind == "camera":
    print("📷 reading the REAL camera")
else:
    print(f"🎞️  no camera: {src.why}\n   -> reading the recorded frames of /data/academy/19-live-camera")

latency = load_latency(CALIB)
if latency is None:
    sys.exit("finish TODO 4 (load_latency) first")
print(f"camera delay from the calibration file: {latency} s")

grab_times = []
for i in range(n):
    t = src.grab()                      # cheap: wait for the frame and note the time
    if t is None:
        sys.exit("the camera stopped sending frames")
    grab_times.append(t)
img = src.retrieve()                    # expensive: decode ONLY the last frame
src.release()

fps = measure_fps(grab_times)
if fps is None:
    sys.exit("finish TODO 2 (measure_fps) first")
print(f"{n} frames in {grab_times[-1] - grab_times[0]:.2f} s -> {fps:.1f} fps")

with open("out/stamps.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["frame", "grab_time_s", "exposure_time_s"])
    for i, t in enumerate(grab_times):
        e = exposure_time(t, latency)
        if e is None:
            sys.exit("finish TODO 3 (exposure_time) first")
        w.writerow([i, f"{t:.4f}", f"{e:.4f}"])

halves = split_halves(img)
if halves is None:
    sys.exit("finish TODO 1 (split_halves) first")
top, bottom = halves
cv2.imwrite("out/full.jpg", img)
cv2.imwrite("out/top.jpg", top)
cv2.imwrite("out/bottom.jpg", bottom)
with open("out/capture_info.json", "w") as f:
    json.dump({"source": src.kind, "frames": n, "fps": round(fps, 2), "latency_s": latency,
               "frame_size": [img.shape[1], img.shape[0]], "top_size": [top.shape[1], top.shape[0]]}, f, indent=1)
print(f"saved out/full.jpg {img.shape[1]}x{img.shape[0]}, out/top.jpg {top.shape[1]}x{top.shape[0]}, "
      f"out/bottom.jpg {bottom.shape[1]}x{bottom.shape[0]}, out/stamps.csv, out/capture_info.json")

# Lesson 19 — grab frames from the camera (or the recorded frames), measure their timing,
# stamp each frame with its exposure time, and save the two halves of the last one.
#
#     python3 capture.py            # 60 frames (about 2 s)
#     python3 capture.py 150        # 150 frames
#
# It NEVER opens a camera that another program is using (it checks with `fuser` first):
# without a free camera it replays the recorded Insta360 frames at the camera's rhythm.
# It writes, in out/:
#   full.jpg, top.jpg, bottom.jpg   the last frame and its two halves (open them in the editor)
#   stamps.csv                      grab time and exposure time of every frame
#   capture_info.json               where the frames came from, timing statistics, delay
# You don't need to change this file: finish the TODOs of camera_tools.py.
import csv
import json
import os
import sys
import time

import cv2

from camera_tools import CALIB, FrameSource, exposure_time, frame_stats, load_latency, split_halves

n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
os.makedirs("out", exist_ok=True)

src = FrameSource()
if src.kind == "camera":
    print("📷 reading the REAL camera")
else:
    print(f"🎞️  no camera: {src.why}\n   -> replaying the recorded frames of /data/academy/19-live-camera")

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
t0 = time.perf_counter()
img = src.retrieve()                    # expensive: decode ONLY the last frame
decode_ms = (time.perf_counter() - t0) * 1000
src.release()

st = frame_stats(grab_times)
if st is None:
    sys.exit("finish TODO 2 (frame_stats) first")
print(f"{n} frames: {st['fps']:.2f} fps, median period {st['median_ms']:.2f} ms, jitter {st['jitter_ms']:.2f} ms, "
      f"max gap {st['max_gap_ms']:.1f} ms, ~{st['dropped']} dropped; retrieve() of the last one: {decode_ms:.0f} ms")

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
info = {"source": src.kind, "frames": n, "latency_s": latency, "retrieve_ms": round(decode_ms, 1),
        "frame_size": [img.shape[1], img.shape[0]], "top_size": [top.shape[1], top.shape[0]]}
info.update({k: (round(v, 3) if isinstance(v, float) else v) for k, v in st.items()})
with open("out/capture_info.json", "w") as f:
    json.dump(info, f, indent=1)
print(f"saved out/full.jpg {img.shape[1]}x{img.shape[0]}, out/top.jpg {top.shape[1]}x{top.shape[0]}, "
      f"out/bottom.jpg {bottom.shape[1]}x{bottom.shape[0]}, out/stamps.csv, out/capture_info.json")

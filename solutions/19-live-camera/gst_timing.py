#!/usr/bin/env python3
# Lesson 19 — measure frame timing on a LIVE GStreamer source, through NAVERA's own
# GstCapture class (camera_pkg/gst_capture.py in your NAVERA copy). No camera needed:
# `videotestsrc is-live=true` produces frames on a real clock, at 144/5 = 28.8 fps like the
# Insta360. The pixels are converted to BGR (OpenCV's order) and handed to us by an appsink
# that keeps only the newest frame — the same settings as NAVERA's CSI pipeline.
#
#     python3 gst_timing.py                  # grab as fast as frames come
#     python3 gst_timing.py --work-ms 50     # pretend each frame needs 50 ms of processing
#
# Writes out/gst_timing_w<work>.json (statistics from YOUR frame_stats()) and
# out/gst_grab_times_w<work>.csv. You don't need to change this file.
import argparse
import csv
import json
import os
import sys
import time

from camera_tools import frame_stats

sys.path.insert(0, os.path.expanduser("~/navera/camera_pkg"))
from camera_pkg.gst_capture import GstCapture       # noqa: E402  (NAVERA's real class)

ap = argparse.ArgumentParser()
ap.add_argument("--frames", type=int, default=150)
ap.add_argument("--work-ms", type=int, default=0, help="simulated processing time per frame")
ap.add_argument("--size", default="960x540")
a = ap.parse_args()
w, h = a.size.split("x")

PIPELINE = (f"videotestsrc is-live=true pattern=ball ! video/x-raw,width={w},height={h},framerate=144/5 ! "
            "videoconvert ! video/x-raw,format=BGR ! "
            "appsink name=sink drop=true max-buffers=1 sync=false")
print("pipeline:", PIPELINE.replace(" ! ", "\n   ! "))
cap = GstCapture(PIPELINE)
if not cap.isOpened():
    sys.exit("GStreamer could not start the pipeline")

times = []
for i in range(a.frames + 5):
    if not cap.grab():                       # waits for the next frame (paced by the source)
        sys.exit("no frame from GStreamer")
    t = time.time()
    if i >= 5:                               # skip the first frames (start-up)
        times.append(t)
    if a.work_ms:
        ok, img = cap.retrieve()             # get the pixels ...
        time.sleep(a.work_ms / 1000.0)       # ... and "process" them
cap.release()

st = frame_stats(times)
if st is None:
    sys.exit("finish TODO 2 (frame_stats) first")
os.makedirs("out", exist_ok=True)
# frames the source produced that we never saw (appsink drop=true kept only the newest)
st["lost_vs_nominal"] = int(round(28.8 * (times[-1] - times[0]))) - (len(times) - 1)
st.update(work_ms=a.work_ms, size=a.size, source="gstreamer videotestsrc 28.8 fps (live)")
with open(f"out/gst_timing_w{a.work_ms}.json", "w") as f:
    json.dump(st, f, indent=1)
with open(f"out/gst_grab_times_w{a.work_ms}.csv", "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["grab_time_s"])
    wr.writerows([[f"{t:.6f}"] for t in times])
print(f"\n{st['n']} frames, {st['fps']:.2f} fps, period {st['period_ms']:.2f} ms "
      f"(median {st['median_ms']:.2f}), jitter {st['jitter_ms']:.2f} ms, "
      f"max gap {st['max_gap_ms']:.1f} ms, dropped {st['dropped']}\n"
      f"the source made 28.8 frames/s: {st['lost_vs_nominal']} of its frames were never grabbed (dropped by the appsink)")
print(f"saved out/gst_timing_w{a.work_ms}.json")

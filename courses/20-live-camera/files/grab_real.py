"""grab_real.py — OPTIONAL (lab Step 12): time a REAL camera with YOUR frame_stats(). Only if you booked the class
camera in the dashboard (or you have your own USB camera on your own computer).

    python3 grab_real.py                          the first camera, 150 frames (about 5 s)
    python3 grab_real.py --device /dev/video2 --frames 300
    python3 grab_real.py --file clip.avi          a video file instead of a camera (to try the script anywhere;
                                                  a file has no live rhythm, so its numbers mean nothing)

It opens the camera like a live camera program does (V4L2, MJPG, 1920 × 1080 asked, a buffer of ONE frame),
grabs every frame, stamps each grab on the computer's clock, decodes only the last frame, and writes
out/real_camera.json and out/real_last.jpg. It refuses a camera that another program in your session is
using (fuser); the dashboard booking is what keeps other users off the shared camera.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----


def busy(device):
    """True if another process has the device open (fuser prints its process numbers)."""
    try:
        r = subprocess.run(["fuser", device], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and r.stdout.strip() != ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=None)
    ap.add_argument("--file", default=None)
    ap.add_argument("--frames", type=int, default=150)
    a = ap.parse_args()
    import cv2
    tm = rk.load_student("navera_lite.timing")
    if a.file:
        source, cap = a.file, cv2.VideoCapture(a.file)
    else:
        source = a.device or next(iter(sorted(glob.glob("/dev/video*"))), None)
        if source is None:
            sys.exit("no camera here (no /dev/video*): this step is optional — book the camera in the dashboard, "
                     "open a NEW terminal, and try again; or skip it")
        if busy(source):
            sys.exit(f"{source} is used by another program right now: never open a busy camera. Try later.")
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        sys.exit(f"cannot open {source}")
    stamps = []
    try:
        for _ in range(a.frames):
            if not cap.grab():                       # waits for the next frame, keeps it compressed
                break
            stamps.append(time.monotonic())          # the grab time, on the computer's clock
        t = time.perf_counter()
        ok, frame = cap.retrieve()                   # decode ONLY the last frame
        decode_ms = 1000 * (time.perf_counter() - t)
    finally:
        cap.release()
    if len(stamps) < 2:
        sys.exit(f"only {len(stamps)} frame(s) grabbed from {source}")
    s = rk.need_ok(tm, "frame_stats", stamps)
    os.makedirs("out", exist_ok=True)
    if ok:
        cv2.imwrite(os.path.join("out", "real_last.jpg"), frame)
    rec = {"source": source, "file": bool(a.file), "frames": len(stamps), "decode_ms": round(decode_ms, 2),
           "size": None if not ok else [int(frame.shape[1]), int(frame.shape[0])], **s}
    json.dump(rec, open(os.path.join("out", "real_camera.json"), "w"), indent=1, default=float)
    print(f"{source}: {s['n']} frames, {s['fps']:.2f} frames/s, median {s['median_ms']:.1f} ms, jitter "
          f"{s['jitter_ms']:.1f} ms, largest gap {s['max_gap_ms']:.0f} ms, dropped {s['dropped']}; "
          f"one decode {decode_ms:.1f} ms" + ("" if not ok else f"; picture {frame.shape[1]} × {frame.shape[0]}"))
    print("saved out/real_camera.json" + (" and out/real_last.jpg (open it: who is on it? do not share it)" if ok else ""))


if __name__ == "__main__":
    main()

# Lesson 19 — tools to read NAVERA's real camera (the Insta360 ONE R).
#
# Fill in the four TODOs, save (Ctrl+S), then try them:
#     python3 camera_tools.py
# The real work (camera or recorded frames) is done by capture.py, which uses these functions.

import numpy as np


def split_halves(frame):
    """The Insta360 sends ONE picture with its two lenses stacked: the top lens in the
    upper half, the bottom lens in the lower half (1920x1080 -> two 1920x540 halves).
    Return (top, bottom) as two numpy arrays.

    Remember (lesson 8): an image is an array frame[row, column], frame.shape[0] is
    the height (number of rows)."""
    # TODO 1: cut the frame in two at half its height and return (top, bottom)
    return None


def measure_fps(grab_times):
    """Frames per second from a list of grab times (seconds, in order).

    5 frames grabbed at 0.0, 0.1, 0.2, 0.3, 0.4 s -> 4 gaps in 0.4 s -> 10 fps.
    Return 0.0 when there are fewer than 2 times (no gap: no rate)."""
    # TODO 2: number of gaps divided by the time from the first to the last grab
    return None


def exposure_time(grab_time_s, latency_s):
    """The instant the picture was really taken. The camera needs `latency_s` seconds
    to expose, compress and send the picture: when we grab it, it is already that old."""
    # TODO 3: one line
    return None


def load_latency(calib_file):
    """The camera delay (seconds) stored as `latency_s` in a NAVERA calibration file
    (YAML). Return 0.0 when the file has no `latency_s` — like live_camera.py does."""
    import yaml
    with open(calib_file) as f:
        calib = yaml.safe_load(f)
    # TODO 4: `calib` is a dict. Return its "latency_s" as a float, or 0.0 if it is missing
    return None


# ---- you don't need to change anything below this line (but read it!) ----
import csv
import glob
import os
import time

DEVICE = "/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0"
RECORDED = "/data/academy/19-live-camera"
CALIB = RECORDED + "/insta360_top.yaml"


class FrameSource:
    """Frames from the real camera when it is here and free, else from recorded frames.

    Same two steps as NAVERA's live_camera.py (_grab_loop):
        t = src.grab()       wait for the next frame, note the time — cheap, no decoding
        img = src.retrieve() decode the last grabbed frame into an image — slow (MJPG)
    """

    def __init__(self, device=DEVICE, recorded=RECORDED, width=1920, height=1080):
        import cv2
        self.kind, self.why, self.cap = None, "", None
        if os.path.exists(device):
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))   # compressed frames
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)                            # newest frame, not a queue
            if cap.isOpened() and cap.grab():
                self.cap, self.kind = cap, "camera"
            else:
                cap.release()
                self.why = "the camera is there but sends nothing (busy? used by someone else?)"
        else:
            self.why = f"no {device} (camera not booked, or unplugged)"
        if self.kind is None:
            self.files = sorted(glob.glob(os.path.join(recorded, "frames", "*.jpg")))
            if not self.files:
                raise RuntimeError(f"no camera ({self.why}) and no recorded frames in {recorded}")
            with open(os.path.join(recorded, "grab_times.csv")) as f:
                rec = [float(r["grab_time_s"]) for r in csv.DictReader(f)]
            self.gaps = [b - a for a, b in zip(rec, rec[1:])]     # the recorded rhythm
            self.kind, self.i, self.next_t = "recorded", -1, None

    def grab(self):
        """Wait for the next frame. Returns its grab time (time.time(), s), or None."""
        if self.kind == "camera":
            return time.time() if self.cap.grab() else None
        self.i = (self.i + 1) % len(self.files)
        now = time.time()
        if self.next_t is not None and self.next_t > now:          # replay at the camera's rhythm
            time.sleep(self.next_t - now)
        t = time.time()
        self.next_t = t + self.gaps[self.i % len(self.gaps)]
        return t

    def retrieve(self):
        """The last grabbed frame as a BGR image (numpy array), or None."""
        import cv2
        if self.kind == "camera":
            ok, img = self.cap.retrieve()
            return img if ok else None
        return cv2.imread(self.files[self.i])

    def release(self):
        if self.cap is not None:
            self.cap.release()


if __name__ == "__main__":
    fake = np.zeros((1080, 1920, 3), np.uint8)
    fake[540:] = 255                                   # bottom half white
    halves = split_halves(fake)
    if halves is None:
        print("TODO 1 not done yet: split_halves() returns None")
    else:
        top, bottom = halves
        print("split_halves: top", top.shape, "mean", top.mean(), "| bottom", bottom.shape, "mean", bottom.mean())
    print("measure_fps([0, 0.1, 0.2, 0.3, 0.4]) =", measure_fps([0.0, 0.1, 0.2, 0.3, 0.4]), "(expected 10.0)")
    print("exposure_time(100.0, 0.138) =", exposure_time(100.0, 0.138), "(expected 99.862)")
    if os.path.exists(CALIB):
        print("load_latency(insta360_top.yaml) =", load_latency(CALIB), "(expected 0.138)")

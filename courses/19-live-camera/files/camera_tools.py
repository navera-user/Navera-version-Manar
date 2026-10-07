# Lesson 19 — timing tools for a live camera: frame statistics, the camera delay, and the
# attitude of the vehicle at the instant each picture was really taken.
#
# Fill in the TODOs (1 to 8), save (Ctrl+S), then try them:
#     python3 camera_tools.py
# The scripts of the lab (capture.py, gst_timing.py, analyse.py, compare_with_navera.py)
# import these functions. A TODO that is not done returns None, and the scripts tell you
# which one is missing.
#
# Each TODO says WHAT to compute and WHERE the lesson explains it. The "how" is yours.
# If the check fails, its hint gives you more help.
#
# Conventions (the same as lesson 16):
#   * times are in seconds (float), e.g. time.time()
#   * a quaternion is a numpy array (w, x, y, z), unit length
#     (ROS messages and NAVERA store (x, y, z, w) — compare_with_navera.py reorders them)

import bisect
import math

import numpy as np


# ======================================================================= part A: frames
def split_halves(frame):
    """The Insta360 sends ONE picture with its two lenses stacked: the top lens in the
    upper half, the bottom lens in the lower half (1920x1080 -> two 1920x540 halves).

    Input:  frame, a numpy image of shape (H, W, 3), any height H.
    Output: (top, bottom), two numpy images of shape (H/2, W, 3).
    Do not write 540: compute the half from the frame itself."""
    # TODO 1: return (top, bottom)
    return None


def frame_stats(grab_times):
    """Statistics of a list of grab times (seconds, in increasing order).
    Lesson section 5 defines every quantity and has a worked example.

    Input:  grab_times, a list (or array) of n floats.
    Output: a dict with exactly these keys:
      n           number of frames (int)
      fps         mean frame rate (n frames, but n - 1 intervals)
      period_ms   mean interval, in ms
      median_ms   median interval, in ms (the nominal period)
      jitter_ms   standard deviation of the intervals, in ms (population std, ddof = 0)
      max_gap_ms  largest interval, in ms
      dropped     estimated number of missing frames (int), with the 1.5 x median rule
    All values are 0 (0.0 for the floats) when n < 2."""
    # TODO 2: build and return the dict described above
    return None


def exposure_time(grab_time_s, latency_s):
    """The instant the picture was really taken (lesson section 6).
    Input: the grab time and the camera delay (s). Output: the exposure time (s)."""
    # TODO 3
    return None


def load_latency(calib_file):
    """The camera delay (seconds) stored as `latency_s` in a NAVERA calibration file
    (YAML). Return 0.0 when the file has no `latency_s` — like live_camera.py does."""
    import yaml
    with open(calib_file) as f:
        calib = yaml.safe_load(f)
    # TODO 4: `calib` is a dict. Output: a float (the delay, or 0.0)
    return None


# ======================================================================= part B: the delay
def latency_from_flashes(flash_times, frame_times, brightness):
    """The screen-flash method of navera_tools/bench/camera_latency.py (lesson section 6).

    flash_times  when the program turned the screen white (s)
    frame_times  grab time of every frame (s, increasing)
    brightness   brightness of the centre of every frame (same length as frame_times)

    The exact rule (it is NAVERA's), for each flash time t0:
      lo = median brightness of the frames grabbed in [t0 - 0.3, t0)
      hi = median brightness of the frames grabbed in [t0 + 0.4, t0 + 0.65]
      if a window is empty, or hi - lo < 20: the camera did not see this flash -> skip it
      otherwise the delay is  t - t0  for the FIRST frame with t >= t0 and
      brightness > (lo + hi) / 2
    Output: the list of delays (s), in the order of the flashes."""
    # TODO 5: implement the rule above
    return None


# ======================================================================= part C: attitude
def quat_angle_deg(q0, q1):
    """The angle (degrees, 0..180) of the rotation between two unit quaternions.
    The formula is at the end of lesson section 8. Two traps (both are tested):
      * q and -q are the same attitude: the result must be 0 for them;
      * rounding can push a dot product to 1.0000000002, and acos() then fails."""
    # TODO 6
    return None


def slerp(q0, q1, f):
    """Spherical linear interpolation between unit quaternions, f in [0, 1].
    Lesson section 8 gives the formula and its THREE practical rules (shortest path,
    almost-equal quaternions with dot > 0.9995, normalise). Apply all three.
    Output: a unit quaternion, as a numpy array (w, x, y, z)."""
    # TODO 7
    return None


def attitude_at(t, imu_times, imu_quats, max_gap_s=0.2):
    """The attitude at time t from IMU samples (times increasing, quats (w,x,y,z)).
    Use the same rule as NAVERA's navera_common/sensor_history.py (History.at), described
    at the end of lesson section 8 ("When there is no sample"):
      * t before the first sample: the first quaternion if it is at most max_gap_s away, else None
      * t after the last sample:   the last quaternion if it is at most max_gap_s away, else None
      * t between two samples t0 <= t <= t1:
          None inside a hole (t1 - t0 > 2 * max_gap_s) when t is more than max_gap_s from
          both sides; otherwise interpolate q0 -> q1 with your slerp.
    The module `bisect` (already imported) finds the two samples around t quickly."""
    # TODO 8
    return None


# ---- you don't need to change anything below this line (but read it!) ----
import csv
import glob
import os
import shutil
import subprocess
import time

DEVICE = "/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0"
DATA = "/data/academy/19-live-camera"
CALIB = DATA + "/insta360_top.yaml"


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def q_yaw(deg):
    """A pure heading rotation (about z) as (w, x, y, z)."""
    a = math.radians(deg) / 2
    return np.array([math.cos(a), 0.0, 0.0, math.sin(a)])


def camera_busy(device):
    """True when another process already has the camera open (we never open a busy camera)."""
    if shutil.which("fuser") is None:
        return False
    r = subprocess.run(["fuser", os.path.realpath(device)], capture_output=True, text=True)
    return bool(r.stdout.strip())


class FrameSource:
    """Frames from the real camera when it is here and free, else from recorded frames.

    Same two steps as NAVERA's live_camera.py (_grab_loop):
        t = src.grab()       wait for the next frame, note the time — cheap, no decoding
        img = src.retrieve() decode the last grabbed frame into an image — slow (MJPG)
    """

    def __init__(self, device=DEVICE, recorded=DATA, width=1920, height=1080):
        import cv2
        self.kind, self.why, self.cap = None, "", None
        if not os.path.exists(device):
            self.why = f"no {device} (camera not booked, or unplugged)"
        elif camera_busy(device):
            self.why = "the camera is used by another program right now (fuser) — not opened"
        else:
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))   # compressed frames
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)                            # newest frame, not a queue
            if cap.isOpened() and cap.grab():
                self.cap, self.kind = cap, "camera"
            else:
                cap.release()
                self.why = "the camera is there but sends nothing"
        if self.kind is None:
            self.files = sorted(glob.glob(os.path.join(recorded, "frames", "*.jpg")))
            if not self.files:
                raise RuntimeError(f"no camera ({self.why}) and no recorded frames in {recorded}")
            rec = [float(r["grab_time_s"]) for r in read_csv(os.path.join(recorded, "grab_times.csv"))]
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
    fake[540:] = 255
    r = split_halves(fake)
    print("1 split_halves:", None if r is None else [(x.shape, float(x.mean())) for x in r],
          "(expected top (540,1920,3) mean 0.0, bottom mean 255.0)")
    print("2 frame_stats([0, .1, .2, .4, .5]):", frame_stats([0.0, 0.1, 0.2, 0.4, 0.5]),
          "(expected fps 8.0, median 100 ms, max gap 200 ms, dropped 1)")
    print("3 exposure_time(100.0, 0.138) =", exposure_time(100.0, 0.138), "(expected 99.862)")
    if os.path.exists(CALIB):
        print("4 load_latency(insta360_top.yaml) =", load_latency(CALIB), "(expected 0.138)")
    ft = [i * 0.05 for i in range(40)]
    br = [30.0 if t < 1.12 else 200.0 for t in ft]
    print("5 latency_from_flashes([1.0], ...) =", latency_from_flashes([1.0], ft, br), "(expected [0.15])")
    print("6 quat_angle_deg(yaw 10, yaw 40) =", quat_angle_deg(q_yaw(10), q_yaw(40)), "(expected 30.0)")
    s = slerp(q_yaw(0), q_yaw(90), 0.5)
    print("7 slerp(yaw 0, yaw 90, 0.5) =", s, "(expected yaw 45: [0.924 0 0 0.383])")
    print("8 attitude_at(0.1, [0, 0.2], [yaw 0, yaw 20]) =", attitude_at(0.1, [0.0, 0.2], [q_yaw(0), q_yaw(20)]),
          "(expected yaw 10: [0.996 0 0 0.087])")

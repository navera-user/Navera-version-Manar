"""Lesson 23 — Visual odometry: count your steps with a camera.

Run:   python3 vo.py sheet                  a contact sheet of the flight's photos (frames.png)
       python3 vo.py pair 10                look at one step: frames 10 and 11
       python3 vo.py                        the whole flight: track, drift, map fixes, two PNGs
       python3 vo.py --altitude 114.25      the same, with another altitude than the barometer's
"""
import csv
import json
import math
import os
import sys

import cv2
import numpy as np

DATA = "/data/academy/23-visual-odometry"


# TODO 1: meters per pixel of a nadir camera (lesson 17)
def frame_m_per_px(altitude_m, hfov_deg, width_px):
    """Ground size of one pixel: footprint width / image width.
    footprint width = 2 x altitude x tan(hfov / 2)."""
    return 2.0 * altitude_m * math.tan(math.radians(hfov_deg) / 2.0) / width_px


# TODO 2: how far did the picture slide between two frames?
def frame_shift(prev, cur):
    """(dx, dy) in pixels: how much the ground moved in the picture from prev to cur.
    dx > 0: the ground moved RIGHT, dy > 0: the ground moved DOWN."""
    a, b = to_grey_float(prev), to_grey_float(cur)
    window = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(a, b, window)
    return dx, dy


# TODO 3: from a picture shift to a drone movement
def pixels_to_meters(dx, dy, m_per_px):
    """(east, north) in meters moved by the DRONE when the ground slid (dx, dy) pixels
    in a north-up picture. The ground slides the opposite way to the drone, and the
    image's y axis points DOWN (south)."""
    return -dx * m_per_px, dy * m_per_px


# TODO 4: add up the steps
def integrate(steps, start=(0.0, 0.0)):
    """The track: a list of (east, north) positions, one per frame.
    track[0] = start, track[i] = track[i-1] + steps[i-1]  (len(track) == len(steps) + 1)."""
    track = [tuple(start)]
    e, n = start
    for de, dn in steps:
        e, n = e + de, n + dn
        track.append((e, n))
    return track


# TODO 5: how fast does the error grow?
def drift_per_100m(track, truth):
    """Final position error (m) for every 100 m flown along the true path.
    truth: the true (east, north) of every frame, same length as track."""
    flown = sum(math.hypot(truth[i][0] - truth[i - 1][0], truth[i][1] - truth[i - 1][1])
                for i in range(1, len(truth)))
    err = math.hypot(track[-1][0] - truth[-1][0], track[-1][1] - truth[-1][1])
    return 100.0 * err / flown


# TODO 6: reset the drift with map fixes
def with_map_fixes(steps, fixes, start=(0.0, 0.0)):
    """Like integrate(), but at every frame i that has a map fix (fixes = {i: (east, north)})
    the position is REPLACED by the fix; the next steps continue from there."""
    track = [tuple(start)]
    e, n = start
    for i, (de, dn) in enumerate(steps, start=1):
        e, n = e + de, n + dn
        if i in fixes:
            e, n = fixes[i]
        track.append((e, n))
    return track


# ---- you don't need to change anything below this line ----

def to_grey_float(img):
    """A colour picture → grey, float32 (what phaseCorrelate wants)."""
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img.astype(np.float32)


def load_flight():
    with open(os.path.join(DATA, "info.json")) as f:
        info = json.load(f)
    truth, frames = [], []
    with open(os.path.join(DATA, "truth.csv")) as f:
        for r in csv.DictReader(f):
            truth.append((float(r["east_m"]), float(r["north_m"])))
            frames.append(os.path.join(DATA, "frames", r["file"]))
    fixes = {}
    with open(os.path.join(DATA, "map_fixes.csv")) as f:
        for r in csv.DictReader(f):
            fixes[int(r["frame"])] = (float(r["east_m"]), float(r["north_m"]))
    return info, frames, truth, fixes


def measure_steps(frames, m_per_px):
    """Visual odometry: one (east, north) step per pair of consecutive frames."""
    steps, prev = [], cv2.imread(frames[0])
    for path in frames[1:]:
        cur = cv2.imread(path)
        dx, dy = frame_shift(prev, cur)
        steps.append(pixels_to_meters(dx, dy, m_per_px))
        prev = cur
    return steps


def errors(track, truth):
    return [math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(track, truth)]


def plot(truth, track, fixed, fixes, path_track="vo_track.png", path_err="vo_error.png"):
    import warnings
    warnings.filterwarnings("ignore", message="Unable to import Axes3D")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.plot(*zip(*truth), "-", color="#1d2733", lw=2, label="truth")
    ax.plot(*zip(*track), "-", color="#d64545", label="visual odometry only")
    if fixed:
        ax.plot(*zip(*fixed), "-", color="#0b6e8a", label="odometry + map fixes")
        ax.plot(*zip(*fixes.values()), "o", color="#f2a33a", label="map fixes")
    ax.plot(*truth[0], "k^", ms=9)
    ax.set_xlabel("east (m)")
    ax.set_ylabel("north (m)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_title("Synthetic flight over Sousse: where the drone thinks it is")
    fig.savefig(path_track, dpi=90, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(errors(track, truth), color="#d64545", label="visual odometry only")
    if fixed:
        ax.plot(errors(fixed, truth), color="#0b6e8a", label="odometry + map fixes")
        for i in fixes:
            ax.axvline(i, color="#f2a33a", lw=0.8, ls=":")
    ax.set_xlabel("frame (one every 20 m)")
    ax.set_ylabel("position error (m)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.savefig(path_err, dpi=90, bbox_inches="tight")
    plt.close(fig)


def show_pair(i):
    info, frames, truth, _ = load_flight()
    mpp = frame_m_per_px(info["altitude_m"], info["camera_hfov_deg"], info["width_px"])
    a, b = cv2.imread(frames[i]), cv2.imread(frames[i + 1])
    dx, dy = frame_shift(a, b)
    de, dn = pixels_to_meters(dx, dy, mpp)
    te, tn = truth[i + 1][0] - truth[i][0], truth[i + 1][1] - truth[i][1]
    print(f"frames {i} -> {i + 1}: the ground slid dx = {dx:+.2f} px, dy = {dy:+.2f} px")
    print(f"  the drone moved   east {de:+6.2f} m, north {dn:+6.2f} m   (m per px = {mpp:.4f})")
    print(f"  the truth says    east {te:+6.2f} m, north {tn:+6.2f} m")
    sheet = np.hstack([a, np.full((a.shape[0], 6, 3), 255, np.uint8), b])
    cv2.imwrite(f"pair_{i}.png", sheet)
    print(f"  saved pair_{i}.png (left: frame {i}, right: frame {i + 1})")


def show_sheet():
    _, frames, _, _ = load_flight()
    small = [cv2.resize(cv2.imread(p), (160, 120)) for p in frames]
    rows = [np.hstack(small[r:r + 10]) for r in range(0, len(small), 10)]
    for k, im in enumerate(small):
        r, c = divmod(k, 10)
        cv2.putText(rows[r], str(k), (c * 160 + 4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite("frames.png", np.vstack(rows))
    print(f"saved frames.png: the {len(frames)} photos of the flight, 10 per row, in order")


def main(altitude=None):
    info, frames, truth, fixes = load_flight()
    alt = info["altitude_m"] if altitude is None else altitude
    mpp = frame_m_per_px(alt, info["camera_hfov_deg"], info["width_px"])
    print(f"{len(frames)} frames, camera at {alt} m ({'barometer' if altitude is None else 'your value'}), "
          f"{info['camera_hfov_deg']} deg, {info['width_px']} px wide -> {mpp:.4f} m per pixel")
    steps = measure_steps(frames, mpp)
    track = integrate(steps)
    err = errors(track, truth)
    print(f"visual odometry only : final error {err[-1]:6.1f} m, worst {max(err):6.1f} m, "
          f"drift {drift_per_100m(track, truth):.2f} m per 100 m")
    try:
        fixed = with_map_fixes(steps, fixes)
    except NotImplementedError:
        fixed = None
        print("with_map_fixes(): TODO 6 not done yet — the plots show odometry only")
    if fixed is not None:
        errf = errors(fixed, truth)
        print(f"with a map fix every {min(fixes)} frames: final error {errf[-1]:6.1f} m, worst {max(errf):6.1f} m")
    plot(truth, track, fixed, fixes)
    print("saved vo_track.png and vo_error.png")


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "pair":
            show_pair(int(sys.argv[2]))
        elif len(sys.argv) >= 2 and sys.argv[1] == "sheet":
            show_sheet()
        elif len(sys.argv) >= 3 and sys.argv[1] == "--altitude":
            main(float(sys.argv[2]))
        else:
            main()
    except NotImplementedError as e:
        print(f"Not finished yet: {e} is still to do. Read the lab, fill it in, save, and run again.")
        sys.exit(1)

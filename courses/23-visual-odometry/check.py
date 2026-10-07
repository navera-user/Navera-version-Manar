import csv
import json
import math
import os

import cv2
import numpy as np

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()
DATA = "/data/academy/23-visual-odometry"
# reference values measured with the teacher's solution on this dataset
REF_PAIR_10 = (15.73, 36.89)        # ground shift frames 10 -> 11, pixels
REF_FINAL_ERR = 55.5                # m, odometry only, barometer altitude
REF_DRIFT = 3.52                    # m per 100 m


def flight():
    with open(os.path.join(DATA, "info.json")) as f:
        info = json.load(f)
    with open(os.path.join(DATA, "truth.csv")) as f:
        rows = list(csv.DictReader(f))
    truth = [(float(r["east_m"]), float(r["north_m"])) for r in rows]
    frames = [os.path.join(DATA, "frames", r["file"]) for r in rows]
    with open(os.path.join(DATA, "map_fixes.csv")) as f:
        fixes = {int(r["frame"]): (float(r["east_m"]), float(r["north_m"])) for r in csv.DictReader(f)}
    return info, frames, truth, fixes


def pair2(v, what):
    try:
        a, b = v
        return float(a), float(b)
    except Exception:
        raise CheckFailed(f"{what} should be a pair of two numbers like (1.5, -2.0), got {v!r}")


_cache = {}


def student_flight():
    """Steps and tracks computed with the student's own functions (once)."""
    if not _cache:
        m = load_student("vo.py")
        fm, fs, pm, integ = need(m, "frame_m_per_px", "frame_shift", "pixels_to_meters", "integrate")
        info, frames, truth, fixes = flight()
        mpp = float(fm(info["altitude_m"], info["camera_hfov_deg"], info["width_px"]))
        steps, prev = [], cv2.imread(frames[0])
        for p in frames[1:]:
            cur = cv2.imread(p)
            dx, dy = pair2(fs(prev, cur), "frame_shift()")
            steps.append(pair2(pm(dx, dy, mpp), "pixels_to_meters()"))
            prev = cur
        track = [pair2(p, "a track point") for p in integ(steps)]
        _cache.update(steps=steps, track=track, truth=truth, fixes=fixes)
    return _cache


@c.test("frame_m_per_px() gives the ground size of a pixel",
        hint="footprint width = 2 × altitude × tan(hfov/2), then divide by the width in pixels. "
             "math.tan wants radians: math.radians(hfov / 2).")
def _():
    (f,) = need(load_student("vo.py"), "frame_m_per_px")
    c.near(f(114.25, 70, 320), 0.5000, tol=0.002, what="frame_m_per_px(114.25, 70, 320)")
    c.near(f(100, 90, 1000), 0.2000, tol=0.001, what="frame_m_per_px(100, 90, 1000)")


@c.test("frame_shift() measures a known slide of a picture (within 0.5 px)",
        hint="Use cv2.phaseCorrelate(a, b, window) on grey float32 images, with a Hanning window. "
             "Return (dx, dy), the first thing phaseCorrelate gives back.")
def _():
    (fs,) = need(load_student("vo.py"), "frame_shift")
    img = cv2.imread(os.path.join(DATA, "frames", "frame_030.jpg"))
    for tx, ty in ((6.5, -3.0), (-11.0, 8.25)):
        M = np.float32([[1, 0, tx], [0, 1, ty]])
        moved = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REFLECT)
        dx, dy = pair2(fs(img, moved), "frame_shift()")
        c.ok(abs(dx - tx) <= 0.5 and abs(dy - ty) <= 0.5,
             f"the picture was slid by ({tx}, {ty}) px, frame_shift() says ({dx:.2f}, {dy:.2f})")


@c.test("frame_shift() on two real frames of the flight (10 → 11)",
        hint="Compare the PREVIOUS frame with the CURRENT one, in that order: phaseCorrelate(prev, cur).")
def _():
    (fs,) = need(load_student("vo.py"), "frame_shift")
    a = cv2.imread(os.path.join(DATA, "frames", "frame_010.jpg"))
    b = cv2.imread(os.path.join(DATA, "frames", "frame_011.jpg"))
    dx, dy = pair2(fs(a, b), "frame_shift()")
    c.ok(abs(dx - REF_PAIR_10[0]) <= 1.0 and abs(dy - REF_PAIR_10[1]) <= 1.0,
         f"got ({dx:.2f}, {dy:.2f}) px, expected about ({REF_PAIR_10[0]}, {REF_PAIR_10[1]})")


@c.test("pixels_to_meters() has the right signs",
        hint="The ground slides the OPPOSITE way to the drone. Ground slides left (dx < 0) → the drone went "
             "east. Ground slides down (dy > 0, the image y axis points down) → the drone went north.")
def _():
    (pm,) = need(load_student("vo.py"), "pixels_to_meters")
    e, n = pair2(pm(-10, 0, 0.5), "pixels_to_meters(-10, 0, 0.5)")
    c.ok(abs(e - 5.0) < 1e-6 and abs(n) < 1e-6, f"pixels_to_meters(-10, 0, 0.5) = ({e}, {n}), expected (5.0, 0.0)")
    e, n = pair2(pm(0, 10, 0.5), "pixels_to_meters(0, 10, 0.5)")
    c.ok(abs(e) < 1e-6 and abs(n - 5.0) < 1e-6, f"pixels_to_meters(0, 10, 0.5) = ({e}, {n}), expected (0.0, 5.0)")
    e, n = pair2(pm(4, -2, 2.0), "pixels_to_meters(4, -2, 2.0)")
    c.ok(abs(e + 8.0) < 1e-6 and abs(n + 4.0) < 1e-6, f"pixels_to_meters(4, -2, 2.0) = ({e}, {n}), expected (-8.0, -4.0)")


@c.test("integrate() adds up the steps into a track",
        hint="Start the list with `start`, then add each step to the last position. "
             "The track has one point more than there are steps.")
def _():
    (integ,) = need(load_student("vo.py"), "integrate")
    t = [pair2(p, "a track point") for p in integ([(1, 2), (3, -1), (0, 5)])]
    c.eq([tuple(round(v, 6) for v in p) for p in t], [(0, 0), (1, 2), (4, 1), (4, 6)], "integrate([(1,2),(3,-1),(0,5)])")
    t = [pair2(p, "a track point") for p in integ([(1, 1)], start=(10, 20))]
    c.eq([tuple(round(v, 6) for v in p) for p in t], [(10, 20), (11, 21)], "integrate([(1,1)], start=(10,20))")


@c.test("drift_per_100m() on a simple example",
        hint="Distance flown = sum of the lengths of the TRUE steps. Error = distance between the last "
             "track point and the last true point. Answer = 100 × error / distance flown.")
def _():
    (d,) = need(load_student("vo.py"), "drift_per_100m")
    truth = [(0, 0), (0, 100), (0, 200), (0, 300)]
    track = [(0, 0), (1, 99), (2, 199), (6, 300)]
    c.near(d(track, truth), 2.0, tol=1e-6, what="drift_per_100m(...) for 6 m off after 300 m")
    truth = [(0, 0), (30, 40), (30, 90)]       # 50 m + 50 m
    track = [(0, 0), (30, 40), (33, 94)]       # 5 m off
    c.near(d(track, truth), 5.0, tol=1e-6, what="drift_per_100m(...) for 5 m off after 100 m")


@c.test("with_map_fixes() replaces the position at each fix",
        hint="Same loop as integrate(); after adding step i, if i is a key of `fixes`, the position "
             "becomes fixes[i]. The following steps start from the fix.")
def _():
    (w,) = need(load_student("vo.py"), "with_map_fixes")
    t = [pair2(p, "a track point") for p in w([(10, 0)] * 4, {2: (0, 0)})]
    c.eq([tuple(round(v, 6) for v in p) for p in t], [(0, 0), (10, 0), (0, 0), (10, 0), (20, 0)],
         "with_map_fixes([(10,0)]*4, {2: (0,0)})")


@c.test(f"the whole flight: final error about {REF_FINAL_ERR:.0f} m with odometry only",
        hint="Run `python3 vo.py`. If the track goes the wrong way, check the signs of TODO 3; if it is "
             "far too short or long, check TODO 1 (altitude from info.json, the barometer's).")
def _():
    s = student_flight()
    e = math.dist(s["track"][-1], s["truth"][-1])
    c.ok(len(s["track"]) == len(s["truth"]), f"the track has {len(s['track'])} points, expected {len(s['truth'])}")
    c.near(e, REF_FINAL_ERR, tol=8.0, what="the final error (m)")


@c.test(f"the drift is measured: about {REF_DRIFT} m per 100 m",
        hint="drift_per_100m(track, truth) with the track of the whole flight.")
def _():
    (d,) = need(load_student("vo.py"), "drift_per_100m")
    s = student_flight()
    c.near(d(s["track"], s["truth"]), REF_DRIFT, tol=0.6, what="drift per 100 m")


@c.test("map fixes every 10 frames keep the error small (worst < 1/3 of odometry alone, < 20 m)",
        hint="with_map_fixes(steps, fixes) with the fixes of map_fixes.csv: the error should fall back at "
             "frames 10, 20, 30…")
def _():
    (w,) = need(load_student("vo.py"), "with_map_fixes")
    s = student_flight()
    fixed = [pair2(p, "a track point") for p in w(s["steps"], s["fixes"])]
    worst_vo = max(math.dist(a, b) for a, b in zip(s["track"], s["truth"]))
    worst_fx = max(math.dist(a, b) for a, b in zip(fixed, s["truth"]))
    c.ok(worst_fx < worst_vo / 3 and worst_fx < 20,
         f"worst error with fixes {worst_fx:.1f} m, odometry alone {worst_vo:.1f} m")


@c.test("python3 vo.py runs and draws vo_track.png and vo_error.png",
        hint="Run `python3 vo.py` in the terminal and read its last lines.")
def _():
    for f in ("vo_track.png", "vo_error.png"):
        if os.path.exists(f):
            os.remove(f)
    code, out = sh("python3 vo.py", timeout=90)
    c.ok(code == 0, "vo.py stopped with an error:\n" + out[-600:])
    c.file_exists("vo_track.png")
    c.file_exists("vo_error.png")


c.run()

import csv
import json
import math
import os
import re

import cv2
import numpy as np

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()
DATA = "/data/academy/24-visual-odometry"
# reference values measured with the teacher's solution on this dataset (OpenCV 4.11, numpy 1.26)
REF_PAIR_10 = (15.73, 36.89)        # ground shift frames 10 -> 11, pixels (cv2.phaseCorrelate)
REF_FINAL_ERR = 54.3                # m, odometry only, barometer height
REF_DRIFT = 3.43                    # m per 100 m, barometer height
REF_DRIFT_TRUE_H = 2.59             # m per 100 m, height 114.25 m
REF_NAVERA_DRIFT = 3.57             # NAVERA FrameOdometry, m per 100 m


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


def nums(v, k, what):
    try:
        out = tuple(float(x) for x in v)
    except Exception:
        raise CheckFailed(f"{what} should be a tuple of {k} numbers, got {v!r}")
    if len(out) != k:
        raise CheckFailed(f"{what} should be a tuple of {k} numbers, got {len(out)} of them: {v!r}")
    return out


def V():
    return load_student("vo.py")


def grey(name):
    return cv2.imread(os.path.join(DATA, "frames", name), cv2.IMREAD_GRAYSCALE).astype(np.float32)


_cache = {}


def student_flight():
    if not _cache:
        fm, fs, se, integ = need(V(), "frame_m_per_px", "frame_shift", "shift_to_east_north", "integrate")
        info, frames, truth, fixes = flight()
        mpp = float(fm(info["altitude_m"], info["camera_hfov_deg"], info["width_px"]))
        steps, prev = [], cv2.imread(frames[0])
        for p in frames[1:]:
            cur = cv2.imread(p)
            dx, dy = nums(fs(prev, cur, "numpy"), 2, "frame_shift(prev, cur, 'numpy')")
            steps.append(nums(se(dx, dy, mpp, 0.0), 2, "shift_to_east_north()"))
            prev = cur
        track = [nums(p, 2, "a track point") for p in integ(steps)]
        _cache.update(steps=steps, track=track, truth=truth, fixes=fixes, mpp=mpp, frames=frames)
    return _cache


@c.test("TODO 1 — frame_m_per_px() gives the ground size of a pixel",
        hint="footprint = 2 × h × tan(HFOV/2), divided by the width in pixels. math.tan wants radians.")
def _():
    (f,) = need(V(), "frame_m_per_px")
    c.near(f(114.25, 70, 320), 0.5000, tol=0.002, what="frame_m_per_px(114.25, 70, 320)")
    c.near(f(100, 90, 1000), 0.2000, tol=0.001, what="frame_m_per_px(100, 90, 1000)")


@c.test("TODO 2 — phase_correlation() finds an integer circular shift exactly, with a high peak",
        hint="Peak of the inverse FFT of the normalised cross-power spectrum Fb·conj(Fa)/|…|. "
             "Indices past the middle of the array are negative shifts.")
def _():
    (pc,) = need(V(), "phase_correlation")
    a = grey("frame_030.jpg")
    for sx, sy in ((-12, 7), (25, -9)):
        b = np.roll(a, (sy, sx), axis=(0, 1))
        dx, dy, r = nums(pc(a, b), 3, "phase_correlation(a, b)")
        c.ok(abs(dx - sx) < 0.1 and abs(dy - sy) < 0.1,
             f"b = a rolled by dx={sx}, dy={sy}: your function says ({dx:.2f}, {dy:.2f})")
        c.ok(r > 0.5, f"the peak value (response) for an exact shift is {r:.3f}; expected > 0.5 "
                      "(did you normalise the cross-power spectrum?)")


@c.test("TODO 2 — phase_correlation() is sub-pixel (half-pixel shifts within 0.15 px)",
        hint="Fit a parabola through the peak and its two neighbours, separately in x and y: "
             "offset = (c₋ − c₊) / (2 (c₋ − 2c₀ + c₊)).")
def _():
    (pc,) = need(V(), "phase_correlation")
    big = cv2.resize(cv2.imread(os.path.join(DATA, "frames", "frame_030.jpg"), 0), None, fx=4, fy=4,
                     interpolation=cv2.INTER_CUBIC).astype(np.float32)

    def view(ox, oy):        # a 280 x 200 picture whose content is shifted by (-ox/4, -oy/4) px
        return cv2.resize(big[40 + oy:40 + oy + 800, 40 + ox:40 + ox + 1120], (280, 200), interpolation=cv2.INTER_AREA)

    a = view(0, 0)
    for ox, oy in ((-2, 0), (0, 6), (-6, -2)):
        dx, dy, _ = nums(pc(a, view(ox, oy)), 3, "phase_correlation(a, b)")
        tx, ty = -ox / 4.0, -oy / 4.0
        c.ok(abs(dx - tx) <= 0.15 and abs(dy - ty) <= 0.15,
             f"true shift ({tx}, {ty}) px, your function says ({dx:.3f}, {dy:.3f})")


@c.test("TODO 2 — two unrelated pictures give a low response (< 0.1)",
        hint="The response is the value of the correlation peak. With nothing in common there is no clear peak.")
def _():
    (pc,) = need(V(), "phase_correlation")
    rng = np.random.default_rng(7)
    _, _, r = nums(pc(rng.normal(size=(240, 320)), rng.normal(size=(240, 320))), 3, "phase_correlation()")
    c.ok(r < 0.1, f"response {r:.3f} for two random noise pictures")


@c.test("TODO 3 — frame_shift(): numpy and OpenCV agree on frames 10 → 11; unknown method → ValueError",
        hint="'opencv': cv2.createHanningWindow((WIDTH, HEIGHT), cv2.CV_32F) and cv2.phaseCorrelate(a, b, window). "
             "Keep the order (prev, cur).")
def _():
    (fs,) = need(V(), "frame_shift")
    a = cv2.imread(os.path.join(DATA, "frames", "frame_010.jpg"))
    b = cv2.imread(os.path.join(DATA, "frames", "frame_011.jpg"))
    for m in ("opencv", "numpy"):
        dx, dy = nums(fs(a, b, m), 2, f"frame_shift(a, b, '{m}')")
        c.ok(abs(dx - REF_PAIR_10[0]) <= 0.5 and abs(dy - REF_PAIR_10[1]) <= 0.5,
             f"method {m}: ({dx:.2f}, {dy:.2f}) px, expected about {REF_PAIR_10}")
    try:
        fs(a, b, "magic")
    except ValueError:
        return
    c.ok(False, "frame_shift(a, b, 'magic') did not raise ValueError")


@c.test("TODO 4 — shift_to_east_north(): signs with a north-up photo and with a heading",
        hint="right = −dx·m_per_px, forward = +dy·m_per_px (the ground moves the other way, y points down); "
             "then east = fwd·sinθ + right·cosθ, north = fwd·cosθ − right·sinθ.")
def _():
    (se,) = need(V(), "shift_to_east_north")
    cases = [((-10, 0, 0.5, 0.0), (5.0, 0.0)), ((0, 10, 0.5, 0.0), (0.0, 5.0)),
             ((0, 10, 0.5, 90.0), (5.0, 0.0)), ((-10, 0, 0.5, 90.0), (0.0, -5.0)),
             ((4, -2, 2.0, 0.0), (-8.0, -4.0)), ((0, 20, 1.0, 210.0), (-10.0, -17.3205))]
    for args, want in cases:
        e, n = nums(se(*args), 2, f"shift_to_east_north{args}")
        c.ok(abs(e - want[0]) < 1e-3 and abs(n - want[1]) < 1e-3,
             f"shift_to_east_north{args} = ({e:.3f}, {n:.3f}), expected {want}")


@c.test("TODO 5, 6 — integrate() and drift_per_100m() on small examples",
        hint="integrate: start, then add each step (n steps → n + 1 points). "
             "drift: 100 × final error / length of the TRUE path.")
def _():
    integ, d = need(V(), "integrate", "drift_per_100m")
    t = [tuple(round(v, 6) for v in nums(p, 2, "a track point")) for p in integ([(1, 2), (3, -1), (0, 5)])]
    c.eq(t, [(0, 0), (1, 2), (4, 1), (4, 6)], "integrate([(1,2),(3,-1),(0,5)])")
    t = [tuple(round(v, 6) for v in nums(p, 2, "a track point")) for p in integ([(1, 1)], start=(10, 20))]
    c.eq(t, [(10, 20), (11, 21)], "integrate([(1,1)], start=(10,20))")
    c.near(d([(0, 0), (1, 99), (2, 199), (6, 300)], [(0, 0), (0, 100), (0, 200), (0, 300)]), 2.0, 1e-6,
           "drift_per_100m (6 m off after 300 m)")
    c.near(d([(0, 0), (30, 40), (33, 94)], [(0, 0), (30, 40), (30, 90)]), 5.0, 1e-6,
           "drift_per_100m (5 m off after 100 m)")


@c.test("TODO 7 — fuse_with_fixes(): growing sigma and the Kalman update",
        hint="After each step: sigma += k·|step| + c. At a fix: K = σ²/(σ² + R²), x += K (fix − x), σ = √((1−K)σ²).")
def _():
    (fu,) = need(V(), "fuse_with_fixes")
    res = fu([(10, 0)] * 4, {2: (0, 0)})
    c.ok(isinstance(res, tuple) and len(res) == 2, f"it should return (track, sigmas), got {type(res).__name__}")
    track, sig = res
    t = [tuple(round(v, 4) for v in nums(p, 2, "a track point")) for p in track]
    c.eq(t, [(0, 0), (10, 0), (10, 0), (20, 0), (30, 0)], "the track of fuse_with_fixes([(10,0)]*4, {2: (0,0)})")
    want = [0.0, 2.0, math.sqrt(8), math.sqrt(8) + 2, math.sqrt(8) + 4]
    c.ok(len(sig) == 5 and all(abs(float(a) - b) < 1e-3 for a, b in zip(sig, want)),
         f"sigmas {[round(float(s), 3) for s in sig]}, expected {[round(w, 3) for w in want]}")
    tr2, _ = fu([(10, 0)] * 2, {2: (0, 0)}, fix_sigma=0.001)
    c.ok(abs(float(tr2[-1][0])) < 0.01, "with a nearly perfect fix (fix_sigma=0.001) the position should become the fix")


@c.test(f"Whole flight — odometry only: final error ≈ {REF_FINAL_ERR:.0f} m, drift ≈ {REF_DRIFT} m / 100 m",
        hint="Run `python3 vo.py`. A track going the wrong way → signs of TODO 4; far too long or short → TODO 1.")
def _():
    (d,) = need(V(), "drift_per_100m")
    s = student_flight()
    c.ok(len(s["track"]) == len(s["truth"]), f"the track has {len(s['track'])} points, expected {len(s['truth'])}")
    c.near(math.dist(s["track"][-1], s["truth"][-1]), REF_FINAL_ERR, tol=8.0, what="final error (m)")
    c.near(d(s["track"], s["truth"]), REF_DRIFT, tol=0.5, what="drift per 100 m")


@c.test("Whole flight — fused with the map fixes: worst error < 15 m and 2σ covers ≥ 90 % of frames",
        hint="fuse_with_fixes(steps, fixes) with the fixes of map_fixes.csv and the default k, c, fix_sigma.")
def _():
    (fu,) = need(V(), "fuse_with_fixes")
    s = student_flight()
    track, sig = fu(s["steps"], s["fixes"])
    err = [math.dist(nums(a, 2, "a track point"), b) for a, b in zip(track, s["truth"])]
    inside = sum(1 for e, q in zip(err[1:], sig[1:]) if e <= 2 * float(q)) / (len(err) - 1)
    c.ok(max(err) < 15, f"worst error with fixes {max(err):.1f} m")
    c.ok(inside >= 0.9, f"the 2σ band contains the error on only {100 * inside:.0f} % of the frames")


@c.test("TODO 8 — navera_steps(): NAVERA's FrameOdometry on the flight",
        hint="FrameOdometry().step(frame, 0.0, m_per_px, float(t)) for every frame; the first call returns None "
             "(no previous frame) and is not a step. Return (steps, refused).")
def _():
    (ns,) = need(V(), "navera_steps")
    s = student_flight()
    res = ns(s["frames"], s["mpp"])
    c.ok(isinstance(res, tuple) and len(res) == 2, f"it should return (steps, refused), got {type(res).__name__}")
    steps, refused = res
    c.eq(len(steps), len(s["frames"]) - 1, "the number of steps")
    integ, d = need(V(), "integrate", "drift_per_100m")
    track = integ([nums(p, 2, "a step") for p in steps])
    c.near(d(track, s["truth"]), REF_NAVERA_DRIFT, tol=0.4, what="NAVERA's drift per 100 m")


@c.test("TODO 9, 10 — random walk: exponent ≈ 0.5 for random errors, ≈ 1 for a bias",
        hint="simulate_drift: cumulative sums of per-step error vectors, RMS over trials (axis 0). "
             "growth_exponent: slope of np.polyfit(log n, log rms, 1).")
def _():
    m = load_student("drift_sim.py")
    sim, gx = need(m, "simulate_drift", "growth_exponent")
    r = np.asarray(sim(100, sigma=0.5, bias=0.0, trials=2000, seed=0), float)
    c.eq(r.shape, (100,), "simulate_drift(100, ...).shape")
    c.near(r[99], 0.5 * math.sqrt(200), tol=0.4, what="RMS after 100 random steps (theory σ√(2n))")
    b = np.asarray(sim(50, sigma=0.0, bias=0.2, trials=10, seed=0), float)
    c.near(b[49], 10.0, tol=1e-6, what="error after 50 steps of bias 0.2 m")
    c.near(gx(3.0 * np.arange(1, 51) ** 0.7), 0.7, tol=1e-6, what="growth_exponent(3 n^0.7)")
    c.near(gx(r), 0.5, tol=0.05, what="exponent, random errors")
    c.near(gx(b), 1.0, tol=0.01, what="exponent, bias only")


@c.test("TODO 11 — vo_gate() reproduces NAVERA's odometry gate",
        hint="Accept when |v_vo − v_ref| ≤ max(3·vel_sigma, 0.3·|v_ref|, 3.0) — the rule in vision_nav.py odometry().")
def _():
    (g,) = need(load_student("navera_nav.py"), "vo_gate")
    cases = [(((20, 0), (20, 0), 1.0), True), (((26.5, 0), (20, 0), 1.0), False),
             (((25.9, 0), (20, 0), 1.0), True), (((2.9, 0), (0, 0), 0.5), True),
             (((0, 3.2), (0, 0), 0.5), False), (((0, 0), (5, 0), 2.0), True), (((0, 0), (7, 0), 2.0), False)]
    for args, want in cases:
        c.eq(bool(g(*args)), want, f"vo_gate{args}")


@c.test("results.json holds every measurement (run the lab's commands)",
        hint="Run, in order: python3 vo.py compare, python3 vo.py, python3 vo.py --altitude 114.25, "
             "python3 vo.py navera, python3 drift_sim.py, python3 navera_nav.py.")
def _():
    c.file_exists("results.json")
    try:
        r = json.load(open("results.json"))
    except ValueError as e:
        raise CheckFailed(f"results.json is not valid JSON: {e}")
    for k in ("fft_vs_opencv", "barometer", "other_height", "navera", "drift_sim", "navigator"):
        c.ok(k in r, f"results.json has no '{k}' part yet")
    c.ok(r["fft_vs_opencv"]["mean_px"] < 0.4, f"mean |numpy − OpenCV| = {r['fft_vs_opencv']['mean_px']} px (> 0.4)")
    c.near(r["barometer"]["drift_per_100m"], REF_DRIFT, 0.5, "results.json barometer drift")
    c.ok("worst_error_fused_m" in r["barometer"], "results.json barometer part has no fusion result (TODO 7, rerun vo.py)")
    c.near(r["other_height"]["height_m"], 114.25, 0.01, "the height of the second run (use --altitude 114.25)")
    c.near(r["other_height"]["drift_per_100m"], REF_DRIFT_TRUE_H, 0.4, "drift with the true height")
    c.ok(r["navigator"]["B_no_fixes"]["first_unavailable"] is not None, "scenario B never became 'unavailable'?")


@c.test("report.md — five sections, filled, with your measured numbers",
        hint="Replace every '...' and write a few sentences per section. Include the drift (barometer and true "
             "height), the two exponents and the frame where scenario B becomes unavailable, as printed.")
def _():
    c.file_exists("report.md")
    txt = open("report.md", encoding="utf-8").read()
    for h in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5."):
        c.ok(h in txt, f"the heading '{h} …' is missing")
    c.ok("..." not in txt, "there is still a '...' to replace")
    c.ok(len(re.findall(r"[A-Za-z]{3,}", txt)) >= 250, "the report is too short (aim for 250+ words)")
    try:
        r = json.load(open("results.json"))
    except (OSError, ValueError):
        raise CheckFailed("results.json is missing or broken: the report's numbers are compared with it")
    found = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", txt)]

    def has(v, tol, what):
        c.ok(any(abs(x - v) <= tol for x in found), f"I can't find {what} (≈ {v}) in report.md")
    has(r["barometer"]["drift_per_100m"], 0.06, "the drift with the barometer height")
    has(r["other_height"]["drift_per_100m"], 0.06, "the drift with the true height")
    has(r["drift_sim"]["exponent_random"], 0.03, "the random-walk exponent")
    has(float(r["navigator"]["B_no_fixes"]["first_unavailable"]), 0.0, "the first 'unavailable' frame of scenario B")
    has(r["barometer"]["worst_error_fused_m"], 0.6, "the worst error with map fixes")


c.run()

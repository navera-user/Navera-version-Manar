import contextlib
import io
import math
import os
import re

import cv2
import numpy as np
import yaml

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run

c = Checker()

# ---- unseen inputs (the lab never uses them) and expected values from the course reference -------------------
# (solutions/19-calibration/check_values.py recomputes every constant below)
K2 = np.array([[410.0, 0.0, 655.0], [0.0, 430.0, 372.0], [0.0, 0.0, 1.0]])       # another fisheye camera, 1300 × 740
D2 = np.array([0.08, -0.05, 0.02, -0.004])
D3 = [0.12, -0.35, 0.30, -0.10]                    # a lens whose curve turns back at 71.19° (θ_d 1.10195)
K3 = np.array([[500.0, 0.0, 600.0], [0.0, 520.0, 300.0], [0.0, 0.0, 1.0]])
SUB12 = ["f0022", "f0030", "f0044", "f0080", "f0090", "f0111", "f0216", "f0230", "f0252", "f0286", "f0322", "f0323"]
SUB12_FX, SUB12_FY, SUB12_CX, SUB12_RMS = 673.879097, 737.968807, 930.48215, 0.527085
SUB12_PER_VIEW = [0.830617, 0.614426, 0.472407, 0.526265, 0.379666, 0.83537, 0.472892, 0.395696, 0.496496, 0.40271,
                  0.248449, 0.271392]
TEST6 = ["f0022", "f0090", "f0216", "f0252", "f0287", "f0323"]
KT = np.array([[666.522254, 0.0, 940.663123], [0.0, 726.080102, 321.97075], [0.0, 0.0, 1.0]])
DT = np.array([0.280922, -0.799218, 1.529579, -1.119904])
TEST6_RMS = 0.573833
TEST6_PER_VIEW = [0.963813, 0.421329, 0.479258, 0.499019, 0.401254, 0.479106]
OBJ = np.zeros((54, 1, 3))
OBJ[:, 0, :2] = np.array([(cc * 0.03294, r * 0.03294) for r in range(6) for cc in range(9)])


def corners():
    z = np.load(io.BytesIO(hidden("corners.npz", text=False)))
    return [str(n) for n in z["names"]], [np.asarray(v, dtype=np.float64) for v in z["corners"]]


def lens():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.fisheye", fresh=True)


def functions(*names):
    fns = need(lens(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/fisheye.py)")
    return fns


def source_of(name):
    """The text of one function of the student's navera_lite/fisheye.py (read as text, never run)."""
    try:
        text = open(os.path.join("navera_lite", "fisheye.py"), encoding="utf-8").read()
    except OSError:
        raise CheckFailed("navera_lite/fisheye.py is missing — copy it again from the starter files")
    m = re.search(r"^def " + name + r"\(.*?(?=^def |^# @|^class |\Z)", text, re.S | re.M)
    return m.group(0) if m else ""


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")


def num(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    if isinstance(v, (tuple, list)) or (hasattr(v, "shape") and getattr(v, "shape", ()) != ()):
        raise CheckFailed(f"{what} should return one number, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return one number, got {v!r}")


def arr(v, shape, what):
    if v is None:
        raise CheckFailed(f"{what} returned None")
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return numbers, got {v!r}"[:300])
    if a.shape != shape:
        raise CheckFailed(f"{what} should return shape {shape}, got shape {a.shape}")
    return a


def pair(v, what):
    """(rms, [per view]) from a student function."""
    try:
        total, per = v
        return float(total), [float(p) for p in per]
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return (rms, [rms of each view]), got {v!r}"[:300])


TIPS = [("too many indices", " — X_cam is an (N, 3) array: take its columns with X[:, 0], X[:, 1], X[:, 2]"),
        ("Point3f", " — cv2.fisheye wants float64 board points of shape (N, 1, 3), in a LIST with one array per view"),
        ("CALIB_CHECK_COND", " — OpenCV refused a view (that is expected here; do not catch the error)"),
        ("'NoneType'", " — a function you call returned None (an earlier TODO?)"),
        ("could not broadcast", " — two arrays of different shapes: OpenCV corners are (N, 1, 2), reshape(-1, 2)")]


def go(fn, *args, seconds=40, **kw):
    try:
        return run(fn, *args, seconds=seconds, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def projection_ok():
    """TODO 7 and 8 use the student's fisheye_project: say so plainly when it is the real culprit."""
    (f,) = need(lens(), "fisheye_project")
    if is_stub(f):
        raise CheckFailed("this function uses YOUR fisheye_project(), which is not written yet (TODO 1)")
    X = np.array([[0.4, -0.2, 1.0], [-0.9, 0.3, 1.2], [0.0, 0.0, 2.0]])
    want, _ = cv2.fisheye.projectPoints(X.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K2, D2)
    try:
        got = np.asarray(run(f, X, K2, D2), dtype=float).reshape(-1, 2)
        good = got.shape == (3, 2) and np.allclose(got, want.reshape(-1, 2), atol=1e-6)
    except (CheckFailed, TypeError, ValueError):
        good = False
    if not good:
        raise CheckFailed("this function uses YOUR fisheye_project(), which is not right yet: fix check 1 (TODO 1) first")


def rms_ok():
    """TODO 8 uses the student's reprojection_rms: say so plainly when it is the real culprit."""
    (f,) = need(lens(), "reprojection_rms")
    if is_stub(f):
        raise CheckFailed("holdout_rms() uses YOUR reprojection_rms(), which is not written yet (TODO 7)")
    rng = np.random.default_rng(4)
    views, rvecs, tvecs = [], [], []
    for _ in range(3):
        rv, tv = rng.uniform(-0.3, 0.3, (3, 1)), np.array([[-0.1], [-0.05], [0.5]])
        p, _ = cv2.fisheye.projectPoints(OBJ, rv, tv, K2, D2)
        views.append(p.reshape(-1, 1, 2))
        rvecs.append(rv)
        tvecs.append(tv)
    try:
        total, _ = pair(run(f, OBJ, views, rvecs, tvecs, K2, D2), "reprojection_rms")
        good = total < 1e-6
    except CheckFailed:
        good = False
    if not good:
        raise CheckFailed("holdout_rms() uses YOUR reprojection_rms(), which is not right yet: fix check 9 (TODO 7) first")


def isnan(v):
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


# ======================================================================== session 1 — Lens modeller
@c.test("TODO 1: fisheye_project() on another lens — 200 directions up to 75°, a point on the axis, one row per point",
        hint="Lesson §2: a = X/Z, b = Y/Z, r = √(a²+b²), θ = atan(r), θ_d from the polynomial, a and b times θ_d/r (1 on "
             "the axis), then fx, cx for u and fy, cy for v. Return an (N, 2) array. Write the steps yourself.")
def _():
    (f,) = functions("fisheye_project")
    body = source_of("fisheye_project")
    if re.search(r"projectPoints|distortPoints", body):
        raise CheckFailed("fisheye_project() calls OpenCV's projection: write the five steps of lesson §2 yourself "
                          "(the lab compares YOUR model with OpenCV's)")
    rng = np.random.default_rng(71)
    ang = np.radians(rng.uniform(0, 75, 200))
    az = rng.uniform(0, 2 * np.pi, 200)
    X = np.stack([np.sin(ang) * np.cos(az), np.sin(ang) * np.sin(az), np.cos(ang)], axis=1) * rng.uniform(0.5, 9, (200, 1))
    want, _ = cv2.fisheye.projectPoints(X.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K2, D2)
    want = want.reshape(-1, 2)
    got = arr(go(f, X, K2, D2), (200, 2), "fisheye_project(200 points)")
    pin = np.stack([K2[0, 0] * X[:, 0] / X[:, 2] + K2[0, 2], K2[1, 1] * X[:, 1] / X[:, 2] + K2[1, 2]], axis=1)
    if np.allclose(got, pin, atol=1e-3):
        raise CheckFailed("fisheye_project() gives the ideal PINHOLE: the angle θ and the lens polynomial are missing")
    if np.allclose(got[:, 0], want[:, 0], atol=1e-6) and not np.allclose(got[:, 1], want[:, 1], atol=1e-6):
        raise CheckFailed("u is right but v is not: v = fy·b' + cy with fy = K[1, 1], cy = K[1, 2]")
    err = float(np.abs(got - want).max())
    c.ok(err < 1e-6, f"fisheye_project() differs from the fisheye model by up to {err:.3g} px on another lens "
         "(fx 410, fy 430, D = [0.08, −0.05, 0.02, −0.004])")
    got = arr(go(f, np.array([[0.0, 0.0, 3.0], [0.2, 0.1, 1.0]]), K2, D2), (2, 2), "fisheye_project(two points)")
    c.ok(not np.isnan(got[0]).any(), "a point ON the optical axis gives nan: θ_d / r is 0/0 there, its limit is 1 "
         "(lesson §2, the warning)")
    c.ok(np.allclose(got[0], [655.0, 372.0], atol=1e-9), f"a point on the optical axis must land on (cx, cy) = "
         f"(655, 372), got {got[0].round(3).tolist()}")
    one = arr(go(f, [[0.5, -0.3, 2.0]], K2, D2), (1, 2), "fisheye_project(a list with one point)")
    c.ok(np.all(np.isfinite(one)), "fisheye_project of one point given as a list must work too (np.asarray)")


@c.test("TODO 2: theta_from_theta_d() on another lens — round trips, the rising root, nan beyond the top",
        hint="Lesson §3 and lab Step 3: find where θ_d(θ) stops rising on [0, π/2] (a fine grid and np.diff), return "
             "float('nan') above that top or below 0, else bisection on the rising part. Radians.")
def _():
    (f,) = functions("theta_from_theta_d")
    for td, want in ((0.3, 0.297594), (0.8, 0.804116), (1.0, 1.037915)):
        v = go(f, td, D3)
        if isnan(v) or v is None:
            raise CheckFailed(f"theta_from_theta_d({td}) on a lens whose curve rises up to θ_d = 1.102: there is an "
                              f"answer, got {v!r}")
        v = num(v, f"theta_from_theta_d({td})")
        if abs(v - math.degrees(want)) < 0.01:
            raise CheckFailed("theta_from_theta_d returns DEGREES: return radians")
        c.near(v, want, 1e-5, f"theta_from_theta_d({td}) (radians, another lens)")
    v = num(go(f, 1.1018511, D3), "theta_from_theta_d(1.10185)")
    if abs(v - 1.1762) < 2e-3:
        raise CheckFailed("theta_from_theta_d(1.10185) on another lens = 1.1762: that is the BENCH lens' top — find each "
                          "lens' own top with a grid and np.diff, never type a number (lab Step 3, plan (1))")
    if v > 1.26:
        raise CheckFailed(f"theta_from_theta_d(1.10185) = {v:.4f}: past the top of this lens' curve (1.2424 rad). Find "
                          "where θ_d(θ) stops rising first, and search only up to there (lab Step 3, the plan)")
    if abs(v - 1.2474) < 0.004:
        raise CheckFailed("theta_from_theta_d(1.10185): you returned the root on the FALLING part of the curve; return "
                          "the rising one (search only up to the top)")
    c.near(v, 1.237436, 2e-3, "theta_from_theta_d(1.10185), just below the top")
    for td in (1.12195, 1.5, -0.1):
        v = go(f, td, D3)
        c.ok(v is not None and isnan(v), f"theta_from_theta_d({td}) must be nan (no angle of the rising part gives it), "
             f"got {v!r}")
    rng = np.random.default_rng(3)
    worst = 0.0
    for t in rng.uniform(0.01, 1.2, 12):
        td = float(t * (1 + D3[0] * t ** 2 + D3[1] * t ** 4 + D3[2] * t ** 6 + D3[3] * t ** 8))
        worst = max(worst, abs(num(go(f, td, D3), "theta_from_theta_d") - t))
    c.ok(worst < 1e-5, f"round trips θ → θ_d → θ miss by up to {worst:.2g} rad: more bisection steps, or a finer grid")


@c.test("TODO 3: stretch_at() on another lens and other views, and nan where it has no meaning",
        hint="Lesson §5: (f_new / cos²θ) / (fx · θ_d′(θ)), θ_d′ = 1 + 3k1θ² + 5k2θ⁴ + 7k3θ⁶ + 9k4θ⁸, θ in radians "
             "inside; nan when θ_d′ ≤ 0 or θ ≥ 90°.")
def _():
    (f,) = functions("stretch_at")
    v = go(f, 50.0, 380.0, K3, D3)
    if isnan(v) or (v is not None and not isinstance(v, (tuple, list)) and abs(float(v)) < 1e-6):
        raise CheckFailed(f"stretch_at(50, 380) = {v!r} on a lens valid up to 71°: is θ still in DEGREES inside cos and the "
                          "polynomial? t = math.radians(theta_deg)")
    v = num(v, "stretch_at(50, 380)")
    for bad, why in ((1.83941, "you left out the lens' slope θ_d′(θ): the lens records fx·θ_d′(θ) pixels per radian"),
                     (1.86314, "that is θ_d/θ (an average), not the derivative θ_d′(θ)"),
                     (0.48060, "upside down: straight-view pixels per radian on top, lens pixels per radian below")):
        if abs(v - bad) < 1e-3:
            raise CheckFailed(f"stretch_at(50, 380) = {v:.4f}: {why}")
    c.near(v, 2.080740, 1e-4, "stretch_at(50°, f_new 380, another lens)")
    c.near(num(go(f, 25.0, 450.0, K3, D3), "stretch_at(25, 450)"), 1.075885, 1e-4, "stretch_at(25°, f_new 450)")
    c.near(num(go(f, 0.0, 610.0, K3, D3), "stretch_at(0, 610)"), 1.22, 1e-6, "stretch_at(0°, f_new 610) = f_new / fx")
    for args, why in (((72.0, 450.0), "72° is past this lens' top (71.2°): θ_d′ < 0"),
                      ((90.0, 450.0), "a pinhole cannot show 90°")):
        v = go(f, *args, K3, D3)
        c.ok(v is not None and isnan(v), f"stretch_at{args} must be nan ({why}), got {v!r}")


@c.test("TODO 4: undistort() of an unseen picture by another lens, against the model",
        hint="Lesson §4 and lab Step 5: cv2.fisheye.initUndistortRectifyMap(K, D, identity, K_new, (w, h), "
             "cv2.CV_16SC2), then cv2.remap with bilinear interpolation and a constant border. Same shape and dtype.")
def _():
    (f,) = functions("undistort")
    rng = np.random.default_rng(9)
    img = cv2.GaussianBlur(rng.integers(0, 256, (740, 1300, 3), dtype=np.uint8), (0, 0), 3)
    K_new = np.array([[290.0, 0.0, 650.0], [0.0, 290.0, 370.0], [0.0, 0.0, 1.0]])
    m1, m2 = cv2.fisheye.initUndistortRectifyMap(K2, D2, np.eye(3), K_new, (1300, 740), cv2.CV_16SC2)
    want = cv2.remap(img, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    got = go(f, img, K2, D2, K_new)
    a = np.asarray(got) if got is not None else None
    if a is None:
        raise CheckFailed("undistort() returned None")
    c.ok(a.shape == img.shape, f"undistort() of a 1300 × 740 picture must keep its shape {img.shape}, got {a.shape} — "
         "the size is (width, height)")
    c.ok(a.dtype == np.uint8, f"undistort() must return a uint8 image, got {a.dtype}")
    black = np.all(want == 0, axis=2)
    diff = np.abs(a.astype(int) - want.astype(int))
    if float(diff[~black].mean()) > 2.0:
        raise CheckFailed(f"undistort() differs from the straightened picture by {diff[~black].mean():.1f} grey levels on "
                          "average: check K_new (the 4th argument), the identity rotation and bilinear interpolation")
    if black.any() and not np.all(a[black] == 0):
        raise CheckFailed("undistort(): directions the lens picture does not contain must stay BLACK — a constant border")
    c.ok(float(diff.mean()) < 0.5, f"undistort() differs from the straightened picture by {diff.mean():.1f} grey levels on "
         "average: check K_new (the 4th argument), the identity rotation and bilinear interpolation")
    grey = go(f, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), K2, D2, K_new)
    c.ok(grey is not None and np.asarray(grey).shape == (740, 1300), "undistort() of a GREY picture must work too "
         "(take the size from img.shape[:2])")


@c.test("Steps 0–3: prediction, your projection, a pixel's angle",
        hint="Step 2: your fisheye_project of (−1.6, 0.4, 1.4) m and its "
             "distance to (fx·a + cx, fy·b + cy). Step 3: a' = (u − cx)/fx, b' = (v − cy)/fy, θ_d = √(a'² + b'²), "
             "then your theta_from_theta_d, in degrees.")
def _():
    pe, u, v, gap, ang, why = answers("PREDICT_EDGE", "STEP2_U", "STEP2_V", "PINHOLE_GAP_PX", "PIXEL_ANGLE_DEG",
                                      "EXPLAIN_TURN_BACK")
    predicted("PREDICT_EDGE", pe)
    u, v = number(u, "STEP2_U"), number(v, "STEP2_V")
    if abs(u - 182.22) < 0.5 and abs(v - 523.77) < 0.5:
        raise CheckFailed("STEP2_U / STEP2_V: that is the PINHOLE pixel; write your fisheye_project's pixel")
    c.near(u, 331.98, 0.02, "STEP2_U (px)")
    c.near(v, 482.88, 0.02, "STEP2_V (px)")
    gap = number(gap, "PINHOLE_GAP_PX")
    c.near(gap, 155.2, 0.15, "PINHOLE_GAP_PX (px)")
    ang = number(ang, "PIXEL_ANGLE_DEG")
    if abs(ang - 48.26) < 0.05:
        raise CheckFailed("PIXEL_ANGLE_DEG ≈ 48.3: you used fx for both a' and b' — b' = (v − cy) / fy")
    if abs(ang - 51.80) < 0.05:
        raise CheckFailed("PIXEL_ANGLE_DEG ≈ 51.8: that is θ_d in degrees — invert the polynomial with theta_from_theta_d")
    if abs(ang - 0.8345) < 0.01:
        raise CheckFailed("PIXEL_ANGLE_DEG: that is in radians — math.degrees(…)")
    c.near(ang, 47.82, 0.03, "PIXEL_ANGLE_DEG (degrees)")
    explained("EXPLAIN_TURN_BACK", why,
              ((r"corner", r"data", r"view", r"fit", r"measur", r"calibrat", r"\b5[0-2]", r"observ", r"seen", r"sample"),
               "what the polynomial was fitted on"),
              ((r"extrapol", r"beyond", r"outside", r"no (corner|data|point)", r"not (seen|measured|constrain)",
                r"nothing", r"free", r"unconstrain", r"polynomial", r"farther", r"past"),
               "why it can do anything beyond that"))


@c.test("Steps 4–5: the trade-off engineer's numbers, and the straightened view",
        hint="Step 4: run_lens.py stretch (the 111° line, edge); H_max = 2·atan((w/2)/fx) in degrees; the partner: "
             "fx 540 px, w 1920 px. Step 5: run_lens.py straighten (f0216). EXPLAIN_…: in your own words, with numbers.")
def _():
    ps, se, hm, hp, why_fov, b0, b1, why_res = answers(
        "PREDICT_STRETCH", "STRETCH_EDGE_111", "H_MAX_DEG", "H_MAX_PARTNER_DEG", "EXPLAIN_FOV", "BEND_BEFORE_PX",
        "BEND_AFTER_PX", "EXPLAIN_RESIDUAL")
    predicted("PREDICT_STRETCH", ps)
    se = number(se, "STRETCH_EDGE_111")
    if abs(se - 3.12) < 0.02:
        raise CheckFailed("STRETCH_EDGE_111 ≈ 3.12 is 1/cos²(55.5°) alone: write your stretch_at's value at the edge")
    c.near(se, 2.51, 0.01, "STRETCH_EDGE_111")
    hm = number(hm, "H_MAX_DEG")
    if abs(hm - 55.47) < 0.05:
        raise CheckFailed("H_MAX_DEG ≈ 55.5: that is half the view — H_max = 2·atan(960 / fx)")
    c.near(hm, 110.94, 0.02, "H_MAX_DEG (degrees)")
    hp = number(hp, "H_MAX_PARTNER_DEG")
    if abs(hp - 60.64) < 0.05:
        raise CheckFailed("H_MAX_PARTNER_DEG ≈ 60.6: that is half the view — 2·atan(960 / 540)")
    c.near(hp, 121.28, 0.02, "H_MAX_PARTNER_DEG (degrees)")
    explained("EXPLAIN_FOV", why_fov,
              ((r"\d",), "two numbers from the table"),
              ((r"detail", r"resolution", r"centre", r"center", r"f_new", r"focal", r"pixels per", r"38", r"39", r"%"),
               "what a wider view loses at the centre"),
              ((r"stretch", r"edge", r"valid", r"interpol", r"invent", r"calibrat", r"75", r"nan", r"beyond"),
               "what happens at the edges"))
    b0, b1 = number(b0, "BEND_BEFORE_PX"), number(b1, "BEND_AFTER_PX")
    c.near(b0, 5.12, 0.05, "BEND_BEFORE_PX (px)")
    c.near(b1, 0.63, 0.05, "BEND_AFTER_PX (px)")
    explained("EXPLAIN_RESIDUAL", why_res,
              ((r"rms", r"calibrat", r"model", r"fit", r"0\.5", r"error"), "the calibration's own error"),
              ((r"detect", r"corner", r"noise", r"screen", r"flat", r"pixel", r"jpeg", r"blur", r"interpol"),
               "another source of error"))


# ======================================================================== session 2 — Calibrator
@c.test("TODO 5: board_points() for other boards — order, shape, Z = 0, float64",
        hint="Lesson §8, Corners: row by row, the column index changing fastest; point (row r, column c) = (c·s, r·s, 0); "
             "shape (cols·rows, 1, 3), float64.")
def _():
    (f,) = functions("board_points")
    a = arr(go(f, 4, 3, 0.025), (12, 1, 3), "board_points(4, 3, 0.025)")
    want = np.array([[cc * 0.025, r * 0.025, 0.0] for r in range(3) for cc in range(4)])
    swapped = np.array([[cc * 0.025, r * 0.025, 0.0] for cc in range(4) for r in range(3)])
    if np.allclose(a.reshape(-1, 3), swapped):
        raise CheckFailed("board_points: the ROW index changes fastest; the detector goes row by row, the COLUMN index "
                          "changing fastest")
    c.ok(np.allclose(a.reshape(-1, 3), want, atol=1e-12), "board_points(4, 3, 0.025) is not the board's corners in "
         "the detector's order")
    raw = go(f, 7, 5, 0.02)
    c.ok(np.asarray(raw).dtype == np.float64, f"board_points must be float64 (cv2.fisheye needs it), got "
         f"{np.asarray(raw).dtype}")
    a = arr(raw, (35, 1, 3), "board_points(7, 5, 0.02)")
    c.ok(np.allclose(a[-1, 0], [0.12, 0.08, 0.0]) and np.allclose(a[:, 0, 2], 0.0),
         f"board_points(7, 5, 0.02): the last corner should be (0.12, 0.08, 0), got {a[-1, 0].tolist()}")


@c.test("TODO 6: calibrate_fisheye() on 12 real views, and a refused view raises",
        hint="Lesson §8: cv2.fisheye.calibrate([obj]·N, views, size, identity, four zeros, flags = RECOMPUTE_EXTRINSIC | "
             "CHECK_COND | FIX_SKEW, criteria = CRITERIA). Return its five results. Do not catch cv2.error.")
def _():
    (f,) = functions("calibrate_fisheye")
    names, views = corners()
    vs = [views[names.index(n)] for n in SUB12]
    res = go(f, OBJ, vs, (1920, 540), seconds=60)
    try:
        rms, K, D, rvecs, tvecs = res
        K = np.asarray(K, dtype=float)
        D = np.asarray(D, dtype=float).ravel()
    except (TypeError, ValueError):
        raise CheckFailed(f"calibrate_fisheye must return (rms, K, D, rvecs, tvecs), got {res!r}"[:300])
    if abs(K[0, 0] - 711.58) < 1:
        raise CheckFailed("calibrate_fisheye: the poses are not recomputed at each step — add "
                          "cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC")
    c.ok(abs(K[0, 1]) < 1e-9, f"the skew K[0, 1] = {K[0, 1]:.3g}: add cv2.fisheye.CALIB_FIX_SKEW")
    c.near(K[0, 0], SUB12_FX, 0.05, "fx of 12 real views")
    c.near(K[1, 1], SUB12_FY, 0.05, "fy of 12 real views")
    c.near(K[0, 2], SUB12_CX, 0.05, "cx of 12 real views")
    c.near(float(rms), SUB12_RMS, 1e-4, "the RMS of 12 real views")
    c.ok(len(rvecs) == 12 and len(tvecs) == 12, "one rvec and one tvec per view")
    try:
        out = run(f, OBJ, views, (1920, 540), seconds=60)
    except CheckFailed as e:
        c.ok("CALIB_CHECK_COND" in str(e) or "Ill-conditioned" in str(e),
             f"on all 36 views OpenCV must refuse a view with a CALIB_CHECK_COND error, got: {e}"[:400])
        return
    if out is None:
        raise CheckFailed("calibrate_fisheye returned None on all 36 views: do not catch cv2.error — calibrate_robust() "
                          "needs it to drop the refused view")
    raise CheckFailed("on all 36 views calibrate_fisheye refused nothing: add cv2.fisheye.CALIB_CHECK_COND (OpenCV "
                      "then refuses an ill-conditioned view)")


@c.test("TODO 7: reprojection_rms() — your projection of a real calibration, per view and over all corners",
        hint="Lesson §7: for each view R = cv2.Rodrigues(rvec)[0], X_c = R·X + t (O @ R.T + t), YOUR fisheye_project, "
             "the squared distances to the detected corners; RMS over ALL corners, and one RMS per view.")
def _():
    (f,) = functions("reprojection_rms")
    projection_ok()
    body = source_of("reprojection_rms")
    if re.search(r"projectPoints", body):
        raise CheckFailed("reprojection_rms() calls cv2.fisheye.projectPoints: use YOUR fisheye_project (lesson §7)")
    names, views = corners()
    vs = [views[names.index(n)] for n in SUB12]
    rms, K, D, rvecs, tvecs = cv2.fisheye.calibrate(
        [OBJ] * 12, vs, (1920, 540), np.eye(3), np.zeros((4, 1)),
        flags=cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND | cv2.fisheye.CALIB_FIX_SKEW,
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-9))
    total, per = pair(go(f, OBJ, vs, list(rvecs), list(tvecs), K, D), "reprojection_rms")
    if abs(total - float(np.mean(SUB12_PER_VIEW))) < 1e-4:
        raise CheckFailed("reprojection_rms: the mean of the per-view RMS values is not the RMS — square every corner's "
                          "error, average them ALL, then the square root (lesson §7, 🧰 RMS)")
    if abs(total - SUB12_RMS ** 2) < 1e-4:
        raise CheckFailed("reprojection_rms gives the MEAN SQUARE: take the square root (lesson §7, 🧰 RMS)")
    if total > 2.0:
        raise CheckFailed(f"reprojection_rms over 12 real views = {total:.3g} px, far too large for a good calibration: "
                          "are the corners placed in the camera frame right? X_c = R·X + t for every corner, i.e. "
                          "O @ R.T + t (lab Step 8, hint 2)")
    c.near(total, SUB12_RMS, 1e-5, "reprojection_rms over all corners of 12 real views")
    c.ok(len(per) == 12 and np.allclose(per, SUB12_PER_VIEW, atol=1e-5), "the per-view RMS values are not right "
         "(one RMS per view, over that view's 54 corners)")


@c.test("TODO 8: holdout_rms() — a calibration made from 16 views, tested on 6 views it never saw",
        hint="Lesson §7 point 1, lab Step 10: for each test view, cv2.fisheye.undistortPoints(view, K, D) → normalised "
             "rays, cv2.solvePnP(obj, rays, identity, None) → its pose; then YOUR reprojection_rms.")
def _():
    (f,) = functions("holdout_rms")
    projection_ok()
    rms_ok()
    names, views = corners()
    total, per = pair(go(f, OBJ, [views[names.index(n)] for n in TEST6], KT, DT), "holdout_rms")
    if total > 5:
        raise CheckFailed(f"holdout_rms = {total:.1f} px: the poses are wrong — undo the lens first "
                          "(cv2.fisheye.undistortPoints), then solvePnP with K = identity and no distortion")
    if abs(total - TEST6_RMS ** 2) < 2e-3 or abs(total - float(np.mean(TEST6_PER_VIEW))) < 1e-3:
        raise CheckFailed(f"holdout_rms = {total:.4f}: the poses are right, but your reprojection_rms() does not compute "
                          "the RMS over all corners yet — fix check 9 (TODO 7) first")
    c.near(total, TEST6_RMS, 2e-3, "holdout_rms on 6 unseen views (px)")
    c.ok(len(per) == 6 and np.allclose(per, TEST6_PER_VIEW, atol=3e-3), "the per-view hold-out RMS values are not "
         "right (one per test view)")


@c.test("Steps 7–9: your calibration, the detective, and the stability of fx",
        hint="Run python3 calibrate_lab.py calibrate (fx, RMS, views used and refused, farthest corner used, the worst "
             "view) and stability (the std of fx for 8 and 30 views). EXPLAIN_…: in your own words.")
def _():
    pf, fx, rms, used, refused, far, why_ref, worst, ps, s8, s30, why_st = answers(
        "PREDICT_FX", "MY_FX", "MY_RMS", "VIEWS_USED", "REFUSED_VIEWS", "FARTHEST_USED_DEG", "EXPLAIN_REFUSED",
        "WORST_VIEW", "PREDICT_STD", "FX_STD_8", "FX_STD_30", "EXPLAIN_STABILITY")
    predicted("PREDICT_FX", pf)
    predicted("PREDICT_STD", ps)
    fx, rms = number(fx, "MY_FX"), number(rms, "MY_RMS")
    if abs(fx - 660.48) < 0.5:
        raise CheckFailed("MY_FX = 660.5 is the BENCH file's fx: write the one YOUR calibration printed")
    c.near(fx, 670.28, 0.05, "MY_FX (px)")
    c.near(rms, 0.506, 0.002, "MY_RMS (px)")
    c.eq(int(number(used, "VIEWS_USED")), 34, "VIEWS_USED")
    try:
        ref = sorted(str(x).strip().lower().replace(".jpg", "") for x in refused)
    except TypeError:
        raise CheckFailed(f"REFUSED_VIEWS should be a list of names, e.g. [\"f0001\", \"f0002\"], got {refused!r}")
    c.ok(ref == ["f0023", "f0208"], f"REFUSED_VIEWS = {refused!r}: copy the names calibrate_lab.py calibrate prints "
         "as refused")
    far = number(far, "FARTHEST_USED_DEG")
    if abs(far - 51.8) < 0.3:
        raise CheckFailed("FARTHEST_USED_DEG ≈ 51.8: that corner is in a REFUSED view; write the farthest corner USED")
    c.near(far, 43.0, 0.15, "FARTHEST_USED_DEG (degrees)")
    explained("EXPLAIN_REFUSED", why_ref,
              ((r"far", r"edge", r"extreme", r"right", r"angle", r"4[45]", r"5[12]", r"off.?axis", r"side", r"outer"),
               "what the refused views have in common"),
              ((r"pose", r"ill", r"condition", r"unstable", r"no other", r"alone", r"only", r"constrain", r"unreliable",
                r"distort", r"model", r"few"), "why OpenCV cannot trust them"))
    c.ok(isinstance(worst, str) and worst.strip().lower().replace(".jpg", "") == "f0022",
         f"WORST_VIEW = {worst!r}: the USED view with the largest RMS in the calibrate table (a name in quotes)")
    s8, s30 = number(s8, "FX_STD_8"), number(s30, "FX_STD_30")
    c.near(s8, 38.9, 0.3, "FX_STD_8 (px)")
    c.near(s30, 3.4, 0.3, "FX_STD_30 (px)")
    explained("EXPLAIN_STABILITY", why_st,
              ((r"rms", r"fit", r"0\.5", r"error"), "what the RMS does not show"),
              ((r"view", r"photo", r"image", r"more", r"many", r"\b30\b", r"\b40\b", r"number"), "how many views to take"))


@c.test("Steps 10–11: the hold-out, the calibration tool's file, and the three reasons",
        hint="Step 10: calibrate_lab.py holdout (train, test, Brown–Conrady test). Step 11: CLI_HFOV_DEG from your fx "
             "and NAVERA's rule (lesson §5), then run python3 -m navera_lite.tools.calibrate … --out my_calib.yaml in the "
             "lesson folder. REASON_…: the lesson's §3, §5 and §7, and lab Steps 9 and 11 (its three facts).")
def _():
    tr, te, bc, why_bc, hf, why_fx, why_hf = answers("TRAIN_RMS", "TEST_RMS", "BC_TEST_RMS", "REASON_BC", "CLI_HFOV_DEG",
                                                     "REASON_FX", "REASON_HFOV")
    tr, te, bc = number(tr, "TRAIN_RMS"), number(te, "TEST_RMS"), number(bc, "BC_TEST_RMS")
    if abs(tr - 0.567) < 0.002 and abs(te - 0.474) < 0.002:
        raise CheckFailed("TRAIN_RMS and TEST_RMS are swapped")
    c.near(tr, 0.474, 0.002, "TRAIN_RMS (px)")
    c.near(te, 0.567, 0.002, "TEST_RMS (px)")
    c.near(bc, 0.570, 0.002, "BC_TEST_RMS (px)")
    explained("REASON_BC", why_bc,
              ((r"corner", r"test", r"view", r"data", r"\b4[0-5]", r"\b5[0-2]", r"cent"), "where the test corners are"),
              ((r"beyond", r"edge", r"outside", r"large angle", r"wide", r"90", r"tan", r"part", r"diverg", r"differ",
                r"curve"), "where the two models differ"))
    if not os.path.exists("my_calib.yaml"):
        raise CheckFailed("my_calib.yaml is missing: run the calibration tool of lab Step 11 in your lesson folder")
    try:
        cal = yaml.safe_load(open("my_calib.yaml"))
        fx = float(cal["camera_matrix"][0])
        out_hfov = float(cal["out_hfov_deg"])
        rms = float(cal["rms_px"])
    except Exception:
        raise CheckFailed("my_calib.yaml is not a calibration file written by the tool: run lab Step 11 again")
    c.near(fx, 670.28, 0.05, "fx in my_calib.yaml (px)")
    c.ok(rms < 1.0, f"my_calib.yaml has RMS {rms}: above 1 px")
    c.ok(int(cal.get("views", 0)) == 34 and [int(cal.get("image_width", 0)), int(cal.get("image_height", 0))] == [1920, 540],
         "my_calib.yaml: 34 views of 1920 × 540 expected — run the tool on the course's views")
    hf = number(hf, "CLI_HFOV_DEG")
    if abs(hf - 110.94) < 0.01:
        raise CheckFailed("CLI_HFOV_DEG = 110.94 is the BENCH lens' width: use YOUR fx")
    c.near(hf, out_hfov, 0.006, "CLI_HFOV_DEG (it should equal the out_hfov_deg of your my_calib.yaml)")
    c.near(hf, 110.15, 0.01, "CLI_HFOV_DEG (degrees)")
    explained("REASON_FX", why_fx,
              ((r"left out", r"\b39\b", r"three (views|photos|frames|images)", r"\b3 (views|photos|frames|images)",
                r"face", r"dataset", r"remov", r"missing", r"exclud", r"not (the )?same (views|photos|frames|images)",
                r"different (views|photos|frames|images|set)", r"other (views|photos|frames|images)",
                r"which (views|photos|frames|images)", r"set of (views|photos|frames|images)"),
               "that the course's views are not the bench's (which views were left out)"),
              ((r"spread", r"std", r"stab", r"vary", r"varies", r"uncertain", r"distance", r"trade", r"correlat",
                r"subset", r"never", r"660", r"not well", r"determin", r"cannot tell", r"same rms"),
               "how poorly the views pin fx down (your Step 9 subsets, the trade with the distance)"), min_words=12)
    explained("REASON_HFOV", why_hf,
              ((r"fx", r"focal", r"f_new", r"670"), "which number sets the width"),
              ((r"atan", r"2 ?·? ?atan", r"960", r"rule", r"larger", r"longer", r"bigger", r"narrow", r"≥", r">="),
               "the rule that turns it into a width"))


@c.test("report.md: the memo — three sections, ≥ 150 words, the key numbers",
        hint="Keep the headings '## Lens model', '## My calibration', '## Recommendation'. Quote the widest straight "
             "view (Step 4, in °), your fx (Step 7, MY_FX, in px) and your hold-out (test) RMS (Step 10, TEST_RMS, in px).")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## Lens model", "## My calibration", "## Recommendation"):
        c.ok(re.search(r"^" + re.escape(h), text, re.M | re.I) is not None, f"report.md has no '{h}' heading")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    words = re.findall(r"[A-Za-zÀ-ÿ']{2,}", body)
    c.ok(len(words) >= 150, f"report.md has {len(words)} words of your own (at least 150 expected)")
    for pat, what in [(r"\b11[01](\.\d+)?\s*(°|deg)", "the widest straight view, in ° (Step 4)"),
                      (r"\b67[01](\.\d+)?\s*px", "your fx, in px (Step 7)"),
                      (r"\b0\.5[67]\d*\s*px", "your hold-out (test) RMS, in px (Step 10)")]:
        c.ok(re.search(pat, body) is not None, f"report.md does not quote {what}")
    rec = re.split(r"^## Recommendation", body, flags=re.M | re.I)[-1]
    c.ok(len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", rec)) >= 40, "the Recommendation section needs at least 40 words: 3–5 "
         "concrete rules")


c.milestone("lens_modeller", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "Steps 0–3:", "Steps 4–5:",
            label="Session 1 complete: Lens modeller badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("calibrator", "TODO", "Step", "report",
            label="Mission complete: Lens modeller and Calibrator badges earned")

c.run()

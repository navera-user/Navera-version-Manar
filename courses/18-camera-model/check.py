import contextlib
import hashlib
import io
import math
import re

import numpy as np

from academy_check import CheckFailed, Checker, explained, is_stub, load_student, need, predicted, run, sh

c = Checker()

# ---- unseen inputs (the lab never uses them) and their expected values, from the course reference -------------
K1 = np.array([[700.0, 0.0, 500.0], [0.0, 700.0, 400.0], [0.0, 0.0, 1.0]])       # a 1000 × 800 camera
C1 = np.array([10.0, -20.0, 180.0])
C2 = np.array([-30.0, 15.0, 210.0])


def hpr(heading_deg, pitch_deg=0.0, roll_deg=0.0):
    """R_wc from human angles (the conventions sheet), built here so the check never trusts the student's copy."""
    y, p, r = math.radians(90.0 - heading_deg), math.radians(-pitch_deg), math.radians(roll_deg)
    rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1.0]])
    ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1.0, 0], [-math.sin(p), 0, math.cos(p)]])
    rx = np.array([[1.0, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    mount = np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
    return rz @ ry @ rx @ mount


R1 = hpr(0.0)
R2 = hpr(125.0, -18.0, 7.0)


def cam():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.camera", fresh=True)


def functions(*names):
    fns = need(cam(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/camera.py)")
    return fns


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


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
        raise CheckFailed(f"{what} returned None here, but this case has an answer — check your None condition")
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return numbers, got {v!r}")
    if a.shape != shape:
        raise CheckFailed(f"{what} should return shape {shape}, got shape {a.shape}: {v!r}")
    return a


def near_arr(a, want, tol):
    return bool(np.all(np.abs(np.asarray(a, dtype=float) - np.asarray(want, dtype=float)) <= tol))


TIPS = [("matmul", " — a matrix product with the wrong shapes: K and R are (3, 3), a point is 3 numbers "
                   "(np.asarray(X, dtype=float))"),
        ("unsupported operand type(s) for -: 'list'", " — lists do not subtract: np.asarray(X, dtype=float) − "
                                                      "np.asarray(C, dtype=float)"),
        ("Singular matrix", " — K cannot be inverted: is your K right?"),
        ("can't multiply sequence", " — a list times a number repeats the list: make numpy arrays first"),
        ("'NoneType'", " — a function you call returned None (an earlier TODO?)")]


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


# ======================================================================== session 1 — Measurer
@c.test("TODO 1–2: focal_px() and K_from_hfov() on unseen cameras",
        hint="Lesson §2: f = (w/2) / tan(HFOV/2), the angle in RADIANS. K = [[f, 0, w/2], [0, f, h/2], [0, 0, 1]] "
             "as a numpy array of floats.")
def _():
    fp, kf = functions("focal_px", "K_from_hfov")
    v = num(go(fp, 50.0, 2048), "focal_px(50, 2048)")
    if v < 0 or abs(v - -7668.895) < 1:
        raise CheckFailed(f"focal_px(50, 2048) = {v:.1f}: math.tan got DEGREES — use math.tan(math.radians(hfov) / 2)")
    if abs(v - 859.238) < 0.01:
        raise CheckFailed("focal_px(50, 2048) = 859.2: you used the whole angle; the right half of the image (w/2) is "
                          "seen under HFOV/2")
    c.near(v, 2195.975, 0.01, "focal_px(50, 2048)")
    c.near(num(go(fp, 120.0, 640), "focal_px(120, 640)"), 184.752, 0.01, "focal_px(120, 640)")
    got = go(kf, 75.0, 1600, 1200)
    if got is not None and not isinstance(got, np.ndarray):
        raise CheckFailed(f"K_from_hfov returns a {type(got).__name__}: return a numpy array, np.array([[…], […], […]]) "
                          "— later code multiplies it with @")
    K = arr(got, (3, 3), "K_from_hfov(75, 1600, 1200)")
    if abs(K[2, 0] - 800) < 1e-6 or abs(K[1, 0]) > 1:
        raise CheckFailed("K_from_hfov: cx and cy belong in the LAST COLUMN (K[0, 2], K[1, 2]); the last row is [0, 0, 1]")
    c.ok(near_arr(K[2], [0, 0, 1], 1e-12), f"the last row of K should be [0, 0, 1], got {K[2].tolist()}")
    c.ok(abs(K[0, 2] - 800) < 1e-9 and abs(K[1, 2] - 600) < 1e-9,
         f"the principal point should be the image centre (800, 600), got ({K[0, 2]}, {K[1, 2]})")
    c.ok(abs(K[0, 1]) < 1e-12 and abs(K[1, 0]) < 1e-12, "the skew K[0, 1] (and K[1, 0]) must be 0")
    c.near(K[0, 0], 1042.5803, 0.001, "K[0, 0] (f)")
    c.near(K[1, 1], 1042.5803, 0.001, "K[1, 1] (f again: square pixels)")


@c.test("TODO 3: project() — level and tilted cameras, a camera not at the origin, a point in the air, behind",
        hint="Lesson §2 and worked example 1: move X into the camera frame (subtract C, then the TRANSPOSE of R_wc), "
             "None when the depth is ≤ 0, then K and divide by the third number. Return a numpy array of 2 floats.")
def _():
    (f,) = functions("project")
    got = go(f, K1, R1, C1, [55.0, 40.0, 0.0])
    if got is None:
        raise CheckFailed("project() returned None for a ground point 180 m below a level camera: the depth is the "
                          "z of X_c = R_wcᵀ · (X − C) — did you subtract the camera centre C?")
    uv = arr(got, (2,), "project(level camera)")
    c.ok(near_arr(uv, [675.0, 166.666667], 1e-4), f"level camera, nose north: project gives {uv.round(3).tolist()} — "
         "is v = f·Y/Z + cy with Y pointing DOWN the image (north is up)?")
    uv = arr(go(f, K1, R2, C2, [-50.0, 120.0, 0.0]), (2,), "project(tilted camera)")
    if near_arr(uv, [404.714761, 445.661442], 1e-3):
        raise CheckFailed("tilted camera: you used R_wc @ (X − C); world → camera needs the TRANSPOSE, R_wc.T @ (X − C) "
                          "(a level camera nose north hid this: its R_wc is symmetric)")
    if near_arr(uv, [-578.71882, 2133.719311], 1e-3):
        raise CheckFailed("tilted camera: you forgot to subtract the camera centre C")
    c.ok(near_arr(uv, [358.192562, 424.157339], 1e-4), f"tilted camera (heading 125°, pitch −18°, roll 7°): project "
         f"gives {uv.round(3).tolist()}")
    uv = arr(go(f, K1, R2, C2, [-90.0, 60.0, 30.0]), (2,), "project(a point 30 m above the ground)")
    c.ok(near_arr(uv, [577.015905, 456.767752], 1e-4), f"a point in the air (z = 30 m) gives {uv.round(3).tolist()} — "
         "project() works for any 3-D point, not only on the ground: use X as given")
    got = go(f, K1, R2, C2, [-30.0, 15.0, 260.0])
    c.ok(got is None, f"a point 50 m ABOVE the camera is behind it (depth ≤ 0): return None, not {got!r}")
    uv = arr(go(f, K1, R2, C2, [400.0, 300.0, 0.0]), (2,), "project(a point outside the image)")
    c.ok(near_arr(uv, [-1116.839752, -460.441626], 1e-3), "a point in front of the camera but outside the image must "
         "still be projected (negative pixels are fine): only depth ≤ 0 gives None")


@c.test("TODO 4: backproject_ground() — a tilted camera away from the origin, and a ray to the sky",
        hint="Lesson §3 and worked example 2: the ray's direction in the WORLD (K⁻¹, then R_wc), None when it does "
             "not go down, then the ray–plane intersection with z = 0, starting from C. Return [east, north].")
def _():
    (f,) = functions("backproject_ground")
    g = arr(go(f, K1, R2, C2, 500, 400), (2,), "backproject_ground(the image centre)")
    if near_arr(g, [-55.784758, 83.745555], 1e-3):
        raise CheckFailed("the ray must be turned into the world with R_wc @ (not R_wc.T @): R_wc goes camera → world")
    if near_arr(g, [-40.342681, 61.345523], 1e-3):
        raise CheckFailed("the ground point ignores where the camera is: X = C + λ·d, with C = (−30, 15, 210) here")
    c.ok(near_arr(g, [-70.342681, 76.345523], 1e-4), f"the image centre of a tilted camera hits the ground at "
         f"{g.round(3).tolist()} — not the right point")
    for uv, want in (((120, 650), [-66.454029, 260.295847]), ((900, 100), [-64.993517, -60.405216])):
        g = arr(go(f, K1, R2, C2, *uv), (2,), f"backproject_ground{uv}")
        c.ok(near_arr(g, want, 1e-4), f"pixel {uv} hits the ground at {g.round(3).tolist()} — not the right point")
    got = go(f, K1, hpr(0.0, 75.0, 0.0), [0.0, 0.0, 100.0], 500, 0)
    c.ok(got is None, f"nose 75° up, the top row: that ray goes above the horizon and never meets the ground — return "
         f"None when d[2] ≥ 0 (you returned {got!r})")


@c.test("TODO 5: gsd() on unseen heights and cameras",
        hint="Lesson §4: GSD = 2·h·tan(HFOV/2) / w (= h / f), the angle in RADIANS.")
def _():
    (f,) = functions("gsd")
    v = num(go(f, 240.0, 84.0, 1600), "gsd(240, 84, 1600)")
    if abs(v - 0.687416) < 1e-4:
        raise CheckFailed("gsd(240, 84, 1600) = 0.687: math.tan got DEGREES — math.tan(math.radians(hfov) / 2)")
    if abs(v - 2.854309) < 1e-4:
        raise CheckFailed("gsd(240, 84, 1600) = 2.854: the half-angle — the half-width w/2 is seen under HFOV/2")
    c.near(v, 0.270121, 1e-5, "gsd(240, 84, 1600)")
    c.near(num(go(f, 55.0, 120.0, 640), "gsd(55, 120, 640)"), 0.297696, 1e-5, "gsd(55, 120, 640)")


def pad_image(rows, cols, shape):
    img = np.full(shape + (3,), 90, np.uint8)
    img[::2, ::3] = (60, 200, 120)                                  # a green pattern: never orange
    img[rows[0]:rows[1] + 1, cols[0]:cols[1] + 1] = (0, 140, 255)
    return img


@c.test("TODO A–C: pad_size_px(), pad_centre_px() on unseen images, height_from_size() on unseen objects",
        hint="np.nonzero of the mask gives two arrays, rows first. The width counts COLUMNS, both ends included; the "
             "centre is (mean column, mean row) — u is a column. No orange pixel → None. TODO C: lesson §4, "
             "\"Measuring with a known object\".")
def _():
    with contextlib.redirect_stdout(io.StringIO()):
        mp = load_student("measure_pad.py", fresh=True)
    size, centre, hfs = need(mp, "pad_size_px", "pad_centre_px", "height_from_size")
    for fn, k in ((size, "A"), (centre, "B"), (hfs, "C")):
        if is_stub(fn):
            raise CheckFailed(f"{fn.__name__}() is not written yet (TODO {k} in measure_pad.py)")
    for rows, cols, shape, w, uv in (((10, 17), (20, 34), (40, 60), 15, (27.0, 13.5)),
                                     ((100, 129), (7, 18), (200, 50), 12, (12.5, 114.5))):
        img = pad_image(rows, cols, shape)
        n = go(size, img)
        if isinstance(n, bool) or not isinstance(n, (int, np.integer)):
            raise CheckFailed(f"pad_size_px() must return an int (a number of columns), got {n!r} — int(…)")
        if n == w - 1:
            raise CheckFailed(f"pad_size_px gives {n} for orange columns {cols[0]} to {cols[1]}: both ends are "
                              "included, so add 1")
        if n in (rows[1] - rows[0] + 1, rows[1] - rows[0]):
            raise CheckFailed(f"pad_size_px gives {n}: that is the number of ROWS — np.nonzero gives (rows, cols), "
                              "the width counts columns")
        c.eq(int(n), w, f"pad_size_px of an orange block in columns {cols[0]}–{cols[1]}")
        got = go(centre, img)
        try:
            u, v = (float(x) for x in got)
        except (TypeError, ValueError):
            raise CheckFailed(f"pad_centre_px() must return two numbers (u, v), got {got!r}")
        if abs(u - uv[1]) < 1e-9 and abs(v - uv[0]) < 1e-9:
            raise CheckFailed("pad_centre_px returns (row, column): a pixel is (u, v) = (COLUMN, ROW) — swap them")
        c.ok(abs(u - uv[0]) < 1e-6 and abs(v - uv[1]) < 1e-6, f"pad_centre_px of an orange block in rows {rows[0]}–"
             f"{rows[1]}, columns {cols[0]}–{cols[1]} gives ({u:g}, {v:g})")
    blank = np.full((30, 40, 3), 90, np.uint8)
    for fn in (size, centre):
        got = go(fn, blank)
        c.ok(got is None, f"{fn.__name__}() of an image with no orange pixel should return None, not {got!r}")
    v = num(go(hfs, 1000.0, 12.0, 40), "height_from_size(1000, 12, 40)")
    if abs(v - 10.0 / 3.0) < 0.01 or abs(v - 0.48) < 0.01:
        raise CheckFailed(f"height_from_size(1000, 12, 40) = {v:.3g}: upside down — one pixel covers size_m / n_px "
                          "metres, and at nadir GSD = h / f (lesson §4)")
    c.near(v, 300.0, 1e-6, "height_from_size(1000, 12, 40)")
    c.near(num(go(hfs, 659.79, 4.5, 18), "height_from_size(659.79, 4.5, 18)"), 164.9475, 1e-3,
           "height_from_size(659.79, 4.5, 18)")


@c.test("Steps 0–3: prediction, the Insta360's vertical FOV, the mast, the image centre of a nose-down camera",
        hint="Step 1: VFOV = 2·atan((H_img/2)/f), H_img = 540 px, with your focal_px(111, 1920). Step 2: the distance between the two "
             "pixels printed by run_camera.py project. Step 3: run_camera.py centre, the −15° line (a distance, "
             "positive). CENTRE_ROLL_E_M / _N_M: your own backproject_ground of pixel (480, 270) at 200 m, heading 40°, "
             "pitch −15°, roll +10°. EXPLAIN_…: in your own words.")
def _():
    pt, vf, lean, why_mast, behind, why_tilt, re_, rn, why_t = answers(
        "PREDICT_TILT", "VFOV_INSTA_DEG", "MAST_LEAN_PX", "EXPLAIN_MAST", "CENTRE_BEHIND_M", "EXPLAIN_TILT",
        "CENTRE_ROLL_E_M", "CENTRE_ROLL_N_M", "EXPLAIN_T")
    predicted("PREDICT_TILT", pt)
    vf = number(vf, "VFOV_INSTA_DEG")
    c.ok(abs(vf - 111.0) > 0.5, "VFOV_INSTA_DEG = 111: that is the HORIZONTAL field of view; the vertical one uses "
                                "the image height (540 px)")
    if abs(vf - 22.26) < 0.05:
        raise CheckFailed("VFOV_INSTA_DEG ≈ 22.3: that is HALF the angle — VFOV = 2·atan(270 / f)")
    c.near(vf, 44.51, 0.02, "VFOV_INSTA_DEG (degrees)")
    lean = number(lean, "MAST_LEAN_PX")
    if abs(lean - 32.0) < 0.1 or abs(lean - 20.0) < 0.1:
        raise CheckFailed("MAST_LEAN_PX: the mast leans in u AND v — the distance is √(Δu² + Δv²)")
    c.near(lean, 37.7, 0.2, "MAST_LEAN_PX (px)")
    explained("EXPLAIN_MAST", why_mast,
              ((r"clos", r"near", r"depth", r"distance", r"\b120\b", r"smaller", r"higher", r"height", r"tall",
                r"above"), "why the top projects differently (its depth)"),
              ((r"flat", r"ground", r"lean", r"wrong", r"error", r"away", r"farther", r"further", r"outward",
                r"displace", r"position"), "what it means for a flat-ground model"))
    behind = number(behind, "CENTRE_BEHIND_M")
    c.ok(behind > 0, "CENTRE_BEHIND_M is a distance: write it positive (the sign of north is in the runner's print)")
    c.near(behind, 53.59, 0.1, "CENTRE_BEHIND_M (m)")
    explained("EXPLAIN_TILT", why_tilt,
              ((r"body", r"fix", r"attach", r"mount", r"belly", r"rigid", r"screw", r"turns with", r"rotat"),
               "that the camera turns with the body"),
              ((r"back", r"behind", r"rear", r"tail", r"south"), "which way the optical axis goes"))
    re_, rn = number(re_, "CENTRE_ROLL_E_M"), number(rn, "CENTRE_ROLL_N_M")
    c.ok(re_ != 0 or rn != 0, "CENTRE_ROLL_E_M / _N_M are still 0: compute them with your backproject_ground (Step 3)")
    if abs(re_ + 17.58) < 0.3 and abs(rn + 62.41) < 0.3:
        raise CheckFailed("CENTRE_ROLL_E_M / _N_M are swapped: backproject_ground returns [east, north]")
    c.near(re_, -62.41, 0.3, "CENTRE_ROLL_E_M (m)")
    c.near(rn, -17.58, 0.3, "CENTRE_ROLL_N_M (m)")
    explained("EXPLAIN_T", why_t,
              ((r"world", r"camera"), "which frame each function goes to"),
              ((r"transpose", r"invers", r"\.t\b", r"ᵀ", r"opposite", r"other way", r"revers", r"undo", r"back"),
               "why one direction needs the transpose"), min_words=6)


@c.test("Steps 4–5: the heights of photos A and B, and where the pad of photo T is",
        hint="Run python3 measure_pad.py after TODO A, B (and TODO 1–5): copy its heights (one decimal), the width of "
             "B's ±1 px range (largest − smallest), the pad of photo T (east, north); then compute "
             "yourself the 'level camera' point (camera_rotation_hpr(40)) and the pad with 150 m instead of 170 m, "
             "and their distances to the pad.")
def _():
    (pp, ha, hb, rb, why_px, pe, pn, lev, why_lev, hsh) = answers(
        "PREDICT_PAD", "HEIGHT_A_M", "HEIGHT_B_M", "HEIGHT_B_RANGE_M", "EXPLAIN_PIXEL", "PAD_T_E_M", "PAD_T_N_M",
        "LEVEL_ERROR_M", "EXPLAIN_LEVEL", "HEIGHT_SHIFT_M")
    predicted("PREDICT_PAD", pp)
    ha, hb = number(ha, "HEIGHT_A_M"), number(hb, "HEIGHT_B_M")
    c.ok(ha != 0 and hb != 0, "HEIGHT_A_M / HEIGHT_B_M are still 0: run python3 measure_pad.py (Step 4)")
    c.near(ha, 134.0, 0.2, "HEIGHT_A_M (m)")
    c.near(hb, 261.8, 0.3, "HEIGHT_B_M (m)")
    rb = number(rb, "HEIGHT_B_RANGE_M")
    if abs(rb - 11.95) < 0.3:
        raise CheckFailed("HEIGHT_B_RANGE_M ≈ 12: that is half the range — write largest − smallest")
    c.near(rb, 23.9, 0.3, "HEIGHT_B_RANGE_M (m)")
    explained("EXPLAIN_PIXEL", why_px, ((r"pixel", r"\bpx"), "the role of one pixel"),
              ((r"fewer", r"smaller", r"\b22\b", r"\b43\b", r"high", r"fraction", r"relative", r"percent", r"%",
                r"half", r"twice", r"proportion"), "why the same pixel matters more in one photo"))
    pe, pn = number(pe, "PAD_T_E_M"), number(pn, "PAD_T_N_M")
    if abs(pe - 20.8) < 0.5 and abs(pn + 41.4) < 0.5:
        raise CheckFailed("PAD_T_E_M / PAD_T_N_M: that is the 'level camera' point — the pad is the first line, "
                          "computed with the real attitude")
    c.near(pe, -17.9, 0.3, "PAD_T_E_M (m)")
    c.near(pn, -66.0, 0.3, "PAD_T_N_M (m)")
    c.near(number(lev, "LEVEL_ERROR_M"), 45.9, 0.3, "LEVEL_ERROR_M (m)")
    hsh = number(hsh, "HEIGHT_SHIFT_M")
    if abs(hsh - 20.0) < 0.5:
        raise CheckFailed("HEIGHT_SHIFT_M = 20: that is the height difference; back-project the pad's pixel with "
                          "C = (0, 0, 150) and measure how far the GROUND point moves")
    c.near(hsh, 8.04, 0.15, "HEIGHT_SHIFT_M (m)")
    explained("EXPLAIN_LEVEL", why_lev,
              ((r"pitch", r"roll", r"tilt", r"attitude", r"angle", r"orientation", r"nose"), "what the level assumption ignores"),
              ((r"imu", r"attitude", r"straighten", r"rotation", r"orientation", r"know", r"measure", r"sensor"),
               "what the matcher needs"))


# ======================================================================== session 2 — Straightener
@c.test("TODO 6: footprint() — four corners in order, a tilted camera away from the origin, and the sky",
        hint="Lesson §4: backproject_ground of (0, 0), (w, 0), (w, h), (0, h), in that order, as a (4, 2) array; "
             "None if any corner returns None.")
def _():
    (f,) = functions("footprint")
    want = np.array([[110.136042, 122.11977], [-58.767909, -89.932376], [-290.642557, 20.471562],
                     [-90.688012, 368.617269]])
    p = arr(go(f, K1, R2, C2, 1000, 800), (4, 2), "footprint(tilted camera)")
    if not near_arr(p, want, 1e-3) and all(any(near_arr(q, w, 1e-3) for q in p) for w in want):
        raise CheckFailed("footprint: the right four corners, in the wrong order — top-left (0, 0), top-right (w, 0), "
                          "bottom-right (w, h), bottom-left (0, h)")
    c.ok(near_arr(p, want, 1e-3), f"footprint of a tilted camera: the corners {p.round(1).tolist()} are not right "
         "(if a backproject_ground check fails above, fix it first)")
    got = go(f, K1, hpr(0.0, -65.0, 0.0), [0.0, 0.0, 100.0], 1000, 800)
    c.ok(got is None, f"nose 65° down: the image bottom looks above the horizon — footprint must return None, "
         f"not {got!r}")


@c.test("TODO 7: tilt_position_error() — exact, in metres, positive, on unseen cases",
        hint="Lesson §6: where the optical axis meets the ground with the error and without it, the difference as a "
             "positive distance; radians inside tan; not the small-angle formula.")
def _():
    (f,) = functions("tilt_position_error")
    v = num(go(f, 320.0, 25.0, 1.5), "tilt_position_error(320, 25, 1.5)")
    if abs(v - 10.199225) < 1e-3:
        raise CheckFailed("tilt_position_error(320, 25, 1.5) = 10.199: that is the small-angle formula h·δθ/cos²θ — "
                          "the docstring asks for the exact difference of the two tangents")
    if abs(v - 8.377580) < 1e-3:
        raise CheckFailed("tilt_position_error(320, 25, 1.5) = 8.378 = h·δθ: that ignores the tilt; compute the ground "
                          "point with and without the error")
    if v > 1000:
        raise CheckFailed(f"tilt_position_error(320, 25, 1.5) = {v:.0f}: math.tan got DEGREES — use math.radians")
    c.near(v, 10.327664, 1e-4, "tilt_position_error(320, 25, 1.5)")
    c.near(num(go(f, 80.0, 0.0, 3.0), "tilt_position_error(80, 0, 3)"), 4.192622, 1e-4, "tilt_position_error(80, 0, 3)")
    v = num(go(f, 200.0, 15.0, -2.0), "tilt_position_error(200, 15, −2)")
    c.ok(v >= 0, f"tilt_position_error(200, 15, −2) = {v:.3f}: a distance is positive — abs(…)")
    c.near(v, 7.416200, 1e-4, "tilt_position_error(200, 15, −2)")


@c.test("TODO 8: nadir_homography() on an unseen camera, scaled so that H[2, 2] = 1",
        hint="Lab Step 9: your paper trace — a pixel of the real photo becomes a ray in the real camera, then in "
             "the world, then in the level camera's axes, then a pixel again. Scale the result so that H[2, 2] = 1.")
def _():
    (f,) = functions("nadir_homography")
    want = np.array([[1.036208, -0.212695, -60.420367], [0.100111, 0.746296, 222.16217], [0.00016, -0.000425, 1.0]])
    Hm = arr(go(f, K1, R2, hpr(125.0)), (3, 3), "nadir_homography(K, tilted, level)")
    if abs(Hm[2, 2] - 1.0377596) < 1e-5:
        raise CheckFailed("nadir_homography: right matrix, but not scaled — divide it by H[2, 2] (the docstring asks "
                          "H[2, 2] = 1)")
    if near_arr(Hm, [[1.143951, -0.19533, -142.687193], [0.152662, 0.826771, 177.43952], [0.000267, -0.000405, 1.0]], 1e-4):
        raise CheckFailed("nadir_homography: the two rotations are swapped — the real camera's ray goes to the world "
                          "with R_wc, then into the level camera with the transpose of R_wv (lab Step 9, hint 3)")
    if near_arr(Hm, [[0.880224, -2.387688, -0.725239], [0.715868, -1.924847, -0.580249], [-1.253788, 3.342763, 1.0]], 1e-4):
        raise CheckFailed("nadir_homography: K and its inverse are swapped — a pixel first becomes a ray with K⁻¹ (on the "
                          "right, applied first), and K turns the ray back into a pixel at the end")
    inv = np.linalg.inv(Hm) if abs(np.linalg.det(Hm)) > 1e-12 else np.zeros((3, 3))
    if abs(inv[2, 2]) > 1e-12 and near_arr(inv / inv[2, 2], want, 1e-4):
        raise CheckFailed("nadir_homography: this is the INVERSE — it maps the level view back to the tilted one. The "
                          "first matrix to act on a pixel of the REAL photo turns it into a ray in the real camera "
                          "(lab Step 9, hint 4)")
    c.ok(near_arr(Hm, want, 1e-5), f"nadir_homography of a tilted camera (heading 125°, pitch −18°, roll 7°) to a level "
         f"one: {Hm.round(5).tolist()} is not right")
    Hm = arr(go(f, K1, R2, R2), (3, 3), "nadir_homography(K, R, R)")
    c.ok(near_arr(Hm, np.eye(3), 1e-9), "nadir_homography(K, R, R) should be the identity (nothing to straighten)")
    Hm = arr(go(f, K1, R2, hpr(0.0)), (3, 3), "nadir_homography(K, tilted, north-up)")
    c.ok(near_arr(Hm, [[-0.498537, -0.963408, 967.120139], [0.82647, -0.695811, 42.9341], [0.00016, -0.000425, 1.0]],
                  1e-5), "nadir_homography to a level, north-up camera is not right")


@c.test("Steps 6–7: the footprint's area, and height errors as scale errors",
        hint="Step 6: area at −30° / area at 0° from run_camera.py footprint. Step 7: scale = true GSD / predicted GSD "
             "= h_true / h_predicted; a ±15 % gate accepts 0.85 to 1.15; measured height = predicted × scale.")
def _():
    pa, ratio, why_fp, sp, verdict, hs = answers("PREDICT_AREA", "AREA_RATIO_30", "EXPLAIN_FOOTPRINT", "SCALE_PLATEAU",
                                                 "VERDICT_PLATEAU", "HEIGHT_FROM_SCALE_M")
    predicted("PREDICT_AREA", pa)
    ratio = number(ratio, "AREA_RATIO_30")
    if abs(ratio - 0.52) < 0.01:
        raise CheckFailed("AREA_RATIO_30 ≈ 0.52: upside down — area at −30° divided by the area at 0°")
    c.near(ratio, 1.92, 0.01, "AREA_RATIO_30")
    explained("EXPLAIN_FOOTPRINT", why_fp,
              ((r"far", r"distan", r"slant", r"range", r"away"), "that the far side is seen from farther away"),
              ((r"wide", r"spread", r"angle", r"perspective", r"grazing", r"stretch", r"more ground", r"larger",
                r"bigger"), "why that makes it wider"))
    sp = number(sp, "SCALE_PLATEAU")
    if abs(sp - 1.667) < 0.01:
        raise CheckFailed("SCALE_PLATEAU ≈ 1.67: upside down — scale = h_true / h_predicted (the drone is LOWER than "
                          "predicted, so the photo shows less ground: s < 1)")
    c.near(sp, 0.60, 0.005, "SCALE_PLATEAU")
    c.ok(isinstance(verdict, str) and verdict.strip().lower() in ("accepted", "refused"),
         f"VERDICT_PLATEAU should be \"accepted\" or \"refused\", got {verdict!r}")
    c.ok(verdict.strip().lower() == "refused", "VERDICT_PLATEAU: |0.6 − 1| = 0.4 is outside ±15 %")
    hs = number(hs, "HEIGHT_FROM_SCALE_M")
    if abs(hs - 277.8) < 0.5:
        raise CheckFailed("HEIGHT_FROM_SCALE_M ≈ 277.8: h_true = h_predicted × s, not divided")
    c.near(hs, 324.0, 0.5, "HEIGHT_FROM_SCALE_M (m)")


@c.test("Step 8: the attacker — which attitude error pushes the centre point out of a 30 m σ",
        hint="With your tilt_position_error(250, 8, d): increase d in small steps (or bisect) until the error reaches "
             "30 m; the same at a tilt of 35°. EXPLAIN_ATTACK: why the tilted camera is more fragile.")
def _():
    pa, a8, a35, why = answers("PREDICT_ATTACK", "ATTACK_DTILT_DEG", "ATTACK_DTILT_35_DEG", "EXPLAIN_ATTACK")
    predicted("PREDICT_ATTACK", pa)
    a8, a35 = number(a8, "ATTACK_DTILT_DEG"), number(a35, "ATTACK_DTILT_35_DEG")
    if abs(a8 - 6.74) < 0.02 or abs(a35 - 4.61) < 0.02:
        raise CheckFailed("ATTACK_…: these come from the small-angle formula — use your exact tilt_position_error")
    if abs(a8 - 6.84) < 0.02:
        raise CheckFailed("ATTACK_DTILT_DEG ≈ 6.84 = atan(30/250): that is a level camera; the camera is tilted 8°")
    c.near(a8, 6.60, 0.02, "ATTACK_DTILT_DEG (degrees, tilt 8°)")
    c.near(a35, 4.36, 0.02, "ATTACK_DTILT_35_DEG (degrees, tilt 35°)")
    explained("EXPLAIN_ATTACK", why,
              ((r"tan", r"cos", r"slope", r"grow", r"steep", r"faster", r"non.?linear", r"curve", r"derivative"),
               "how the ground distance grows with the angle"),
              ((r"tilt", r"oblique", r"angle", r"35", r"inclin"), "the role of the tilt"))


@c.test("Step 9: the straightened photo T — the pad's size and position measured in it",
        hint="Run python3 run_camera.py straighten. Width: the pad's px in the straightened view. Position: east = "
             "(u − 480) × gsd(170, 90, 960), north = −(v − 270) × gsd(…) (north is UP the image).")
def _():
    ps, px, se, sn, why = answers("PREDICT_STRAIGHT", "STRAIGHT_PAD_PX", "STRAIGHT_PAD_E_M", "STRAIGHT_PAD_N_M",
                                  "EXPLAIN_STRAIGHT")
    predicted("PREDICT_STRAIGHT", ps)
    px = number(px, "STRAIGHT_PAD_PX")
    c.ok(abs(px - 35) <= 1, f"STRAIGHT_PAD_PX = {px:g}: the pad's width printed by run_camera.py straighten (an int)")
    se, sn = number(se, "STRAIGHT_PAD_E_M"), number(sn, "STRAIGHT_PAD_N_M")
    if abs(sn - 66.1) < 0.5:
        raise CheckFailed("STRAIGHT_PAD_N_M is positive: v grows DOWN the image, so north = −(v − 270) × GSD")
    c.near(se, -18.0, 0.4, "STRAIGHT_PAD_E_M (m)")
    c.near(sn, -66.1, 0.4, "STRAIGHT_PAD_N_M (m)")
    explained("EXPLAIN_STRAIGHT", why,
              ((r"rotat", r"turn", r"same (camera )?cent", r"same (point|place|position|spot)", r"orientation"),
               "that only the camera's orientation changes"),
              ((r"depth", r"distance", r"ray", r"direction"), "why no depth is needed"))


# the shipped compare_with_opencv.py (not a secret: it only proves the file is unchanged)
COMPARE_SHA256 = "dfcb9910cd8dc5f0be0d9f737af78f7670f07a284d71be64a59cb5cba614b079"


@c.test("Step 10: your rotations follow the conventions, and the unchanged compare_with_opencv.py says ALL MATCH",
        hint="Run python3 compare_with_opencv.py: each ✘ line names the function to fix (run_camera.py test helps). "
             "Do not edit that file; copy it again from /academy/courses/18-camera-model/files/ if you did.")
def _():
    (hpr_s,) = need(cam(), "camera_rotation_hpr")
    for att in ((40.0, -14.0, 5.0), (215.0, -25.0, -8.0), (300.0, 6.0, 12.0)):
        R = arr(go(hpr_s, *att), (3, 3), f"camera_rotation_hpr{att}")
        c.ok(near_arr(R, hpr(*att), 1e-9), f"camera_rotation_hpr{att} does not follow the conventions sheet: is "
             "navera_lite/rotations.py (or camera_rotation_hpr) changed? Restore the course's version")
    c.file_exists("compare_with_opencv.py")
    src = open("compare_with_opencv.py", "rb").read()
    c.ok(hashlib.sha256(src).hexdigest() == COMPARE_SHA256, "compare_with_opencv.py was changed — copy it again "
         "from the starter files (cp /academy/courses/18-camera-model/files/compare_with_opencv.py .) and run it "
         "unchanged")
    code, out = sh("python3 compare_with_opencv.py", timeout=110)
    c.ok(code == 0, "compare_with_opencv.py stopped with an error:\n" + out[-600:])
    bad = [ln for ln in out.splitlines() if ln.startswith("✘")]
    c.ok("ALL MATCH" in out, "compare_with_opencv.py does not say ALL MATCH yet:\n" + "\n".join(bad[:4]))


@c.test("report.md: the memo — three sections, ≥ 120 words, the key numbers",
        hint="Keep the headings '## Tilt', '## Height', '## Straightening'. Quote your numbers: the heights of photos "
             "A and B (Step 4), how far off the level assumption was (Step 5), the pad's width in the straightened "
             "view (Step 9).")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## Tilt", "## Height", "## Straightening"):
        c.ok(re.search(r"^" + re.escape(h), text, re.M | re.I) is not None, f"report.md has no '{h}' heading")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    words = re.findall(r"[A-Za-zÀ-ÿ']{2,}", body)
    c.ok(len(words) >= 120, f"report.md has {len(words)} words of your own (at least 120 expected)")
    for pat, what in [(r"\b13[34](\.\d+)?\s*m", "the height of photo A, in m (Step 4)"),
                      (r"\b26[12](\.\d+)?\s*m", "the height of photo B, in m (Step 4)"),
                      (r"\b4[56](\.\d+)?\s*m", "how far off the level-camera assumption was, in m (Step 5)"),
                      (r"\b3[456]\s*(px|pixel)", "the pad's width in the straightened view, in px (Step 9)")]:
        c.ok(re.search(pat, body) is not None, f"report.md does not quote {what}")


c.milestone("measurer", "TODO 1–2:", "TODO 3:", "TODO 4:", "TODO 5:", "TODO A–C:", "Steps 0–3:", "Steps 4–5:",
            label="Session 1 complete: Measurer badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("straightener", "TODO", "Step", "report",
            label="Mission complete: Measurer and Straightener badges earned")

c.run()

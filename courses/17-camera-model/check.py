import json
import math
import os
import re

import numpy as np

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()
DATA = "/data/academy/17-camera-model"
NADIR = np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])


def cm():
    return load_student("camera_math.py")


def ref_R(heading, pitch, roll):
    """Independent R_wc (same convention as camera_math.camera_rotation)."""
    y, p, r = math.radians(90 - heading), math.radians(-pitch), math.radians(roll)
    Rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    return Rz @ Ry @ Rx @ NADIR


def K90():
    return np.array([[480.0, 0, 480.0], [0, 480.0, 270.0], [0, 0, 1.0]])


def as_vec(v, n, what):
    c.ok(v is not None, f"{what} returned None")
    try:
        a = np.asarray(v, dtype=float).ravel()
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should be numbers, got {v!r}")
    c.ok(a.size == n, f"{what} should have {n} values, got {a.size}: {v!r}")
    return a


def vnear(got, want, tol, what):
    g = as_vec(got, len(want), what)
    c.ok(np.all(np.abs(g - np.asarray(want)) <= tol),
         f"{what} is {np.round(g, 3).tolist()}, expected {np.round(want, 3).tolist()} (± {tol:g})")


@c.test("TODO 1 — focal_px() and fov_deg(): 480 px for 90° on 960 px, the Insta360 view is 659.8 px and 44.5° high",
        hint="f = (w/2) / tan(HFOV/2) with the angle in radians; fov_deg() is the same relation solved for "
             "the angle (math.atan, then math.degrees, and do not forget the factor 2).")
def _():
    focal_px, fov_deg = need(cm(), "focal_px", "fov_deg")
    c.near(focal_px(90, 960), 480.0, tol=0.01, what="focal_px(90, 960)")
    c.near(focal_px(111, 1920), 659.7897, tol=0.01, what="focal_px(111, 1920)")
    c.near(fov_deg(480.0, 960), 90.0, tol=0.01, what="fov_deg(480, 960)")
    c.near(fov_deg(659.7897, 540), 44.511, tol=0.01, what="fov_deg(659.79, 540)")


@c.test("TODO 1 — intrinsic_matrix() is the 3×3 K of an ideal camera",
        hint="Row 1: f, 0, w/2. Row 2: 0, f, h/2. Row 3: 0, 0, 1. Return a numpy array of floats.")
def _():
    (im,) = need(cm(), "intrinsic_matrix")
    K = im(111, 1920, 540)
    c.ok(K is not None, "intrinsic_matrix(111, 1920, 540) returned None")
    K = np.asarray(K, dtype=float)
    c.ok(K.shape == (3, 3), f"K should be 3x3, got shape {K.shape}")
    f = 960 / math.tan(math.radians(55.5))
    want = np.array([[f, 0, 960], [0, f, 270], [0, 0, 1]])
    c.ok(np.allclose(K, want, atol=1e-3), f"K =\n{np.round(K, 2)}\nexpected\n{np.round(want, 2)}")


@c.test("TODO 2 — project(): a camera looking straight down from 150 m",
        hint="x_cam = R_wc.T @ (X - C); then p = K @ x_cam and divide by p[2]. With heading 0 the image top "
             "points north, so a point north of the drone has v < 270.")
def _():
    (project,) = need(cm(), "project")
    K, R, C = K90(), ref_R(0, 0, 0), np.array([0.0, 0.0, 150.0])
    vnear(project(K, R, C, [0.0, 0.0, 0.0]), [480.0, 270.0], 1e-6, "project(K, R, C, the point under the drone)")
    vnear(project(K, R, C, [30.0, 45.0, 0.0]), [576.0, 126.0], 1e-6, "project(K, R, C, [30, 45, 0])")
    vnear(project(K, R, C, [-10.0, -20.0, 50.0]), [432.0, 366.0], 1e-6, "project(K, R, C, [-10, -20, 50])")
    c.ok(project(K, R, C, [0.0, 0.0, 200.0]) is None, "a point ABOVE the camera (z = 200 m) must give None")


@c.test("TODO 2 — project() with a tilted camera (heading 30°, pitch −12°, roll 4°)",
        hint="Use R_wc.T (the transpose) to go from world to camera, and the camera centre C, not the origin.")
def _():
    (project,) = need(cm(), "project")
    K, R, C = K90(), ref_R(30, -12, 4), np.array([5.0, -3.0, 150.0])
    for X in ([38.0, -92.0, 0.0], [-60.0, 10.0, 0.0], [0.0, -40.0, 20.0]):
        x = R.T @ (np.array(X) - C)
        p = K @ x
        vnear(project(K, R, C, X), p[:2] / p[2], 1e-6, f"project(K, R, C, {X})")


@c.test("TODO 3 — ground_point() is the inverse of project() on the ground, and None for the sky",
        hint="d = R_wc @ inv(K) @ [u, v, 1]; lam = -C_z / d_z; X = C + lam*d; return X[:2]. "
             "If d_z >= 0 the ray never reaches the ground.")
def _():
    (gp,) = need(cm(), "ground_point")
    K, C = K90(), np.array([0.0, 0.0, 150.0])
    vnear(gp(K, ref_R(0, 0, 0), C, 0, 0), [-150.0, 84.375], 1e-4, "ground_point(nadir, pixel (0, 0))")
    vnear(gp(K, ref_R(0, -10, 0), C, 480, 270), [0.0, -150 * math.tan(math.radians(10))], 1e-4,
          "ground_point(pitch -10°, image centre)")
    R = ref_R(30, -12, 4)
    for X in ([38.0, -92.0], [-60.0, 10.0], [120.0, -150.0]):
        x = R.T @ (np.array([X[0], X[1], 0.0]) - C)
        p = K @ x
        vnear(gp(K, R, C, p[0] / p[2], p[1] / p[2]), X, 1e-4, f"ground_point(pixel of ground point {X})")
    c.ok(gp(K, ref_R(0, -70, 0), C, 480, 540) is None,
         "pitch -70°: the bottom row looks above the horizon, ground_point(..., 480, 540) must be None")


@c.test("TODO 4 — footprint_polygon() and polygon_area(): 50 625 m² straight down, 66 466 m² at pitch −20°",
        hint="Corners in the order (0,0), (w,0), (w,h), (0,h) through ground_point(); shoelace: "
             "0.5*|sum(x*roll(y,-1) - roll(x,-1)*y)|. Return None if a corner sees the sky.")
def _():
    fpoly, area = need(cm(), "footprint_polygon", "polygon_area")
    c.near(area(np.array([[0, 0], [4, 0], [4, 3], [0, 3]])), 12.0, tol=1e-9, what="polygon_area(4 x 3 rectangle)")
    c.near(area(np.array([[0, 0], [0, 3], [4, 3], [4, 0]])), 12.0, tol=1e-9, what="polygon_area(clockwise rectangle)")
    K, C = K90(), np.array([0.0, 0.0, 150.0])
    P = fpoly(K, ref_R(0, 0, 0), C, 960, 540)
    c.ok(P is not None, "footprint_polygon(nadir) returned None")
    vnear(P, [-150, 84.375, 150, 84.375, 150, -84.375, -150, -84.375], 1e-3, "footprint_polygon(nadir)")
    c.near(area(P), 50625.0, tol=0.5, what="nadir footprint area")
    P20 = fpoly(K, ref_R(0, -20, 0), C, 960, 540)
    c.ok(P20 is not None, "footprint_polygon(pitch -20°) returned None")
    c.near(area(P20), 66466.1, tol=1.0, what="footprint area at pitch -20°")
    c.ok(fpoly(K, ref_R(0, -70, 0), C, 960, 540) is None, "at pitch -70° two corners see the sky: expected None")


@c.test("TODO 5 — meters_per_pixel() and map_m_per_px() are NAVERA's formulas",
        hint="GSD = 2 h tan(HFOV/2) / w. Map: 40075016.7 * cos(lat) / 2**z / 256 (cos wants radians too).")
def _():
    mpp, mmpp = need(cm(), "meters_per_pixel", "map_m_per_px")
    for h, fov, w in ((150, 111, 1920), (120, 90, 960), (400, 60, 1280)):
        want = 2.0 * h * math.tan(math.radians(fov) / 2.0) / w          # navera_common.camera_model
        c.near(mpp(h, fov, w), want, tol=want * 1e-6, what=f"meters_per_pixel({h}, {fov}, {w})")
    for lat, z in ((23.59, 17), (35.83, 17), (17.02, 19), (0.0, 0)):
        want = 40075016.7 * math.cos(math.radians(lat)) / 2 ** z / 256.0   # day_pkg.local_matcher
        c.near(mmpp(lat, z), want, tol=want * 1e-6, what=f"map_m_per_px({lat}, {z})")


@c.test("TODO 5 — best_zoom() picks the map zoom closest in ratio, in Muscat and in Sousse",
        hint="For each z in `zooms` compute abs(math.log(map_mpp / photo_mpp)) and return the z (an int) "
             "with the smallest value; only choose among `zooms`.")
def _():
    (bz,) = need(cm(), "best_zoom")
    cases = (((300, 111, 1920, 23.59), 18), ((300, 111, 1920, 35.83), 18), ((150, 111, 1920, 23.59), 19),
             ((1200, 111, 1920, 23.59), 16), ((640, 111, 1920, 23.59), 17), ((20000, 111, 1920, 35.8), 13),
             ((5, 90, 960, 35.8), 19))
    for args, want in cases:
        got = bz(*args)
        c.ok(got == want, f"best_zoom{args} is {got!r}, expected {want}")
    c.ok(bz(300, 111, 1920, 23.59, zooms=[15, 16, 17]) == 17, "best_zoom must only choose among `zooms`")


@c.test("TODO 6 — height_from_object(), fitted_scale(), tilt_position_error()",
        hint="size_px/f = size_m/h; the fitted scale is h_true / h_believed; the error is "
             "h*(tan(tilt+dtilt) - tan(tilt)), angles in radians.")
def _():
    hfo, fs, tpe = need(cm(), "height_from_object", "fitted_scale", "tilt_position_error")
    c.near(hfo(12, 48, 480), 120.0, tol=1e-6, what="height_from_object(12, 48, 480)")
    c.near(hfo(4.5, 20, 659.79), 148.453, tol=0.01, what="height_from_object(4.5, 20, 659.79)")
    c.near(fs(150, 200), 4 / 3, tol=1e-6, what="fitted_scale(150, 200)")
    c.near(fs(1800, 300), 1 / 6, tol=1e-6, what="fitted_scale(1800, 300)")
    c.near(tpe(150, 10, 1), 2.7080, tol=0.001, what="tilt_position_error(150, 10, 1)")
    c.near(tpe(150, 0, 1), 2.6182, tol=0.001, what="tilt_position_error(150, 0, 1)")


@c.test("TODO 7 — pad_size_px() and pad_centre_px() on the three photos",
        hint="rows, cols = np.nonzero(mask); width = cols.max() - cols.min() + 1; centre = "
             "(cols.mean(), rows.mean()) — u is a column, v is a row. None when the mask is empty.")
def _():
    import cv2
    mp = load_student("measure_pad.py")
    psp, pcp = need(mp, "pad_size_px", "pad_centre_px")
    for name, want in (("photo_A.png", 48), ("photo_B.png", 27)):
        img = cv2.imread(f"{DATA}/{name}")
        c.ok(img is not None, f"cannot read {DATA}/{name} (ask your teacher)")
        got = psp(img)
        c.ok(got is not None, f"pad_size_px() returned None for {name}")
        c.near(got, want, tol=0.5, what=f"pad_size_px({name})")
    img = cv2.imread(f"{DATA}/photo_T.png")
    vnear(pcp(img), [761.0, 358.1], 2.0, "pad_centre_px(photo_T.png)")
    empty = np.zeros((50, 50, 3), np.uint8)
    c.ok(psp(empty) is None and pcp(empty) is None, "with no orange pixel, both functions must return None")


@c.test("measure_pad.py: heights of photos A and B (120 m, 210 m ± 3 %) and the pad of photo T on the ground (± 1.5 m)",
        hint="Run `python3 measure_pad.py`. If the pad of photo T is far off, check ground_point() and that "
             "pad_centre_px() returns (u, v) = (column, row), not (row, column).")
def _():
    code, out = sh("python3 measure_pad.py", timeout=60)
    c.ok(code == 0, "measure_pad.py stopped with an error:\n" + out[-600:])
    found = {m.group(1): float(m.group(2)) for m in re.finditer(r"(photo_[AB])\.png: .*? at (\d+(?:\.\d+)?) m", out)}
    for p, want in (("photo_A", 120.0), ("photo_B", 210.0)):
        c.ok(p in found, f"no height printed for {p}:\n{out[-400:]}")
        c.ok(abs(found[p] - want) <= 0.03 * want, f"{p}: {found[p]:.0f} m, expected about {want:.0f} m")
    m = re.search(r"photo_T\.png: .*?ground (-?\d+(?:\.\d+)?) m east, (-?\d+(?:\.\d+)?) m north", out)
    c.ok(m is not None, "no ground position printed for photo_T:\n" + out[-400:])
    e, n = float(m.group(1)), float(m.group(2))
    c.ok(math.hypot(e - 38.0, n + 92.0) <= 1.5, f"photo_T pad at E {e:.1f}, N {n:.1f} m; the truth is 1.5 m or less away "
                                                 "from your answer only when your geometry is right")


@c.test("compare_with_navera.py: your formulas give NAVERA's numbers (ALL MATCH)",
        hint="Run `python3 compare_with_navera.py` and read the lines marked ✘: the numbers show yours and NAVERA's.")
def _():
    code, out = sh("python3 compare_with_navera.py", timeout=60)
    c.ok("ALL MATCH" in out, "not everything matches yet:\n" + out[-900:])


@c.test("results.json from experiments.py has the right numbers",
        hint="Run `python3 experiments.py` again after your last change; it rewrites results.json.")
def _():
    c.file_exists("results.json")
    try:
        r = json.load(open("results.json"))
        got = {"f": r["insta360"]["f_px"], "vfov": r["insta360"]["vfov_deg"],
               "area20": r["footprint_150m"]["-20"]["area_m2"], "e": r["map"]["h_equal_z17_muscat_m"],
               "zm": r["map"]["best_zoom_300m_muscat"], "L": r["errors"]["jebel_akhdar_fitted_scale"],
               "T": r["pads"]["photo_T.png"]["pad_en_m"]}
    except (KeyError, TypeError, ValueError) as e:
        raise CheckFailed(f"results.json is incomplete ({e}) — run python3 experiments.py to the end")
    c.near(got["f"], 659.79, 0.01, "insta360 f_px")
    c.near(got["vfov"], 44.511, 0.01, "insta360 vfov_deg")
    c.near(got["area20"], 66466.1, 1.0, "footprint area at pitch -20")
    c.near(got["e"], 722.2, 0.2, "h_equal_z17_muscat_m")
    c.eq(got["zm"], 18, "best_zoom_300m_muscat")
    c.near(got["L"], 0.1667, 0.0005, "jebel_akhdar_fitted_scale")
    c.ok(math.hypot(got["T"][0] - 38.0, got["T"][1] + 92.0) <= 1.5, f"photo_T pad_en_m {got['T']} is too far from the truth")


KEY = {"A": (659.79, 0.05), "B": (44.51, 0.05), "C": (66466.1, 5.0), "D": (54.6, 0.2), "E": (722.2, 1.0),
       "F": (638.9, 1.0), "G": (213.3, 0.6), "H": (205.7, 0.6), "I": (221.5, 0.6), "J": (37.6, 1.5),
       "K": (-91.8, 1.5), "L": (0.1667, 0.001), "M": (7.5, 0.05)}


def report_text():
    c.file_exists("report.md")
    return open("report.md", encoding="utf-8").read()


@c.test("report.md — the key-number table (A to M) is filled in and right",
        hint="One number per row in the 'value' column. D is the distance (positive) of the image-centre ground "
             "point at pitch −20°. M: NAVERA's gate is max(0.15, 2·σh/h) — when does 2·σh/h exceed 0.15?")
def _():
    txt = report_text()
    wrong = []
    for k, (want, tol) in KEY.items():
        m = re.search(r"^\|\s*" + k + r"\s*\|[^|]*\|\s*([^|]*)\|", txt, re.M)
        if not m:
            wrong.append(f"{k}: row not found")
            continue
        num = re.search(r"[-−]?\d+(?:\.\d+)?", m.group(1).replace(",", "").replace(" ", ""))
        if not num:
            wrong.append(f"{k}: empty")
            continue
        v = float(num.group(0).replace("−", "-"))
        if abs(v - want) > tol:
            wrong.append(f"{k}: {v:g} is not right")
    c.ok(not wrong, "; ".join(wrong))


SECTIONS = {"1. Tilt": ("behind", "back"), "2. Muscat and Sousse": ("cos", "latitude"),
            "3. Measuring the height with an object": ("pixel", "px"), "4. Height uncertainty": ("scale",)}


@c.test("report.md — the four analysis sections are written (40+ words each, no TODO left)",
        hint="Replace each TODO paragraph with your own explanation. Section 1 must say where (in front / "
             "behind) the image centre lands; 2 must explain the latitude effect; 3 must talk about pixels; "
             "4 about the scale the matcher sees.")
def _():
    txt = report_text()
    parts = re.split(r"(?m)^##\s+", txt)
    secs = {p.splitlines()[0].strip(): "\n".join(p.splitlines()[1:]) for p in parts[1:] if p.strip()}
    problems = []
    for title, words in SECTIONS.items():
        body = secs.get(title)
        if body is None:
            problems.append(f"section '## {title}' not found")
            continue
        if "TODO" in body:
            problems.append(f"'{title}' still has its TODO")
            continue
        if len(re.findall(r"[A-Za-z]+", body)) < 40:
            problems.append(f"'{title}' has fewer than 40 words")
        elif not any(w in body.lower() for w in words):
            problems.append(f"'{title}' should mention {' or '.join(repr(w) for w in words)}")
    c.ok(not problems, "; ".join(problems))


c.run()

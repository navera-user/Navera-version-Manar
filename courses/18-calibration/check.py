import json
import math
import os
import re

import numpy as np

from academy_check import Checker, load_student, need

c = Checker()
DATA = "/data/academy/18-calibration"
CALIB = DATA + "/insta360_top.yaml"
FRAME = DATA + "/views/f0208.jpg"
REAL = dict(fx=660.4827288497767, fy=721.3969246428146, cx=937.0585411264981, cy=317.6611884647247,
            k1=0.23188047333874745)
# 12 views that OpenCV accepts together (no ill-conditioned one): fast enough for grading
SUBSET = ["f0030", "f0080", "f0086", "f0091", "f0111", "f0216", "f0245", "f0257", "f0285", "f0292",
          "f0323", "f0130"]


def fm():
    return load_student("fisheye_model.py")


def cl():
    return load_student("calibrate_lab.py")


def calib():
    (load_calibration,) = need(fm(), "load_calibration")
    r = load_calibration(CALIB)
    c.ok(isinstance(r, tuple) and len(r) == 3, "load_calibration() must return three things: K, D, size")
    K, D, size = r
    c.ok(K is not None and D is not None and size is not None, "load_calibration() still returns None (TODO 1)")
    return np.asarray(K, dtype=float), np.asarray(D, dtype=float).ravel(), size


def bench():
    """K, D of the bench file, read by the check itself (so TODOs 2-7 are graded even before TODO 1)."""
    import yaml
    d = yaml.safe_load(open(CALIB))
    return np.array(d["camera_matrix"], dtype=float).reshape(3, 3), np.array(d["distortion"], dtype=float), (1920, 540)


def board():
    obj = np.zeros((54, 1, 3), np.float64)
    obj[:, 0, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2) * 0.03294
    return obj


def ref_views():
    z = np.load(DATA + "/corners_ref.npz")
    names = list(z["names"])
    return [np.array(z["corners"][names.index(n)], dtype=np.float64) for n in SUBSET]


_ref = {}


def ref_fisheye():
    import cv2
    if "f" not in _ref:
        flags = (cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND | cv2.fisheye.CALIB_FIX_SKEW)
        vs = ref_views()
        _ref["f"] = cv2.fisheye.calibrate([board()] * len(vs), vs, (1920, 540), np.eye(3), np.zeros((4, 1)),
                                          flags=flags, criteria=(3, 200, 1e-9))
    return _ref["f"]


def results(section):
    c.file_exists("results.json")
    try:
        d = json.load(open("results.json"))
    except ValueError as e:
        c.ok(False, f"results.json is not valid JSON ({e}) — run the scripts again, don't edit it by hand")
    c.ok(section in d, f"results.json has no '{section}' part yet — run "
                       f"{'fisheye_model.py' if section == 'model' else 'calibrate_lab.py'}")
    return d[section]


def bend(points):
    p = np.asarray(points, dtype=float).reshape(-1, 2)
    m = p.mean(axis=0)
    _, _, vt = np.linalg.svd(p - m)
    return float(np.max(np.abs((p - m) @ vt[1])))


def worst(img):
    import cv2
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ok, cs = cv2.findChessboardCornersSB(grey, (9, 6), flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    if not ok:
        return None
    g = cs.reshape(6, 9, 2)
    return max([bend(g[r]) for r in range(6)] + [bend(g[:, k]) for k in range(9)])


@c.test("load_calibration() reads K (3x3), D (k1..k4) and the size",
        hint='K = the 9 numbers of "camera_matrix" in 3 rows of 3; D from "distortion"; size = (image_width, '
             'image_height) — width first.')
def _():
    K, D, size = calib()
    c.eq(K.shape, (3, 3), "the shape of K")
    c.near(K[0, 0], REAL["fx"], 0.01, "K[0, 0] (fx)")
    c.near(K[1, 2], REAL["cy"], 0.01, "K[1, 2] (cy)")
    c.eq(D.size, 4, "the number of values in D")
    c.near(D[0], REAL["k1"], 1e-6, "D[0] (k1)")
    c.eq(tuple(int(v) for v in size), (1920, 540), "size")


@c.test("project_fisheye() reproduces cv2.fisheye.projectPoints (incl. a point on the axis)",
        hint="Follow the five steps of 'The full fisheye projection' in the course (normalise, angle, polynomial, rescale, "
             "apply K). On the optical axis r = 0: the limit of theta_d / r is 1, so avoid the division there.")
def _():
    import cv2
    (proj,) = need(fm(), "project_fisheye")
    K, D, _ = bench()
    rng = np.random.default_rng(7)
    X = np.vstack([[0.0, 0.0, 2.0], [1.0, 0.5, 2.0], rng.uniform([-3, -1, 0.5], [3, 1, 4], (40, 3))])
    got = proj(X, K, D)
    c.ok(got is not None, "project_fisheye() returns None (TODO 2)")
    got = np.asarray(got, dtype=float)
    c.eq(got.shape, (42, 2), "the shape of the result")
    c.ok(np.all(np.isfinite(got)), "some results are nan/inf — the point on the optical axis has r = 0: "
                                   "avoid dividing by zero there (theta_d / r → 1)")
    ref, _ = cv2.fisheye.projectPoints(X.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K, D)
    err = float(np.abs(got - ref.reshape(-1, 2)).max())
    c.ok(err < 1e-6, f"your pixels differ from OpenCV's by up to {err:.3g} px — check the formula")
    c.near(got[1, 0], 1250.347, 0.01, "u of the worked example (1.0, 0.5, 2.0)")


@c.test("theta_from_theta_d() inverts the lens polynomial on its rising part",
        hint="Bisection between 0 and the end of the rising part (where theta_d_of() stops increasing). "
             "Round trip: theta_from_theta_d(theta_d_of(t, D), D) must give t back.")
def _():
    (inv, tdo) = need(fm(), "theta_from_theta_d", "theta_d_of")
    _, D, _ = bench()
    for t in (0.0, 0.2, 0.6, 0.9, 1.1):
        got = inv(float(tdo(t, D)), D)
        c.ok(got is not None, "theta_from_theta_d() returns None (TODO 3)")
        c.near(got, t, 1e-5, f"theta_from_theta_d(theta_d_of({t}))")


@c.test("theta_from_theta_d() returns nan where the calibration cannot describe the lens",
        hint="For the bench calibration the rising part ends at 67.4° (theta_d = 1.249). theta_d = 1.30 or the "
             "left image edge (cx/fx = 1.419) has no answer: return float('nan'), don't return the falling-branch root.")
def _():
    (inv,) = need(fm(), "theta_from_theta_d")
    K, D, _ = bench()
    for td in (1.30, K[0, 2] / K[0, 0]):
        got = inv(float(td), D)
        c.ok(got is not None, "theta_from_theta_d() returns None (TODO 3)")
        c.ok(isinstance(got, float) and math.isnan(got), f"theta_from_theta_d({td:.3f}) = {got!r}, expected nan")
    got = inv(1.24, D)
    c.ok(got is not None and math.isfinite(got) and got < math.radians(67.5),
         f"theta_from_theta_d(1.24) = {got!r}: expected the root on the RISING part (below 67.4°)")


@c.test("reprojection_rms() gives the same RMS as cv2.fisheye.calibrate (12 real views)",
        hint="Per view: R = cv2.Rodrigues(rvec)[0], X_cam = X_board·Rᵀ + t, e = project_fisheye(X_cam) − seen. "
             "RMS = sqrt(mean over ALL corners of ex² + ey²). Return (rms, list of per-view RMS).")
def _():
    (rr,) = need(fm(), "reprojection_rms")
    rms, K, D, rv, tv = ref_fisheye()
    r = rr(board(), ref_views(), rv, tv, K, D.ravel())
    c.ok(isinstance(r, tuple) and len(r) == 2 and r[0] is not None,
         "reprojection_rms() must return (rms, per_view_list) (TODO 4)")
    c.near(r[0], rms, 1e-4, "your RMS (px)")
    c.eq(len(r[1]), len(SUBSET), "the number of per-view values")
    c.ok(min(r[1]) <= rms <= max(r[1]), "the overall RMS should lie between the smallest and largest per-view RMS")


@c.test("straight_camera_matrix(): 90° on 1000x500, and NAVERA's 111° view of the Insta360",
        hint="f = (w/2) / tan(hfov/2) with math.radians(); 90° → f = 500, centre (500, 250). For 111° on 1920 px: "
             "f = 960 / tan(55.5°) ≈ 659.8. Use the WIDTH.")
def _():
    (scm,) = need(fm(), "straight_camera_matrix")
    K = scm(90.0, (1000, 500))
    c.ok(K is not None, "straight_camera_matrix() returns None (TODO 5)")
    K = np.asarray(K, dtype=float)
    c.eq(K.shape, (3, 3), "the shape of the matrix")
    for (i, j), want in {(0, 0): 500.0, (1, 1): 500.0, (0, 2): 500.0, (1, 2): 250.0, (2, 2): 1.0}.items():
        c.near(K[i, j], want, 0.01, f"K[{i}, {j}]")
    c.near(np.asarray(scm(111.0, (1920, 540)), dtype=float)[0, 0], 659.79, 0.05, "f for 111° on 1920 px")


@c.test("undistort() gives NAVERA's picture, and its chessboard lines are straight",
        hint="Two OpenCV calls: build the maps once (no rotation, the NEW camera K_new, size as (width, height) — numpy's "
             "shape is (height, width, 3)), then remap with bilinear interpolation and a constant (black) border.")
def _():
    import cv2
    (und,) = need(fm(), "undistort")
    K, D, size = bench()
    img = cv2.imread(FRAME)
    f = 960.0 / math.tan(math.radians(55.5))
    Kn = np.array([[f, 0, 960.0], [0, f, 270.0], [0, 0, 1]])
    out = und(img, K, D, Kn)
    c.ok(out is not None, "undistort() returns None (TODO 6)")
    out = np.ascontiguousarray(out)
    c.eq(out.shape, img.shape, "the shape of the straightened picture")
    m1, m2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), Kn, size, cv2.CV_16SC2)
    ref = cv2.remap(img, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    d = float(np.abs(out.astype(int) - ref.astype(int)).mean())
    c.ok(d < 2.0, f"your picture differs from NAVERA's by {d:.1f} grey levels per pixel on average — is K_new "
                  "the NEW camera, and R the identity?")
    before, after = worst(img), worst(out)
    c.ok(after is not None and after < 2.0, f"most bent line after straightening: {after} px (under 2 expected)")


@c.test("line_bend_px() measures a straight line, a bent row and a bent column",
        hint="Points (0,0) (10,0) (20,4) (30,0) (40,0): the best line is y = 0.8, the middle point is 3.2 px away. A "
             "column (x and y swapped) must give the same — y = a·x + b cannot describe a vertical line; cv2.fitLine can.")
def _():
    (lb,) = need(fm(), "line_bend_px")
    v = lb(np.array([[x, 2.0 * x + 1.0] for x in range(0, 50, 5)]))
    c.ok(v is not None, "line_bend_px() returns None (TODO 7)")
    c.near(v, 0.0, 0.01, "line_bend_px(points on y = 2x + 1)")
    row = np.array([[0, 0], [10, 0], [20, 4], [30, 0], [40, 0]], dtype=float)
    c.near(lb(row), 3.2, 0.05, "line_bend_px(bent row)")
    c.near(lb(row[:, ::-1].copy()), 3.2, 0.05, "line_bend_px(bent column)")


@c.test("board_points() puts the 54 corners on the plane Z = 0, in the detector's order",
        hint="Shape (54, 1, 3), float64. Corner k = j*cols + i (row j, column i) is at (i·s, j·s, 0): the second "
             "corner is (s, 0, 0), the tenth (0, s, 0).")
def _():
    (bp,) = need(cl(), "board_points")
    obj = bp(9, 6, 0.03294)
    c.ok(obj is not None, "board_points() returns None (TODO 8)")
    obj = np.asarray(obj)
    c.eq(obj.shape, (54, 1, 3), "the shape")
    c.eq(str(obj.dtype), "float64", "the dtype")
    c.ok(np.allclose(obj, board()), "the coordinates or their order differ: corner 1 should be (0.03294, 0, 0) and "
                                    "corner 9 (0, 0.03294, 0)")


@c.test("calibrate_fisheye() calibrates 12 real views like OpenCV with NAVERA's flags",
        hint="One object-point array per view, initial K = identity and D = zeros (4x1), the three flags of TODO 9 combined "
             "with |, and the criteria tuple; return the 5 values OpenCV returns. Do not catch cv2.error.")
def _():
    (cf,) = need(cl(), "calibrate_fisheye")
    r = cf(board(), ref_views(), (1920, 540))
    c.ok(r is not None and len(r) == 5, "calibrate_fisheye() must return (rms, K, D, rvecs, tvecs) (TODO 9)")
    rms, K = ref_fisheye()[:2]
    c.near(r[0], rms, 0.005, "RMS (px)")
    c.near(np.asarray(r[1])[0, 0], K[0, 0], 0.5, "fx (px)")
    c.near(np.asarray(r[1])[0, 1], 0.0, 1e-9, "the skew K[0, 1] (FIX_SKEW)")


@c.test("calibrate_pinhole() fits Brown–Conrady on float64 corners without crashing",
        hint="cv2.calibrateCamera wants float32 points (\"Point3f\"): convert obj and every view with "
             ".astype(np.float32) — NAVERA's own --model pinhole has exactly this bug.")
def _():
    (cp,) = need(cl(), "calibrate_pinhole")
    r = cp(board(), ref_views(), (1920, 540))
    c.ok(r is not None and len(r) == 5, "calibrate_pinhole() must return (rms, K, dist, rvecs, tvecs) (TODO 10)")
    c.ok(0.3 < float(r[0]) < 0.8, f"RMS {float(r[0]):.3f} px — expected about 0.51 px on these 12 views")
    c.eq(np.asarray(r[2]).size, 5, "the number of distortion values (k1, k2, p1, p2, k3)")


@c.test("results.json 'model': you ran fisheye_model.py (straightening measured)",
        hint="Run `python3 fisheye_model.py` once all of TODOs 1–7 work (Lab step 4).")
def _():
    m = results("model")
    c.ok(m.get("project_max_diff_px", 1) < 1e-6, "project_max_diff_px is too large — rerun after fixing TODO 2")
    c.near(m.get("bend_before_px"), 6.5, 0.6, "bend_before_px")
    c.ok(m.get("bend_after_px", 99) < 2.0, "bend_after_px should be under 2 px")
    c.near(m.get("curve_peak_deg"), 67.4, 0.3, "curve_peak_deg")
    c.near(m.get("max_out_hfov_deg"), 110.94, 0.02, "max_out_hfov_deg")
    c.file_exists("before_after.jpg")


@c.test("results.json 'calibration': your calibration of 36 real views, checked and stress-tested",
        hint="Run `python3 calibrate_lab.py` (Lab step 6). Your RMS must equal OpenCV's (reprojection_rms), and the "
             "result should reproduce NAVERA's tool on the same views (fx ≈ 670 px).")
def _():
    m = results("calibration")
    c.eq(m.get("views_detected"), 36, "views_detected")
    c.ok(abs(m["rms_mine_px"] - m["rms_opencv_px"]) < 1e-3, "rms_mine_px and rms_opencv_px differ")
    c.ok(abs(m["fx"] - 670.3) < 5, f"fx = {m['fx']:.1f} px, expected about 670 px")
    c.ok(m["rms_opencv_px"] < 0.7, f"RMS {m['rms_opencv_px']:.3f} px is too large")
    s = m.get("subsets", {})
    c.ok("8" in s and "30" in s and s["8"]["std"] > s["30"]["std"],
         "the subset experiment is missing (or fx is not more stable with 30 views than with 8)")
    h = m.get("holdout", {})
    c.ok(0.2 < h.get("test_rms_px", 0) < 1.5, "the hold-out test RMS is missing or unrealistic")
    c.ok(0.3 < m.get("pinhole", {}).get("rms_px", 0) < 1.0, "the Brown–Conrady RMS is missing — finish TODO 10")


@c.test("you ran NAVERA's calibrate_camera.py: my_calib.yaml agrees with your own calibration",
        hint="Lab step 7: python3 ~/navera/navera_tools/calibrate_camera.py --images /data/academy/18-calibration/views "
             "--board 9x6 --square-mm 32.94 --out my_calib.yaml")
def _():
    import yaml
    c.file_exists("my_calib.yaml")
    try:
        d = yaml.safe_load(open("my_calib.yaml"))
        fx, rms, model = float(d["camera_matrix"][0]), float(d["rms_px"]), d["model"]
    except Exception as e:
        c.ok(False, f"my_calib.yaml is not a NAVERA calibration file ({type(e).__name__}: {e})")
    c.eq(model, "fisheye", "the model in my_calib.yaml")
    c.eq((d["image_width"], d["image_height"]), (1920, 540), "the picture size in my_calib.yaml")
    c.ok(abs(fx - REAL["fx"]) / REAL["fx"] < 0.03, f"fx = {fx:.1f} px is far from the bench's 660 px — check --board 9x6")
    c.ok(rms < 1.0, f"RMS {rms:.2f} px is too large")
    if os.path.exists("results.json") and "calibration" in json.load(open("results.json")):
        mine = json.load(open("results.json"))["calibration"]["fx"]
        c.ok(abs(mine - fx) < 1.0, f"NAVERA's tool gives fx = {fx:.2f} px, your calibrate_lab.py {mine:.2f} px: "
                                   "same views and same algorithm should agree within 1 px")


SECTIONS = ["My calibration", "Stability and hold-out", "Fisheye or Brown–Conrady", "The 111° crop",
            "Recommendation"]


def numbers(text):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]


@c.test("report.md: five sections of analysis, with your own numbers",
        hint="Keep the five '## ' headings of the template, write at least 40 words under each, and quote your fx "
             "(± 1 px) in section 1 and the focal length of a 150° straight view (≈ 257 px) in section 4.")
def _():
    c.file_exists("report.md")
    txt = open("report.md", encoding="utf-8").read()
    parts = re.split(r"^##\s+", txt, flags=re.M)
    found = {}
    for p in parts[1:]:
        title, _, body = p.partition("\n")
        for s in SECTIONS:
            if s.lower().replace("–", "-") in title.lower().replace("–", "-"):
                found[s] = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    missing = [s for s in SECTIONS if s not in found]
    c.ok(not missing, f"missing section(s): {', '.join(missing)}")
    short = [s for s in SECTIONS if len(re.findall(r"[A-Za-z]{2,}", found[s])) < 40]
    c.ok(not short, f"write at least 40 words in: {', '.join(short)}")
    if os.path.exists("results.json") and "calibration" in json.load(open("results.json")):
        fx = json.load(open("results.json"))["calibration"]["fx"]
        c.ok(any(abs(v - fx) <= 1.0 for v in numbers(found[SECTIONS[0]])),
             f"section 1 should quote your fx ({fx:.1f} px)")
    c.ok(any(abs(v - 257.2) <= 2.0 for v in numbers(found[SECTIONS[3]])),
         "section 4 should quote the focal length of a 150° straight view (compute it: 960 / tan 75°)")


ANSWERS = {"Q1": ("a", "Count the equations: one homography gives 2 constraints on K."),
           "Q2": ("b", "Think of training error vs test error in any fitted model."),
           "Q3": ("b", "K is measured in pixels of ONE picture size. Read 'In NAVERA'.")}


@c.test("quiz (answers.py)", hint="Each answer is one letter between quotes, e.g. Q1 = \"b\".")
def _():
    m = load_student("answers.py")
    for q, (good, hint) in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f'{q} = "{v}" is not the right answer — {hint}')


c.run()

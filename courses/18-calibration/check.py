import math
import os

import numpy as np

from academy_check import Checker, load_student, need

c = Checker()
DATA = "/data/academy/18-calibration"
CALIB = DATA + "/insta360_top.yaml"
FRAME = DATA + "/views/f0208.jpg"
REAL = dict(fx=660.4827288497767, fy=721.3969246428146, cx=937.0585411264981, cy=317.6611884647247,
            k1=0.23188047333874745)


def fe():
    return load_student("fisheye.py")


def calib():
    (load_calibration,) = need(fe(), "load_calibration")
    r = load_calibration(CALIB)
    c.ok(isinstance(r, tuple) and len(r) == 3, "load_calibration() must return three things: K, D, size")
    K, D, size = r
    c.ok(K is not None and D is not None and size is not None, "load_calibration() still returns None (TODO 1)")
    return np.asarray(K, dtype=float), np.asarray(D, dtype=float).ravel(), size


def bend(points):
    """Reference: largest distance to the total-least-squares line."""
    p = np.asarray(points, dtype=float).reshape(-1, 2)
    m = p.mean(axis=0)
    _, _, vt = np.linalg.svd(p - m)
    n = vt[1]                                           # normal of the best line
    return float(np.max(np.abs((p - m) @ n)))


def worst(img):
    import cv2
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ok, cs = cv2.findChessboardCornersSB(grey, (9, 6), flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    if not ok:
        return None
    g = cs.reshape(6, 9, 2)
    return max([bend(g[r]) for r in range(6)] + [bend(g[:, k]) for k in range(9)])


@c.test("load_calibration() reads K, the camera matrix",
        hint='K is the 9 numbers of "camera_matrix" put in 3 rows of 3: np.array(d["camera_matrix"]).reshape(3, 3).')
def _():
    K, _, _ = calib()
    c.eq(K.shape, (3, 3), "the shape of K")
    c.near(K[0, 0], REAL["fx"], 0.01, "K[0, 0] (fx)")
    c.near(K[0, 2], REAL["cx"], 0.01, "K[0, 2] (cx)")
    c.near(K[1, 1], REAL["fy"], 0.01, "K[1, 1] (fy)")


@c.test("load_calibration() reads D (4 fisheye numbers) and the picture size",
        hint='D comes from "distortion"; size is a tuple (d["image_width"], d["image_height"]) — width first.')
def _():
    _, D, size = calib()
    c.eq(D.size, 4, "the number of values in D")
    c.near(D[0], REAL["k1"], 1e-6, "D[0] (k1)")
    c.eq(tuple(int(v) for v in size), (1920, 540), "size")


@c.test("straight_camera_matrix(90, (1000, 500)) is a perfect camera of 90°",
        hint="tan(45°) = 1, so f = (1000/2) / 1 = 500; the centre is (w/2, h/2) = (500, 250). Did you use math.radians()?")
def _():
    (scm,) = need(fe(), "straight_camera_matrix")
    K = scm(90.0, (1000, 500))
    c.ok(K is not None, "straight_camera_matrix() returns None (TODO 2)")
    K = np.asarray(K, dtype=float)
    c.eq(K.shape, (3, 3), "the shape of the matrix")
    c.near(K[0, 0], 500.0, 0.01, "f in K[0, 0]")
    c.near(K[1, 1], 500.0, 0.01, "f in K[1, 1]")
    c.near(K[0, 2], 500.0, 0.01, "cx in K[0, 2]")
    c.near(K[1, 2], 250.0, 0.01, "cy in K[1, 2]")
    c.near(K[2, 2], 1.0, 1e-9, "K[2, 2]")


@c.test("straight_camera_matrix(111, (1920, 540)): NAVERA's straight view of the Insta360",
        hint="Half of 111° is 55.5°: f = 960 / tan(55.5°). Use the WIDTH (the first number of size).")
def _():
    (scm,) = need(fe(), "straight_camera_matrix")
    K = scm(111.0, (1920, 540))
    c.ok(K is not None, "straight_camera_matrix() returns None (TODO 2)")
    K = np.asarray(K, dtype=float)
    c.near(K[0, 0], 659.79, 0.05, "f")
    c.near(K[1, 2], 270.0, 0.01, "cy")


@c.test("fisheye_fov_deg() finds the lens' field of view: about 166° x 43°",
        hint="Left edge: cx pixels from the centre, right edge: (w - 1 - cx). Divide by fx to get radians, "
             "add them, then math.degrees(). Vertically use cy, fy and h.")
def _():
    m = fe()
    (fov,) = need(m, "fisheye_fov_deg")
    K, _, size = calib()
    r = fov(K, size)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, "fisheye_fov_deg() must return two numbers: (hfov, vfov)")
    c.ok(r[0] is not None, "fisheye_fov_deg() returns None (TODO 5)")
    c.near(r[0], 166.47, 0.1, "the horizontal field of view (deg)")
    c.near(r[1], 42.81, 0.1, "the vertical field of view (deg)")


@c.test("line_bend_px() gives 0 for points on a straight line",
        hint="Fit the line through ALL the points, then measure each point's distance to it. Return a float.")
def _():
    (lb,) = need(fe(), "line_bend_px")
    pts = np.array([[x, 2.0 * x + 1.0] for x in range(0, 50, 5)])
    v = lb(pts)
    c.ok(v is not None, "line_bend_px() returns None (TODO 4)")
    c.near(v, 0.0, 0.01, "line_bend_px(points on y = 2x + 1)")


@c.test("line_bend_px() measures a bent row AND a bent column",
        hint="Points (0,0) (10,0) (20,4) (30,0) (40,0): the best line is y = 0.8, so the middle point is 3.2 px "
             "away. For a COLUMN (x and y swapped) a fit of y = a·x + b fails — use cv2.fitLine, which works "
             "in every direction.")
def _():
    (lb,) = need(fe(), "line_bend_px")
    row = np.array([[0, 0], [10, 0], [20, 4], [30, 0], [40, 0]], dtype=float)
    c.near(lb(row), 3.2, 0.05, "line_bend_px(bent row)")
    c.near(lb(row[:, ::-1].copy()), 3.2, 0.05, "line_bend_px(bent column)")


@c.test("undistort() gives the same picture as NAVERA's camera_model.py",
        hint="Use cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), K_new, (w, h), cv2.CV_16SC2), then "
             "cv2.remap(img, map1, map2, cv2.INTER_LINEAR). The size is (width, height) = (img.shape[1], img.shape[0]).")
def _():
    import cv2
    (und,) = need(fe(), "undistort")
    K, D, size = calib()
    img = cv2.imread(FRAME)
    f = 960.0 / math.tan(math.radians(55.5))
    Kn = np.array([[f, 0, 960.0], [0, f, 270.0], [0, 0, 1]])
    out = und(img, K, D, Kn)
    c.ok(out is not None, "undistort() returns None (TODO 3)")
    out = np.asarray(out)
    c.eq(out.shape, img.shape, "the shape of the straightened picture")
    m1, m2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), Kn, size, cv2.CV_16SC2)
    ref = cv2.remap(img, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    d = float(np.abs(out.astype(int) - ref.astype(int)).mean())
    c.ok(d < 2.0, f"your picture differs from NAVERA's by {d:.1f} grey levels per pixel on average "
                  "(less than 2 expected) — is K_new used as the NEW camera, and D as the 4 fisheye numbers?")


@c.test("the straightened chessboard really has straight lines",
        hint="This uses your undistort() on views/f0208.jpg: before, a line bends ~6.5 px; after, it should "
             "be under 2 px.")
def _():
    import cv2
    (und,) = need(fe(), "undistort")
    K, D, _ = calib()
    img = cv2.imread(FRAME)
    f = 960.0 / math.tan(math.radians(55.5))
    out = und(img, K, D, np.array([[f, 0, 960.0], [0, f, 270.0], [0, 0, 1]]))
    c.ok(out is not None, "undistort() returns None (TODO 3)")
    before, after = worst(img), worst(np.ascontiguousarray(out))
    c.ok(after is not None, "the chessboard cannot be found in your straightened picture")
    c.ok(after < 2.0 and after < before / 2,
         f"most bent line: {before:.1f} px before, {after:.1f} px after — it should be under 2 px")


@c.test("you ran fisheye.py: before_after.jpg is saved",
        hint="Run `python3 fisheye.py` in the terminal (Step 5) once all the TODOs work.")
def _():
    import cv2
    c.file_exists("before_after.jpg")
    im = cv2.imread("before_after.jpg")
    c.ok(im is not None and im.shape[:2] == (1080, 1920),
         "before_after.jpg should be the two 1920x540 pictures one above the other — run fisheye.py again")


@c.test("you calibrated the lens yourself: my_calib.yaml",
        hint="Run NAVERA's calibrate_camera.py on /data/academy/18-calibration/views with --board 9x6 "
             "--square-mm 32.94 --out my_calib.yaml (Step 7).")
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
    c.ok(abs(fx - REAL["fx"]) / REAL["fx"] < 0.03,
         f"fx = {fx:.1f} px is far from the real 660 px — check --board 9x6 and the image folder")
    c.ok(rms < 1.0, f"RMS {rms:.2f} px is too large — check --board 9x6")


ANSWERS = {"Q1": ("a", "Read 'How wide should the straight picture be?' in the course again."),
           "Q2": ("b", "K is measured in pixels of ONE picture size. Read the part 'In NAVERA'."),
           "Q3": ("b", "RMS is measured in pixels on the picture, not in meters.")}

for q, (good, hint) in ANSWERS.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f'{q} = "{v}" is not the right answer')

c.run()

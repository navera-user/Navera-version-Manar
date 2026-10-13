"""navera_lite/fisheye.py — a real lens: the fisheye (Kannala–Brandt) model, where it is valid, how much a
straight view stretches it, straightening, and calibration from chessboard views (Zhang's idea, done by
OpenCV) with an honest test on views the calibration never saw. Part of NAVERA Lite, the course's teaching
stack (mission 19). Written for the course; it is not NAVERA code.

Conventions (courses/_lib/CONVENTIONS.md and mission 18):
  camera : OpenCV — x to the image right, y to the image BOTTOM, z along the optical axis (out of the lens).
  Pixels : (u, v) = (column, row), the origin at the top-left corner of the image; size = (width, height).
  theta  : the angle between a ray and the optical axis. Radians inside the maths, degrees at the
           interface when a name ends in _deg.
  K      : 3 × 3 [[fx, 0, cx], [0, fy, cy], [0, 0, 1]] (no skew).  D : the 4 fisheye numbers k1, k2, k3, k4.
  OpenCV point arrays: board points (N, 1, 3), detected corners (N, 1, 2), float64.
"""
import math
import re

import cv2
import numpy as np
import yaml

# @part 19
BOARD = (9, 6)                    # inner corners of the course's chessboard: 9 columns × 6 rows
# @part 19
SQUARE_M = 0.03294                # side of one square of the board shown on the bench screen (m)
# @part 19
CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-9)


# ============================================================================ given helpers

# @part 19
def load_calibration(path):
    """Read a calibration file (YAML) as a dict with numpy values ready for the maths:
    "model" (str), "K" (3 × 3 float array), "D" (float array of the 4 fisheye numbers k1..k4),
    "size" ((width, height) in pixels), "rms_px", "views", "out_hfov_deg", "crop" ([x, y, w, h] or None)
    and every other key of the file as it is.

    Example: load_calibration("/data/academy/19-calibration/insta360_top.yaml")["K"][0, 0] → about 660.48
    """
    with open(path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "camera_matrix" not in raw or "distortion" not in raw:
        raise ValueError(f"{path} is not a calibration file (no camera_matrix / distortion)")
    out = dict(raw)
    out["K"] = np.array(raw["camera_matrix"], dtype=float).reshape(3, 3)
    out["D"] = np.array(raw["distortion"], dtype=float).ravel()[:4]
    out["size"] = (int(raw["image_width"]), int(raw["image_height"]))
    out.setdefault("model", "fisheye")
    out.setdefault("crop", None)
    return out


# @part 19
def save_calibration(path, K, D, size, rms_px, views, out_hfov_deg=111.0, crop=None, note=""):
    """Write a calibration file in the same YAML layout as the bench file (load_calibration reads it back).

    Example: save_calibration("my_calib.yaml", K, D, (1920, 540), 0.51, 34) writes my_calib.yaml
    """
    K = np.asarray(K, dtype=float)
    data = {"model": "fisheye", "image_width": int(size[0]), "image_height": int(size[1]),
            "camera_matrix": [float(v) for v in K.ravel()],
            "distortion": [float(v) for v in np.asarray(D, dtype=float).ravel()[:4]],
            "rms_px": round(float(rms_px), 3), "views": int(views), "out_hfov_deg": float(out_hfov_deg),
            "crop": [int(v) for v in (crop or (0, 0, size[0], size[1]))]}
    with open(path, "w") as f:
        f.write("# camera calibration written by NAVERA Lite (python3 -m navera_lite.tools.calibrate)"
                + (f" — {note}" if note else "") + "\n")
        yaml.safe_dump(data, f, sort_keys=False)


# @part 19
def theta_d_of(theta, D):
    """The lens polynomial of the fisheye model: theta_d = theta·(1 + k1·theta² + k2·theta⁴ + k3·theta⁶ + k4·theta⁸).
    theta in radians (a float or a numpy array); returns the same shape (radians of the IDEAL equidistant lens:
    the distance from the principal point is fx · theta_d).

    Example: theta_d_of(0.5097, [0.2319, -0.4170, 0.5338, -0.2386]) → about 0.5303
    """
    k1, k2, k3, k4 = (float(v) for v in np.asarray(D, dtype=float).ravel()[:4])
    t = np.asarray(theta, dtype=float)
    t2 = t * t
    out = t * (1.0 + k1 * t2 + k2 * t2 ** 2 + k3 * t2 ** 3 + k4 * t2 ** 4)
    return float(out) if out.ndim == 0 else out


# @part 19
def find_corners(img, board=BOARD):
    """The inner corners of the chessboard in an image (BGR or grey): a (N, 1, 2) float64 array in the
    detector's order (row by row, the column index changing fastest), or None when the board is not found.
    Slow on purpose (exhaustive search, sub-pixel accuracy): about 1–2 s for a 1920 × 540 view.

    Example: find_corners(cv2.imread("/data/academy/19-calibration/views/f0216.jpg")).shape → (54, 1, 2)
    """
    grey = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ok, c = cv2.findChessboardCornersSB(grey, tuple(board), flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    return c.astype(np.float64).reshape(-1, 1, 2) if ok else None


# @part 19
def calibrate_robust(obj, views, size, names=None, min_views=6):
    """Your calibrate_fisheye() on every view, dropping the views OpenCV refuses as ill-conditioned
    (CALIB_CHECK_COND names them: "... input array N") one at a time, until it succeeds.

    Returns ((rms, K, D, rvecs, tvecs), kept_names, dropped_names). Names default to the view indices.
    Raises the last cv2.error if fewer than min_views views would remain.
    Example: calibrate_robust(obj, views, (1920, 540), names)[2] → ['f0023', 'f0208'] on the course's views
    """
    views = list(views)
    names = list(names) if names is not None else list(range(len(views)))
    dropped = []
    while True:
        try:
            result = calibrate_fisheye(obj, views, size)
        except cv2.error as e:
            m = re.search(r"input array (\d+)", str(e))
            if not m or len(views) <= min_views:
                raise
            bad = int(m.group(1))
            dropped.append(names[bad])
            del views[bad], names[bad]
            continue
        if result is None:
            raise ValueError("calibrate_fisheye() returned None: is it written yet? Does it catch cv2.error? (It must "
                             "not: a refused view must reach calibrate_robust as an error.)")
        return result, names, dropped


# ============================================================================ the lens model (session 1)

# @part 19 todo 1
def fisheye_project(X_cam, K, D):
    """Pixels of 3-D points seen by a fisheye camera (the OpenCV fisheye model, no skew).

    X_cam: N points in the CAMERA frame, an (N, 3) array or list (metres, z > 0 along the optical axis).
    K: 3 × 3 intrinsic matrix; D: the 4 fisheye numbers k1..k4.
    Returns an (N, 2) numpy array of (u, v) pixels. A point on the optical axis lands on (cx, cy).
    Example: with the bench calibration (load_calibration(...)), fisheye_project([[1.0, 0.5, 2.0]], K, D)
             → about [[1250.35, 488.75]]
    """
    X = np.asarray(X_cam, dtype=float).reshape(-1, 3)
    K = np.asarray(K, dtype=float)
    a = X[:, 0] / X[:, 2]
    b = X[:, 1] / X[:, 2]
    r = np.hypot(a, b)
    theta = np.arctan(r)
    td = theta_d_of(theta, D)
    scale = np.ones_like(r)
    nz = r > 1e-12
    scale[nz] = td[nz] / r[nz]
    u = K[0, 0] * a * scale + K[0, 2]
    v = K[1, 1] * b * scale + K[1, 2]
    return np.stack([u, v], axis=1)


# @part 19 todo 2
def theta_from_theta_d(theta_d, D):
    """The ray angle theta (radians) whose lens polynomial gives theta_d: the inverse of theta_d_of(), on the
    RISING part of the curve only (from 0 to the first maximum below 90°).

    theta_d: one float ≥ 0 (radians of the ideal lens = the distance from the principal point / fx).
    Returns a float (radians, within 1e-9 rad), or float("nan") when no angle of the rising part gives
    theta_d: the calibration cannot describe that pixel.
    Example: with the bench D, theta_from_theta_d(0.5303, D) → about 0.5097 ; theta_from_theta_d(1.30, D) → nan
    """
    theta_d = float(theta_d)
    if theta_d < 0.0 or math.isnan(theta_d):
        return float("nan")
    grid = np.linspace(0.0, math.pi / 2, 20001)
    vals = theta_d_of(grid, D)
    falling = np.nonzero(np.diff(vals) <= 0.0)[0]
    top = int(falling[0]) if len(falling) else len(grid) - 1
    if theta_d > vals[top]:
        return float("nan")
    lo, hi = 0.0, float(grid[top])
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if theta_d_of(mid, D) < theta_d:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# @part 19 todo 3
def stretch_at(theta_deg, f_new_px, K, D):
    """How much a straight (pinhole) picture with focal length f_new_px stretches the fisheye picture at theta_deg
    from the optical axis, along a horizontal radius: the straight picture's pixels per radian there divided by
    the lens' own pixels per radian there. 1 = the same detail; above 1 = pixels invented by interpolation;
    below 1 = real detail thrown away.

    Returns a float, or float("nan") where the lens model is not valid (its curve no longer rises) or at or
    beyond 90° (a pinhole cannot show it).
    Example: with the bench K, D: stretch_at(0.0, 659.79, K, D) → about 0.999 ; stretch_at(40.0, 659.79, K, D)
             → about 1.474
    """
    t = math.radians(float(theta_deg))
    if not 0.0 <= t < math.pi / 2:
        return float("nan")
    k1, k2, k3, k4 = (float(v) for v in np.asarray(D, dtype=float).ravel()[:4])
    slope = 1.0 + 3 * k1 * t ** 2 + 5 * k2 * t ** 4 + 7 * k3 * t ** 6 + 9 * k4 * t ** 8
    if slope <= 0.0:
        return float("nan")
    fx = float(np.asarray(K, dtype=float)[0, 0])
    return (float(f_new_px) / math.cos(t) ** 2) / (fx * slope)


# @part 19 todo 4
def undistort(img, K, D, K_new):
    """The straightened picture: what an ideal pinhole camera K_new, at the same place and turned the same way,
    would see. Same size as img; directions the lens never saw come out black.

    img: a numpy image (H × W or H × W × 3, uint8). K, D: the fisheye calibration. K_new: 3 × 3.
    Returns a numpy image of the same shape and dtype.
    Example: undistort(img, K, D, K_from_hfov(111.0, 1920, 540)).shape → (540, 1920, 3) for a 1920 × 540 view
    """
    h, w = img.shape[:2]
    m1, m2 = cv2.fisheye.initUndistortRectifyMap(np.asarray(K, dtype=float), np.asarray(D, dtype=float).ravel()[:4],
                                                 np.eye(3), np.asarray(K_new, dtype=float), (w, h), cv2.CV_16SC2)
    return cv2.remap(img, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


# ============================================================================ calibration (session 2)

# @part 19 todo 5
def board_points(cols, rows, square_m):
    """The 3-D positions of the board's inner corners in the BOARD's own frame: the board is the plane Z = 0,
    corner (0, 0) at the origin, x along a row, y down the columns, in the detector's order (row by row, the
    column index changing fastest).

    Returns a (cols·rows, 1, 3) float64 array (metres).
    Example: board_points(3, 2, 0.5)[:, 0] → [[0, 0, 0], [0.5, 0, 0], [1.0, 0, 0], [0, 0.5, 0], [0.5, 0.5, 0], [1.0, 0.5, 0]]
    """
    obj = np.zeros((rows * cols, 1, 3), np.float64)
    i = 0
    for r in range(rows):
        for c in range(cols):
            obj[i, 0, 0] = c * square_m
            obj[i, 0, 1] = r * square_m
            i += 1
    return obj


# @part 19 todo 6
def calibrate_fisheye(obj, views, size):
    """One fisheye calibration (OpenCV's cv2.fisheye.calibrate) on all the views, with three flags: recompute the
    board poses at each iteration, refuse ill-conditioned views, no skew — and the stop criteria CRITERIA,
    starting from K = identity and D = four zeros. A refused view raises cv2.error: do not
    catch it (calibrate_robust() needs it).

    obj: board_points (N, 1, 3); views: a list of detected corners, each (N, 1, 2) float64; size: (width, height).
    Returns (rms_px, K, D, rvecs, tvecs) exactly as OpenCV gives them: a float, a 3 × 3 array, a 4 × 1 array and
    two lists of 3 × 1 arrays (one per view).
    Example: calibrate_fisheye(obj, views_34, (1920, 540))[0] → about 0.506 (views_34: the 34 course views that
             OpenCV accepts; with all 36, OpenCV refuses one and raises cv2.error)
    """
    flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND | cv2.fisheye.CALIB_FIX_SKEW
    objs = [np.asarray(obj, dtype=np.float64).reshape(-1, 1, 3)] * len(views)
    imgs = [np.asarray(v, dtype=np.float64).reshape(-1, 1, 2) for v in views]
    rms, K, D, rvecs, tvecs = cv2.fisheye.calibrate(objs, imgs, tuple(int(s) for s in size), np.eye(3),
                                                    np.zeros((4, 1)), flags=flags, criteria=CRITERIA)
    return rms, K, D, rvecs, tvecs


# @part 19 todo 7
def reprojection_rms(obj, views, rvecs, tvecs, K, D):
    """The reprojection error of a calibration: each view's board corners obj (N, 1, 3), placed in the camera
    frame by that view's pose (rvec: a Rodrigues vector, tvec: metres — board → camera, as OpenCV returns
    them), projected with fisheye_project(), compared with the corners detected in that view (views[i],
    N × 1 × 2 pixels).

    Returns (rms over ALL corners of all views in px, [rms of each view in px]) — a float and a list of floats.
    Example: reprojection_rms(obj, [corners], [rvec], [tvec], K, D) → (0.0, [0.0]) when the corners are exactly
             the projected points
    """
    O = np.asarray(obj, dtype=float).reshape(-1, 3)
    all_sq, per_view = [], []
    for v, rv, tv in zip(views, rvecs, tvecs):
        R, _ = cv2.Rodrigues(np.asarray(rv, dtype=float).reshape(3, 1))
        Xc = O @ R.T + np.asarray(tv, dtype=float).reshape(1, 3)
        e = fisheye_project(Xc, K, D) - np.asarray(v, dtype=float).reshape(-1, 2)
        sq = (e ** 2).sum(axis=1)
        all_sq.append(sq)
        per_view.append(float(np.sqrt(sq.mean())))
    return float(np.sqrt(np.concatenate(all_sq).mean())), per_view


# @part 19 todo 8
def holdout_rms(obj, test_views, K, D):
    """The honest test of a calibration (K, D): its reprojection error on views it was NOT made from. The pose of
    the board in each test view is unknown, so it is first estimated from that view's corners with K and D held
    fixed; then the error is measured exactly as reprojection_rms() does.

    Returns (rms over all corners in px, [rms of each view in px]).
    Example: a calibration made from 28 of the course's views, tested on the 8 others → about (0.57, [...])
    """
    rvecs, tvecs = [], []
    O = np.asarray(obj, dtype=np.float64).reshape(-1, 1, 3)
    for v in test_views:
        n = cv2.fisheye.undistortPoints(np.asarray(v, dtype=np.float64).reshape(-1, 1, 2), np.asarray(K, dtype=float),
                                        np.asarray(D, dtype=float).ravel()[:4])
        ok, rv, tv = cv2.solvePnP(O, n, np.eye(3), None)
        rvecs.append(rv)
        tvecs.append(tv)
    return reprojection_rms(obj, test_views, rvecs, tvecs, K, D)

# Lab 18 — Part A: the fisheye lens model of NAVERA's Insta360, written by hand.
#
# Run:  python3 fisheye_model.py
# It loads the REAL bench calibration, checks your projection against OpenCV, straightens
# one real frame, measures how bent the chessboard lines are before and after, saves
# before_after.jpg and writes the "model" part of results.json.
import json
import math
import os

import cv2
import numpy as np
import yaml

DATA = "/data/academy/18-calibration"
CALIB_FILE = DATA + "/insta360_top.yaml"
EXAMPLE = DATA + "/views/f0216.jpg"
HFOV = 111.0           # width of the straight picture (deg), as NAVERA publishes it


def load_calibration(path):
    """Read a NAVERA calibration YAML.
    Returns (K, D, size): K a 3x3 float array, D a float array of the 4 fisheye
    coefficients k1..k4, size = (width, height) in pixels."""
    # TODO 1: look at the file first (lab Step 1). Which keys hold K, D and the size?
    #   yaml.safe_load() gives a Python dictionary.
    return None, None, None


def project_fisheye(X_cam, K, D):
    """Project 3D points given in the CAMERA frame (N x 3, metres, z forward) to pixels
    (N x 2) with OpenCV's fisheye model (equidistant + k1..k4 polynomial, no skew)."""
    # TODO 2: the five steps of lesson section 2.3, on all N points at once (numpy columns,
    #   no Python loop needed). One step divides by r: think about a point ON the axis (r = 0).
    #   Out: an (N, 2) array of pixels.
    return None


def theta_d_of(theta, D):
    """theta_d = theta (1 + k1 theta^2 + k2 theta^4 + k3 theta^6 + k4 theta^8) (works on arrays)."""
    k1, k2, k3, k4 = np.asarray(D, dtype=float).ravel()[:4]
    t2 = theta * theta
    return theta * (1 + k1 * t2 + k2 * t2**2 + k3 * t2**3 + k4 * t2**4)


def theta_from_theta_d(theta_d, D):
    """Invert theta_d = theta (1 + k1 theta^2 + ... + k4 theta^8) on its RISING part.
    Returns theta (rad), or float('nan') when no angle of the rising part gives theta_d
    (the calibration cannot describe that pixel)."""
    # TODO 3: lesson section 6 shows the shape of the curve (it rises, then falls).
    #   Lab Step 3 gives the plan. In: theta_d (a float). Out: theta (a float, rad) or nan.
    return None


def reprojection_rms(obj_pts, img_pts_list, rvecs, tvecs, K, D):
    """RMS reprojection error (px) over all views, and the RMS of each view.
    obj_pts: the board corners (54 x 1 x 3) in the board frame; img_pts_list: the corners
    seen in each view; rvecs/tvecs: the pose of the board in each view (from calibration)."""
    # TODO 4: lesson section 4 (the RMS) and section 3 (rvec = a Rodrigues vector, tvec).
    #   For each view: move the board corners into the camera frame, project them with YOUR
    #   project_fisheye(), compare with the corners seen.
    #   Out: (overall RMS over ALL corners, [RMS of each view]).
    return None, None


def straight_camera_matrix(hfov_deg, size):
    """The K of a perfect (pinhole) camera with this horizontal field of view, for an
    image of `size` = (w, h), principal point in the middle. Out: a 3x3 float array."""
    # TODO 5: lesson section 8 (f_new) and lesson 17 (the matrix K). Angles: degrees in, radians for math.tan.
    return None


def undistort(img, K, D, K_new):
    """The straightened image (same size as img), seen by the perfect camera K_new."""
    # TODO 6: lesson section 7 (straightening = a map, then remap) and the API table of
    #   section 5. No rotation. Use the map type cv2.CV_16SC2, bilinear interpolation and a
    #   constant (black) border. Careful with the size order (section 5, "Formats").
    return None


def line_bend_px(points):
    """Largest distance (px) between a point and the best straight line through all of them."""
    # TODO 7: In: an (N, 2) array of corners. Fit the best line in ANY direction (a column is
    #   almost vertical — see the tip in lab Step 4; OpenCV has cv2.fitLine), then the distance
    #   of each point to that line. Out: the LARGEST distance, as a float.
    return None


# ---- you don't need to change anything below this line ----
BOARD = (9, 6)          # inner corners of the chessboard shown on the screen: 9 columns x 6 rows


def find_corners(img):
    """The 54 inner corners of the chessboard (54 x 2 array, row by row), or None."""
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ok, c = cv2.findChessboardCornersSB(grey, BOARD, flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    return c.reshape(-1, 2) if ok else None


def worst_bend(corners):
    """The most bent row or column of the board (pixels)."""
    if corners is None:
        return None
    g = corners.reshape(BOARD[1], BOARD[0], 2)
    bends = [line_bend_px(g[r]) for r in range(BOARD[1])] + [line_bend_px(g[:, c]) for c in range(BOARD[0])]
    return None if any(b is None for b in bends) else max(bends)


def draw(img, corners, label):
    out = img.copy()
    if corners is not None:
        g = corners.reshape(BOARD[1], BOARD[0], 2)
        for r in range(BOARD[1]):                                 # each row, end to end in red
            a, b = g[r][0], g[r][-1]
            cv2.line(out, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (0, 0, 255), 2)
        cv2.drawChessboardCorners(out, BOARD, corners.reshape(-1, 1, 2).astype(np.float32), True)
    cv2.putText(out, label, (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 255), 3)
    return out


def save_results(section, values):
    """Merge one section into results.json (both lab scripts write to it)."""
    data = {}
    if os.path.exists("results.json"):
        try:
            data = json.load(open("results.json"))
        except ValueError:
            data = {}
    data[section] = values
    with open("results.json", "w") as f:
        json.dump(data, f, indent=2)


def todo(name, value):
    if value is None:
        raise SystemExit(f"{name}() is not written yet — it returns None")
    return value


if __name__ == "__main__":
    K, D, size = load_calibration(CALIB_FILE)
    todo("load_calibration", K)
    np.set_printoptions(precision=3, suppress=True)
    print("K =\n", K, "\nD =", D, "\nsize =", size)
    w, h = size
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]

    # 1. your projection against OpenCV's, on 1000 random directions up to 60 deg off-axis
    rng = np.random.default_rng(18)
    ang = np.radians(rng.uniform(0, 60, 1000))
    az = rng.uniform(0, 2 * np.pi, 1000)
    X = np.stack([np.sin(ang) * np.cos(az), np.sin(ang) * np.sin(az), np.cos(ang)], axis=1) * 3.0
    mine = todo("project_fisheye", project_fisheye(X, K, D))
    ref, _ = cv2.fisheye.projectPoints(X.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K, D)
    proj_diff = float(np.abs(np.asarray(mine) - ref.reshape(-1, 2)).max())
    print(f"\nproject_fisheye vs cv2.fisheye.projectPoints: largest difference {proj_diff:.2e} px")
    ex = project_fisheye(np.array([[1.0, 0.5, 2.0]]), K, D)[0]
    print(f"worked example X = (1.0, 0.5, 2.0) m -> pixel ({ex[0]:.2f}, {ex[1]:.2f})")

    # 2. field of view: the ideal rule, then what the calibration can really describe
    hfov_ideal = math.degrees(cx / fx + (w - 1 - cx) / fx)
    vfov_ideal = math.degrees(cy / fy + (h - 1 - cy) / fy)
    print(f"ideal-fisheye field of view (angle = r / f): {hfov_ideal:.1f} x {vfov_ideal:.1f} deg")
    grid = np.linspace(0, math.pi / 2, 20001)
    vals = theta_d_of(grid, D)
    i_peak = int(np.argmax(vals))
    peak_deg, peak_px = math.degrees(grid[i_peak]), float(vals[i_peak] * fx)
    print(f"the calibrated curve rises until {peak_deg:.1f} deg, i.e. {peak_px:.0f} px from the centre")
    left = theta_from_theta_d(cx / fx, D)
    print(f"left edge of the picture ({cx:.0f} px from the centre): theta = "
          f"{'not describable (nan)' if math.isnan(todo('theta_from_theta_d', left)) else f'{math.degrees(left):.1f} deg'}")

    # 3. straighten and measure
    K_new = todo("straight_camera_matrix", straight_camera_matrix(HFOV, size))
    print(f"\nstraight view: f = {K_new[0, 0]:.1f} px for {HFOV:g} deg (lens fx = {fx:.1f} px)")
    img = cv2.imread(EXAMPLE)
    flat = todo("undistort", undistort(img, K, D, K_new))
    c0, c1 = find_corners(img), find_corners(flat)
    b0, b1 = worst_bend(c0), worst_bend(c1)
    todo("line_bend_px", b0)
    if b1 is None:
        raise SystemExit("no chessboard found in the straightened picture — check undistort() (TODO 6)")
    print(f"most bent chessboard line: before {b0:.2f} px, after {b1:.2f} px")
    both = np.vstack([draw(img, c0, f"fisheye: worst line bent {b0:.1f} px"),
                      draw(flat, c1, f"straightened {HFOV:g} deg: {b1:.1f} px")])
    cv2.imwrite("before_after.jpg", both)
    print("saved before_after.jpg — open it in the editor")

    # 4. the crop trade-off
    trade = {}
    for hf in (111.0, 150.0, 166.0):
        f_new = (w / 2) / math.tan(math.radians(hf / 2))
        trade[str(int(hf))] = {"f_new_px": round(f_new, 2), "centre_ratio": round(f_new / fx, 4),
                               "edge_stretch": round(1 / math.cos(math.radians(hf / 2)) ** 2, 2)}
        print(f"straight view {hf:5.1f} deg: f = {f_new:6.1f} px, centre keeps {100 * f_new / fx:5.1f} % "
              f"of the lens' pixels per degree, edges stretched x{trade[str(int(hf))]['edge_stretch']}")
    max_out = math.degrees(2 * math.atan((w / 2) / fx))
    print(f"widest view with f >= fx: 2 atan({w / 2:.0f} / {fx:.1f}) = {max_out:.2f} deg")

    save_results("model", {
        "fx": fx, "fy": fy, "cx": cx, "cy": cy,
        "project_max_diff_px": proj_diff,
        "worked_example_px": [float(ex[0]), float(ex[1])],
        "fov_ideal_deg": [round(hfov_ideal, 2), round(vfov_ideal, 2)],
        "curve_peak_deg": round(peak_deg, 2), "curve_peak_px": round(peak_px, 1),
        "left_edge_theta_deg": None if math.isnan(left) else math.degrees(left),
        "bend_before_px": round(b0, 3), "bend_after_px": round(b1, 3),
        "max_out_hfov_deg": round(max_out, 3),
        "tradeoff": trade,
    })
    print("wrote the 'model' part of results.json")

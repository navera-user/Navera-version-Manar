# Lab 18 — straighten the real Insta360 fisheye picture.
#
# Run:  python3 fisheye.py
# It loads NAVERA's real calibration file, straightens one real frame of the Insta360's
# top lens, measures how bent the chessboard lines are before and after, and saves
# before_after.jpg (open it in the editor).
import math

import cv2
import numpy as np
import yaml

DATA = "/data/academy/18-calibration"
CALIB_FILE = DATA + "/insta360_top.yaml"
EXAMPLE = DATA + "/views/f0208.jpg"
HFOV = 111.0           # width of the straight picture (deg), as NAVERA publishes it


def load_calibration(path):
    """Read a NAVERA calibration YAML.
    Returns (K, D, size): K a 3x3 numpy array, D a numpy array of the 4 fisheye
    coefficients k1..k4, size = (width, height) in pixels."""
    # TODO 1: open the file, read it with yaml.safe_load(), then build
    #   K from the 9 numbers of "camera_matrix" (np.array(...).reshape(3, 3)),
    #   D from the 4 numbers of "distortion",
    #   size from "image_width" and "image_height".
    return None, None, None


def straight_camera_matrix(hfov_deg, size):
    """The K of a perfect (pinhole) camera with this horizontal field of view, for an
    image of `size` = (w, h): focal length f = (w/2) / tan(hfov/2), centre in the middle."""
    # TODO 2: compute f, then return np.array([[f, 0, w/2], [0, f, h/2], [0, 0, 1]]).
    #   Careful: math.tan() wants radians -> math.radians(hfov_deg).
    return None


def undistort(img, K, D, K_new):
    """The straightened image (same size as img), seen by the perfect camera K_new."""
    # TODO 3: cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), K_new, (w, h), cv2.CV_16SC2)
    #   gives two "maps" (where to fetch each output pixel); cv2.remap(img, map1, map2,
    #   cv2.INTER_LINEAR) builds the new picture from them.
    return None


def line_bend_px(points):
    """How far (pixels) the points are from being on one straight line: the largest
    distance between a point and the best straight line through all of them."""
    # TODO 4: fit the best line through the points (cv2.fitLine(points as float32,
    #   cv2.DIST_L2, 0, 0.01, 0.01) gives a direction (vx, vy) and a point (x0, y0)),
    #   then return the LARGEST distance of a point to that line, as a float.
    #   Distance of (x, y) to the line: |(x - x0) * vy - (y - y0) * vx|
    return None


def fisheye_fov_deg(K, size):
    """The field of view of the lens (horizontal, vertical) in degrees, with the ideal
    fisheye rule "angle (radians) = distance from the centre (pixels) / focal length":
    the left edge is cx pixels from the centre, the right edge (w - 1 - cx), etc."""
    # TODO 5: fx, fy, cx, cy are in K (K[0, 0], K[1, 1], K[0, 2], K[1, 2]).
    #   hfov (radians) = cx / fx + (w - 1 - cx) / fx ; same idea vertically with cy, fy, h.
    #   Return both in DEGREES: (hfov, vfov).
    return None, None


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
    lines = [g[r] for r in range(BOARD[1])] + [g[:, c] for c in range(BOARD[0])]
    bends = [line_bend_px(l) for l in lines]
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


if __name__ == "__main__":
    K, D, size = load_calibration(CALIB_FILE)
    print("K =\n", K, "\nD =", D, "\nsize =", size)
    img = cv2.imread(EXAMPLE)
    print(f"picture {img.shape[1]}x{img.shape[0]}")
    if K is None or D is None:
        raise SystemExit("load_calibration() is not written yet (TODO 1)")
    print(f"field of view of the lens (horizontal, vertical): {fisheye_fov_deg(K, size)} deg")
    K_new = straight_camera_matrix(HFOV, size)
    if K_new is None:
        raise SystemExit("straight_camera_matrix() is not written yet (TODO 2)")
    print(f"straight view: f = {K_new[0, 0]:.1f} px for {HFOV:g} deg")
    flat = undistort(img, K, D, K_new)
    if flat is None:
        raise SystemExit("undistort() is not written yet (TODO 3)")
    c0, c1 = find_corners(img), find_corners(flat)
    b0, b1 = worst_bend(c0), worst_bend(c1)
    print(f"most bent chessboard line: before {b0} px, after {b1} px")
    both = np.vstack([draw(img, c0, f"fisheye: worst line bent {b0 if b0 is None else round(b0, 1)} px"),
                      draw(flat, c1, f"straightened {HFOV:g} deg: {b1 if b1 is None else round(b1, 1)} px")])
    cv2.imwrite("before_after.jpg", both)
    print("saved before_after.jpg — open it in the editor")

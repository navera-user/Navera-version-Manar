"""navera_lite/tools/calibrate.py — calibrate a fisheye camera from photos of a chessboard and write the
calibration file. Part of NAVERA Lite, the course's teaching stack (mission 19). Written for the course; it is
not NAVERA code. It uses YOUR board_points() and calibrate_fisheye() (navera_lite/fisheye.py).

    python3 -m navera_lite.tools.calibrate --images /data/academy/19-calibration/views --board 9x6 \\
        --square-mm 32.94 --out my_calib.yaml
    python3 -m navera_lite.tools.calibrate --images frames/ --crop top --out my_calib.yaml    # full 2-lens frames

What it does: finds the inner corners in every photo (slow: 1–2 s per photo), calibrates with every view
that shows the whole board, drops the views OpenCV refuses as ill-conditioned one at a time, and writes the
YAML file (the same layout as the bench file) with the widest straight view that keeps the lens' centre
detail (at most 111°).
"""
import argparse
import glob
import math
import os
import sys

import cv2
import numpy as np

from navera_lite.fisheye import board_points, calibrate_robust, find_corners, save_calibration

# @part 19
CROPS = {"none": None, "top": "top", "bottom": "bottom"}


# @part 19
def crop_box(crop, width, height):
    """The [x, y, w, h] box a crop name keeps in a (width × height) picture: "top" and "bottom" are the two
    halves of a two-lens picture, "none" the whole picture.

    Example: crop_box("top", 1920, 1080) → [0, 0, 1920, 540]
    """
    if crop in (None, "none"):
        return [0, 0, width, height]
    if crop == "top":
        return [0, 0, width, height // 2]
    if crop == "bottom":
        return [0, height // 2, width, height - height // 2]
    raise ValueError(f"crop must be none, top or bottom, got {crop!r}")


# @part 19
def widest_hfov_deg(fx_px, width_px, cap_deg=111.0):
    """The widest straight view that keeps at least the lens' centre detail (f_new ≥ fx), capped at cap_deg.

    Example: widest_hfov_deg(660.48, 1920) → about 110.94
    """
    return min(float(cap_deg), math.degrees(2.0 * math.atan((width_px / 2.0) / float(fx_px))))


# @part 19
def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m navera_lite.tools.calibrate",
                                 description="Calibrate a fisheye camera from chessboard photos (NAVERA Lite).")
    ap.add_argument("--images", required=True, help="a folder of .jpg/.png photos of the board")
    ap.add_argument("--board", default="9x6", help="inner corners, COLUMNSxROWS (default 9x6)")
    ap.add_argument("--square-mm", type=float, default=32.94, help="side of one square, mm (default 32.94)")
    ap.add_argument("--crop", default="none", choices=sorted(CROPS), help="keep one half of a two-lens picture")
    ap.add_argument("--out", default="my_calib.yaml", help="the calibration file to write")
    a = ap.parse_args(argv)
    try:
        cols, rows = (int(v) for v in a.board.lower().split("x"))
    except ValueError:
        sys.exit(f"--board must look like 9x6 (inner corners, columns x rows), got {a.board!r}")
    files = sorted(glob.glob(os.path.join(a.images, "*.jpg")) + glob.glob(os.path.join(a.images, "*.png")))
    if not files:
        sys.exit(f"no .jpg or .png photo in {a.images}")
    obj = board_points(cols, rows, a.square_mm / 1000.0)
    if obj is None:
        sys.exit("board_points() is not written yet (navera_lite/fisheye.py, TODO 5)")
    names, views, size, box = [], [], None, None
    for f in files:
        img = cv2.imread(f)
        if img is None:
            print(f"  {os.path.basename(f)}: not an image, skipped")
            continue
        h, w = img.shape[:2]
        x, y, cw, ch = crop_box(CROPS[a.crop], w, h)
        img = img[y:y + ch, x:x + cw]
        if size is None:
            size, box = (cw, ch), [x, y, cw, ch]
        elif (cw, ch) != size:
            sys.exit(f"{os.path.basename(f)} is {cw}x{ch} after the crop, the first photo {size[0]}x{size[1]}: "
                     "a calibration is for ONE picture size — use photos of one size")
        c = find_corners(img, (cols, rows))
        print(f"  {os.path.basename(f)}: {'board found' if c is not None else 'no board'}", flush=True)
        if c is not None:
            names.append(os.path.splitext(os.path.basename(f))[0])
            views.append(c)
    if len(views) < 6:
        sys.exit(f"only {len(views)} photos show the whole board: take at least 6 (20 or more is better)")
    try:
        (rms, K, D, _, _), kept, dropped = calibrate_robust(obj, views, size, names)
    except cv2.error as e:
        sys.exit(f"OpenCV refused the calibration: {str(e).strip().splitlines()[-1]}")
    hfov = widest_hfov_deg(K[0, 0], size[0])
    save_calibration(a.out, K, D, size, rms, len(kept), out_hfov_deg=round(hfov, 2), crop=box,
                     note=f"{len(kept)} views of a {cols}x{rows} board, {a.square_mm:g} mm squares")
    verdict = "good" if rms < 0.5 else "usable" if rms < 1.0 else "poor: check the board and the photos"
    print(f"\nfisheye calibration from {len(kept)} views ({len(dropped)} refused: {', '.join(map(str, dropped)) or '-'}): "
          f"RMS {rms:.3f} px ({verdict})")
    np.set_printoptions(precision=3, suppress=True)
    print(f"fx {K[0, 0]:.2f}  fy {K[1, 1]:.2f}  cx {K[0, 2]:.2f}  cy {K[1, 2]:.2f}  D {np.asarray(D).ravel()}")
    print(f"widest straight view keeping the centre detail: {hfov:.2f} deg -> written to {a.out}")


if __name__ == "__main__":
    main()

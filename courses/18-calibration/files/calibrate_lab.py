# Lab 18 — Part B: calibrate the Insta360 top lens yourself, and test the calibration.
#
# Run:  python3 calibrate_lab.py
# 1. finds the 9x6 chessboard corners in the 37 real views (about 1 minute the first time,
#    then cached in corners.npz),
# 2. calibrates with YOUR calibrate_fisheye() and recomputes the RMS with YOUR
#    reprojection_rms() from fisheye_model.py,
# 3. measures how stable fx is with 8 / 12 / 20 / 30 views, and the error on views the
#    calibration has never seen (hold-out),
# 4. fits the Brown–Conrady (pinhole) model with YOUR calibrate_pinhole() on the same views,
# and writes the "calibration" part of results.json.
import glob
import math
import os
import re
import time

import cv2
import numpy as np

import fisheye_model as fm

VIEWS = "/data/academy/18-calibration/views"
BOARD = (9, 6)          # inner corners: 9 columns x 6 rows
SQUARE_M = 0.03294      # side of one square on the screen, in metres


def board_points(cols, rows, square_m):
    """3D coordinates of the inner corners in the BOARD frame (the board is the plane Z = 0):
    an array (cols*rows, 1, 3) of float64, in the order the detector returns them —
    row by row, the column index changing fastest: (0,0,0), (s,0,0), (2s,0,0), ..."""
    # TODO 8: corner (column i, row j) is at (i*s, j*s, 0). Build the (cols*rows, 1, 3)
    #   float64 array in the order above (np.mgrid or two loops both work).
    return None


def calibrate_fisheye(obj, views, size):
    """One call of cv2.fisheye.calibrate on all views. Returns (rms, K, D, rvecs, tvecs).
    Flags: recompute the board poses at each iteration, refuse ill-conditioned views,
    no skew."""
    # TODO 9: cv2.fisheye.calibrate(objectPoints, imagePoints, image_size, K, D, flags=..., criteria=...)
    #   objectPoints: one copy of obj per view; imagePoints: the list of views;
    #   start from K = np.eye(3), D = np.zeros((4, 1));
    #   flags: cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND | cv2.fisheye.CALIB_FIX_SKEW
    #   criteria: (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-9)
    #   It returns (rms, K, D, rvecs, tvecs): return them. Do NOT catch cv2.error here
    #   (calibrate_robust() below needs it to drop the refused views).
    return None


def calibrate_pinhole(obj, views, size):
    """The Brown–Conrady model (k1, k2, p1, p2, k3) with cv2.calibrateCamera on the same
    views. Returns (rms, K, dist, rvecs, tvecs). Careful: this function wants float32."""
    # TODO 10: cv2.calibrateCamera(objectPoints, imagePoints, size, None, None) returns
    #   (rms, K, dist, rvecs, tvecs). It refuses float64 points ("should contain vector of
    #   vectors of points of type Point3f") — convert obj and every view to np.float32 first.
    return None


# ---- you don't need to change anything below this line ----
def detect_all():
    """Corners of every view, cached in corners.npz (the detection is the slow part)."""
    files = sorted(glob.glob(os.path.join(VIEWS, "*.jpg")))
    if os.path.exists("corners.npz"):
        z = np.load("corners.npz")
        if len(z["names"]) and set(z["names"]) <= {os.path.basename(f)[:-4] for f in files}:
            print(f"corners.npz: {len(z['names'])} views (delete it to detect again)")
            return list(z["names"]), list(z["corners"]), tuple(int(v) for v in z["size"])
    names, views, size = [], [], None
    t0 = time.time()
    for f in files:
        img = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2GRAY)     # exactly as calibrate_camera.py
        size = (img.shape[1], img.shape[0])
        ok, c = cv2.findChessboardCornersSB(img, BOARD, flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
        print(f"  {os.path.basename(f)}: {'board found' if ok else 'no board'}", flush=True)
        if ok:
            names.append(os.path.basename(f)[:-4])
            views.append(c.astype(np.float64).reshape(-1, 1, 2))
    print(f"detection: {len(views)}/{len(files)} views in {time.time() - t0:.0f} s -> corners.npz")
    np.savez("corners.npz", names=np.array(names), corners=np.array(views), size=np.array(size))
    return names, views, size


def calibrate_robust(obj, views, size, names=None):
    """Your calibrate_fisheye(), dropping the views OpenCV refuses (CALIB_CHECK_COND), as
    navera_tools/calibrate_camera.py does. Returns (result, kept names, dropped names)."""
    views, names = list(views), list(names or range(len(views)))
    dropped = []
    while True:
        try:
            r = calibrate_fisheye(obj, views, size)
            if r is None:
                raise SystemExit("calibrate_fisheye() is not written yet — it returns None")
            return r, names, dropped
        except cv2.error as e:
            m = re.search(r"input array (\d+)", str(e))
            if not m or len(views) <= 8:
                raise
            bad = int(m.group(1))
            dropped.append(names[bad])
            del views[bad], names[bad]


def holdout_rms_fisheye(obj, test_views, K, D):
    """Error on views NOT used for calibration: the pose of the board is estimated from the
    undistorted corners (solvePnP), then the corners are projected with YOUR project_fisheye."""
    sq = []
    for v in test_views:
        n = cv2.fisheye.undistortPoints(v.reshape(-1, 1, 2), K, D)
        ok, rv, tv = cv2.solvePnP(obj.astype(np.float64), n, np.eye(3), None)
        R, _ = cv2.Rodrigues(rv)
        Xc = obj.reshape(-1, 3) @ R.T + tv.reshape(1, 3)
        e = fm.project_fisheye(Xc, K, D) - v.reshape(-1, 2)
        sq.append((e ** 2).sum(axis=1))
    return float(np.sqrt(np.concatenate(sq).mean()))


def holdout_rms_pinhole(obj, test_views, K, dist):
    sq = []
    for v in test_views:
        ok, rv, tv = cv2.solvePnP(obj.astype(np.float32), v.astype(np.float32), K, dist)
        p, _ = cv2.projectPoints(obj.astype(np.float32), rv, tv, K, dist)
        sq.append(((p.reshape(-1, 2) - v.reshape(-1, 2)) ** 2).sum(axis=1))
    return float(np.sqrt(np.concatenate(sq).mean()))


if __name__ == "__main__":
    obj = board_points(*BOARD, SQUARE_M)
    if obj is None:
        raise SystemExit("board_points() is not written yet — it returns None")
    print(f"board: {obj.shape[0]} corners, last one at {obj[-1].ravel()} m")
    names, views, size = detect_all()

    # 1. the calibration on every view
    t0 = time.time()
    (rms, K, D, rvecs, tvecs), kept, dropped = calibrate_robust(obj, views, size, names)
    print(f"\nfisheye calibration: {len(kept)} views used, {len(dropped)} refused {dropped}, "
          f"{time.time() - t0:.1f} s")
    np.set_printoptions(precision=2, suppress=True)
    print(f"  fx {K[0, 0]:.1f}  fy {K[1, 1]:.1f}  cx {K[0, 2]:.1f}  cy {K[1, 2]:.1f}  D {D.ravel()}")
    kept_views = [views[names.index(n)] for n in kept]
    mine, per_view = fm.reprojection_rms(obj, kept_views, rvecs, tvecs, K, D.ravel())
    if mine is None:
        raise SystemExit("reprojection_rms() is not written yet")
    print(f"  RMS: OpenCV {rms:.4f} px, your reprojection_rms() {mine:.4f} px")
    worst = int(np.argmax(per_view))
    print(f"  worst view {kept[worst]}: {per_view[worst]:.3f} px; best {min(per_view):.3f} px")
    def farthest_deg(vs):
        nrm = cv2.fisheye.undistortPoints(np.vstack(vs).reshape(-1, 1, 2), K, D).reshape(-1, 2)
        return float(np.degrees(np.arctan(np.hypot(nrm[:, 0], nrm[:, 1]))).max())
    max_angle, max_angle_all = farthest_deg(kept_views), farthest_deg(views)
    print(f"  farthest corner: {max_angle:.1f} deg from the optical axis in the views used, "
          f"{max_angle_all:.1f} deg in all the views detected")

    # 2. stability: random subsets of views
    rng = np.random.default_rng(18)
    subsets = {}
    print("\nstability of fx (6 random subsets per size):")
    for n in (8, 12, 20, 30):
        fxs, fails = [], 0
        for _ in range(6):
            idx = sorted(rng.choice(len(views), n, replace=False))
            try:
                (r_, K_, *_), _, _ = calibrate_robust(obj, [views[i] for i in idx], size)
                fxs.append(float(K_[0, 0]))
            except cv2.error:
                fails += 1
        subsets[str(n)] = {"fx": [round(v, 2) for v in fxs], "mean": float(np.mean(fxs)),
                           "std": float(np.std(fxs)), "failures": fails}
        print(f"  {n:2d} views: fx = {np.mean(fxs):6.1f} ± {np.std(fxs):5.1f} px  ({fails} failed)")

    # 3. hold-out: calibrate on 4/5 of the views, test on the others
    test_i = [i for i in range(len(views)) if i % 5 == 0]
    train_i = [i for i in range(len(views)) if i % 5 != 0]
    (tr_rms, Kt, Dt, *_), _, _ = calibrate_robust(obj, [views[i] for i in train_i], size)
    te_rms = holdout_rms_fisheye(obj, [views[i] for i in test_i], Kt, Dt)
    print(f"\nhold-out (fisheye): train RMS {tr_rms:.3f} px on {len(train_i)} views, "
          f"test RMS {te_rms:.3f} px on {len(test_i)} unseen views")

    # 4. Brown–Conrady on the same views
    pres = calibrate_pinhole(obj, views, size)
    if pres is None:
        raise SystemExit("calibrate_pinhole() is not written yet — it returns None")
    p_rms, Kp, dp = pres[0], pres[1], pres[2]
    rp, Kpt, dpt, *_ = calibrate_pinhole(obj, [views[i] for i in train_i], size)
    p_te = holdout_rms_pinhole(obj, [views[i] for i in test_i], Kpt, dpt)
    print(f"Brown–Conrady (pinhole) model: RMS {p_rms:.3f} px, fx {Kp[0, 0]:.1f} px, "
          f"dist {np.asarray(dp).ravel()}; hold-out test RMS {p_te:.3f} px")

    fm.save_results("calibration", {
        "views_detected": len(views), "views_used": len(kept), "dropped": dropped,
        "fx": float(K[0, 0]), "fy": float(K[1, 1]), "cx": float(K[0, 2]), "cy": float(K[1, 2]),
        "D": [float(v) for v in D.ravel()],
        "rms_opencv_px": float(rms), "rms_mine_px": float(mine),
        "worst_view": kept[worst], "worst_view_rms_px": per_view[worst],
        "max_corner_angle_deg": max_angle, "max_corner_angle_all_deg": max_angle_all,
        "subsets": subsets,
        "holdout": {"train_rms_px": float(tr_rms), "test_rms_px": te_rms,
                    "train_views": len(train_i), "test_views": len(test_i)},
        "pinhole": {"rms_px": float(p_rms), "fx": float(Kp[0, 0]),
                    "dist": [float(v) for v in np.asarray(dp).ravel()], "test_rms_px": p_te},
    })
    print("\nwrote the 'calibration' part of results.json")

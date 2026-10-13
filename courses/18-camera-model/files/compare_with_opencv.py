"""compare_with_opencv.py — an independent check of YOUR camera.py: OpenCV, the computer-vision library used
by most robots, computes the same things its own way (lab Step 10).

    python3 compare_with_opencv.py

0. camera_rotation_hpr() vs rotations built by OpenCV's own cv2.Rodrigues (axis-angle steps), so a wrong
                                                 rotations.py cannot hide: OpenCV's side never uses it
1. project()             vs cv2.projectPoints   (OpenCV takes the world → camera rotation as a Rodrigues
                                                 vector rvec and the translation tvec = −R_cw · C)
2. backproject_ground()  vs cv2.undistortPoints (OpenCV turns pixels into normalised rays K⁻¹·[u, v, 1];
                                                 the script intersects them with the ground itself)
3. nadir_homography()    vs cv2.findHomography  (OpenCV fits a homography to 50 pixel pairs: where ground
                                                 points appear in the real view and in the level view)
4. the straightened image vs cv2.warpPerspective of OpenCV's own homography
"""
import sys

import cv2
import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

cam = rk.load_student("navera_lite.camera")
W, H, HFOV = 960, 540, 90.0
ATTITUDES = [(0.0, 0.0, 0.0), (40.0, -14.0, 5.0), (215.0, -25.0, -8.0), (300.0, 6.0, 12.0)]
rng = np.random.default_rng(2026)
fails = 0


def verdict(ok, text):
    global fails
    fails += not ok
    print(("✔ " if ok else "✘ ") + text)


MOUNT = np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])   # nadir mount, image top = nose


def ref_R(heading_deg, pitch_deg, roll_deg):
    """R_wc built by OpenCV from the conventions sheet, never from your rotations.py: turn about Up by the ENU yaw
    90° − heading, about the body's left axis by the ROS pitch (= −human pitch), about the nose by the roll,
    then the nadir mount. cv2.Rodrigues turns an axis × angle vector into a rotation matrix."""
    rz, _ = cv2.Rodrigues(np.array([0.0, 0.0, np.radians(90.0 - heading_deg)]))
    ry, _ = cv2.Rodrigues(np.array([0.0, np.radians(-pitch_deg), 0.0]))
    rx, _ = cv2.Rodrigues(np.array([np.radians(roll_deg), 0.0, 0.0]))
    return rz @ ry @ rx @ MOUNT


print("0. Attitude: your camera_rotation_hpr() (through rotations.py) against OpenCV's cv2.Rodrigues")
for hd, p, r in ATTITUDES:
    mine = np.asarray(cam.camera_rotation_hpr(hd, p, r), dtype=float)
    verdict(mine.shape == (3, 3) and np.allclose(mine, ref_R(hd, p, r), atol=1e-9),
            f"heading {hd:5.1f}°, pitch {p:+5.1f}°, roll {r:+5.1f}°: R_wc "
            + ("agrees" if mine.shape == (3, 3) and np.allclose(mine, ref_R(hd, p, r), atol=1e-9)
               else "DIFFERS — rotations.py or camera_rotation_hpr does not follow the conventions sheet"))
print()
K = rk.need_ok(cam, "K_from_hfov", HFOV, W, H)
K = np.asarray(K, dtype=float)
K_cv = np.array([[W / 2 / np.tan(np.radians(HFOV / 2)), 0, W / 2], [0, W / 2 / np.tan(np.radians(HFOV / 2)), H / 2],
                 [0, 0, 1.0]])
verdict(np.allclose(K, K_cv, atol=1e-9), "K_from_hfov(90, 960, 540) is the ideal camera K (f = 480, centre (480, 270))")

print("\n1. Projection: your project() against cv2.projectPoints, 300 ground and air points per attitude")
for hd, p, r in ATTITUDES:
    R = cam.camera_rotation_hpr(hd, p, r)                 # yours, given to your functions
    Rr = ref_R(hd, p, r)                                   # OpenCV's, used on OpenCV's side
    C = np.array([rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(120, 300)])
    X = np.column_stack([rng.uniform(-400, 400, 300) + C[0], rng.uniform(-400, 400, 300) + C[1],
                         rng.uniform(0, 60, 300)])
    R_cw = Rr.T                                            # OpenCV wants world → camera: rvec, tvec = −R_cw·C
    rvec, _ = cv2.Rodrigues(R_cw)
    tvec = -R_cw @ C
    ref, _ = cv2.projectPoints(X.reshape(-1, 1, 3), rvec, tvec, K_cv, None)
    ref = ref.reshape(-1, 2)
    depth = (X - C) @ Rr[:, 2]                         # the depth of each point along the optical axis
    worst, wrong_none = 0.0, 0
    for k in range(len(X)):
        inside = -W <= ref[k, 0] <= 2 * W and -H <= ref[k, 1] <= 2 * H     # far outside: float noise grows
        uv, err = rk.call(cam, "project", K_cv, R, C, X[k])
        if err and "returned None" not in err:
            sys.exit(err)
        if uv is None:
            wrong_none += depth[k] > 0
            continue
        if depth[k] <= 0:
            wrong_none += 1
            continue
        if inside:
            worst = max(worst, float(np.hypot(*(np.asarray(uv, dtype=float) - ref[k]))))
    verdict(worst < 1e-4 and wrong_none == 0,
            f"heading {hd:5.1f}°, pitch {p:+5.1f}°, roll {r:+5.1f}°: worst difference {worst:.1e} px"
            + (f", {wrong_none} points wrongly None / not None" if wrong_none else ""))

print("\n2. Back-projection: your backproject_ground() against OpenCV's normalised rays")
for hd, p, r in ATTITUDES:
    R = cam.camera_rotation_hpr(hd, p, r)
    Rr = ref_R(hd, p, r)
    C = np.array([0.0, 0.0, 180.0])
    uv = np.column_stack([rng.uniform(0, W, 200), rng.uniform(0, H, 200)])
    norm = cv2.undistortPoints(uv.reshape(-1, 1, 2), K_cv, None).reshape(-1, 2)
    worst, wrong_none = 0.0, 0
    for k in range(len(uv)):
        d = Rr @ np.array([norm[k, 0], norm[k, 1], 1.0])
        want = None if d[2] >= 0 else (C + (-C[2] / d[2]) * d)[:2]
        got, err = rk.call(cam, "backproject_ground", K_cv, R, C, uv[k, 0], uv[k, 1])
        if err and "returned None" not in err:
            sys.exit(err)
        if (got is None) != (want is None):
            wrong_none += 1
            continue
        if got is not None:
            worst = max(worst, float(np.hypot(*(np.asarray(got, dtype=float) - want))))
    verdict(worst < 1e-6 and wrong_none == 0, f"heading {hd:5.1f}°, pitch {p:+5.1f}°, roll {r:+5.1f}°: worst difference "
            f"{worst:.1e} m" + (f", {wrong_none} rays wrongly None / not None" if wrong_none else ""))

print("\n3. Straightening: your nadir_homography() against cv2.findHomography on 50 pixel pairs")
level = cam.camera_rotation_hpr(0.0)
level_r = ref_R(0.0, 0.0, 0.0)
for hd, p, r in ATTITUDES[1:]:
    R = cam.camera_rotation_hpr(hd, p, r)
    Rr = ref_R(hd, p, r)
    C = np.array([0.0, 0.0, 170.0])
    src = np.column_stack([rng.uniform(100, W - 100, 50), rng.uniform(80, H - 80, 50)])
    ground = []
    for u, v in src:
        d = Rr @ np.linalg.solve(K_cv, [u, v, 1.0])
        ground.append(C + (-C[2] / d[2]) * d)
    ground = np.array(ground)
    dst, _ = cv2.projectPoints(ground.reshape(-1, 1, 3), cv2.Rodrigues(level_r.T)[0], -level_r.T @ C, K_cv, None)
    H_cv, _ = cv2.findHomography(src, dst.reshape(-1, 2), 0)
    H_cv = H_cv / H_cv[2, 2]
    Hm = rk.need_ok(cam, "nadir_homography", K_cv, R, level)
    Hm = np.asarray(Hm, dtype=float)
    if Hm.shape != (3, 3):
        sys.exit(f"nadir_homography() must return a 3 × 3 array, it returned shape {Hm.shape}")
    Hm = Hm / Hm[2, 2]
    moved = max(float(np.hypot(*(np.subtract(cam.warp_point(Hm, u, v), cam.warp_point(H_cv, u, v)))))
                for u, v in ((0, 0), (W, 0), (W, H), (0, H), (W / 2, H / 2)))
    verdict(moved < 1e-3, f"heading {hd:5.1f}°, pitch {p:+5.1f}°, roll {r:+5.1f}°: corners and centre agree within "
            f"{moved:.1e} px")

print("\n4. The straightened photo T: your homography vs OpenCV's, pixel by pixel")
mp = rk.load_student("measure_pad")
img = mp._read("photo_T.png")
R = cam.camera_rotation_hpr(40.0, -14.0, 5.0)
Rr = ref_R(40.0, -14.0, 5.0)
Hm = np.asarray(rk.need_ok(cam, "nadir_homography", K_cv, R, level), dtype=float)
mine = cv2.warpPerspective(img, Hm, (W, H))
src = np.array([[100, 80], [860, 80], [860, 460], [100, 460], [480, 270], [300, 400]], float)
gr = []
for u, v in src:
    d = Rr @ np.linalg.solve(K_cv, [u, v, 1.0])
    gr.append(np.array([0, 0, 170.0]) + (-170.0 / d[2]) * d)
dst, _ = cv2.projectPoints(np.array(gr).reshape(-1, 1, 3), cv2.Rodrigues(level_r.T)[0], -level_r.T @ np.array([0, 0, 170.0]),
                           K_cv, None)
H_cv, _ = cv2.findHomography(src, dst.reshape(-1, 2), 0)
ref = cv2.warpPerspective(img, H_cv, (W, H))
diff = np.abs(mine.astype(int) - ref.astype(int)).max(axis=2)
share = float((diff > 30).mean())
verdict(share < 0.01, f"{100 * (1 - share):.2f} % of the pixels agree (the rest: rounding at the borders)")

print("\nALL MATCH — your camera model agrees with OpenCV." if fails == 0 else
      f"\n{fails} line(s) disagree: fix the function named on each ✘ line (run_camera.py test helps).")

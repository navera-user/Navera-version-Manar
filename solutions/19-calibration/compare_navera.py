# Compare YOUR undistort() with the one NAVERA runs on every frame (navera_common/camera_model.py).
#   python3 compare_navera.py
# Nothing to change here.
import cv2
import numpy as np
import yaml
from navera_common.camera_model import CameraModel     # from your NAVERA copy (~/navera)

import fisheye_model as fm

calib = yaml.safe_load(open(fm.CALIB_FILE))
cam = CameraModel.from_calibration(calib)               # exactly what live_camera.py does
print(f"NAVERA: model {cam.model}, picture {cam.size[0]}x{cam.size[1]}")
print(f"NAVERA: max_out_hfov_deg() = 2 atan(w/2 / fx) = {cam.max_out_hfov_deg():.2f} deg")
print(f"NAVERA: out_hfov_deg asked in the file = {calib.get('out_hfov_deg')}, used = {cam.out_hfov_deg:.2f} deg "
      f"(capped), K_out focal length = {cam.K_out[0, 0]:.2f} px (lens fx = {cam.K[0, 0]:.2f} px)")

img = cv2.imread(fm.EXAMPLE)
theirs = cam.undistort(img)
K, D, size = fm.load_calibration(fm.CALIB_FILE)
K_new = fm.straight_camera_matrix(cam.out_hfov_deg, size)
mine = None if K is None or K_new is None else fm.undistort(img, K, D, K_new)
if mine is None:
    raise SystemExit("finish load_calibration(), straight_camera_matrix() and undistort() first")
diff = np.abs(mine.astype(int) - theirs.astype(int))
print(f"mean difference per pixel: {diff.mean():.3f} grey levels (0 = identical)")

# the same comparison for single points: NAVERA's undistort_points() against your model
pts = np.array([[[200.0, 100.0]], [[960.0, 270.0]], [[1700.0, 450.0]]])
und = cam.undistort_points(pts)                         # pixels of the straight picture
for p, q in zip(pts.reshape(-1, 2), und):
    print(f"  fisheye pixel ({p[0]:6.1f}, {p[1]:5.1f}) -> straight pixel ({q[0]:7.1f}, {q[1]:6.1f})")
cv2.imwrite("navera_vs_mine.jpg", np.vstack([theirs, mine]))
print("saved navera_vs_mine.jpg (top: NAVERA, bottom: yours)")

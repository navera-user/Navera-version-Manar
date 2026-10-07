# Compare YOUR undistort() with the one NAVERA uses on the drone (navera_common/camera_model.py).
#   python3 compare_navera.py
# Nothing to change here.
import cv2
import numpy as np
import yaml
from navera_common.camera_model import CameraModel     # from your NAVERA copy (~/navera)

import fisheye

calib = yaml.safe_load(open(fisheye.CALIB_FILE))
cam = CameraModel.from_calibration(calib)               # exactly what live_camera.py does
print(f"NAVERA: model {cam.model}, picture {cam.size[0]}x{cam.size[1]}")
print(f"NAVERA: widest straight view keeping the centre's detail = {cam.max_out_hfov_deg():.2f} deg")
print(f"NAVERA: published field of view out_hfov_deg = {cam.out_hfov_deg:.2f} deg, "
      f"focal length of the straight picture = {cam.K_out[0, 0]:.1f} px")

img = cv2.imread(fisheye.EXAMPLE)
theirs = cam.undistort(img)
K, D, size = fisheye.load_calibration(fisheye.CALIB_FILE)
mine = fisheye.undistort(img, K, D, fisheye.straight_camera_matrix(cam.out_hfov_deg, size))
if mine is None:
    raise SystemExit("your undistort() returns None: finish TODO 3 first")
diff = np.abs(mine.astype(int) - theirs.astype(int))
print(f"mean difference per pixel: {diff.mean():.2f} (0 = identical, 255 = opposite)")
cv2.imwrite("navera_vs_mine.jpg", np.vstack([theirs, mine]))
print("saved navera_vs_mine.jpg (top: NAVERA, bottom: yours)")

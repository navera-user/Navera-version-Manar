# Draw the lens curve of the real Insta360 calibration: where a ray that enters the lens
# at angle "theta" from the axis lands on the picture.
#   python3 lens_curve.py      -> saves lens_curve.png (open it in the editor)
# Nothing to change here: just run it and read the picture (Step 6 of the lab).
import math
import warnings

warnings.filterwarnings("ignore")     # a harmless matplotlib warning about 3D plots

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

d = yaml.safe_load(open("/data/academy/18-calibration/insta360_top.yaml"))
fx = d["camera_matrix"][0]
cx = d["camera_matrix"][2]
k1, k2, k3, k4 = d["distortion"]

theta = np.radians(np.linspace(0, 85, 400))                    # angle of the ray, from the axis
r_pinhole = fx * np.tan(theta)                                 # a perfect pinhole camera
r_ideal = fx * theta                                           # an ideal fisheye: distance = f x angle
r_real = fx * theta * (1 + k1 * theta**2 + k2 * theta**4 + k3 * theta**6 + k4 * theta**8)   # OpenCV fisheye

deg = np.degrees(theta)
plt.figure(figsize=(8, 5))
plt.plot(deg, r_pinhole, label="pinhole: f x tan(angle)")
plt.plot(deg, r_ideal, "--", label="ideal fisheye: f x angle")
plt.plot(deg, r_real, linewidth=3, label="Insta360 calibration (k1..k4)")
plt.axhline(cx, color="grey", linestyle=":")
plt.text(2, cx + 20, f"left edge of the picture: {cx:.0f} px from the centre", color="grey")
plt.ylim(0, 1600)
plt.xlabel("angle of the ray from the optical axis (deg)")
plt.ylabel("distance from the image centre (px)")
plt.title("Where a ray lands on the picture")
plt.legend()
plt.grid(alpha=0.3)
plt.savefig("lens_curve.png", dpi=90, bbox_inches="tight")
i = int(np.argmax(r_real))
print(f"the calibrated curve rises up to {r_real[i]:.0f} px at {deg[i]:.0f} deg, then turns back down")
print("saved lens_curve.png — open it in the editor")

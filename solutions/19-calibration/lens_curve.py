# Draw the lens curves: where a ray that enters at angle theta from the optical axis lands,
# for the pinhole, the ideal fisheye, the bench calibration, YOUR fisheye calibration and
# YOUR Brown–Conrady (pinhole) calibration.
#   python3 lens_curve.py      -> saves lens_curve.png (open it in the editor)
# Nothing to change here. Run calibrate_lab.py first to see your own curves too.
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

d = yaml.safe_load(open("/data/academy/19-calibration/insta360_top.yaml"))
fx, cx = d["camera_matrix"][0], d["camera_matrix"][2]


def fisheye_r(theta, f, k):
    t2 = theta ** 2
    return f * theta * (1 + k[0] * t2 + k[1] * t2 ** 2 + k[2] * t2 ** 3 + k[3] * t2 ** 4)


def brown_r(theta, f, dist):
    k1, k2, p1, p2, k3 = (list(dist) + [0.0] * 5)[:5]
    r = np.tan(theta)                        # normalised radius of the ideal pinhole
    return f * r * (1 + k1 * r ** 2 + k2 * r ** 4 + k3 * r ** 6)   # radial part only, along a radius


theta = np.radians(np.linspace(0, 85, 500))
deg = np.degrees(theta)
plt.figure(figsize=(8.5, 5.2))
plt.plot(deg, fx * np.tan(theta), label="ideal pinhole: f tan(theta)")
plt.plot(deg, fx * theta, "--", label="ideal fisheye: f theta")
plt.plot(deg, fisheye_r(theta, fx, d["distortion"]), linewidth=3, label="bench calibration (38 views)")
mine = {}
if os.path.exists("results.json"):
    mine = json.load(open("results.json")).get("calibration", {})
if mine:
    plt.plot(deg, fisheye_r(theta, mine["fx"], mine["D"]), ":", linewidth=2.5, label="your fisheye calibration")
    p = mine["pinhole"]
    plt.plot(deg, brown_r(theta, p["fx"], p["dist"]), "-.", linewidth=2, label="your Brown–Conrady fit")
    plt.axvspan(mine["max_corner_angle_deg"], 85, color="grey", alpha=0.12)
    plt.text(mine["max_corner_angle_deg"] + 1, 1500, "no corner used by\nyour calibration", color="grey")
plt.axhline(cx, color="grey", linestyle=":")
plt.text(2, cx + 20, f"left edge of the picture: {cx:.0f} px from the centre", color="grey")
plt.ylim(0, 1600)
plt.xlabel("angle theta of the ray from the optical axis (deg)")
plt.ylabel("distance r from the principal point (px)")
plt.title("Where a ray lands on the Insta360 picture")
plt.legend(loc="upper left", fontsize=9)
plt.grid(alpha=0.3)
plt.savefig("lens_curve.png", dpi=90, bbox_inches="tight")
r = fisheye_r(theta, fx, d["distortion"])
i = int(np.argmax(r))
print(f"bench calibration: the curve rises up to {r[i]:.0f} px at {deg[i]:.0f} deg, then turns back down")
print("saved lens_curve.png — open it in the editor")

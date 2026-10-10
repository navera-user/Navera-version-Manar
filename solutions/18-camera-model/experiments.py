# Lesson 18 — run every experiment of the lab with YOUR functions, save the numbers in
# results.json and draw two charts (footprint.png, scale.png). Nothing to change here.
# Run:   python3 experiments.py
import json
import math
import sys
import warnings

warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import camera_math as cm
import measure_pad as mp

REYKJAVIK_LAT, SOUSSE_LAT = 64.15, 35.83
INSTA = dict(hfov=111.0, w=1920, h=540)          # NAVERA's straightened Insta360 view
LAB = dict(hfov=90.0, w=960, h=540)              # the lab photos' camera


def need(value, what):
    if value is None:
        sys.exit(f"{what} returned None — finish that TODO first, then run again.")
    return value


res = {}
# 1. intrinsics of the Insta360 straightened view
f = need(cm.focal_px(INSTA["hfov"], INSTA["w"]), "focal_px()")
res["insta360"] = {"f_px": round(f, 3), "vfov_deg": round(need(cm.fov_deg(f, INSTA["h"]), "fov_deg()"), 3),
                   "gsd_150m": round(need(cm.meters_per_pixel(150, INSTA["hfov"], INSTA["w"]), "meters_per_pixel()"), 4)}

# 2. footprints of the lab camera at 150 m, heading north, nose-down pitch 0 / 10 / 20 / 30 deg
K = need(cm.intrinsic_matrix(LAB["hfov"], LAB["w"], LAB["h"]), "intrinsic_matrix()")
C = np.array([0.0, 0.0, 150.0])
fp = {}
fig, ax = plt.subplots(figsize=(7, 7))
for pitch, col in ((0, "#0b6e8a"), (-10, "#2f9e44"), (-20, "#f08c00"), (-30, "#d64545")):
    R = cm.camera_rotation(0.0, pitch, 0.0)
    poly = need(cm.footprint_polygon(K, R, C, LAB["w"], LAB["h"]), "footprint_polygon()")
    centre = need(cm.ground_point(K, R, C, LAB["w"] / 2, LAB["h"] / 2), "ground_point()")
    area = need(cm.polygon_area(poly), "polygon_area()")
    fp[str(pitch)] = {"area_m2": round(area, 1), "centre_en_m": [round(float(centre[0]), 2), round(float(centre[1]), 2)],
                      "corners_en_m": np.round(np.asarray(poly, float), 2).tolist()}
    closed = np.vstack([poly, poly[:1]])
    ax.fill(closed[:, 0], closed[:, 1], color=col, alpha=0.15)
    ax.plot(closed[:, 0], closed[:, 1], color=col, lw=2, label=f"pitch {pitch:+d}°: {area / 1e3:.0f}k m²")
    ax.plot(*centre, "o", color=col)
ax.plot(0, 0, "k^", ms=10, label="point under the drone")
ax.text(-250, 70, "drone flies north (nose up the page)", fontsize=9)
ax.set_aspect("equal")
ax.set_xlabel("east (m)")
ax.set_ylabel("north (m)")
ax.set_title("Ground footprint at 150 m, heading north, nose-down pitch")
ax.grid(alpha=0.3)
ax.legend(loc="lower right", fontsize=9)
fig.tight_layout()
fig.savefig("footprint.png", dpi=90)
plt.close(fig)
res["footprint_150m"] = fp

# 3. map zoom: Reykjavik vs Sousse
res["map"] = {
    "reykjavik_z17_mpp": round(need(cm.map_m_per_px(REYKJAVIK_LAT, 17), "map_m_per_px()"), 4),
    "sousse_z17_mpp": round(cm.map_m_per_px(SOUSSE_LAT, 17), 4),
    "best_zoom_300m_reykjavik": need(cm.best_zoom(300, INSTA["hfov"], INSTA["w"], REYKJAVIK_LAT), "best_zoom()"),
    "best_zoom_300m_sousse": cm.best_zoom(300, INSTA["hfov"], INSTA["w"], SOUSSE_LAT),
    # GSD is proportional to h: the height where it equals the zoom-17 map
    "h_equal_z17_reykjavik_m": round(cm.map_m_per_px(REYKJAVIK_LAT, 17) / cm.meters_per_pixel(1.0, INSTA["hfov"], INSTA["w"]), 1),
    "h_equal_z17_sousse_m": round(cm.map_m_per_px(SOUSSE_LAT, 17) / cm.meters_per_pixel(1.0, INSTA["hfov"], INSTA["w"]), 1),
}
hs = np.arange(20, 1001, 10)
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(hs, [cm.meters_per_pixel(h, INSTA["hfov"], INSTA["w"]) for h in hs], lw=2,
        label="Insta360 straightened view (111°, 1920 px)")
for z in range(16, 20):
    ax.axhline(cm.map_m_per_px(REYKJAVIK_LAT, z), color="grey", ls="-", lw=1)
    ax.axhline(cm.map_m_per_px(SOUSSE_LAT, z), color="grey", ls=":", lw=1)
    ax.text(1010, cm.map_m_per_px(REYKJAVIK_LAT, z), f"z{z}", va="bottom", fontsize=9)
ax.plot([], [], color="grey", ls="-", label="map zoom levels, Reykjavik (64.2° N)")
ax.plot([], [], color="grey", ls=":", label="map zoom levels, Sousse (35.8° N)")
ax.set_xlim(0, 1080)
ax.set_xlabel("height above ground (m)")
ax.set_ylabel("metres per pixel")
ax.set_title("Photo resolution vs map resolution")
ax.legend(loc="upper left", fontsize=9)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("scale.png", dpi=90)
plt.close(fig)

# 4. the photos (measure_pad.py)
pads = {}
for name in ("photo_A.png", "photo_B.png"):
    m = mp.measure_nadir(name)
    if m is not None:
        pads[name] = {"width_px": m[0], "height_m": round(m[1], 1), "height_range_m": [round(m[2], 1), round(m[3], 1)]}
t = mp.locate_tilted()
if t is not None:
    pads["photo_T.png"] = {"pad_px": [round(t[0], 1), round(t[1], 1)], "pad_en_m": [round(t[2], 2), round(t[3], 2)]}
res["pads"] = pads

# 5. errors
# Take-off in a mountain valley (ground about 500 m above sea level), climb to 2300 m GPS altitude,
# fly over a high plateau (ground about 2000 m). "GPS altitude - take-off ground" says 1800 m.
believed, true = 2300.0 - 500.0, 2300.0 - 2000.0
res["errors"] = {
    "mountain_believed_agl_m": believed, "mountain_true_agl_m": true,
    "mountain_fitted_scale": round(need(cm.fitted_scale(believed, true), "fitted_scale()"), 4),
    "tilt_error_1deg_at_150m_tilt10_m": round(need(cm.tilt_position_error(150, 10, 1), "tilt_position_error()"), 3),
    "tilt_error_1deg_at_150m_tilt30_m": round(cm.tilt_position_error(150, 30, 1), 3),
}

with open("results.json", "w") as fh:
    json.dump(res, fh, indent=1)
print(json.dumps(res["map"], indent=1))
print(json.dumps(res["errors"], indent=1))
print("\nsaved results.json, footprint.png, scale.png — open them in the editor")

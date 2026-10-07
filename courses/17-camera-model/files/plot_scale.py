# Lesson 17 — draw meters per pixel against height, with the map zoom levels.
# Run:   python3 plot_scale.py      then open scale.png in the editor.
import warnings
warnings.filterwarnings("ignore")      # a harmless matplotlib warning about 3D plots
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import camera_math as cm

heights = list(range(20, 801, 10))
mpp = [cm.meters_per_pixel(h, 111, 1920) for h in heights]
if None in mpp:
    raise SystemExit("finish TODO 1 (meters_per_pixel) first")
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(heights, mpp, lw=2, label="Insta360 straightened view (111°, 1920 px)")
for z in range(16, 20):
    m = cm.map_meters_per_pixel(35.8, z)
    if m is None:
        raise SystemExit("finish TODO 3 (map_meters_per_pixel) first")
    ax.axhline(m, ls="--", color="grey")
    ax.text(810, m + 0.03, f"zoom {z}", va="bottom", fontsize=9)
ax.set_xlim(0, 880)
ax.set_xlabel("height above ground (m)")
ax.set_ylabel("meters per pixel")
ax.set_title("Where the photo's resolution meets the map's (Sousse)")
ax.legend(loc="upper left")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("scale.png", dpi=100)
print("saved scale.png — open it in the editor")

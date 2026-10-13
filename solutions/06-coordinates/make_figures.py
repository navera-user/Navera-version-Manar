"""make_figures.py — draws courses/06-coordinates/assets/great_circle.svg from the course reference.

    cd solutions/06-coordinates && python3 make_figures.py
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from navera_lite.geo import great_circle_points, max_offset_km  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "courses", "06-coordinates", "assets")
NY, LON = (40.6413, -73.7781), (51.4700, -0.4543)          # New York JFK, London Heathrow

pts = great_circle_points(NY, LON, 101)
fig, ax = plt.subplots(figsize=(7, 4.2))
ax.plot([NY[1], LON[1]], [NY[0], LON[0]], "--", color="#d17a00", lw=2, label="straight line on the lat/lon map")
ax.plot([p[1] for p in pts], [p[0] for p in pts], "-", color="#0b6e8a", lw=2.5, label="great circle (shortest path)")
for name, p in (("New York", NY), ("London", LON)):
    ax.plot(p[1], p[0], "s", color="#b0453a")
    ax.annotate(name, (p[1], p[0]), xytext=(6, -14), textcoords="offset points")
ax.set_xlim(-80, 5)
ax.set_ylim(35, 60)
ax.set_xlabel("longitude (°)")
ax.set_ylabel("latitude (°)")
ax.set_title(f"On a lat/lon map the shortest path bends towards the pole (up to {max_offset_km(NY, LON):.0f} km here)")
ax.grid(alpha=.3)
ax.legend(loc="lower right", fontsize=9)
fig.savefig(os.path.join(OUT, "great_circle.svg"), bbox_inches="tight")
print("written great_circle.svg", round(max_offset_km(NY, LON), 1))

#!/usr/bin/env python3
"""make_figures.py — teacher only. Draws courses/07-map-tiles/assets/ribat_zooms.jpg: the tile that holds the
Ribat of Sousse at zooms 13, 15, 17 and 19, from the course's OpenStreetMap map (© OpenStreetMap contributors).

    cd solutions/_navera_lite && python3 ../07-map-tiles/make_figures.py [path/to/osm_sousse.mbtiles]
"""
import math
import os
import sys

import cv2
import numpy as np

from navera_lite import tiles

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/academy-data/osm_sousse.mbtiles")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "courses", "07-map-tiles", "assets",
                   "ribat_zooms.jpg")
RIBAT = (35.8277, 10.6388)

db = tiles.open_map(SRC)
panels = []
for z in (13, 15, 17, 19):
    x, y = tiles.tile_xy(*RIBAT, z)
    tx, ty = math.floor(x), math.floor(y)
    img = tiles.decode_tile(tiles.read_tile(db, z, tx, ty))
    px, py = int((x - tx) * 256), int((y - ty) * 256)
    cv2.circle(img, (px, py), 7, (0, 0, 220), 2)
    w = 256 * tiles.m_per_px(RIBAT[0], z)
    head = np.full((44, 256, 3), 255, np.uint8)
    cv2.putText(head, f"zoom {z}: {z}/{tx}/{ty}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1, cv2.LINE_AA)
    cv2.putText(head, f"tile {w:,.0f} m wide".replace(",", " "), (6, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (80, 80, 80), 1, cv2.LINE_AA)
    panels.append(np.vstack([head, img]))
    panels.append(np.full((300, 8, 3), 255, np.uint8))
fig = np.hstack(panels[:-1])
fig = np.vstack([fig, np.full((22, fig.shape[1], 3), 255, np.uint8)])
tiles.stamp_attribution(fig)
cv2.imwrite(os.path.realpath(OUT), fig, [cv2.IMWRITE_JPEG_QUALITY, 85])
print("wrote", os.path.realpath(OUT), fig.shape)

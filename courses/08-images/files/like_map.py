# Can the drone photo be compared with the map? Uses YOUR make_like_map().
#     python3 like_map.py
import json

import cv2
import numpy as np

import images_lab as L

D = "/data/academy/08-images/"
info = json.load(open(D + "info.json"))
photo = cv2.imread(D + info["photo"]["file"])
map_patch = cv2.imread(D + info["map"]["file"])
heading = info["photo"]["heading_deg"]
photo_mpp, map_mpp = info["photo"]["m_per_px"], info["map"]["m_per_px"]
print(f"photo: {photo.shape[1]} x {photo.shape[0]} px, {photo_mpp} m/px, top of the photo towards {heading} deg")
print(f"map  : {map_patch.shape[1]} x {map_patch.shape[0]} px, {map_mpp:.4f} m/px, north up\n")

S = 160
g = cv2.cvtColor(map_patch, cv2.COLOR_BGR2GRAY).astype(np.float32)
map_c = L.middle(np.clip(np.rint((g - g.min()) / (g.max() - g.min()) * 255), 0, 255).astype(np.uint8), S)
raw = cv2.resize(L.middle(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY), S), (S, S))
row = [map_c, raw]
print(f"{'photo as it is':<26} difference {L.difference(raw, map_c):6.1f}   similarity {L.similarity(raw, map_c):5.2f}")
for method in ("normalise", "equalise", "clahe"):
    ready = L.make_like_map(photo, heading, photo_mpp, map_mpp, method)
    if ready is None:
        raise SystemExit("make_like_map() returns None: finish TODO 11")
    ready = np.asarray(ready)
    if ready.dtype != np.uint8:
        print(f"WARNING: make_like_map() returned dtype {ready.dtype}, not uint8 — convert with to_uint8()")
    c = L.middle(ready, S)
    if c.shape != map_c.shape:
        raise SystemExit(f"the middle of your result has shape {c.shape}: the result {ready.shape} is too small")
    print(f"{'make_like_map ' + method:<26} difference {L.difference(c, map_c):6.1f}   similarity {L.similarity(c, map_c):5.2f}")
    row.append(np.clip(c, 0, 255).astype(np.uint8))
    if method == "normalise":
        cv2.imwrite("prepared_photo.png", np.clip(ready, 0, 255).astype(np.uint8))
pad = np.full((S, 8), 255, np.uint8)
strip = np.hstack([x for p in row for x in (p, pad)][:-1])
cv2.imwrite("comparison.png", cv2.resize(strip, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
print("\nSaved comparison.png: map | photo as it is | normalise | equalise | clahe  (160 x 160 middles)")
print("and prepared_photo.png (your whole prepared photo, normalise).")

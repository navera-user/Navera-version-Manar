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
print(f"photo: {photo.shape[1]} x {photo.shape[0]} px, {photo_mpp} m/px, top of the photo towards {heading}°")
print(f"map  : {map_patch.shape[1]} x {map_patch.shape[0]} px, {map_mpp:.3f} m/px, north up\n")

S = 160                                                        # compare the 160 x 160 middle of both


def middle(img):
    h, w = img.shape[:2]
    return img[(h - S) // 2:(h - S) // 2 + S, (w - S) // 2:(w - S) // 2 + S]


g = cv2.cvtColor(map_patch, cv2.COLOR_BGR2GRAY).astype(np.float32)
map_c = middle(((g - g.min()) / (g.max() - g.min()) * 255).round().astype(np.uint8))
raw = cv2.resize(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)[240 - S // 2:240 + S // 2, 320 - S // 2:320 + S // 2], (S, S))
ready = L.make_like_map(photo, heading, photo_mpp, map_mpp)
if ready is None:
    raise SystemExit("make_like_map() returns None: finish TODO 10")
ready_c = middle(np.asarray(ready))
if ready_c.shape != map_c.shape:
    raise SystemExit(f"the middle of your result has shape {ready_c.shape}, expected {map_c.shape}")

for name, pic in (("photo as it is", raw), ("after make_like_map", ready_c)):
    print(f"{name:<22} difference {L.difference(pic, map_c):6.1f}   similarity {L.similarity(pic, map_c):5.2f}")

pad = np.full((S, 10), 255, np.uint8)
row = np.hstack([map_c, pad, raw, pad, ready_c])
big = cv2.resize(row, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
cv2.imwrite("comparison.png", big)
cv2.imwrite("prepared_photo.png", ready)
print("\nSaved comparison.png: map | photo as it is | your prepared photo (the 160 x 160 middle of each)")
print("and prepared_photo.png (your whole prepared photo).")

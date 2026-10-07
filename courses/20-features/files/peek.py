"""Look inside a descriptor: the 'fingerprint' of one keypoint.   python3 peek.py
Uses YOUR detect_keypoints() from features.py (TODO 1 must be done)."""
import os

import cv2
import numpy as np

from features import DATA, detect_keypoints

city = cv2.imread(os.path.join(DATA, "terrain_city.jpg"))
for method in ("ORB", "SIFT"):
    kps, des = detect_keypoints(city, method)
    print(f"\n{method}: {len(kps)} keypoints, descriptor array shape {des.shape}, type {des.dtype}")
    k = kps[0]
    print(f"  keypoint 0 at x={k.pt[0]:.1f}, y={k.pt[1]:.1f}, size {k.size:.1f} px, angle {k.angle:.0f}°")
    np.set_printoptions(linewidth=100)
    print("  its descriptor:", des[0] if method == "SIFT" else des[0])
    if method == "ORB":
        bits = np.unpackbits(des[0])
        print(f"  as bits ({bits.size} of them):", "".join(map(str, bits[:64])), "...")

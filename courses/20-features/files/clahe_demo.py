"""What CLAHE (local contrast boost) does to keypoints.   python3 clahe_demo.py [file name]
Saves clahe_demo.png: left the original, right after CLAHE, keypoints drawn on both."""
import os
import sys

import cv2
import numpy as np

DATA = "/data/academy/20-features"
name = sys.argv[1] if len(sys.argv) > 1 else "drone_city_blurry_dark.jpg"
grey = cv2.imread(os.path.join(DATA, name), cv2.IMREAD_GRAYSCALE)
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))     # the same settings as NAVERA
boosted = clahe.apply(grey)
sift = cv2.SIFT_create(contrastThreshold=0.02)                   # the same threshold as NAVERA
k1, k2 = sift.detect(grey), sift.detect(boosted)
print(f"{name}: {len(k1)} SIFT keypoints before CLAHE, {len(k2)} after")
a = cv2.drawKeypoints(cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR), k1, None, (0, 0, 255))
b = cv2.drawKeypoints(cv2.cvtColor(boosted, cv2.COLOR_GRAY2BGR), k2, None, (0, 0, 255))
cv2.imwrite("clahe_demo.png", np.hstack([a, b]))
print("→ saved clahe_demo.png (left: original, right: CLAHE)")

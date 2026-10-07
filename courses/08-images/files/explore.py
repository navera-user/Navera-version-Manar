# Opens a real aerial photo and shows that it is just a big table of numbers.
#     python3 explore.py                 (or: python3 explore.py another_picture.jpeg)
import sys

import cv2
import numpy as np

path = sys.argv[1] if len(sys.argv) > 1 else "/data/navera_data/camera_pkg/camera_pkg/data/day/frame_0005.jpeg"
img = cv2.imread(path)                       # BGR colour picture, as a numpy array
if img is None:
    raise SystemExit(f"cannot read {path}")

print("file      :", path)
print("type      :", type(img).__name__, "of", img.dtype)
print("shape     :", img.shape, "-> height (rows), width (columns), channels (blue, green, red)")
print("numbers   :", img.size, "values in total")
print("top-left pixel img[0, 0] =", img[0, 0], " (blue, green, red)")
y, x = img.shape[0] // 2, img.shape[1] // 2
print(f"centre pixel img[{y}, {x}] =", img[y, x])
for i, name in enumerate(("blue", "green", "red")):
    ch = img[:, :, i]
    print(f"{name:>5} channel: min {ch.min():3d}  max {ch.max():3d}  mean {ch.mean():6.1f}")

grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
print("\nThe 8 x 8 grey pixels in the very centre (0 = black, 255 = white):")
block = grey[y - 4:y + 4, x - 4:x + 4]
for row in block:
    print("  " + " ".join(f"{v:3d}" for v in row))

zoom = cv2.resize(img[y - 4:y + 4, x - 4:x + 4], (256, 256), interpolation=cv2.INTER_NEAREST)
cv2.imwrite("centre_8x8_zoomed.png", zoom)
cv2.imwrite("frame.png", img)
print("\nSaved frame.png (the photo) and centre_8x8_zoomed.png (those 64 pixels, each drawn 32 x 32).")

# Lesson 17 — measure the height of a drone from its photo.
# Each photo in /data/academy/17-camera-model/ shows an orange landing pad, 12 m x 12 m.
# The photos come from a straight-down camera, 960 px wide, field of view 90 deg.
# Run:   python3 measure_pad.py
import cv2
import numpy as np

from camera_math import height_from_object

DATA = "/data/academy/17-camera-model"
PAD_SIZE_M = 12.0
WIDTH_PX, HFOV_DEG = 960, 90.0


def orange_mask(img):
    """True where the pixel is the pad's orange (OpenCV images are B, G, R)."""
    b = img[:, :, 0].astype(int)
    g = img[:, :, 1].astype(int)
    r = img[:, :, 2].astype(int)
    return (r > 200) & (g > 100) & (g < 180) & (b < 80)


def pad_size_px(img):
    """Width in pixels of the orange pad: the number of COLUMNS between the leftmost and the
    rightmost orange pixel (both included)."""
    mask = orange_mask(img)
    rows, cols = np.nonzero(mask)
    if len(cols) == 0:
        return None
    return int(cols.max() - cols.min() + 1)


# ---- you don't need to change anything below this line ----
if __name__ == "__main__":
    for name in ("photo_A.png", "photo_B.png"):
        img = cv2.imread(f"{DATA}/{name}")
        if img is None:
            print(f"{name}: cannot read the photo")
            continue
        px = pad_size_px(img)
        if px is None:
            print(f"{name}: pad size TODO not done yet")
            continue
        h = height_from_object(PAD_SIZE_M, px, HFOV_DEG, WIDTH_PX)
        print(f"{name}: the 12 m pad is {px} px wide -> the drone was at "
              + (f"{h:.0f} m" if h is not None else "TODO 2 not done yet"))
        # a picture to look at: the mask in white
        cv2.imwrite(f"mask_{name}", (orange_mask(img) * 255).astype(np.uint8))
    print("Open mask_photo_A.png in the editor to see what the mask found.")

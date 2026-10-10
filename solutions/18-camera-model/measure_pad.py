# Lesson 18 — measure the world with a photo.
# /data/academy/18-camera-model/ has three synthetic drone photos made from NAVERA's satellite map
# of Sousse (Tunisia). The camera is an ideal pinhole: 960 x 540 px, HFOV 90 deg (f = 480 px).
# Each photo shows an orange landing pad, 12 m x 12 m, lying on the ground.
#   photo_A.png, photo_B.png : camera looking straight down, height unknown -> measure it
#   photo_T.png              : camera tilted (heading 30, pitch -12, roll +4 deg) at 150 m
#                              -> find WHERE the pad is on the ground, relative to the drone
# Run:   python3 measure_pad.py
import cv2
import numpy as np

from camera_math import camera_rotation, focal_px, ground_point, height_from_object, intrinsic_matrix

DATA = "/data/academy/18-camera-model"
PAD_SIZE_M = 12.0
WIDTH_PX, HEIGHT_PX, HFOV_DEG = 960, 540, 90.0
TILTED = dict(height_m=150.0, heading_deg=30.0, pitch_deg=-12.0, roll_deg=4.0)


def orange_mask(img):
    """Boolean array, True where the pixel is the pad's orange (OpenCV images are B, G, R)."""
    b = img[:, :, 0].astype(int)
    g = img[:, :, 1].astype(int)
    r = img[:, :, 2].astype(int)
    return (r > 200) & (g > 100) & (g < 180) & (b < 80)


# ---------------------------------------------------------------- TODO 7
def pad_size_px(img):
    """Width of the pad in pixels: the number of COLUMNS from the leftmost to the rightmost
    orange pixel, both included (an int). None if there is no orange pixel."""
    rows, cols = np.nonzero(orange_mask(img))
    if len(cols) == 0:
        return None
    return int(cols.max() - cols.min() + 1)


def pad_centre_px(img):
    """Centre of the pad in the image: (u, v) = (mean column, mean row) of the orange pixels,
    as two floats. None if there is no orange pixel."""
    rows, cols = np.nonzero(orange_mask(img))
    if len(cols) == 0:
        return None
    return float(cols.mean()), float(rows.mean())


# ---- you don't need to change anything below this line ----
def measure_nadir(name):
    """(pad width px, height m, height if 1 px less, height if 1 px more) or None."""
    img = cv2.imread(f"{DATA}/{name}")
    if img is None:
        print(f"{name}: cannot read the photo")
        return None
    px = pad_size_px(img)
    if px is None:
        print(f"{name}: pad size TODO not done yet")
        return None
    f = focal_px(HFOV_DEG, WIDTH_PX)
    hs = [height_from_object(PAD_SIZE_M, n, f) if f else None for n in (px, px + 1, px - 1)]
    if None in hs:
        print(f"{name}: the pad is {px} px wide -> height: TODO 1 / TODO 6 not done yet")
        return None
    print(f"{name}: the 12 m pad is {px} px wide -> the drone was at {hs[0]:.0f} m "
          f"(+-1 px: {hs[1]:.0f} to {hs[2]:.0f} m)")
    cv2.imwrite(f"mask_{name}", (orange_mask(img) * 255).astype(np.uint8))
    return px, hs[0], hs[1], hs[2]


def locate_tilted(name="photo_T.png"):
    """(u, v, east, north) of the pad in the tilted photo, or None."""
    img = cv2.imread(f"{DATA}/{name}")
    if img is None:
        print(f"{name}: cannot read the photo")
        return None
    c = pad_centre_px(img)
    if c is None:
        print(f"{name}: pad centre TODO not done yet")
        return None
    K = intrinsic_matrix(HFOV_DEG, WIDTH_PX, HEIGHT_PX)
    R = camera_rotation(TILTED["heading_deg"], TILTED["pitch_deg"], TILTED["roll_deg"])
    g = ground_point(K, R, np.array([0.0, 0.0, TILTED["height_m"]]), c[0], c[1]) if K is not None else None
    if g is None:
        print(f"{name}: pad at pixel ({c[0]:.1f}, {c[1]:.1f}) -> ground point: TODO 1 / TODO 3 not done yet")
        return None
    print(f"{name}: pad at pixel ({c[0]:.1f}, {c[1]:.1f}) -> on the ground {g[0]:.1f} m east, "
          f"{g[1]:.1f} m north of the point under the drone")
    return c[0], c[1], float(g[0]), float(g[1])


if __name__ == "__main__":
    measure_nadir("photo_A.png")
    measure_nadir("photo_B.png")
    locate_tilted()
    print("Open mask_photo_A.png in the editor to see what the mask found.")

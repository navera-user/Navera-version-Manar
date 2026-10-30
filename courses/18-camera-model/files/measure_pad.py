"""measure_pad.py — measure the world with a photo (mission 18, lab Steps 4–5 and 9).

/data/academy/18-camera-model/ holds three synthetic drone photos of Sousse, Tunisia (rendered from
OpenStreetMap data, © OpenStreetMap contributors). The camera is an ideal pinhole: 960 × 540 px,
HFOV 90°. Each photo shows an orange landing pad, 12 m × 12 m, lying on the ground.
    photo_A.png, photo_B.png : straight down, image top = north, height unknown  -> measure the height
    photo_T.png              : tilted (170 m, heading 40°, pitch −14°, roll +5°)  -> where is the pad?

You write TODO A, TODO B and TODO C. Run:   python3 measure_pad.py
"""
import os
import sys

import cv2
import numpy as np

import runner_kit as rk

DATA = os.environ.get("ACADEMY_DATA_18", "/data/academy/18-camera-model")
PAD_SIZE_M = 12.0
WIDTH_PX, HEIGHT_PX, HFOV_DEG = 960, 540, 90.0
TILTED = {"height_m": 170.0, "heading_deg": 40.0, "pitch_deg": -14.0, "roll_deg": 5.0}


def orange_mask(img):
    """Boolean array (rows × columns), True where the pixel has the pad's orange.
    OpenCV images are B, G, R: img[row, column] = [blue, green, red]."""
    b = img[:, :, 0].astype(int)
    g = img[:, :, 1].astype(int)
    r = img[:, :, 2].astype(int)
    return (r > 200) & (g > 100) & (g < 180) & (b < 80)


# TODO A ------------------------------------------------------------------------------------------
def pad_size_px(img):
    """Width of the pad in the image: the number of COLUMNS from the leftmost to the rightmost orange
    pixel, both included. Start from orange_mask(img).

    Input: an image (numpy array rows × columns × 3, B G R). Returns an int, or None when no pixel is orange.
    Example: a mask whose orange pixels sit in columns 10 to 13 (rows do not matter) → 4
    """
    return None   # TODO: replace this line with your code


# TODO B ------------------------------------------------------------------------------------------
def pad_centre_px(img):
    """Centre of the pad in the image: (u, v) = (mean column, mean row) of the orange pixels.

    Input: an image (numpy array rows × columns × 3, B G R). Returns (u, v), two floats, or None when no
    pixel is orange.
    Example: orange pixels at (row 2, column 10) and (row 4, column 20) → (15.0, 3.0)
    """
    return None   # TODO: replace this line with your code


# TODO C ------------------------------------------------------------------------------------------
def height_from_size(f_px, size_m, n_px):
    """Height (m) above flat ground of a camera looking straight down (focal length f_px pixels) that sees an
    object of size_m metres as n_px pixels long (lesson §4, "Measuring with a known object").

    Returns one float (metres).
    Example: height_from_size(800.0, 4.5, 30) → 120.0   (a 4.5 m car, 30 px long)
    """
    return None   # TODO: replace this line with your code


# ---- you don't need to change anything below this line (but read it!) ----
cam = rk.load_student("navera_lite.camera")


def _read(name):
    img = cv2.imread(os.path.join(DATA, name))
    if img is None:
        sys.exit(f"cannot read {os.path.join(DATA, name)} — is the dataset mounted? (ls /data/academy/18-camera-model)")
    return img


def _mine(fn, *args):
    """Call TODO A / TODO B of this file with runner_kit's plain-sentence errors."""
    v, err = rk.call(sys.modules[__name__], fn, *args)
    return v, err


def measure_nadir(name):
    """(pad width px, height m, height if the pad were 1 px wider, 1 px narrower), or None."""
    img = _read(name)
    px, err = _mine("pad_size_px", img)
    if err:
        print(f"{name}: {err}")
        return None
    if isinstance(px, bool) or not isinstance(px, (int, np.integer)):
        print(f"{name}: pad_size_px() must return an int (a number of columns), it returned {px!r}")
        return None
    f, err = rk.call(cam, "focal_px", HFOV_DEG, WIDTH_PX)
    if err:
        print(f"{name}: the pad is {px} px wide — height: {err}")
        return None
    hs = []
    for n in (px, px + 1, px - 1):
        h, err = _mine("height_from_size", f, PAD_SIZE_M, n)
        if err:
            print(f"{name}: the pad is {px} px wide — height: {err}")
            return None
        hs.append(float(h))
    check, err = rk.call(cam, "gsd", hs[0], HFOV_DEG, WIDTH_PX)
    note = "" if err else f"   (your gsd() at that height: {check * 100:.1f} cm/px)"
    print(f"{name}: the 12 m pad is {px} px wide -> the camera was {hs[0]:.1f} m above the ground "
          f"(±1 px: {hs[1]:.1f} to {hs[2]:.1f} m){note}")
    mask = orange_mask(img)
    os.makedirs("out", exist_ok=True)
    cv2.imwrite(os.path.join("out", f"mask_{name}"), (mask * 255).astype(np.uint8))
    return px, hs[0], hs[1], hs[2]


def locate_tilted(name="photo_T.png"):
    """(u, v, east, north) of the pad in the tilted photo."""
    img = _read(name)
    c, err = _mine("pad_centre_px", img)
    if err:
        print(f"{name}: {err}")
        return None
    try:
        u, v = (float(x) for x in c)
    except (TypeError, ValueError):
        print(f"{name}: pad_centre_px() must return two numbers (u, v), it returned {c!r}")
        return None
    if not (0 <= u < WIDTH_PX and 0 <= v < HEIGHT_PX):
        print(f"{name}: pixel ({u:.1f}, {v:.1f}) is outside the {WIDTH_PX} × {HEIGHT_PX} image — "
              "is it (u, v) = (column, row)? (TODO B, Step 5's hint 2)")
        return None
    K, err = rk.call(cam, "K_from_hfov", HFOV_DEG, WIDTH_PX, HEIGHT_PX)
    if err:
        print(f"{name}: pad at pixel ({u:.1f}, {v:.1f}) — {err}")
        return None
    C = np.array([0.0, 0.0, TILTED["height_m"]])
    R = cam.camera_rotation_hpr(TILTED["heading_deg"], TILTED["pitch_deg"], TILTED["roll_deg"])
    g, err = rk.call(cam, "backproject_ground", K, R, C, u, v)
    if err:
        print(f"{name}: pad at pixel ({u:.1f}, {v:.1f}) — {err}")
        return None
    print(f"{name}: pad at pixel ({u:.1f}, {v:.1f}) -> on the ground {g[0]:.1f} m east, {g[1]:.1f} m north "
          "of the point under the drone")
    return u, v, float(g[0]), float(g[1])


if __name__ == "__main__":
    measure_nadir("photo_A.png")
    measure_nadir("photo_B.png")
    locate_tilted()
    if os.path.exists(os.path.join("out", "mask_photo_A.png")):
        rk.saved("out/mask_photo_A.png (what orange_mask found in photo A)")

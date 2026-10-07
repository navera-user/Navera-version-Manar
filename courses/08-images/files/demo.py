# Runs YOUR functions of images_lab.py on a real aerial photo and saves the results in out/.
#     python3 demo.py
import os

import cv2
import numpy as np

import images_lab as L

FRAME = "/data/navera_data/camera_pkg/camera_pkg/data/day/frame_0005.jpeg"
img = cv2.imread(FRAME)
os.makedirs("out", exist_ok=True)


def save(name, result):
    if result is None:
        print(f"  {name:<16} TODO (the function returns None)")
        return None
    result = np.asarray(result)
    cv2.imwrite(os.path.join("out", name + ".png"), result)
    print(f"  {name:<16} shape {str(result.shape):<16} dtype {result.dtype}  min {int(result.min()):3d}"
          f"  max {int(result.max()):3d}  -> out/{name}.png")
    return result


def run(name, fn, *args):
    try:
        return save(name, fn(*args))
    except Exception as e:                               # show the error but go on with the others
        print(f"  {name:<16} ERROR {type(e).__name__}: {e}")
        return None


print(f"photo {FRAME}: shape {img.shape}\n")
run("flipped", L.flip_horizontal, img)
gray = run("gray", L.to_gray, img)
run("crop", L.crop, img, 600, 200, 400, 300)
run("crop_center", L.crop_center, img, 500, 500)
run("rotated_30", L.rotate, img, 30)
run("half_size", L.scale, img, 0.5)
run("brighter", L.adjust, img, 1.0, 60)
run("more_contrast", L.adjust, img, 1.8, -100)
dark = np.clip(img.astype(np.float32) * 0.35 + 30, 0, 255).astype(np.uint8)   # a dull, dark photo
save("dark", dark)
run("dark_normalised", L.normalise, dark)
run("blur_15", L.blur, img, 15)
run("edges", L.edges, img)
print("\nClick the pictures in out/ (file list on the left of the editor) to see them.")

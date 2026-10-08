# Runs YOUR functions of images_lab.py on a real aerial photo and saves the results in out/.
#     python3 demo.py
# Each line shows the shape, the dtype and the range of the result: watch the dtypes!
import os
import warnings

import cv2
import numpy as np

import images_lab as L

FRAME = "/data/navera_data/camera_pkg/camera_pkg/data/day/frame_0005.jpeg"
img = cv2.imread(FRAME)
if img is None:
    raise SystemExit(f"data not found ({FRAME}) — ask the teacher to connect the data disk")
os.makedirs("out", exist_ok=True)


def save(name, result):
    """Save a result as out/<name>.png. Float results are converted HERE, on purpose, with a message."""
    if result is None:
        print(f"  {name:<18} TODO (the function returns None)")
        return None
    result = np.asarray(result)
    shown = result
    if result.dtype != np.uint8:
        shown = np.clip(np.rint(result), 0, 255).astype(np.uint8)       # what cv2.imwrite would need
    cv2.imwrite(os.path.join("out", name + ".png"), shown)
    print(f"  {name:<18} shape {str(result.shape):<15} dtype {str(result.dtype):<8} "
          f"min {float(result.min()):8.2f}  max {float(result.max()):8.2f}  -> out/{name}.png")
    return result


def run(name, fn, *args):
    try:
        return save(name, fn(*args))
    except Exception as e:                               # show the error but go on with the others
        print(f"  {name:<18} ERROR {type(e).__name__}: {str(e).strip().splitlines()[-1]}")
        return None


print(f"photo {FRAME}: shape {img.shape}, dtype {img.dtype}\n")
run("flipped", L.flip_horizontal, img)
gray = run("gray", L.to_gray, img)
dark = (img.astype(np.float32) * 0.35 + 30).astype(np.uint8)          # a dull, dark photo (safe: max 119)
dgray = run("dark_gray", L.to_gray, dark)
if dgray is not None:
    run("dark_normalised", L.normalise, dgray)
    run("dark_equalised", L.equalise, dgray)
    save("dark_clahe", cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(dgray))
    h = L.histogram(dgray)
    if h is not None:
        import matplotlib
        matplotlib.use("Agg")
        warnings.filterwarnings("ignore", message="Unable to import Axes3D")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.bar(range(256), h, width=1.0, color="#0b6e8a", label="dark photo")
        e = L.equalise(dgray)
        if e is not None:
            ax.bar(range(256), L.histogram(e), width=1.0, color="#d64545", alpha=0.5, label="after equalise()")
        ax.set_xlabel("grey value")
        ax.set_ylabel("pixels")
        ax.legend()
        fig.savefig("out/histogram.png", dpi=90, bbox_inches="tight")
        print(f"  {'histogram':<18} {int(np.count_nonzero(h))} grey values used out of 256 -> out/histogram.png")
if gray is not None:
    k = L.gaussian_kernel(7, 2.0)
    if k is None:
        print(f"  {'blur_own':<18} TODO (gaussian_kernel returns None)")
    else:
        run("blur_own", L.convolve2d, gray, k)
    g = L.sobel(gray)
    if g is None:
        print(f"  {'sobel_magnitude':<18} TODO (sobel returns None)")
    else:
        save("sobel_magnitude", np.hypot(g[0], g[1]) / 4.0)
    M = L.rotation_scale_matrix(gray.shape[1] / 2, gray.shape[0] / 2, 30.0, 0.5)
    if M is None:
        print(f"  {'rotated_30_half':<18} TODO (rotation_scale_matrix returns None)")
    else:
        run("rotated_30_half", L.warp_affine, gray, M, gray.shape[1], gray.shape[0])

print("\nThe dtype trap, on purpose: CLAHE on a float64 picture")
try:
    cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(dark[..., 1].astype(np.float64))
except cv2.error as e:
    print("  OpenCV says:", str(e).strip().splitlines()[-1])
print("\nClick the pictures in out/ (file list on the left of the editor) to see them.")

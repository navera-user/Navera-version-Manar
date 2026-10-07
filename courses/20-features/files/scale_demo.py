"""Characteristic scale of disks of growing radius.   python3 scale_demo.py
Uses YOUR characteristic_scale() (TODO 4). Prints sigma* for a few radii next to r/sqrt(2)
and saves scale_curves.png: sigma* against the radius for r = 3 ... 20 px."""
import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from features import characteristic_scale  # noqa: E402

SIGMAS = [1.0 * 1.08 ** i for i in range(45)]          # 1 to ~30 px, 8 % apart


def disk(r, size=201):
    im = np.full((size, size), 40, np.uint8)
    cv2.circle(im, (size // 2, size // 2), r, 210, -1)
    return im


try:
    radii = list(range(3, 21))
    found = [characteristic_scale(disk(r), 100, 100, SIGMAS) for r in radii]
except NotImplementedError:
    raise SystemExit("TODO 4 (characteristic_scale) is not done yet.")
print(f"{'radius r':>9s} {'sigma*':>8s} {'r/sqrt2':>8s}")
for r, s in zip(radii, found):
    if r in (4, 8, 16):
        print(f"{r:9d} {s:8.2f} {r / 2 ** 0.5:8.2f}")
plt.figure(figsize=(6, 4))
plt.plot(radii, found, "o", label="your sigma*")
plt.plot(radii, [r / 2 ** 0.5 for r in radii], "-", label="r / √2 (theory)")
plt.xlabel("disk radius r (px)")
plt.ylabel("characteristic scale sigma* (px)")
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig("scale_curves.png", dpi=90)
print("→ saved scale_curves.png (your sigma* against the radius)")

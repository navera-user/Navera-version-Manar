#!/usr/bin/env python3
"""Mission 25: the check's unseen test cases and their expected values (teacher only).

    python3 solutions/25-thermal-night/check_values.py [COMPARE_SETS_NPZ]

Writes courses/25-thermal-night/hidden/unit_cases.npz (expected outputs of the reference on the check's unseen
inputs: prepare, cut_pair, to_input) and, given the compare_sets.npz saved by the build's values run (the runner's
`compare` sets, made with the reference cut_pair), hidden/compare_pairs.npz (night and noon). Prints the constants
pasted into check.py (reference weights solutions/25-thermal-night/my_homography.pt on the hidden test pairs).
The INPUTS are rebuilt in check.py from the same seeds (functions below are copied there): keep them in sync.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
HIDDEN = os.path.join(REPO, "courses", "25-thermal-night", "hidden")
sys.path.insert(0, os.path.join(REPO, "solutions", "_navera_lite"))
from navera_lite import homography_net as hn  # noqa: E402
from navera_lite import night  # noqa: E402


# ---- the check's unseen inputs (the same code is in check.py)
def smooth_frame(seed, h, w):
    """A smooth random picture (blobs and gradients): interpolation choices change it little."""
    import cv2
    rng = np.random.default_rng(seed)
    small = rng.uniform(0, 255, (h // 16 + 2, w // 16 + 2)).astype(np.float32)
    big = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    yy, xx = np.mgrid[0:h, 0:w]
    big = 0.7 * big + 0.3 * (255 * xx / w)
    return np.clip(big, 0, 255).astype(np.uint8)


PREP_CASES = [   # seed, h, w, alt, hfov, vfov, heading, map_m_per_px, out_px
    (251, 300, 400, 300.0, 70.0, 55.0, 25.0, 6.0, 64),
    (252, 256, 320, 500.0, 60.0, 48.0, -110.0, 9.0, 40),
    (253, 240, 360, 450.0, 80.0, 56.0, 90.0, 8.0, 56),
]
CUT_CASES = [    # seed, corner_xy, offsets
    (261, (21.0, 33.0), [3.0, -2.0, 5.5, 1.0, -4.0, 6.0, 0.5, -7.5]),
    (262, (40.0, 12.0), [-9.0, 4.0, -6.0, 8.0, -11.0, 2.0, -7.0, 5.0]),
]


def corner_centred(frame, alt, hf, vf, hd, mpp, op, kind="corner"):
    """prepare() made with one plausible mistake: kind "corner" (the centre at (w/2, h/2) → (out/2, out/2)),
    "mirror" (the 'up' vector used as the 2nd column), "onescale" (fw / w for both axes)."""
    import cv2
    import math
    h, w = frame.shape
    fw, fh = night.footprint_m(alt, hf, vf)
    sx, sy = (fw / w) / mpp, (fh / h) / mpp
    if kind == "onescale":
        sy = sx
    a = math.radians(hd)
    c, s = math.cos(a), math.sin(a)
    A = np.array([[c * sx, -s * sy], [s * sx, c * sy]])
    if kind == "mirror":
        A = np.array([[c * sx, s * sy], [s * sx, -c * sy]])
    cin, cout = (np.array([w / 2.0, h / 2.0]), op / 2.0) if kind == "corner" else (np.array([(w - 1) / 2.0, (h - 1) / 2.0]), (op - 1) / 2.0)
    M = np.hstack([A, (np.array([cout, cout]) - A @ cin)[:, None]])
    return cv2.warpAffine(frame, M, (op, op), flags=cv2.INTER_AREA, borderValue=0)


def scene(seed):
    return np.random.default_rng(seed).integers(0, 256, (140, 150)).astype(np.uint8)


def main():
    import torch
    out = {}
    for k, (seed, h, w, alt, hf, vf, hd, mpp, op) in enumerate(PREP_CASES):
        p, cov, why = night.prepare(smooth_frame(seed, h, w), alt, hf, vf, hd, mpp, op, need=0.5)
        out[f"prep{k}"] = p
        out[f"prep{k}_cov"] = np.float64(cov)
        # two plausible mistakes, so that check.py can name them: the turn the other way, the corner-based centre
        out[f"prep{k}_wrongturn"] = night.prepare(smooth_frame(seed, h, w), alt, hf, vf, -hd, mpp, op, need=0.5)[0]
        out[f"prep{k}_corner"] = corner_centred(smooth_frame(seed, h, w), alt, hf, vf, hd, mpp, op)
        out[f"prep{k}_mirror"] = corner_centred(smooth_frame(seed, h, w), alt, hf, vf, hd, mpp, op, kind="mirror")
        out[f"prep{k}_onescale"] = corner_centred(smooth_frame(seed, h, w), alt, hf, vf, hd, mpp, op, kind="onescale")
    for k, (seed, c, off) in enumerate(CUT_CASES):
        a, b = hn.cut_pair(scene(seed), scene(seed + 100), c, off)
        out[f"cut{k}_a"], out[f"cut{k}_b"] = a, b
    x = np.random.default_rng(271).integers(0, 256, (3, 2, 8, 8)).astype(np.uint8)
    x[1, 1] = 77                                                         # one uniform channel
    out["toin"] = hn.to_input(x).numpy()
    np.savez_compressed(os.path.join(HIDDEN, "unit_cases.npz"), **out)
    print("unit_cases.npz written; coverages", [round(float(out[f'prep{k}_cov']), 6) for k in range(3)])
    if len(sys.argv) > 1:
        d = np.load(sys.argv[1])
        np.savez_compressed(os.path.join(HIDDEN, "compare_pairs.npz"), night_x=d["night_x"], night_y=d["night_y"],
                            noon_x=d["noon_x"], noon_y=d["noon_y"])
        print("compare_pairs.npz written")
    t = np.load(os.path.join(HIDDEN, "test_pairs.npz"))
    torch.set_num_threads(2)
    net = hn.load_weights(os.path.join(HERE, "my_homography.pt"))
    ce = hn.centre_error(hn.predict(net, t["x"]), t["y"])
    e0 = hn.centre_error(np.zeros_like(t["y"]), t["y"])
    en = []
    for (a, b), y in zip(t["x"], t["y"]):
        dx, dy, _ = night.ncc_locate(b[16:48, 16:48], a)
        tx, ty = hn.centre_shift(hn.offsets_to_H(y))
        en.append(np.hypot(dx - tx, dy - ty))
    print(f"TEST: reference net median {np.median(ce):.3f} px, prior {np.median(e0):.3f}, NCC {np.median(en):.3f}")
    if len(sys.argv) > 1:
        for k in ("night", "noon"):
            e = hn.centre_error(hn.predict(net, d[f"{k}_x"]), d[f"{k}_y"])
            print(f"compare {k}: reference net median {np.median(e):.3f} px")


if __name__ == "__main__":
    main()

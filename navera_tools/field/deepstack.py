#!/usr/bin/env python3
"""Deep stacks from a raw 360 recording: EVERY decoded frame of a still window (not the live server's 2 key frames a
second), to measure how many more stars a long stack shows and to solve them again (resolve_prior --images).

    python3 -m navera_tools.field.deepstack <raw360_NNNN.bin or raw folder> --out DIR [--window-s 30] [--max 4]

Per window of --window-s seconds in which the camera's stillness test says stopped all along: the mean of every
frame (each pixel's brightest sample dropped, as stack.py), the faint signal amplified by sqrt(N) about the
background so the detector's 1 DN noise floor and the 8-bit rounding do not eat the gain. Written: stack_KK.png,
single_KK.png (the window's first frame), and index.jsonl (image, up_imu, t_exp, frames, seconds, noise and
spots for 1 frame, 12 frames ~ the live 6 s key-frame stack, and all frames).

The stars drift 0.25 deg/min across the sky (~2.5 px/min at this lens' scale): a 30 s window smears them ~1 px,
no compensation is needed; longer windows would need it. Memory: two float frames (~60 MB) plus the decoder;
CPU: one core decodes ~11 frames/s on the Jetson. Run with nice next to a live test, never two at once.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SATURATED = 250.0


def finish(acc, top, n):
    """(gained stack, plain mean) of n frames summed in acc, top = each pixel's brightest sample."""
    import cv2
    import numpy as np
    reject = n >= 4
    mean = (acc - top) / (n - 1) if reject else acc / n
    gain = math.sqrt(n - 1 if reject else n)
    bg = cv2.blur(mean, (65, 65))
    out = np.where(mean >= SATURATED, mean, np.minimum(bg + gain * (mean - bg), SATURATED - 1.0))
    return np.clip(out, 0.0, None).astype(np.float32), mean


def noise_dn(img, mask):
    """Robust noise (DN) of the fine structure inside mask."""
    import cv2
    import numpy as np
    f = img.astype(np.float32)
    res = f - cv2.GaussianBlur(f, (0, 0), 12)
    return float(1.4826 * np.median(np.abs(res[mask])))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("raw")
    ap.add_argument("--out", required=True)
    ap.add_argument("--window-s", type=float, default=30.0)
    ap.add_argument("--max", type=int, default=4, help="windows to write")
    ap.add_argument("--skip-s", type=float, default=0.0, help="seconds of video to skip first")
    a = ap.parse_args(argv)
    import cv2
    import numpy as np
    from navera_tools.field import allsky, replay360, sky360
    os.makedirs(a.out, exist_ok=True)
    lenses = sky360.default_lenses()
    yy, xx = np.mgrid[0:1920, 0:3840]
    inside = np.zeros((1920, 3840), bool)
    for L in lenses:
        inside |= np.hypot(xx - L.cx, yy - L.cy) < L.radius - 20
    del yy, xx

    def spots(img, up):
        return sum(len(allsky.detect_spots(img, L, up_imu=up, min_alt=allsky.LOCATE_MIN_ALT)) for L in lenses)

    win, done, ms_first = None, 0, None
    for t, ms, frame, drv in replay360.frames(a.raw, every_frame=True):
        ms_first = ms if ms_first is None else ms_first
        if ms - ms_first < a.skip_s * 1000.0:
            continue
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if not drv.stopped(at_ms=ms).get("stopped"):
            win = None
            continue
        if win is None:
            win = {"ms0": ms, "t0": t, "acc": np.zeros_like(g), "top": np.zeros_like(g), "n": 0, "first": g.copy(),
                   "ups": [], "n12": None}
        win["acc"] += g
        np.maximum(win["top"], g, out=win["top"])
        win["n"] += 1
        if win["n"] == 12:
            win["n12"] = finish(win["acc"], win["top"], 12)[0]
        if win["n"] % 15 == 1:
            up = drv.gravity(at_ms=ms)[0]
            if up is not None:
                win["ups"].append(np.asarray(up, float))
        if ms - win["ms0"] < a.window_s * 1000.0 or not win["ups"]:
            continue
        up = np.mean(win["ups"], axis=0)
        up /= np.linalg.norm(up)
        stack, mean = finish(win["acc"], win["top"], win["n"])
        name = f"stack_{done:02d}.png"
        cv2.imwrite(os.path.join(a.out, name), np.clip(stack, 0, 255).astype(np.uint8))
        cv2.imwrite(os.path.join(a.out, f"single_{done:02d}.png"), np.clip(win["first"], 0, 255).astype(np.uint8))
        row = {"idx": done, "image": name, "up_imu": [round(float(v), 6) for v in up],
               "t_exp": round((win["t0"] + t) / 2.0, 3), "frames": win["n"],
               "seconds": round((ms - win["ms0"]) / 1e3, 1),
               "noise_dn": {"single": round(noise_dn(win["first"], inside), 3),
                            "mean_all": round(noise_dn(mean, inside), 4)},
               "spots": {"single": spots(win["first"], up), "n12": spots(win["n12"], up) if win["n12"] is not None
                         else None, "all": spots(stack, up)}}
        # t_exp: the Jetson arrival times of the window's ends (the live server's frame stamps add the stream delay)
        with open(os.path.join(a.out, "index.jsonl"), "a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)
        done, win = done + 1, None
        if done >= a.max:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())

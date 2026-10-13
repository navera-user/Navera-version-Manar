"""phase.py — lab Step 3b: where did each flash fall between two frames, and does that explain the spread of the delays?

    python3 phase.py          your delays (TODO 2) against your flash phases (TODO P), a straight-line fit, out/phase.png

The PHASE of a flash is how long before the flash the program grabbed its last frame: a flash just after a grab has
a phase near 0; a flash just before the next grab has a phase near one frame period T.
"""
import csv
import os
import sys

import numpy as np

import runner_kit as rk

DATA = os.environ.get("LAB20_DATA", "/data/academy/20-live-camera")


# TODO P --------------------------------------------------------------------------------------------
def flash_phase(t0, frame_s):
    """The phase of the flash at t0 (seconds): t0 minus the grab time of the LAST frame grabbed at or before t0.
    frame_s: the frames' grab times (seconds, increasing). None when no frame was grabbed at or before t0.

    Example: flash_phase(1.0, [0.9, 0.97, 1.01]) → about 0.03
             flash_phase(0.5, [0.9, 0.97]) → None
    """
    return None   # TODO: replace this line with your code


# ---- you don't need to change anything below this line ----
def main():
    tm = rk.load_student("navera_lite.timing")
    with open(os.path.join(DATA, "flashes.csv"), newline="") as f:
        flashes = [float(r["t_white_s"]) for r in csv.DictReader(f)]
    with open(os.path.join(DATA, "bench_frames.csv"), newline="") as f:
        rows = list(csv.DictReader(f))
    ft = [float(r["grab_s"]) for r in rows]
    fb = [float(r["brightness"]) for r in rows]
    d = rk.need_ok(tm, "delay_from_flashes", flashes, ft, fb)
    here = sys.modules[__name__]
    pts = []
    for k, (t0, x) in enumerate(zip(flashes, d)):
        if x is None:
            continue
        ph = rk.need_ok(here, "flash_phase", t0, ft)
        pts.append((k, 1000.0 * ph, 1000.0 * x))
    med = float(np.median([p[2] for p in pts]))
    T = 1000.0 / 28.8
    keep = [p for p in pts if p[2] <= med + 2 * T]             # leave out a flash hit by a stall
    left = [p[0] for p in pts if p not in keep]
    ph = np.array([p[1] for p in keep])
    dl = np.array([p[2] for p in keep])
    slope, intercept = np.polyfit(ph, dl, 1)
    r = float(np.corrcoef(ph, dl)[0, 1])
    print("flash   phase (ms)   delay (ms)")
    for k, p_, x in pts:
        print(f"{k:5d}   {p_:10.1f}   {x:10.1f}" + ("   (left out of the fit)" if k in left else ""))
    print(f"\nstraight-line fit on {len(keep)} flashes: delay = {slope:.3f} × phase + {intercept:.1f} ms   "
          f"(correlation r = {r:.3f})")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(ph, dl, "o", label="one flash")
        xs = np.array([0.0, T])
        ax.plot(xs, slope * xs + intercept, "-", label=f"fit: slope {slope:.2f}")
        ax.set_xlabel("phase: time since the last grab before the flash (ms)")
        ax.set_ylabel("measured delay (ms)")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        os.makedirs("out", exist_ok=True)
        fig.savefig(os.path.join("out", "phase.png"), dpi=110)
        rk.saved(os.path.join("out", "phase.png"))


if __name__ == "__main__":
    main()

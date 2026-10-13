"""detective.py — Step 8: a colleague's attitude table looks wrong. Find out why, and prove it.

    python3 detective.py

The log /data/academy/16-rotations/attitude_log.csv holds the orientation of a 150 s drone flight
exactly as a ROS sensor_msgs/Imu message stores it: (x, y, z, w). A colleague's script turned it into
the table colleague_attitude.csv (roll, pitch_up, heading). Your two TODOs below, then run this file.
"""
import csv
import math
import sys

import numpy as np

from navera_lite import rotations as rot

DATA = "/data/academy/16-rotations"


# TODO A ------------------------------------------------------------------------------------------
def misread(q_ros):
    """The quaternion the colleague's script really used, written back in OUR order (x, y, z, w).

    q_ros: the four numbers of one log row, in the file's order (qx, qy, qz, qw). The colleague's script
    believed the four numbers were (w, x, y, z). Returns a numpy array (x, y, z, w) of what it used.

    Example: misread((0.1, 0.2, 0.3, 0.9)) → array([0.2, 0.3, 0.9, 0.1])
    """
    w, x, y, z = (float(v) for v in q_ros)          # what the colleague's script believed
    return np.array([x, y, z, w])


# TODO B ------------------------------------------------------------------------------------------
def tilt_deg(q):
    """How far the vehicle is tilted from level, in degrees in [0, 180]: the angle between the body's
    "up" axis (0, 0, 1) and the world's up. 0 = level, 90 = on its side, 180 = upside down.
    q: an attitude quaternion (x, y, z, w). Use your own functions from navera_lite/rotations.py.

    Example: tilt_deg(rot.q_from_euler_zyx(math.radians(30), 0.0, math.radians(200))) → about 30.0
    """
    up = rot.q_rotate(q, (0.0, 0.0, 1.0))           # the body's up axis, in the world
    return math.degrees(math.acos(max(-1.0, min(1.0, float(up[2])))))


# ---- you don't need to change anything below this line (but you can read it!) ----

def load(name):
    try:
        with open(f"{DATA}/{name}") as f:
            return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]
    except FileNotFoundError:
        sys.exit(f"{DATA}/{name} is missing: this file is in the course data (/data/academy/16-rotations/)")


def need(fn, *args):
    try:
        v = fn(*args)
    except Exception as e:
        tip = (" — it uses your functions of navera_lite/rotations.py: finish TODOs 1–11 first "
               "(python3 run_rotations.py test)") if "NoneType" in str(e) or isinstance(e, NotImplementedError) else ""
        if "math domain" in str(e):
            tip = (" — acos/asin got a number just above 1: clamp before acos/asin; if the function is from "
                   "navera_lite/rotations.py (q_angle_deg?), fix it there")
        sys.exit(f"{fn.__name__}() stopped with {type(e).__name__}: {e}{tip}")
    if v is None:
        sys.exit(f"{fn.__name__}() returned None: write its TODO (and `return` the result)")
    return v


def main():
    log = load("attitude_log.csv")
    coll = load("colleague_attitude.csv")
    t = np.array([r["t_s"] for r in log])
    q = np.array([[r["qx"], r["qy"], r["qz"], r["qw"]] for r in log])
    print(f"{len(t)} samples, t = {t[0]:.1f} … {t[-1]:.1f} s\n")

    # 0. can your misread() reproduce the colleague's table?
    worst = 0.0
    for k in range(len(t)):
        qm = np.asarray(need(misread, q[k]), dtype=float)
        mine = need(rot.rpy_human, qm)
        theirs = (coll[k]["roll_deg"], coll[k]["pitch_up_deg"], coll[k]["heading_deg"])
        d = [abs(a - b) for a, b in zip(mine, theirs)]
        d[2] = min(d[2], 360 - d[2])
        worst = max(worst, max(d))
    verdict = "✔ reproduced" if worst < 0.1 else "✘ NOT reproduced: check misread()"
    print(f"0. your misread() + rpy_human against the colleague's table: largest difference {worst:.2f}°  {verdict}\n")

    # 1. on the pad
    pad = t < 9.0
    true_pad = [need(rot.rpy_human, q[k]) for k in np.where(pad)[0]]
    print("1. On the pad (t < 9 s), mean of the samples:")
    print(f"     read as ROS (x, y, z, w):  roll {np.mean([v[0] for v in true_pad]):6.1f}°  "
          f"pitch_up {round(float(np.mean([v[1] for v in true_pad])), 1) + 0.0:5.1f}°  heading {np.mean([v[2] for v in true_pad]):6.1f}°")
    print(f"     the colleague's table:     roll {np.mean([coll[k]['roll_deg'] for k in np.where(pad)[0]]):6.1f}°  "
          f"pitch_up {np.mean([coll[k]['pitch_up_deg'] for k in np.where(pad)[0]]):5.1f}°  "
          f"heading {np.mean([coll[k]['heading_deg'] for k in np.where(pad)[0]]):6.1f}°\n")

    # 2. lengths
    lengths = np.linalg.norm(q, axis=1)
    lengths_m = np.array([np.linalg.norm(need(misread, x)) for x in q])
    print(f"2. Length of every quaternion: ROS reading {lengths.min():.6f} … {lengths.max():.6f};  "
          f"misread {lengths_m.min():.6f} … {lengths_m.max():.6f}\n")

    # 3. tilt along the flight
    tilt_true = np.array([need(tilt_deg, x) for x in q], dtype=float)
    tilt_mis = np.array([need(tilt_deg, need(misread, x)) for x in q], dtype=float)
    k = int(np.argmax(tilt_mis))
    print(f"3. Tilt from level: ROS reading max {tilt_true.max():5.1f}°;  misread max {tilt_mis.max():5.1f}° "
          f"(at t = {t[k]:.1f} s, when the true heading is {need(rot.rpy_human, q[k])[2]:.1f}°)\n")

    # 4. rotation between consecutive samples
    step_true = np.array([need(rot.q_angle_deg, q[i], q[i + 1]) for i in range(len(q) - 1)], dtype=float)
    step_mis = np.array([need(rot.q_angle_deg, need(misread, q[i]), need(misread, q[i + 1]))
                         for i in range(len(q) - 1)], dtype=float)
    print(f"4. Rotation between consecutive samples (0.1 s): largest {step_true.max():.3f}° (ROS reading) and "
          f"{step_mis.max():.3f}° (misread);")
    print(f"   largest difference between the two readings, sample by sample: {np.abs(step_true - step_mis).max():.2e}°\n")

    # 5. sign of q
    dots = np.sum(q[:-1] * q[1:], axis=1)
    flips = np.where(dots < 0)[0]
    for i in flips:
        print(f"5. Between t = {t[i]:.1f} s and t = {t[i + 1]:.1f} s the four numbers change sign: "
              f"q0 · q1 = {dots[i]:+.4f};  q_angle_deg = {step_true[i]:.3f}°")
    if len(flips) == 0:
        print("5. No sign change between consecutive samples.")

    plt = None
    try:
        import warnings
        warnings.filterwarnings("ignore", message="Unable to import Axes3D")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        pass
    if plt is not None:
        import os
        os.makedirs("out", exist_ok=True)
        heading_true = [need(rot.rpy_human, x)[2] for x in q]
        fig, axs = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True)
        axs[0].plot(t, heading_true, label="heading, read as ROS (x, y, z, w)")
        axs[0].plot(t, [c["heading_deg"] for c in coll], label="heading, colleague", alpha=0.8)
        axs[0].set_ylabel("heading (°)")
        axs[0].legend(fontsize=8)
        axs[1].plot(t, tilt_true, label="tilt, ROS reading")
        axs[1].plot(t, tilt_mis, label="tilt, misread", alpha=0.8)
        axs[1].set_ylabel("tilt from level (°)")
        axs[1].set_xlabel("t (s)")
        axs[1].legend(fontsize=8)
        for ax in axs:
            ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig("out/detective.png", dpi=110)
        print("\n🖼  picture saved: out/detective.png (open it in the 📝 Code tab)")


if __name__ == "__main__":
    main()

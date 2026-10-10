# Lesson 16 — from raw IMU samples to an attitude: gyro integration, accelerometer tilt,
# complementary filter, tilt-compensated compass and true north.
# Fill in TODOs 8–12, save, then run:   python3 imu_filters.py
# It reads the simulated log /data/academy/16-rotations/imu_log.csv (a flight near Monastir), writes
# results.json (graded) and attitude.png (click it in the file list to open it).
#
# Conventions: the same as quaternions.py — radians inside the functions, quaternions (w, x, y, z),
# body FLU, world ENU, ZYX Euler angles with ROS signs (positive pitch = nose DOWN).
import json
import math

import numpy as np

from quaternions import quat_mul, quat_from_axis_angle, quat_to_matrix, matrix_to_euler

G = 9.80665


# TODO 8: integrate the gyroscope in 3-D.
#   t: array (N,) of times (s); gyro: array (N, 3) of body rates (rad/s); q0: start quaternion (w, x, y, z).
#   Return an array (N, 4) of quaternions with q[0] = q0. Course: section 7.
#   Rules of this lab: step k uses the rate gyro[k-1] (measured at the start of the step) and
#   dt = t[k] − t[k-1]; turn the small rotation of one step into a quaternion with your
#   TODO 4 function (careful when |ω| = 0); think about the SIDE of the product (the rates
#   are measured in the BODY frame); normalise q[k] at each step.
def integrate_gyro(t, gyro, q0):
    return None   # TODO 8: replace this line with your code

# TODO 9: roll and pitch (radians, ROS signs) from accelerometer samples alone.
#   acc: array (N, 3) of specific force (m/s²) in the body frame. Course: section 8.
#   Return two arrays (roll, pitch). numpy functions work on whole columns (no loop needed).
def accel_roll_pitch(acc):
    return None   # TODO 9: replace this line with your code

# TODO 10: complementary filter for roll and pitch (radians), time constant tau (s).
#   Course: section 9 (the filter equation, alpha from tau and dt, and the Euler-angle
#   kinematics that turn body rates p, q, r into roll and pitch rates).
#   Start from the accelerometer angles of sample 0 (your TODO 9). Step k: predict with the
#   gyro of sample k-1 and dt = t[k] − t[k-1], then blend with the accelerometer angles of sample k.
#   Return two arrays (roll, pitch) of length N.
def complementary_tilt(t, gyro, acc, tau):
    return None   # TODO 10: replace this line with your code

# TODO 11: tilt-compensated MAGNETIC heading (degrees, clockwise from magnetic north, in [0, 360)).
#   mag: array (N, 3) body-frame field; roll, pitch: arrays (N,) in radians.
#   Course: section 10 (tilt compensation: first "level" the measured field with roll and
#   pitch, then read the heading from its horizontal part).
#   (rot_x / rot_y are in quaternions.py.) Output: an array of N headings in degrees, in [0, 360).
def mag_heading(mag, roll, pitch):
    return None   # TODO 11: replace this line with your code

# TODO 12: the magnetic declination (deg, east positive) from the World Magnetic Model,
#   exactly like NAVERA's class Declination in ~/navera/imu_pkg/imu_pkg/orientation.py
#   (read how it calls the pygeomag package; use alt = 0).
#   year is a decimal year (2026.79 = mid-October 2026). Output: one float in degrees.
def declination_at(lat, lon, year):
    return None   # TODO 12: replace this line with your code

# ---- you don't need to change anything below this line (but read it!) ----
LOG = "/data/academy/16-rotations/imu_log.csv"
META = "/data/academy/16-rotations/imu_log_meta.json"
TAUS = (0.1, 0.3, 1.0, 3.0, 10.0, 30.0)
WORLD = {"London": (51.501, -0.125), "Reykjavik": (64.147, -21.943), "Cape Town": (-33.925, 18.424),
         "Sydney": (-33.869, 151.209), "Singapore": (1.290, 103.852)}


def load_log(path=LOG):
    """The log as a dict of numpy arrays, one per column."""
    data = np.genfromtxt(path, delimiter=",", names=True)
    return {name: np.asarray(data[name], dtype=float) for name in data.dtype.names}


def wrap180(a):
    """Angle differences brought into [-180, 180) (359 vs 1 is a 2 deg error, not 358)."""
    return (np.asarray(a) + 180.0) % 360.0 - 180.0


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def quat_heading_deg(qs):
    """Compass heading (deg) of each quaternion (w, x, y, z) in an ENU frame."""
    out = []
    for q in qs:
        R = quat_to_matrix(q)
        out.append((90.0 - math.degrees(math.atan2(R[1, 0], R[0, 0]))) % 360.0)
    return np.array(out)


def main():
    import warnings
    warnings.filterwarnings("ignore", message="Unable to import Axes3D")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from quaternions import quat_from_euler

    log = load_log()
    with open(META) as f:
        meta = json.load(f)
    t = log["t_s"]
    gyro = np.stack([log["gx"], log["gy"], log["gz"]], 1)
    acc = np.stack([log["ax"], log["ay"], log["az"]], 1)
    mag = np.stack([log["mx"], log["my"], log["mz"]], 1)
    t_roll, t_pitch, t_head = log["true_roll_deg"], log["true_pitch_deg"], log["true_heading_deg"]
    res = {"samples": int(len(t)), "duration_s": float(t[-1] - t[0])}
    print(f"{len(t)} samples, {t[-1] - t[0]:.0f} s at {(len(t) - 1) / (t[-1] - t[0]):.0f} Hz, "
          f"{meta['place']}")

    # 1. gyroscope alone (dead-reckoning of the attitude from the true start)
    try:
        q0 = quat_from_euler(math.radians(t_roll[0]), math.radians(t_pitch[0]),
                             math.radians(90.0 - t_head[0]))
        ready = q0 is not None and quat_to_matrix(q0) is not None \
            and matrix_to_euler(quat_to_matrix(q0)) is not None
    except (TypeError, ValueError):
        ready = False
    if not ready:
        print("Finish quaternions.py first (TODOs 2, 3, 4 and 6 are used here).")
        return
    qs = integrate_gyro(t, gyro, q0)
    if qs is None:
        print("TODO 8: integrate_gyro() returns None")
        return
    g_head = quat_heading_deg(qs)
    g_rpy = np.degrees(np.array([matrix_to_euler(quat_to_matrix(q)) for q in qs]))
    err = wrap180(g_head - t_head)
    i60 = int(np.argmin(abs(t - 60)))
    res["gyro_heading_error_60s_deg"] = float(err[i60])
    res["gyro_heading_error_end_deg"] = float(err[-1])
    res["gyro_roll_error_end_deg"] = float(g_rpy[-1, 0] - t_roll[-1])
    res["gyro_pitch_error_end_deg"] = float(g_rpy[-1, 1] - t_pitch[-1])
    print(f"gyro only: heading error {err[i60]:+.2f} deg after 60 s, {err[-1]:+.2f} deg after 300 s")

    # 2. accelerometer alone
    ar = accel_roll_pitch(acc)
    if ar is None:
        print("TODO 9: accel_roll_pitch() returns None")
        return
    a_roll, a_pitch = np.degrees(ar[0]), np.degrees(ar[1])
    res["accel_roll_rms_deg"] = rms(a_roll - t_roll)
    res["accel_pitch_rms_deg"] = rms(a_pitch - t_pitch)
    res["accel_roll_max_deg"] = float(np.max(abs(a_roll - t_roll)))
    print(f"accelerometer only: roll RMS {res['accel_roll_rms_deg']:.2f} deg (max "
          f"{res['accel_roll_max_deg']:.1f}), pitch RMS {res['accel_pitch_rms_deg']:.2f} deg")

    # 3. complementary filter, several time constants
    sweep = {}
    best = None
    for tau in TAUS:
        cf = complementary_tilt(t, gyro, acc, tau)
        if cf is None:
            print("TODO 10: complementary_tilt() returns None")
            return
        e = (rms(np.degrees(cf[0]) - t_roll), rms(np.degrees(cf[1]) - t_pitch))
        sweep[str(tau)] = {"roll_rms_deg": e[0], "pitch_rms_deg": e[1]}
        print(f"complementary tau = {tau:5.1f} s: roll RMS {e[0]:.2f} deg, pitch RMS {e[1]:.2f} deg")
        if best is None or e[0] + e[1] < best[1]:
            best = (tau, e[0] + e[1], cf)
    res["complementary_sweep"] = sweep
    res["best_tau_s"] = best[0]
    c_roll, c_pitch = best[2]

    # 4. compass: tilt-compensated magnetic heading, then true heading
    D = declination_at(meta["lat"], meta["lon"], meta["decimal_year"])
    mh = mag_heading(mag, c_roll, c_pitch)
    mh_flat = mag_heading(mag, np.zeros(len(t)), np.zeros(len(t)))
    if mh is None or D is None:
        print("TODO 11/12: mag_heading() or declination_at() returns None")
        return
    true_h = (mh + D) % 360.0
    res["declination_deg"] = float(D)
    res["mag_heading_mean_error_deg"] = float(np.mean(wrap180(mh - t_head)))
    res["true_heading_rms_deg"] = rms(wrap180(true_h - t_head))
    res["no_tilt_comp_rms_deg"] = rms(wrap180(mh_flat + D - t_head))
    print(f"declination at {meta['lat']}, {meta['lon']} ({meta['date']}): {D:+.3f} deg")
    print(f"magnetic heading: mean error {res['mag_heading_mean_error_deg']:+.2f} deg (that is -D)")
    print(f"true heading (magnetic + D, tilt-compensated): RMS {res['true_heading_rms_deg']:.2f} deg; "
          f"without tilt compensation: RMS {res['no_tilt_comp_rms_deg']:.2f} deg")

    # 5. the BNO085's own fused quaternion (x, y, z, w order, magnetic north)
    from quaternions import xyzw_to_wxyz
    qf = [xyzw_to_wxyz(v) for v in zip(log["qx"], log["qy"], log["qz"], log["qw"])]
    fh = (quat_heading_deg(qf) + D) % 360.0
    res["fused_true_heading_rms_deg"] = rms(wrap180(fh - t_head))
    print(f"BNO085 fused quaternion + D: heading RMS {res['fused_true_heading_rms_deg']:.2f} deg")

    # 6. declination around the world
    res["world_declination_deg"] = {k: round(declination_at(la, lo, 2026.79), 3) for k, (la, lo) in WORLD.items()}
    print("declination, October 2026:", ", ".join(f"{k} {v:+.2f}" for k, v in res["world_declination_deg"].items()))

    with open("results.json", "w") as f:
        json.dump(res, f, indent=1)
    print("saved results.json")

    fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    ax[0].plot(t, t_roll, "k-", lw=3, alpha=0.3, label="true roll")
    ax[0].plot(t, a_roll, "-", color="#d9822b", lw=0.5, alpha=0.7, label="accelerometer only")
    ax[0].plot(t, np.degrees(c_roll), "-", color="#0b6e8a", lw=1.2, label=f"complementary, tau={best[0]} s")
    ax[0].set_ylabel("roll (deg)")
    ax[0].legend(loc="upper right", fontsize=8)
    ax[0].set_title("Lesson 16 — attitude from a simulated IMU log (flight near Monastir)")
    ax[1].plot(t, wrap180(true_h - t_head), "-", color="#0b6e8a", lw=0.6, label="compass + declination: error")
    ax[1].plot(t, err, "r-", lw=1.5, label="gyro only: heading error")
    ax[1].axhline(0, color="k", lw=0.5)
    ax[1].set_ylabel("heading error (deg)")
    ax[1].legend(loc="lower left", fontsize=8)
    ax[2].plot(t, t_head, "k-", lw=3, alpha=0.3, label="true heading")
    ax[2].plot(t, g_head, "r-", lw=1, label="gyro only")
    ax[2].set_ylim(0, 360)
    ax[2].set_ylabel("heading (deg)")
    ax[2].set_xlabel("time (s)")
    ax[2].legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig("attitude.png", dpi=80)
    print("saved attitude.png — open it from the file list")


if __name__ == "__main__":
    main()

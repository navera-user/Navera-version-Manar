# Lesson 16 — counting turns blindfolded: integrate a gyroscope and watch it drift.
# Fill in TODO 6, save, then run:   python3 gyro_drift.py
# It reads the simulated IMU log /data/academy/16-imu/imu_log.csv and draws drift.png
# (click it in the file list to open it).
import math


# TODO 6: integrate the gyroscope.
#   times: list of times (s); rates: list of rotation speeds (rad/s), same length.
#   Return a list (same length) of the TOTAL angle turned since the first sample, in DEGREES:
#     angle[0] = 0
#     angle[i] = angle[i-1] + rates[i] × (times[i] − times[i-1])     (then convert to degrees)
#   It is exactly "counting your steps": each small step is speed × time.
def integrate_gyro(times, rates):
    return [0.0] * len(times)


# ---- you don't need to change anything below this line (but you can read it!) ----
LOG = "/data/academy/16-imu/imu_log.csv"


def load_log(path=LOG):
    """The log as a dict of columns (lists of floats)."""
    import csv
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return {k: [float(r[k]) for r in rows] for k in rows[0]}


def wrap180(a):
    """An angle difference brought between -180 and +180 deg (359 - 1 is a 2 deg error, not 358)."""
    return (a + 180.0) % 360.0 - 180.0


def main():
    import warnings
    warnings.filterwarnings("ignore", message="Unable to import Axes3D")   # harmless on this box
    import matplotlib
    matplotlib.use("Agg")                     # no window: we save a PNG
    import matplotlib.pyplot as plt
    try:
        from attitude import quat_to_euler, heading_from_yaw
    except ImportError:
        quat_to_euler = heading_from_yaw = None

    log = load_log()
    t, gz, truth = log["t_s"], log["gz"], log["true_heading_deg"]
    turned = integrate_gyro(t, gz)            # counter-clockwise, degrees
    start = truth[0]
    # yaw counter-clockwise = heading going DOWN, hence the minus sign
    gyro_heading = [(start - a) % 360.0 for a in turned]
    gyro_err = [wrap180(g - h) for g, h in zip(gyro_heading, truth)]

    quat_err = None
    if quat_to_euler is not None:
        q = list(zip(log["qx"], log["qy"], log["qz"], log["qw"]))
        rpy = [quat_to_euler(v) for v in q]
        if rpy[0] is not None and heading_from_yaw(rpy[0][2]) is not None:
            quat_heading = [heading_from_yaw(r[2]) for r in rpy]
            quat_err = [wrap180(a - h) for a, h in zip(quat_heading, truth)]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True)
    ax1.plot(t, truth, "k-", lw=3, alpha=0.35, label="true heading")
    ax1.plot(t, gyro_heading, "r-", lw=1.2, label="gyroscope only (integrated)")
    ax1.set_ylabel("heading (deg)")
    ax1.set_ylim(0, 360)
    ax1.legend(loc="upper left")
    ax1.set_title("Lesson 16 — heading from the gyroscope alone vs the fused orientation")
    ax2.plot(t, gyro_err, "r-", label="gyroscope only: error")
    if quat_err is not None:
        ax2.plot(t, quat_err, "-", color="#0b6e8a", lw=0.8, label="fused quaternion: error")
    ax2.axhline(0, color="k", lw=0.5)
    ax2.set_xlabel("time (s)")
    ax2.set_ylabel("error (deg)")
    ax2.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig("drift.png", dpi=90)

    print(f"{len(t)} samples, {t[-1] - t[0]:.0f} s at {(len(t) - 1) / (t[-1] - t[0]):.0f} Hz")
    print(f"total turn measured by the gyroscope: {turned[-1]:+.1f} deg (counter-clockwise +)")
    for when in (60, 120, 300):
        i = min(range(len(t)), key=lambda k: abs(t[k] - when))
        print(f"after {t[i]:5.0f} s  gyroscope heading error {gyro_err[i]:+6.1f} deg"
              + (f"   fused quaternion error {quat_err[i]:+5.1f} deg" if quat_err else ""))
    if all(a == 0.0 for a in turned):
        print("TODO 6: integrate_gyro() still returns only zeros")
    print("saved drift.png — open it from the file list")


if __name__ == "__main__":
    main()

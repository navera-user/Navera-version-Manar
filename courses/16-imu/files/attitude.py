# Lesson 16 — Which way am I facing?
# Fill in the TODOs one by one, save (Ctrl+S), then run:   python3 attitude.py
#
# Conventions (the same as ROS and NAVERA):
#   * a quaternion is 4 numbers (x, y, z, w), like sensor_msgs/Imu.orientation
#   * body axes:  x forward, y left, z up
#   * world axes: x east, y north, z up  (ENU)
#   * yaw is counter-clockwise from EAST (maths angle); heading is clockwise from NORTH (compass)
import math


# TODO 1: turn a quaternion (x, y, z, w) into (roll, pitch, yaw) in DEGREES.
#   Use the three formulas of the course:
#     roll  = atan2(2(w·x + y·z), 1 − 2(x² + y²))
#     pitch = asin (2(w·y − z·x))          (clamp the value inside [-1, 1] first!)
#     yaw   = atan2(2(w·z + x·y), 1 − 2(y² + z²))
#   math.atan2, math.asin and math.degrees do the work.
def quat_to_euler(q):
    x, y, z, w = q
    return None


# TODO 2: turn a ROS yaw (deg, counter-clockwise from east) into a compass heading
#   (deg, clockwise from north), always between 0 (included) and 360 (excluded).
#   Examples: yaw 90 → heading 0 (north), yaw 0 → heading 90 (east), yaw -90 → 180.
def heading_from_yaw(yaw_deg):
    return None


# TODO 3: a MAGNETIC heading + the declination (deg, east positive) → the TRUE heading,
#   between 0 and 360.  Example: 358 + 3.3 → 1.3
def true_heading(magnetic_heading_deg, declination_deg):
    return None


# TODO 4: the magnetic declination (deg, east positive) at a place and date, from the
#   World Magnetic Model, exactly like NAVERA's imu_pkg/orientation.py (class Declination):
#       from pygeomag import GeoMag
#       GeoMag().calculate(glat=..., glon=..., alt=0, time=year).d
#   year is a decimal year, e.g. 2026.75 for the beginning of October 2026.
def declination_at(lat, lon, year):
    return None


# TODO 5: a camera looking down from height_m, tilted tilt_deg away from vertical:
#   how far (m) from the point under the drone is the centre of its photo?
#   (see the picture "tilt" in the course:  h × tan(tilt))
def ground_offset_m(height_m, tilt_deg):
    return None


# ---- you don't need to change anything below this line (but you can read it!) ----
SAMPLES = {
    "level, nose to the north-east": (0.0, 0.0, 0.382683, 0.923880),
    "level, nose to the east":       (0.0, 0.0, 0.0, 1.0),
    "level, nose to the north":      (0.0, 0.0, 0.707107, 0.707107),
    "banked, nose up, to the SSW":   (0.014348, -0.096250, -0.813078, 0.573964),
}
SOUSSE = (35.8256, 10.6360)


def _navera():
    """NAVERA's own conversion (your copy: ~/navera/imu_pkg/imu_pkg/orientation.py)."""
    try:
        from imu_pkg.orientation import heading_deg
        return heading_deg
    except ImportError:
        return None


if __name__ == "__main__":
    nav_heading = _navera()
    print(f"{'orientation':32s} {'roll':>7s} {'pitch':>7s} {'yaw':>7s} {'heading':>8s} {'NAVERA':>8s}")
    for name, q in SAMPLES.items():
        rpy = quat_to_euler(q)
        if rpy is None:
            print(f"{name:32s}  TODO 1: quat_to_euler() returns None")
            continue
        h = heading_from_yaw(rpy[2])
        nav = round(nav_heading(q), 1) % 360 if nav_heading else float("nan")
        hs = "TODO 2" if h is None else f"{round(h, 1) % 360:8.1f}"     # 359.99 shows as 0.0
        print(f"{name:32s} {rpy[0]:7.1f} {rpy[1]:7.1f} {rpy[2]:7.1f} {hs:>8s} {nav:8.1f}")
    print()
    d = declination_at(*SOUSSE, 2026.75)
    if d is None:
        print("TODO 4: declination_at() returns None")
    else:
        print(f"declination in Sousse, October 2026: {d:+.2f} deg")
        th = true_heading(358.0, d)
        print("TODO 3: true_heading() returns None" if th is None else
              f"a compass reading of 358 deg there is a TRUE heading of {th:.1f} deg")
    off = ground_offset_m(150.0, 10.0)
    print("TODO 5: ground_offset_m() returns None" if off is None else
          f"camera tilted 10 deg at 150 m: the photo centre is {off:.1f} m away from the drone")

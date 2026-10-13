"""navera_lite/imu.py — gyro integration, tilt, complementary filter, compass heading.

Part of NAVERA Lite, the course's teaching stack (mission 17). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 17.
"""


def integrate_gyro(q0, t_s, gyro_rad_s):
    """Attitude from the gyro."""
    ...


def complementary(t_s, gyro, accel, tau_s):
    """Gyro + accelerometer."""
    ...


def true_heading(mag_deg, decl_deg):
    """Compass heading to true heading."""
    ...

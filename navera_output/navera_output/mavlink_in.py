"""What NAVERA reads from the vehicle's autopilot over MAVLink, in NAVERA's frames.

MAVLink is spoken by ArduPilot, PX4 and many other autopilots; the messages read
here are common.xml, not dialect-specific. Frames: MAVLink gives the attitude of the
body (forward-right-down) in north-east-down; NAVERA (ROS REP-103) uses the body
forward-left-up in east-north-up.

    ATTITUDE_QUATERNION / ATTITUDE  -> body attitude (ENU quaternion) + rates
    DISTANCE_SENSOR (pointing down) -> height above ground (corrected for tilt)
    GLOBAL_POSITION_INT.relative_alt-> height above home (barometer-based)
    GPS2_RAW                        -> the vehicle's own second GPS, when it has one

Not read on purpose: GPS_RAW_INT / GLOBAL_POSITION_INT lat/lon — when NAVERA feeds
the autopilot's GPS, reading them back would be NAVERA's own output (a loop).
"""
import math
from typing import Optional, Sequence, Tuple

import numpy as np

# rotations between conventions
R_ENU_NED = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
R_FRD_FLU = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])
MAV_SENSOR_ROTATION_PITCH_270 = 25          # pointing down


def quat_wxyz_to_matrix(w, x, y, z) -> np.ndarray:
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if not n > 0:
        raise ValueError("invalid quaternion")
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def matrix_to_quat_xyzw(R: np.ndarray) -> Tuple[float, float, float, float]:
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s
    if w < 0:
        w, x, y, z = -w, -x, -y, -z
    return x, y, z, w


def ned_frd_to_enu_flu(R_ned_frd: np.ndarray) -> Tuple[float, float, float, float]:
    """Body attitude NED/FRD (MAVLink) -> ENU/FLU quaternion (x, y, z, w) (ROS)."""
    return matrix_to_quat_xyzw(R_ENU_NED @ R_ned_frd @ R_FRD_FLU)


def attitude_quaternion(q1: float, q2: float, q3: float, q4: float) -> Tuple[float, float, float, float]:
    """ATTITUDE_QUATERNION q1..q4 = w, x, y, z (NED, FRD)."""
    return ned_frd_to_enu_flu(quat_wxyz_to_matrix(q1, q2, q3, q4))


def attitude_euler(roll: float, pitch: float, yaw: float) -> Tuple[float, float, float, float]:
    """ATTITUDE roll, pitch, yaw (rad, NED, FRD: roll right-down +, pitch nose-up +,
    yaw clockwise from north)."""
    cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch),
                              math.cos(yaw), math.sin(yaw))
    R = np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                  [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                  [-sp, cp * sr, cp * cr]])
    return ned_frd_to_enu_flu(R)


def rates_frd_to_flu(rollspeed: float, pitchspeed: float, yawspeed: float) -> Tuple[float, float, float]:
    return rollspeed, -pitchspeed, -yawspeed


def downward_range_agl(current_distance_cm: int, min_cm: int, max_cm: int, orientation: int,
                       q_enu_flu: Optional[Sequence[float]] = None) -> Optional[float]:
    """Height above ground from a downward rangefinder (m), corrected for the vehicle's
    tilt when the attitude is known; None if not pointing down or out of range."""
    if orientation != MAV_SENSOR_ROTATION_PITCH_270:
        return None
    # at its limits a rangefinder reports "no echo" (many give exactly max, or min, when
    # nothing comes back — over water, at the edge of range): not a height
    if not (min_cm < current_distance_cm < max_cm) or current_distance_cm <= 0:
        return None
    d = current_distance_cm / 100.0
    if q_enu_flu is not None:
        x, y, z, w = q_enu_flu
        cos_tilt = 1 - 2 * (x * x + y * y)                 # body z . world z
        if cos_tilt < 0.5:                                 # > 60 deg: the beam is not on the ground below
            return None
        d *= cos_tilt
    return d

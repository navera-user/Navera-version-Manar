"""IMU orientation corrections: magnetic → true north, sensor → vehicle (body) frame.

The BNO085 rotation vector is an orientation in a local ENU world frame whose
north is MAGNETIC north, of the SENSOR's axes. NAVERA's consumers (night vision
heading, celestial camera attitude) need TRUE north and the VEHICLE's axes
(REP-103 body frame: x forward, y left, z up). This module does both:

* declination (east positive): true heading = magnetic heading + declination.
  In ENU the yaw is counter-clockwise from east, so the world frame is turned by
  -declination about the up axis: q_true = Rz(-D) * q_mag.
* mounting: the sensor's orientation in the body frame, as roll/pitch/yaw (deg,
  ROS fixed-axis XYZ). With q_mount = body→sensor, q_body = q_sensor * q_mount⁻¹,
  and body-frame vectors are R(q_mount) · v_sensor.

Quaternions are (x, y, z, w), as in sensor_msgs/Imu.
"""
import math
from typing import Optional, Sequence, Tuple

Quat = Tuple[float, float, float, float]
Vec = Tuple[float, float, float]


def quat_mul(a: Sequence[float], b: Sequence[float]) -> Quat:
    """Hamilton product a * b of (x, y, z, w) quaternions."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def quat_conj(q: Sequence[float]) -> Quat:
    return (-q[0], -q[1], -q[2], q[3])


def quat_from_rpy(roll: float, pitch: float, yaw: float) -> Quat:
    """Quaternion of fixed-axis roll, pitch, yaw (rad) — the ROS/tf convention."""
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy)


def rotate(q: Sequence[float], v: Sequence[float]) -> Vec:
    """Vector v rotated by the unit quaternion q."""
    x, y, z, _ = quat_mul(quat_mul(q, (v[0], v[1], v[2], 0.0)), quat_conj(q))
    return (x, y, z)


def heading_deg(q: Sequence[float]) -> float:
    """Heading (deg clockwise from the frame's north) of the body x axis, ENU frame."""
    x, y, z, w = q
    yaw_enu = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return (90.0 - math.degrees(yaw_enu)) % 360.0


class OrientationCorrector:
    """Turns BNO085 samples into true-north, vehicle-frame samples."""

    def __init__(self, mount_rpy_deg: Sequence[float] = (0.0, 0.0, 0.0)):
        r, p, y = (math.radians(float(a)) for a in mount_rpy_deg)
        self.q_mount = quat_from_rpy(r, p, y)          # body → sensor
        self.q_mount_inv = quat_conj(self.q_mount)
        self.identity_mount = all(abs(float(a)) < 1e-9 for a in mount_rpy_deg)

    def apply(self, quat: Sequence[float], gyro: Sequence[float], accel: Sequence[float],
              declination_deg: Optional[float]) -> Tuple[Quat, Vec, Vec]:
        """(orientation, angular velocity, linear acceleration) in the body frame, the
        orientation referenced to true north when declination_deg is known (else left
        on magnetic north)."""
        q = tuple(float(c) for c in quat)
        if not self.identity_mount:
            q = quat_mul(q, self.q_mount_inv)
            gyro = rotate(self.q_mount, gyro)
            accel = rotate(self.q_mount, accel)
        if declination_deg is not None and math.isfinite(declination_deg):
            d = math.radians(-declination_deg)
            q = quat_mul((0.0, 0.0, math.sin(d / 2), math.cos(d / 2)), q)
        return q, tuple(gyro), tuple(accel)


class Declination:
    """Magnetic declination (deg, east positive) at a position, from the World
    Magnetic Model (pygeomag, WMM 2025: valid 2025-2030). Recomputed only when the
    vehicle has moved by more than recompute_km, so it costs nothing per sample."""

    def __init__(self, recompute_km: float = 20.0):
        self.recompute_km = recompute_km
        self.value: Optional[float] = None
        self.at: Optional[Tuple[float, float]] = None
        self.error: Optional[str] = None
        try:
            from pygeomag import GeoMag
            self._gm = GeoMag()
        except Exception as e:                       # library missing: manual value only
            self._gm, self.error = None, f"World Magnetic Model unavailable ({e})"

    @property
    def available(self) -> bool:
        return self._gm is not None

    def update(self, lat: float, lon: float, year: float, alt_km: float = 0.0) -> Optional[float]:
        """Declination at (lat, lon); returns the new value when recomputed, else None."""
        if self._gm is None or not (math.isfinite(lat) and math.isfinite(lon)):
            return None
        if self.at is not None:
            dlat = math.radians(lat - self.at[0])
            dlon = math.radians(lon - self.at[1]) * math.cos(math.radians(lat))
            if 6371.0 * math.hypot(dlat, dlon) < self.recompute_km:
                return None
        try:
            self.value = float(self._gm.calculate(glat=lat, glon=lon, alt=alt_km, time=year).d)
        except Exception as e:                       # e.g. a date outside the model
            self.error = f"World Magnetic Model: {e}"
            return None
        self.at = (lat, lon)
        return self.value

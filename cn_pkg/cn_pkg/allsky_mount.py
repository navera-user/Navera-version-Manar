"""The 360 camera's orientation on the vehicle and the learned tilt of 'up', shared by the flight node
(cn_subscriber, solver_mode allsky360) and the field tools (navera_tools.field.server / reprocess360).

Frames
  ICRS      the stars (J2000), what allsky.locate's R_icrs_imu maps into;
  camera    the 360 camera's own IMU axes (allsky / sky360: +x up when the camera stands, +y the left
            lens's optical axis);
  body      the vehicle (REP-103 FLU: x forward, y left, z up);
  ENU       the local level frame of the vehicle IMU's orientation (sensor_msgs/Imu).

'up' in the camera frame is what the all-sky solver needs (the zenith among the stars is the position; no
heading is used). It comes either from the camera's own accelerometer (frame_meta "up_imu", as in the field)
or from the vehicle's attitude through the full camera-to-body mount rotation R_cam_body:

    up_cam = R_cam_body @ R_enu_body(q).T @ (0, 0, 1)

The mount rotation as installed and the accelerometer's residual tilt are one fixed tilt of 'up' in the
camera (1 deg = ~111 km on every fix; the stars alone do not show it). While a reference position exists
(GPS before it is lost, the phone in a field test), fixes measure it: TiltCalibration learns it on the
first CAL_SAMPLES of them, then freezes it, and every later fix is corrected (R @ (Q @ up)).
"""
import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

# 'up' from the camera's accelerometer, 6-position calibrated, mount to the lenses not yet measured: the stated
# accuracy keeps a margin until the stars calibrate it (field server, ATTITUDE_SIGMA_360_DEG)
ATTITUDE_SIGMA_360_DEG = 0.3
# vehicle moving: 'up' may hold its acceleration (0.1 g of braking or curve = ~6 deg); see the field server's notes
MOVING_ATTITUDE_SIGMA_DEG = 5.0
CAL_MIN_SAMPLES = 4               # fixes before the tilt is first fitted
CAL_SAMPLES = 12                  # fixes the tilt is learned on, then frozen
CAL_SIGMA_FLOOR_DEG = 0.05
KM_PER_DEG = 111.2
SKY_KM_PER_SECOND = 0.4625        # the sky turns 15 arcsec/s: 0.46 km per second of clock error (field analyze.py)

# camera standing on a level vehicle (the field set-up): camera +x = body up, +y = body left, +z = body back
R_CAM_BODY_STANDING = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])


def rotvec(w) -> np.ndarray:
    """Rotation matrix of a rotation vector (rad), Rodrigues."""
    w = np.asarray(w, float)
    t = float(np.linalg.norm(w))
    if t < 1e-15:
        return np.eye(3)
    a = w / t
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def zenith_icrs(lat: float, lon: float, utc: str) -> np.ndarray:
    """Unit vector (ICRS, J2000) of the point overhead at (lat, lon) and utc."""
    import astropy.units as u
    from astropy.coordinates import TETE, SkyCoord
    from cn_pkg.nodes.celestial_math import gast_deg, obs_time
    t = obs_time(utc)
    c = SkyCoord(ra=((gast_deg(utc) + lon) % 360.0) * u.deg, dec=lat * u.deg, frame=TETE(obstime=t)).icrs
    ra, dec = math.radians(c.ra.deg), math.radians(c.dec.deg)
    return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


def position(z_icrs, utc: str) -> Tuple[float, float]:
    """(lat, lon) of the observer whose zenith is z_icrs (ICRS unit vector) at utc."""
    from cn_pkg.nodes.celestial_math import apparent_radec, gast_deg
    z = np.asarray(z_icrs, float) / np.linalg.norm(z_icrs)
    ra, dec = math.degrees(math.atan2(z[1], z[0])) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, z[2]))))
    ra_a, dec_a = apparent_radec(ra, dec, utc)
    return dec_a, (ra_a - gast_deg(utc) + 540.0) % 360.0 - 180.0


def fit_mount(samples) -> np.ndarray:
    """Rotation vector (rad) Q with R (Q up) closest to the true zenith over the samples [(R, up, z_true)].
    A turn about 'up' itself does not move 'up' and cannot be measured: Q is fitted as a tilt only (rotation
    axis perpendicular to the mean 'up'), so its angle is the mounting tilt (before, the free turn about 'up'
    came out as tens of degrees: a 1 deg simulated mount was reported as 56 deg)."""
    from scipy.optimize import least_squares
    u = np.mean([up / np.linalg.norm(up) for _, up, _ in samples], axis=0)
    u /= np.linalg.norm(u)
    e1 = np.cross(u, [1.0, 0, 0] if abs(u[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u, e1)

    def res(p):
        Q = rotvec(p[0] * e1 + p[1] * e2)
        return np.concatenate([np.asarray(R) @ (Q @ up) - z for R, up, z in samples])
    p = least_squares(res, np.zeros(2)).x
    return p[0] * e1 + p[1] * e2


def fit_tilt(samples, sigma_floor_deg: float = CAL_SIGMA_FLOOR_DEG) -> dict:
    """The tilt of 'up' fitted on [(R_icrs_imu, up, true zenith)]: {'w' rotation vector (rad), 'Q', 'n',
    'rms_deg' (residual, corrected for the 2 fitted parameters), 'sigma_deg' (rms, at least the floor)}."""
    w = fit_mount(samples)
    Q = rotvec(w)
    res = [math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(Rk @ (Q @ u) / np.linalg.norm(u), z))))))
           for Rk, u, z in samples]
    n = len(res)
    rms = math.sqrt(sum(x * x for x in res) / n) * math.sqrt(n / max(n - 2, 1))
    return {"w": w, "Q": Q, "n": n, "rms_deg": rms, "sigma_deg": max(rms, sigma_floor_deg)}


def stated_sigma_km(base_deg: float, sigma_fit_deg: Optional[float], moving: bool = False,
                    clock_err_s: float = 0.0, moving_deg: float = MOVING_ATTITUDE_SIGMA_DEG) -> float:
    """1-sigma horizontal accuracy (km) of a 360 fix: the attitude of 'up' (base_deg), the star fit and, while the
    vehicle moves, its acceleration in 'up' add in quadrature; a clock error adds the sky's turn."""
    att = math.hypot(base_deg, sigma_fit_deg or 0.0)
    if moving:
        att = math.hypot(att, moving_deg)
    return att * KM_PER_DEG + abs(clock_err_s) * SKY_KM_PER_SECOND


def rotation_matrix(values: Sequence[float]) -> np.ndarray:
    """A proper rotation from 9 row-major values (the nearest one by SVD: a matrix typed to 4 decimals is
    re-orthonormalised). Raises ValueError for anything that is not close to a rotation."""
    M = np.asarray(values, float).reshape(3, 3)
    U, s, Vt = np.linalg.svd(M)
    R = U @ Vt
    if np.linalg.det(R) < 0 or np.max(np.abs(s - 1.0)) > 0.01:
        raise ValueError(f"not a rotation matrix: {list(values)}")
    return R


def quat_to_matrix(q_xyzw) -> np.ndarray:
    """R_enu_body of a sensor_msgs/Imu orientation (x, y, z, w): body vector → ENU vector."""
    x, y, z, w = (float(v) for v in q_xyzw)
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if not n > 0:
        raise ValueError("invalid quaternion")
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def up_camera_from_body(q_xyzw, R_cam_body: np.ndarray) -> np.ndarray:
    """'up' (unit) in the camera frame from the vehicle's orientation and the camera-to-body mount rotation."""
    up_body = quat_to_matrix(q_xyzw).T @ np.array([0.0, 0.0, 1.0])
    v = np.asarray(R_cam_body, float) @ up_body
    return v / np.linalg.norm(v)


class TiltCalibration:
    """The tilt of 'up' learned on fixes taken with a reference position, then frozen (see the module doc)."""

    def __init__(self, min_samples: int = CAL_MIN_SAMPLES, max_samples: int = CAL_SAMPLES,
                 sigma_floor_deg: float = CAL_SIGMA_FLOOR_DEG):
        self.min_samples, self.max_samples, self.sigma_floor_deg = int(min_samples), int(max_samples), sigma_floor_deg
        self.samples: List[tuple] = []
        self.fit: Optional[dict] = None

    @property
    def frozen(self) -> bool:
        return len(self.samples) >= self.max_samples

    def add(self, R_icrs_imu, up, z_true) -> Optional[dict]:
        """Take one fix as a sample (ignored once frozen); returns the new fit when one was made."""
        if self.frozen:
            return None
        self.samples.append((np.asarray(R_icrs_imu, float), np.asarray(up, float), np.asarray(z_true, float)))
        if len(self.samples) < self.min_samples:
            return None
        self.fit = fit_tilt(self.samples, self.sigma_floor_deg)
        return self.fit

    def corrected(self, R_icrs_imu, up, utc: str) -> Optional[Tuple[float, float]]:
        """(lat, lon) with the learned tilt removed, or None before the first fit."""
        if self.fit is None:
            return None
        return position(np.asarray(R_icrs_imu, float) @ (self.fit["Q"] @ np.asarray(up, float)), utc)

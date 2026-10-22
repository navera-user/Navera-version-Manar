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
first CAL_SAMPLES of them, then freezes it, and every later fix is corrected (R @ (Q @ up)). The fit is robust
(D11): a sample that disagrees with the others is left out and does not count, and a fit without a clear
majority is not applied (fit_tilt).
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
    from cn_pkg.nodes.celestial_math import zenith_position
    return zenith_position(z_icrs, utc)


def fit_mount(samples, loss: str = "linear", f_scale: float = 1.0) -> np.ndarray:
    """Rotation vector (rad) Q with R (Q up) closest to the true zenith over the samples [(R, up, z_true)].

    A turn about 'up' itself does not move 'up' and cannot be measured: Q is fitted as a tilt only (rotation
    axis perpendicular to the mean 'up'), so its angle is the mounting tilt (before, the free turn about 'up'
    came out as tens of degrees: a 1 deg simulated mount was reported as 56 deg). loss / f_scale: as in
    scipy's least_squares (fit_tilt uses a robust loss first, then a plain fit on the samples it keeps).
    """
    from scipy.optimize import least_squares
    u = np.mean([up / np.linalg.norm(up) for _, up, _ in samples], axis=0)
    u /= np.linalg.norm(u)
    e1 = np.cross(u, [1.0, 0, 0] if abs(u[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u, e1)

    def res(p):
        Q = rotvec(p[0] * e1 + p[1] * e2)
        return np.concatenate([np.asarray(R) @ (Q @ up) - z for R, up, z in samples])
    p = least_squares(res, np.zeros(2), loss=loss, f_scale=f_scale).x
    return p[0] * e1 + p[1] * e2


# Outlier rejection of the tilt fit (D11). A good sample's residual is the star fit + 'up' noise: 0.05-0.1 deg
# (simulation and the real screen bench). A bad one (a 'stopped' frame taken while the car moved gently, a stale
# or wrong reference position, a wrong star identification) is off by 0.3-10 deg. A sample is kept when its
# residual is within OUTLIER_K robust sigmas (1.4826 x median), never rejected below OUTLIER_MIN_DEG and never kept
# above OUTLIER_MAX_DEG (with half the samples bad the median itself is pulled: 2 bad of 4 kept all four); the fit
# is trusted (ok) only when a strict majority of the samples, and at least CAL_MIN_INLIERS, agree on a tilt no
# larger than CAL_MAX_TILT_DEG (a camera standing on its mount is within ~2 deg; more is a wrong set-up).
OUTLIER_K = 3.5
OUTLIER_MIN_DEG = 0.3
OUTLIER_MAX_DEG = 1.0
CAL_MIN_INLIERS = 3
CAL_MAX_TILT_DEG = 5.0
ROBUST_F_SCALE = math.radians(0.2)


def _residuals_deg(samples, Q) -> np.ndarray:
    return np.array([math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(np.asarray(Rk) @ (Q @ u)
                                                                            / np.linalg.norm(u), z))))))
                     for Rk, u, z in samples])


def fit_tilt(samples, sigma_floor_deg: float = CAL_SIGMA_FLOOR_DEG, robust: bool = True) -> dict:
    """The tilt of 'up' fitted on [(R_icrs_imu, up, true zenith)].

    Returns {'w' rotation vector (rad), 'Q', 'n' (samples the fit uses), 'n_total', 'rejected' (indices of the
    samples left out as outliers), 'residuals_deg' (every sample against the final fit), 'rms_deg' (residual of
    the kept samples, corrected for the 2 fitted parameters), 'sigma_deg' (rms, at least the floor), 'ok' (the
    fit may be applied: a clear majority agrees and the tilt is plausible), 'why' (when not ok)}.
    robust=False: the plain fit on every sample (the behaviour before outlier rejection).
    """
    samples = list(samples)
    n_total = len(samples)
    keep = np.ones(n_total, bool)
    if robust and n_total >= CAL_MIN_INLIERS + 1:
        w = fit_mount(samples, loss="soft_l1", f_scale=ROBUST_F_SCALE)
        for _ in range(3):
            res = _residuals_deg(samples, rotvec(w))
            scale = 1.4826 * float(np.median(res[keep])) if keep.any() else 0.0
            new = res <= min(max(OUTLIER_K * scale, OUTLIER_MIN_DEG), OUTLIER_MAX_DEG)
            if new.sum() < 2:
                new = res <= np.sort(res)[1]
            changed = not np.array_equal(new, keep)
            keep = new
            w = fit_mount([s for s, k in zip(samples, keep) if k])
            if not changed:
                break
    else:
        w = fit_mount(samples)
    Q = rotvec(w)
    res_all = _residuals_deg(samples, Q)
    res = res_all[keep]
    n = int(keep.sum())
    rms = math.sqrt(float(np.sum(res ** 2)) / n) * math.sqrt(n / max(n - 2, 1))
    tilt = math.degrees(float(np.linalg.norm(w)))
    why = None
    if robust and n < CAL_MIN_INLIERS:
        why = f"only {n} samples agree (< {CAL_MIN_INLIERS})"
    elif robust and n * 2 <= n_total:
        why = f"no clear majority: {n} of {n_total} samples agree"
    elif tilt > CAL_MAX_TILT_DEG:
        why = f"tilt {tilt:.1f} deg (> {CAL_MAX_TILT_DEG}): not a mounting error"
    return {"w": w, "Q": Q, "n": n, "n_total": n_total, "rejected": [int(i) for i in np.nonzero(~keep)[0]],
            "residuals_deg": [round(float(r), 4) for r in res_all], "rms_deg": rms,
            "sigma_deg": max(rms, sigma_floor_deg), "ok": why is None, "why": why}


def stated_sigma_km(base_deg: float, sigma_fit_deg: Optional[float], moving: bool = False,
                    clock_err_s: float = 0.0, moving_deg: float = MOVING_ATTITUDE_SIGMA_DEG) -> float:
    """1-sigma horizontal accuracy (km) of a 360 fix: the attitude of 'up' (base_deg), the star fit and, while the
    vehicle moves, its acceleration in 'up' add in quadrature; a clock error adds the sky's turn.
    """
    att = math.hypot(base_deg, sigma_fit_deg or 0.0)
    if moving:
        att = math.hypot(att, moving_deg)
    return att * KM_PER_DEG + abs(clock_err_s) * SKY_KM_PER_SECOND


def rotation_matrix(values: Sequence[float]) -> np.ndarray:
    """A proper rotation from 9 row-major values (the nearest one by SVD: a matrix typed to 4 decimals is
    re-orthonormalised). Raises ValueError for anything that is not close to a rotation.
    """
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
    """The tilt of 'up' learned on fixes taken with a reference position, then frozen (see the module doc).

    Samples are kept until max_samples of them agree with the fit (outliers, D11, are left out of it and do not
    count), or 2 x max_samples were taken; then the calibration is frozen. A fit is applied only while it is ok
    (fit_tilt: a clear majority of the samples agree on a plausible tilt).
    """

    def __init__(self, min_samples: int = CAL_MIN_SAMPLES, max_samples: int = CAL_SAMPLES,
                 sigma_floor_deg: float = CAL_SIGMA_FLOOR_DEG):
        self.min_samples, self.max_samples, self.sigma_floor_deg = int(min_samples), int(max_samples), sigma_floor_deg
        self.samples: List[tuple] = []
        self.fit: Optional[dict] = None          # the fit applied (ok), None before the first good one
        self.last_fit: Optional[dict] = None     # the latest fit made, ok or not (diagnostics)

    @property
    def frozen(self) -> bool:
        inliers = self.fit["n"] if self.fit is not None else 0
        return inliers >= self.max_samples or len(self.samples) >= 2 * self.max_samples

    def add(self, R_icrs_imu, up, z_true) -> Optional[dict]:
        """Take one fix as a sample (ignored once frozen); returns the new fit when one was made (ok or not)."""
        if self.frozen:
            return None
        self.samples.append((np.asarray(R_icrs_imu, float), np.asarray(up, float), np.asarray(z_true, float)))
        if len(self.samples) < self.min_samples:
            return None
        fit = fit_tilt(self.samples, self.sigma_floor_deg)
        self.last_fit = fit
        if fit["ok"]:
            self.fit = fit
        return fit

    def corrected(self, R_icrs_imu, up, utc: str) -> Optional[Tuple[float, float]]:
        """(lat, lon) with the learned tilt removed, or None before the first good fit."""
        if self.fit is None:
            return None
        return position(np.asarray(R_icrs_imu, float) @ (self.fit["Q"] @ np.asarray(up, float)), utc)

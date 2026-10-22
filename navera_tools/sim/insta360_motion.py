"""Synthetic vehicle motion seen by the Insta360's IMU, with the true attitude — for testing the
Insta360 kit's attitude filter (camera_pkg.insta360_attitude). SIMULATION: kinematics only.

    simulate(profile, seconds, hz=500, seed=0, noise=None) -> Motion

A profile gives the ground speed and the turn rate in time; the vehicle model gives the attitude:
  uav      fixed wing: nose along the track, coordinated turns (bank = atan(V w / g): the
           accelerometer then reads 'up' along the body z axis: the classic trap), pitch from the
           along-track acceleration, light turbulence
  copter   multirotor: thrust tilted to make the horizontal acceleration and overcome drag
  car      level body, suspension roll / pitch from the accelerations, road vibration
The IMU sees the exact kinematics: specific force f = R^T (a_world + g z) and the body rate from
consecutive attitudes; noise is either Gaussian with the measured densities (gyro 0.085 deg/s and
accel 0.002 g per 500 Hz sample, bias random walk) or a REAL recording at rest (its residuals
replayed: rows minus their mean, the real noise spectrum including the camera's own vibration).
"""
import math
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

G = 9.80665


@dataclass
class Motion:
    t: np.ndarray            # s
    R: np.ndarray            # (N, 3, 3) body FLU -> world ENU, true
    w: np.ndarray            # (N, 3) body rate rad/s (with noise and bias)
    f: np.ndarray            # (N, 3) specific force m/s^2 (with noise)
    speed: np.ndarray        # (N,) ground speed m/s, true
    accel_fwd: np.ndarray    # (N,) along-track acceleration m/s^2, true
    east: np.ndarray         # (N,) m
    north: np.ndarray        # (N,) m
    heading: np.ndarray      # (N,) deg from north, true (of the nose)


def _rz(a):
    c, s = np.cos(a), np.sin(a)
    z, o = np.zeros_like(a), np.ones_like(a)
    return np.stack([np.stack([c, -s, z], -1), np.stack([s, c, z], -1), np.stack([z, z, o], -1)], -2)


def _ry(a):
    c, s = np.cos(a), np.sin(a)
    z, o = np.zeros_like(a), np.ones_like(a)
    return np.stack([np.stack([c, z, s], -1), np.stack([z, o, z], -1), np.stack([-s, z, c], -1)], -2)


def _rx(a):
    c, s = np.cos(a), np.sin(a)
    z, o = np.zeros_like(a), np.ones_like(a)
    return np.stack([np.stack([o, z, z], -1), np.stack([z, c, -s], -1), np.stack([z, s, c], -1)], -2)


def _log(R):
    """Rotation vectors of a stack of rotation matrices."""
    c = np.clip((np.trace(R, axis1=-2, axis2=-1) - 1.0) / 2.0, -1.0, 1.0)
    th = np.arccos(c)
    v = np.stack([R[..., 2, 1] - R[..., 1, 2], R[..., 0, 2] - R[..., 2, 0], R[..., 1, 0] - R[..., 0, 1]], -1)
    s = np.where(th > 1e-9, th / (2.0 * np.maximum(np.sin(th), 1e-12)), 0.5)
    return v * s[..., None]


def _smooth_steps(t, times, values, ramp_s):
    """A piecewise-constant signal (values from each time on) with ramps of ramp_s (smooth)."""
    out = np.full_like(t, float(values[0]))
    for k in range(1, len(times)):
        x = np.clip((t - times[k]) / ramp_s, 0.0, 1.0)
        out += (values[k] - values[k - 1]) * (3 * x ** 2 - 2 * x ** 3)
    return out


PROFILES = {
    # (times s, speeds m/s), (times s, turn rates deg/s), vehicle
    "uav_survey": (([0, 5], [28, 30]), ([0, 40, 70, 110, 140, 180, 200, 240], [0, 3, 0, -3, 0, 6, 0, -2]), "uav"),
    "uav_steep": (([0, 5], [25, 32]), ([0, 20, 50, 80, 110, 140], [0, 10, 0, -12, 0, 8]), "uav"),
    "copter": (([0, 10, 25, 40, 60, 75, 95], [0, 12, 12, 4, 15, 0, 8]),
               ([0, 30, 45, 80, 100], [0, 8, 0, -10, 0]), "copter"),
    "car": (([0, 10, 30, 45, 60, 80, 95, 110], [0, 15, 15, 0, 0, 20, 8, 0]),
            ([0, 15, 25, 50, 70, 85, 100], [0, 12, 0, -15, 0, 20, 0]), "car"),
    "still": (([0], [0]), ([0], [0]), "car"),
}


def simulate(profile: str, seconds: float, hz: float = 500.0, seed: int = 0, noise: Optional[np.ndarray] = None,
             heading0_deg: float = 30.0, gyro_bias_dps=(0.02, -0.03, 0.04), bias_walk_dps_rts: float = 0.002,
             gauss_gyro_dps: float = 0.085, gauss_accel_g: float = 0.002, vibration_g: float = 0.0,
             speed_fn: Optional[Callable] = None, turn_fn: Optional[Callable] = None,
             vehicle: Optional[str] = None) -> Motion:
    """noise: real residuals (M, 6) = accel g x3, gyro rad/s x3 in the BODY frame at hz (tiled), or
    None for Gaussian noise. gyro_bias_dps: a constant bias left after the bias at rest (body
    axes), plus a random walk. speed_fn / turn_fn / vehicle override the profile."""
    rng = np.random.default_rng(seed)
    (st, sv), (tt, tv), veh = PROFILES[profile]
    veh = vehicle or veh
    t = np.arange(0.0, seconds, 1.0 / hz)
    speed = speed_fn(t) if speed_fn else _smooth_steps(t, st, sv, 6.0)
    turn = np.radians(turn_fn(t) if turn_fn else _smooth_steps(t, tt, tv, 4.0))       # rad/s, clockwise
    dt = 1.0 / hz
    heading = math.radians(heading0_deg) + np.concatenate([[0.0], np.cumsum(0.5 * (turn[1:] + turn[:-1]) * dt)])
    accel_fwd = np.gradient(speed, dt)
    ve, vn = speed * np.sin(heading), speed * np.cos(heading)
    east = np.concatenate([[0.0], np.cumsum(0.5 * (ve[1:] + ve[:-1]) * dt)])
    north = np.concatenate([[0.0], np.cumsum(0.5 * (vn[1:] + vn[:-1]) * dt)])
    a_world = np.stack([np.gradient(ve, dt), np.gradient(vn, dt), np.zeros_like(t)], -1)
    yaw = math.pi / 2 - heading                                                      # ENU yaw of the nose
    lat_acc = speed * turn                                                           # to the right, m/s^2
    if veh == "uav":
        roll = np.arctan2(lat_acc, G)                                                # right wing down = +roll (FLU)
        pitch = -np.radians(2.0) - 0.02 * accel_fwd                                  # nose a little up
        roll = roll + np.radians(1.5) * np.sin(2 * np.pi * 0.31 * t) * (speed > 1)
        pitch = pitch + np.radians(1.0) * np.sin(2 * np.pi * 0.23 * t + 1.0) * (speed > 1)
        R = _rz(yaw) @ _ry(pitch) @ _rx(roll)
    elif veh == "copter":
        drag = 0.02 * speed * speed                                                  # m/s^2, against the motion
        ax = accel_fwd + drag                                                        # thrust's forward share
        pitch = np.arctan2(ax, G)                                                    # ROS: + = nose down
        roll = np.arctan2(lat_acc, G)
        R = _rz(yaw) @ _ry(pitch) @ _rx(roll)
    else:                                                                            # car
        roll = -np.radians(1.0) * lat_acc / G * 3.0
        pitch = np.radians(1.0) * accel_fwd / G * 3.0
        R = _rz(yaw) @ _ry(pitch) @ _rx(roll)
    f = np.einsum("nji,nj->ni", R, a_world + np.array([0.0, 0.0, G]))
    dR = np.einsum("nji,njk->nik", R[:-1], R[1:])                                    # R_k^T R_k+1
    w = _log(dR) * hz
    w = np.vstack([w, w[-1:]])
    n = len(t)
    if noise is not None:
        idx = np.arange(n) % len(noise)
        f = f + noise[idx, :3] * G
        w = w + noise[idx, 3:]
    else:
        f = f + rng.normal(0.0, gauss_accel_g * G, (n, 3))
        w = w + rng.normal(0.0, math.radians(gauss_gyro_dps), (n, 3))
    walk = np.cumsum(rng.normal(0.0, math.radians(bias_walk_dps_rts) * math.sqrt(dt), (n, 3)), axis=0)
    w = w + np.radians(np.asarray(gyro_bias_dps, float)) + walk
    if vibration_g > 0:
        f = f + vibration_g * G * np.sin(2 * np.pi * 37.0 * t)[:, None] * np.array([0.3, 0.3, 1.0])
    return Motion(t, R, w, f, speed, accel_fwd, east, north, np.degrees(heading) % 360.0)


def decimate(m: Motion, k: int = 5):
    """(t, w, f) means over k samples, as camera_pkg.insta360_imu.ImuStream publishes them."""
    n = len(m.t) // k * k
    return (m.t[:n].reshape(-1, k).mean(1), m.w[:n].reshape(-1, k, 3).mean(1), m.f[:n].reshape(-1, k, 3).mean(1))


def real_noise(rows: np.ndarray, R_body_cam: np.ndarray) -> np.ndarray:
    """Residuals of a recording at rest (camera_pkg.insta360_imu.raw_imu_rows: ms, accel g, gyro
    rad/s in the camera frame) in the body frame: (M, 6) accel g, gyro rad/s, means removed."""
    a = rows[:, 1:4] - rows[:, 1:4].mean(0)
    w = rows[:, 4:7] - rows[:, 4:7].mean(0)
    return np.hstack([a @ R_body_cam.T, w @ R_body_cam.T])


def tilt_error_deg(R_true: np.ndarray, R_est: np.ndarray) -> float:
    """Angle between the true and the estimated 'up' in the body frame (roll / pitch error, deg)."""
    u1, u2 = R_true[2, :], R_est[2, :]
    return math.degrees(math.acos(max(-1.0, min(1.0, float(u1 @ u2)))))

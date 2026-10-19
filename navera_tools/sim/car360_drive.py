#!/usr/bin/env python3
"""Car field-test rehearsal of the 360 celestial chain: a simulated drive (stops every 2-3 min)
through the REAL field server code. SIMULATION ONLY - synthetic IMU and synthetic sky.

    PYTHONPATH=.:cn_pkg:navera_common:navera_tools/sim python3 -m navera_tools.sim.car360_drive \
        [--profile normal] [--cycles 3] [--detector-only] [--json out.json]

What is real here: server.Field (its solve cadence, gates, stopped/moving flags, sigma, session files),
insta360_usb.Insta360Usb.stopped()/gravity() (the camera driver's own stillness and gravity code, fed
synthetic 500 Hz IMU rows), allsky.locate, report/reprocess360. What is simulated: the car (speed,
heading, braking, curves, gentle speed changes, suspension pitch/roll, road vibration 10-30 Hz, body
bounce, bumps, idle engine vibration at the stops), the camera on its mount (tilt, accelerometer
residual tilt error, noise), the video timing (key frames every 0.5 s, stamped 1.5 s late by the
camera and corrected by the driver, arriving 1.7 s after exposure) and the sky (Yale catalogue,
refraction, the measured lens model, as celestial360_conditions renders it).

--detector-only skips the sky: every key frame's stillness/gravity verdict is compared with the
true motion (fast; thousands of frames). The full run renders the frames the server asks for.
"""
import argparse
import collections
import json
import math
import os
import sys
import tempfile
import threading
import time as _time
import types
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg"), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.field import allsky, insta360_usb, server, store  # noqa: E402
from navera_tools.sim import celestial360_conditions as cc  # noqa: E402

G = 9.81
HZ = 500
DT = 1.0 / HZ
ARRIVAL_S = 1.7                  # measured: a frame reaches the server ~1.7 s after its exposure
KEYFRAME_S = 0.5                 # key frames only: ~2 per second
START_UTC = "2026-10-19 21:00:00"
LAT0, LON0 = 36.8, 10.2


@dataclass
class Profile:
    """One drive scenario."""
    name: str = "normal"
    cycles: int = 3
    drive_s: float = 150.0
    stop_s: float = 20.0
    road_vib_g: float = 0.03       # 10-30 Hz road vibration (rms, at 14 m/s; scales with speed)
    bounce_g: float = 0.02         # 1-2 Hz body bounce while moving (rms)
    idle_g: float = 0.02           # engine vibration at the stops (amplitude, all axes)
    idle_hz: float = 26.7          # 4-cylinder idle at 800 rpm: 26.7 Hz firing
    ang_vib_deg: float = 0.005     # 10-30 Hz angular jitter of the camera on its mount (rms, always)
    body_ang_deg: float = 0.1      # 1-3 Hz body pitch/roll oscillation while moving (rms)
    bumps_per_min: float = 4.0
    gentle: bool = True            # gentle 0.02-0.05 g speed changes while cruising
    cruise_mps: float = 14.0
    mount_tilt_deg: float = 2.0    # camera standing on its mount, not perfectly upright
    slope_deg: float = 0.0         # road grade (car pitch) everywhere
    imu_err_deg: float = 0.07      # accelerometer residual 'up' error at rest (measured 0.06-0.08)
    acc_noise_g: float = 0.002     # per sample (6-position calibration: 0.001-0.006)
    gyro_noise_dps: float = 0.17   # per sample
    imu_gap: Optional[tuple] = None  # (start_s, duration_s) of IMU silence
    stamp_err_ms: float = 0.0      # true frame-stamp lag minus the driver's FRAME_STAMP_LAG_MS
    limit_mag: float = 3.0
    seed: int = 1


PROFILES = {
    "normal": Profile(),
    "rough": Profile("rough", road_vib_g=0.05, bounce_g=0.04, idle_g=0.05, bumps_per_min=8),
    "smooth": Profile("smooth", road_vib_g=0.01, bounce_g=0.002, idle_g=0.01, bumps_per_min=0),
    "glass": Profile("glass", road_vib_g=0.003, bounce_g=0.001, idle_g=0.005, bumps_per_min=0, ang_vib_deg=0.002,
                     body_ang_deg=0.01),
    "idle15hz": Profile("idle15hz", idle_g=0.03, idle_hz=15.0),
    "idle_strong": Profile("idle_strong", idle_g=0.05),
    "angvib0.02": Profile("angvib0.02", ang_vib_deg=0.02),
    "no_gentle": Profile("no_gentle", gentle=False),
    "slope8": Profile("slope8", slope_deg=8.0),
    "imu_gap": Profile("imu_gap", imu_gap=(148.0, 6.0)),
    "imu_gap_stop": Profile("imu_gap_stop", imu_gap=(176.0, 3.6)),    # silent through the last braking (stop at 178.2)
    "stamp+300ms": Profile("stamp+300ms", stamp_err_ms=300.0),
    "stamp-300ms": Profile("stamp-300ms", stamp_err_ms=-300.0),
}


# ── the car ──────────────────────────────────────────────────────────────
def lowpass(x, tau):
    a = DT / (tau + DT)
    y = np.empty_like(x)
    acc = x[0]
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def second_order(target, f_hz=1.3, zeta=0.35):
    """Suspension: pitch/roll follow their steady value with a damped 1.3 Hz oscillation."""
    w = 2 * math.pi * f_hz
    y, v = 0.0, 0.0
    out = np.empty_like(target)
    for i, t in enumerate(target):
        acc = -2 * zeta * w * v - w * w * (y - t)
        v += acc * DT
        y += v * DT
        out[i] = y
    return out


def band_noise(rng, n, lo, hi, rms):
    """Gaussian noise band-limited to lo-hi Hz with the given rms."""
    if rms <= 0:
        return np.zeros(n)
    spec = np.fft.rfft(rng.normal(size=n))
    f = np.fft.rfftfreq(n, DT)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return x * rms / (x.std() + 1e-12)


def drive(p: Profile):
    """Arrays at 500 Hz: t, v, a_long (g), a_lat (g), yaw, pitch, roll (rad), x, y (m), moving, at_rest, phase."""
    rng = np.random.default_rng(p.seed)
    st = {"v": 0.0, "a": 0.0, "yr": 0.0}
    V, A, YR, PH = [], [], [], []
    ka, ky = DT / (0.25 + DT), DT / (0.6 + DT)          # jerk limit (0.25 s) and steering (0.6 s) lags

    def step(a_cmd, yr_cmd, ph):
        st["a"] += ka * (a_cmd - st["a"])
        st["yr"] += ky * (yr_cmd - st["yr"])
        a = st["a"]
        if st["v"] <= 0.0 and a <= 0.0:
            a, st["v"] = 0.0, 0.0
        nv = st["v"] + a * G * DT
        if nv < 0.0:
            a, nv = -st["v"] / (G * DT), 0.0
            st["a"] = 0.0                                # stopped: the brake no longer decelerates anything
        st["v"] = nv
        V.append(nv), A.append(a), YR.append(st["yr"] if nv > 0.5 else 0.0), PH.append(ph)

    def emit(a_g, yawrate, dur, ph):
        for _ in range(int(round(dur * HZ))):
            step(a_g, yawrate, ph)

    emit(0.0, 0.0, 25.0, "stop")                         # parked at the start
    for c in range(p.cycles):
        t0 = len(V) * DT
        a_acc = rng.uniform(0.15, 0.3)
        vc = p.cruise_mps * rng.uniform(0.8, 1.2)
        while st["v"] < vc:
            step(a_acc, 0.0, "accel")
        a_brk = rng.uniform(0.1, 0.3)
        while len(V) * DT - t0 < p.drive_s - 20:
            emit(0.0, 0.0, rng.uniform(3, 10), "cruise")
            kind = rng.choice(["curve", "gentle", "brake_corner"] if p.gentle else ["curve", "brake_corner"],
                              p=[0.5, 0.35, 0.15] if p.gentle else [0.7, 0.3])
            dur = rng.uniform(3, 9)
            if kind == "curve":
                emit(0.0, rng.uniform(0.05, 0.3) * rng.choice([-1, 1]) * G / max(st["v"], 3.0), dur, "curve")
            elif kind == "gentle":
                emit(rng.uniform(0.02, 0.05) * rng.choice([-1, 1]) * (1 if st["v"] < 1.4 * vc else -1), 0.0, dur, "gentle")
            else:
                emit(-0.1, 0.0, 2.5, "brake")
                emit(0.1, 0.0, 2.5, "accel")
        while st["v"] > 0.0:
            step(-a_brk, 0.0, "brake")
        emit(0.0, 0.0, p.stop_s, "stop")
    vel, a_long, yawrate, phase = np.array(V), np.array(A), np.array(YR), np.array(PH)
    n = len(vel)
    a_long = lowpass(a_long, 0.05)                       # tyres/suspension soften the stop jerk a little
    a_lat = yawrate * vel / G
    yaw = np.cumsum(yawrate) * DT + rng.uniform(0, 2 * math.pi)
    pitch = np.radians(second_order(-2.5 * a_long) + p.slope_deg)     # 2.5 deg/g of dive/squat
    roll = np.radians(second_order(5.0 * a_lat))                       # 5 deg/g in curves
    moving = vel > 0.0
    t = np.arange(n) * DT
    x = np.cumsum(vel * np.sin(yaw)) * DT
    y = np.cumsum(vel * np.cos(yaw)) * DT
    # at rest: stopped AND the suspension settled - the moment a trusted fix may be taken
    prate = np.abs(np.gradient(np.degrees(pitch), DT))
    at_rest = (~moving) & (prate < 0.2)
    return dict(t=t, v=vel, a_long=a_long, a_lat=a_lat, yaw=yaw, pitch=pitch, roll=roll, x=x, y=y,
                moving=moving, at_rest=at_rest, phase=phase)


def rot(axis, ang):
    return cc.rot(axis, math.degrees(ang))


def imu_stream(p: Profile, car: dict):
    """(R_world_imu (N,3,3), accelerometer (N,3) g, gyro (N,3) rad/s) with vibration and sensor errors."""
    rng = np.random.default_rng(p.seed + 100)
    n = len(car["t"])
    yaw, pitch, roll = car["yaw"], car["pitch"], car["roll"]
    speed_f = np.clip(car["v"] / 14.0, 0, 1.5)
    moving = car["moving"]
    # vibration (world frame, g): road 10-30 Hz, body bounce 1-2 Hz, bumps, idle engine at the stops
    vib = np.zeros((n, 3))
    for k, s in ((0, 0.35), (1, 0.35), (2, 1.0)):
        vib[:, k] += s * speed_f * band_noise(rng, n, 10, 30, p.road_vib_g)
        vib[:, k] += s * moving * band_noise(rng, n, 1, 2, p.bounce_g)
    nb = int(p.bumps_per_min * car["t"][-1] / 60.0)
    for tb in rng.uniform(0, car["t"][-1], nb):
        i0 = int(tb * HZ)
        if not moving[i0]:
            continue
        k = np.arange(min(150, n - i0))
        vib[i0:i0 + len(k), 2] += rng.uniform(0.2, 0.5) * np.exp(-k * DT / 0.08) * np.sin(2 * math.pi * 8 * k * DT)
    tt = car["t"]
    idle = p.idle_g * (np.sin(2 * math.pi * p.idle_hz * tt) + 0.5 * np.sin(2 * math.pi * 2 * p.idle_hz * tt + 1.0))
    idle *= (1 + 0.2 * band_noise(rng, n, 0.1, 1.0, 1.0))
    for k, s in ((0, 0.4), (1, 0.4), (2, 1.0)):
        vib[:, k] += s * idle
    # small angular vibration (deg) from bounce/road
    pv = np.radians(p.body_ang_deg * moving * band_noise(rng, n, 1, 3, 1.0) + p.ang_vib_deg * band_noise(rng, n, 10, 30, 1.0))
    # body: x forward, y left, z up. R_world_body = Rz(yaw') Ry(pitch) Rx(roll) with yaw measured from north
    cy, sy = np.cos(yaw), np.sin(yaw)
    fwd = np.stack([sy, cy, np.zeros(n)], 1)
    left = np.stack([-cy, sy, np.zeros(n)], 1)
    upw = np.tile([0.0, 0.0, 1.0], (n, 1))
    Rb = np.stack([fwd, left, upw], axis=2)               # columns = body axes in world (ENU)
    cp, sp = np.cos(pitch + pv), np.sin(pitch + pv)
    cr, sr = np.cos(roll), np.sin(roll)
    Ry = np.zeros((n, 3, 3))
    Ry[:, 0, 0], Ry[:, 0, 2], Ry[:, 1, 1], Ry[:, 2, 0], Ry[:, 2, 2] = cp, -sp, 1, sp, cp    # nose down for +pitch
    Rx = np.zeros((n, 3, 3))
    Rx[:, 0, 0], Rx[:, 1, 1], Rx[:, 1, 2], Rx[:, 2, 1], Rx[:, 2, 2] = 1, cr, -sr, sr, cr
    R_wb = Rb @ Ry @ Rx
    # camera: IMU +x = body up, +y (left lens) = body forward rotated by a mount yaw, then a small mount tilt
    myaw = rng.uniform(0, 2 * math.pi)
    R_body_imu0 = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
    R_body_imu = rot([0, 0, 1], myaw) @ rot(rng.normal(size=3) * [1, 1, 0], math.radians(p.mount_tilt_deg)) @ R_body_imu0
    R_wi = R_wb @ R_body_imu
    a_world = np.zeros((n, 3))
    a_world += car["a_long"][:, None] * fwd + car["a_lat"][:, None] * left
    f_world = a_world + vib + upw                           # specific force in g
    acc = np.einsum("nji,nj->ni", R_wi, f_world)           # R^T f
    err_axis = np.cross([1.0, 0, 0], rng.normal(size=3))
    acc = acc @ rot(err_axis, math.radians(p.imu_err_deg)).T
    acc += rng.normal(0, p.acc_noise_g, acc.shape)
    dR = np.einsum("nji,njk->nik", R_wi[:-1], R_wi[1:])     # R_k^T R_k+1
    w = np.stack([dR[:, 2, 1] - dR[:, 1, 2], dR[:, 0, 2] - dR[:, 2, 0], dR[:, 1, 0] - dR[:, 0, 1]], 1) / (2 * DT)
    gyro = np.vstack([w, w[-1:]]) + rng.normal(0, math.radians(p.gyro_noise_dps), (n, 3))
    return R_wi, acc, gyro


# ── the camera driver, fed synthetic rows ────────────────────────────────
class Clock:
    def __init__(self, t0):
        self.t = t0

    def module(self):
        m = types.SimpleNamespace(**{k: getattr(_time, k) for k in dir(_time) if not k.startswith("_")})
        m.time = lambda: self.t
        m.sleep = lambda s: setattr(self, "t", self.t + s)
        return m


def fake_driver():
    d = insta360_usb.Insta360Usb.__new__(insta360_usb.Insta360Usb)
    d._lock = threading.Lock()
    d._imu = collections.deque(maxlen=3500)
    d.acc_bias, d.acc_scale, d.gyro_bias = np.zeros(3), np.ones(3), np.zeros(3)
    d.max_rate = math.radians(3.0)
    d._imu_t = 0.0
    d.error = None
    return d


class SimCamera360:
    """server.Camera360's interface over the fake driver and rendered frames."""
    device, cal_path, hfov, latency_s = "simulated insta360 (car)", "none", None, 1.71

    def __init__(self, sim):
        self.sim, self.cam, self.error, self.frame_ms = sim, fake_driver(), None, None

    def latest(self):
        fr = self.sim.newest_frame()
        if fr is None:
            return None, 0.0
        t_exp, img = fr
        self.frame_ms = (t_exp - self.sim.t0) * 1000.0 + self.sim.p.stamp_err_ms   # driver-corrected stamp
        return img, t_exp + ARRIVAL_S - self.latency_s

    def gravity(self, at_frame=False):
        return self.cam.gravity(at_ms=self.frame_ms) if at_frame and self.frame_ms is not None else self.cam.gravity()

    def stopped(self, at_frame=False):
        return self.cam.stopped(at_ms=self.frame_ms) if at_frame and self.frame_ms is not None else self.cam.stopped()


class Sim:
    def __init__(self, p: Profile, render=True):
        self.p = p
        self.car = drive(p)
        self.R_wi, self.acc, self.gyro = imu_stream(p, self.car)
        self.t0 = datetime.strptime(START_UTC, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        self.n = len(self.car["t"])
        self.fed = 0
        self.render = render
        self.rng = np.random.default_rng(p.seed + 7)
        self.exposures = np.arange(0.0, self.car["t"][-1] - 0.1, KEYFRAME_S) + self.rng.uniform(0, 0.05)
        self._cache = {}
        self._noise = None
        self._stars_cache = None

    def latlon(self, ts):
        i = min(int(ts * HZ), self.n - 1)
        return (LAT0 + self.car["y"][i] / 111200.0, LON0 + self.car["x"][i] / (111200.0 * math.cos(math.radians(LAT0))))

    def feed_imu(self, cam, t_sim):
        """Hand the driver every IMU row up to sim time t_sim (rows arrive with ~no delay), except in a gap."""
        k = min(self.n, int(t_sim * HZ))
        gap = self.p.imu_gap
        with cam._lock:
            for i in range(self.fed, k):
                ts = i * DT
                if gap and gap[0] <= ts < gap[0] + gap[1]:
                    continue
                cam._imu.append((self.t0 + ts, ts * 1000.0, *self.acc[i], *self.gyro[i]))
                cam._imu_t = self.t0 + ts
        self.fed = max(self.fed, k)

    def true_up(self, ts):
        i = min(int(ts * HZ), self.n - 1)
        return self.R_wi[i].T @ np.array([0.0, 0, 1])

    def newest_frame(self):
        now = CLOCK.t - self.t0
        k = np.searchsorted(self.exposures, now - ARRIVAL_S, side="right") - 1
        if k < 0:
            return None
        te = float(self.exposures[k])
        if k not in self._cache:
            self._cache = {k: self.render_frame(te) if self.render else np.zeros((1920, 3840), np.uint8)}
        return self.t0 + te, self._cache[k]

    def render_frame(self, te):
        """The standing camera's frame at exposure te (sim s): stars of the moment, blurred by the rotation in 1/30 s."""
        import astropy.units as u
        from astropy.coordinates import AltAz, EarthLocation, SkyCoord
        from astropy.time import Time
        from sky_view import load_bsc5
        if self._stars_cache is None:
            ra, dec, mag = load_bsc5(os.path.expanduser("~/.navera_sim"))
            keep = mag <= self.p.limit_mag
            self._stars_cache = (ra[keep], dec[keep], mag[keep])
        ra, dec, mag = self._stars_cache
        lat, lon = self.latlon(te)
        utc = datetime.fromtimestamp(self.t0 + te, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        aa = SkyCoord(ra=ra * u.deg, dec=dec * u.deg).transform_to(
            AltAz(obstime=Time(utc), location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg)))
        alt = aa.alt.deg + allsky.refraction_deg(aa.alt.deg)
        vis = alt > 0.5
        v = cc.enu(alt[vis], aa.az.deg[vis])
        m = mag[vis]
        if self._noise is None:
            self._noise = [self.rng.normal(10, 3, (1920, 3840)).astype(np.float32) for _ in range(3)]
        img = self._noise[int(te * 2) % 3].copy()
        lenses = server_lenses()
        i0 = int(te * HZ)
        K = 5
        for s in range(K):
            R = self.R_wi[min(self.n - 1, i0 - 8 + 4 * s)]          # +-1/60 s around the exposure
            v_imu = v @ R
            for L in lenses:
                x, y, th = L.project(v_imu @ L.R_lens_imu.T)
                ok = (th < math.radians(100)) & (np.hypot(x - L.cx, y - L.cy) < L.radius - 2) & (x > 5) & (x < 3834) & (y > 5) & (y < 1914)
                for xi, yi, mi in zip(x[ok], y[ok], m[ok]):
                    cc.add_psf(img, xi, yi, cc.star_amp(mi) / K)
        return np.clip(img, 0, 255).astype(np.uint8)


def server_lenses():
    from navera_tools.field import sky360
    return sky360.default_lenses()


CLOCK = Clock(0.0)


# ── detector-only: every key frame's verdict vs the truth ────────────────
def detector_only(p: Profile):
    sim = Sim(p, render=False)
    CLOCK.t = sim.t0
    insta360_usb.time = CLOCK.module()
    cam = SimCamera360(sim)
    rows = []
    for te in sim.exposures:
        t_arr = te + ARRIVAL_S
        if t_arr > sim.car["t"][-1]:
            break
        CLOCK.t = sim.t0 + t_arr
        sim.feed_imu(cam.cam, t_arr)
        cam.frame_ms = te * 1000.0 + p.stamp_err_ms
        st = cam.stopped(at_frame=True)
        up, g, rate = cam.gravity(at_frame=True)
        i = int(te * HZ)
        tu = sim.true_up(te)
        err = None if up is None else math.degrees(math.acos(max(-1.0, min(1.0, float(up @ tu)))))
        server_ok = up is not None and abs(g - 1.0) <= allsky.ACCEL_NORM_TOL
        rows.append({"te": round(float(te), 2), "phase": str(sim.car["phase"][i]), "moving": bool(sim.car["moving"][i]),
                     "at_rest": bool(sim.car["at_rest"][i]), "stopped": bool(st.get("stopped")),
                     "acc_std_g": st.get("acc_std_g"), "rate_dps": st.get("rate_dps"), "why": st.get("why"),
                     "server_ok": bool(server_ok), "up_err_deg": None if err is None else round(err, 3),
                     "a_long_g": round(float(sim.car["a_long"][i]), 3), "a_lat_g": round(float(sim.car["a_lat"][i]), 3)})
    return rows


def summarise_detector(rows):
    """Confusion of the stopped flag against the truth, and the 'up' errors that reach the solver."""
    def q(v, p_):
        return round(float(np.percentile(v, p_)), 3) if len(v) else None
    rest = [r for r in rows if r["at_rest"]]
    mov = [r for r in rows if r["moving"]]
    flagged = [r for r in rows if r["stopped"] and r["server_ok"]]
    bad_flag = [r for r in flagged if r["moving"]]
    st_err = [r["up_err_deg"] for r in flagged]
    mv_used = [r["up_err_deg"] for r in rows if r["server_ok"] and not r["stopped"]]
    return {"frames": len(rows), "at_rest": len(rest), "moving": len(mov),
            "rest_flagged_stopped": sum(r["stopped"] for r in rest),
            "rest_usable_stopped": sum(r["stopped"] and r["server_ok"] for r in rest),
            "moving_flagged_stopped": len(bad_flag),
            "moving_flagged_phases": dict(collections.Counter(r["phase"] for r in bad_flag)),
            "stopped_up_err_deg_p50_p90_max": [q(st_err, 50), q(st_err, 90), q(st_err, 100)],
            "stopped_up_err_over_0.3deg": sum(e > 0.3 for e in st_err),
            "moving_passed_gate": len(mv_used),
            "moving_up_err_deg_p50_p90_max": [q(mv_used, 50), q(mv_used, 90), q(mv_used, 100)],
            "moving_up_err_over_9deg": sum(e > 9.0 for e in mv_used)}


# ── full run through server.Field ────────────────────────────────────────
class QuietField(server.Field):
    """server.Field without its own loop thread: the harness calls the loop body on the simulated clock."""

    def _loop(self):
        return


def full_run(p: Profile, interval_s: float, keep_dir: Optional[str] = None):
    sim = Sim(p, render=True)
    CLOCK.t = sim.t0
    fake = CLOCK.module()
    server.time = store.time = insta360_usb.time = fake
    root = keep_dir or tempfile.mkdtemp(prefix="navera_car360_")
    cam = SimCamera360(sim)
    f = QuietField(root, cam)
    f.interval_s = interval_s
    solve_wall = []
    real_locate = allsky.locate

    def timed_locate(*a, **k):
        t0 = _time.time()
        try:
            return real_locate(*a, **k)
        finally:
            solve_wall.append(_time.time() - t0)
    allsky.locate = timed_locate

    def phone(ts):
        lat, lon = sim.latlon(ts)
        i = min(int(ts * HZ), sim.n - 1)
        f.on_phone({"lat": lat, "lon": lon, "acc": 5, "speed": float(sim.car["v"][i]), "phone_t_ms": int(CLOCK.t * 1000)})

    for k in range(4):
        CLOCK.t = sim.t0 + k * 0.3
        phone(k * 0.3)
    f.go(2), f.go(3), f.go(4)
    t_end = sim.car["t"][-1] - 0.5
    ts = 2.0
    from cn_pkg.star_detect import detect  # noqa: F401  (the loop body imports it)
    while ts < t_end:
        CLOCK.t = sim.t0 + ts
        sim.feed_imu(cam.cam, ts)
        phone(ts)
        img, texp = cam.latest()
        if img is not None:
            f._live360(img, texp)
            f._maybe_solve(img, texp)
        if f.solving:                                    # the solve runs in real time: the car goes on meanwhile
            t0 = _time.time()
            while f.solving:
                _time.sleep(0.02)
            ts += max(0.0, _time.time() - t0)
            continue
        ts += 1.0
    allsky.locate = real_locate
    sid = f.session.id
    f.finish()
    folder = os.path.join(root, sid)
    frames = store.read_jsonl(os.path.join(folder, "frames.jsonl"))
    out = []
    for fr in frames:
        if fr.get("mode") != "360":
            continue
        te = (fr.get("t_exp") or fr["t"]) - sim.t0
        i = min(int(max(te, 0) * HZ), sim.n - 1)
        row = {"idx": fr["idx"], "te": round(te, 1), "phase": str(sim.car["phase"][i]), "moving": bool(sim.car["moving"][i]),
               "at_rest": bool(sim.car["at_rest"][i]), "stopped": fr.get("stopped"), "solved": fr.get("solved"),
               "why": fr.get("why"), "sigma_km": fr.get("sigma_km"), "matched": fr.get("matched"), "solve_s": None}
        if fr.get("solved"):
            lat, lon = sim.latlon(te)
            from navera_tools.field.reprocess360 import haversine_km
            row["err_km"] = round(haversine_km(fr["lat"], fr["lon"], lat, lon), 1)
        out.append(row)
    for r, w in zip([r for r in out if r["solved"] is not None and (r["solved"] or (r["why"] or "").startswith(("rejected", "no star")))], solve_wall):
        r["solve_s"] = round(w, 2)
    return out, folder, solve_wall, sim


def summarise_full(rows, stops, solve_wall):
    def q(v, p_):
        return round(float(np.percentile(v, p_)), 1) if len(v) else None
    st = [r for r in rows if r["solved"] and r["stopped"]]
    mv = [r for r in rows if r["solved"] and not r["stopped"]]
    cover = lambda rs: sum(r["err_km"] <= 3 * r["sigma_km"] for r in rs)      # noqa: E731
    per_stop = []
    for a, b in stops:
        per_stop.append(sum(1 for r in st if a <= r["te"] <= b))
    return {"frames": len(rows), "solved": len(st) + len(mv),
            "stopped_fixes": len(st), "stopped_err_km_p50_p90_max": [q([r["err_km"] for r in st], p) for p in (50, 90, 100)],
            "stopped_within_3sigma": f"{cover(st)}/{len(st)}",
            "stopped_fix_while_moving": sum(r["moving"] for r in st),
            "moving_fixes": len(mv), "moving_err_km_p50_p90_max": [q([r["err_km"] for r in mv], p) for p in (50, 90, 100)],
            "moving_within_3sigma": f"{cover(mv)}/{len(mv)}",
            "stopped_fixes_per_stop": per_stop,
            "why_not": dict(collections.Counter((r["why"] or "").split("(")[0].strip()[:50] for r in rows if not r["solved"])),
            "solve_s_mean_max": [round(float(np.mean(solve_wall)), 2) if solve_wall else None,
                                 round(float(np.max(solve_wall)), 2) if solve_wall else None]}


def stop_windows(sim):
    st = ~sim.car["moving"]
    t = sim.car["t"]
    edges = np.flatnonzero(np.diff(st.astype(int)))
    starts = [0] + [e + 1 for e in edges if not st[e]]
    out = []
    for s in starts:
        e = s
        while e < len(st) and st[e]:
            e += 1
        if e > s:
            out.append((round(float(t[s]), 1), round(float(t[e - 1]), 1)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", default="normal", help=",".join(PROFILES))
    ap.add_argument("--cycles", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--detector-only", action="store_true")
    ap.add_argument("--interval", type=float, default=20.0, help="server solve interval (NAVERA_FIELD_INTERVAL_S)")
    ap.add_argument("--json", default="")
    ap.add_argument("--keep", default="", help="folder for the session files (default: a temp folder)")
    a = ap.parse_args()
    out = {}
    for name in a.profile.split(","):
        p = Profile(**{**asdict(PROFILES[name])})
        if a.cycles:
            p.cycles = a.cycles
        if a.seed is not None:
            p.seed = a.seed
        if a.detector_only:
            rows = detector_only(p)
            s = summarise_detector(rows)
            out[name] = {"summary": s, "rows": rows}
            print(f"SIMULATION ONLY  [{name}] detector:", json.dumps(s))
        else:
            rows, folder, wall, sim = full_run(p, a.interval, a.keep or None)
            s = summarise_full(rows, stop_windows(sim), wall)
            s["folder"] = folder
            s["stops"] = stop_windows(sim)
            out[name] = {"summary": s, "rows": rows}
            print(f"SIMULATION ONLY  [{name}] full:", json.dumps(s))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=float)


if __name__ == "__main__":
    main()

"""The Insta360 One R's own IMU (USB Android mode) as vehicle-body samples on the host clock.

Pure Python + numpy, no ROS: the node (camera_pkg.nodes.insta360_imu_node) and the tests use it.
The USB protocol and the raw recording reader are shared with the field tools
(navera_common.insta360_protocol), not copied.

Pipeline, per IMU packet (50 records, ~500 Hz, camera ms + accelerometer g + gyro rad/s):
  1. CameraClock maps the camera's ms clock to host time (time.time(), the clock every NAVERA
     frame is stamped with): offset = the smallest (host arrival - camera ms of the packet's LAST
     record) over a sliding window, i.e. the least-delayed packet (median USB delay measured
     ~20 ms above it, max ~90 ms). It follows a drift by at most slew_s_per_s and jumps on a
     clock step or a camera restart (camera ms going backwards).
  2. Calibration (load_imu_calibration: accelerometer bias/scale, gyro bias), then the gyro bias
     re-measured whenever the camera is at rest (BiasAtRest, as the field driver does): it moves
     with temperature by tens of mdeg/s per minute (measured below).
  3. Rotated into the vehicle body (mount_rotation: x forward, y left, z up, REP-103) and averaged
     over `decimation` records (the mean rate over the block keeps the integral exact).

Camera IMU frame (measured 2026-10-17, 6 static positions): +x up when the camera stands, +y the
LEFT fisheye circle's optical axis (the right circle looks along -y), +z = x cross y.

Measured at rest on the user's One R (2026-10-20, raw recordings 2026-10-20_1150 and
day_image_2026-10-20/raw40, 41 s and 40 s, camera standing on a table, 497.7 Hz), with
python3 -m camera_pkg.insta360_imu <raw folder or file>:
  gyro white noise  0.0025-0.0033 deg/s/rtHz (Allan deviation at 1 s over the longest quiet
                    stretch, 13 s and 20 s; per-sample std 0.069-0.085 deg/s at 500 Hz)
  gyro bias         Allan floor 0.0008-0.0026 deg/s within 13-20 s; then it creeps: 5 s means
                    up to 0.015 / 0.047 deg/s (worst axis) away from the first 2 s mean within
                    40 s; the turn-on bias differed by 0.19 deg/s between the two recordings
                    (about the vertical axis: -0.074 and -0.266 deg/s)
  accelerometer     per-sample std 0.0011-0.0020 g
Only 40 s of still data per recording: a longer still recording is needed for the bias beyond a
minute (in-run bias instability over a whole flight is NOT measured).
"""
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

import numpy as np

from navera_common.insta360_protocol import (
    CMD_START_LIVE, CMD_STOP_LIVE, EP_IN, EP_OUT, KIND_IMU, PKT_KEEPALIVE, PKT_SYNC, START_FULL, VENDOR,
    frame_packet, imu_records, load_imu_calibration, message_payload, read_raw, split_packets, stream_kind)

G = 9.80665                                   # m/s^2 per g
MEASURED_GYRO_SAMPLE_STD_DPS = 0.085          # per 500 Hz sample, worst axis at rest (module docstring)
MEASURED_ACCEL_SAMPLE_STD_G = 0.002
MEASURED_GYRO_NOISE_DPS_RTHZ = 0.0033         # worst axis, quiet stretches


# ── mounting ─────────────────────────────────────────────────────────────
def axes_matrix(axes: str) -> np.ndarray:
    """R (body <- camera) from 'mount_axes': the camera axes along body x, y, z, e.g. '+y,+z,+x'
    (body forward = camera +y, left = camera +z, up = camera +x: the camera standing, its LEFT
    circle looking forward). Must be a proper rotation (no mirror)."""
    parts = [p.strip().lower() for p in axes.split(",")]
    if len(parts) != 3:
        raise ValueError(f"mount_axes {axes!r}: expected three signed axes, e.g. '+y,+z,+x'")
    R = np.zeros((3, 3))
    for row, p in enumerate(parts):
        sign = -1.0 if p.startswith("-") else 1.0
        name = p.lstrip("+-")
        if name not in ("x", "y", "z"):
            raise ValueError(f"mount_axes {axes!r}: {p!r} is not one of +-x, +-y, +-z")
        R[row, "xyz".index(name)] = sign
    if abs(abs(np.linalg.det(R)) - 1.0) > 1e-9:
        raise ValueError(f"mount_axes {axes!r}: an axis is repeated")
    if np.linalg.det(R) < 0:
        raise ValueError(f"mount_axes {axes!r}: a mirror, not a rotation (flip one sign)")
    return R


def rpy_matrix(roll_deg: float, pitch_deg: float, yaw_deg: float) -> np.ndarray:
    """ROS fixed-axis roll, pitch, yaw: Rz(yaw) Ry(pitch) Rx(roll)."""
    r, p, y = (math.radians(v) for v in (roll_deg, pitch_deg, yaw_deg))
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def mount_rotation(axes: str = "+y,+z,+x", roll_deg: float = 0.0, pitch_deg: float = 0.0,
                   yaw_deg: float = 0.0) -> np.ndarray:
    """R (body <- camera IMU): the axis mapping, then a small trim (roll/pitch/yaw, body frame)."""
    return rpy_matrix(roll_deg, pitch_deg, yaw_deg) @ axes_matrix(axes)


# ── clock ────────────────────────────────────────────────────────────────
class CameraClock:
    """Camera ms -> host seconds. update() with each IMU packet; to_host() for any camera ms
    (an IMU record, or a video frame's exposure: its packet ms - FRAME_STAMP_LAG_MS)."""

    def __init__(self, window_s: float = 20.0, slew_s_per_s: float = 0.002, step_s: float = 0.5,
                 settle_s: float = 3.0):
        """window_s: the minimum is taken over this long; slew_s_per_s: how fast the offset may move
        once settled (2 ms/s: stamps 2 ms apart never go backwards); step_s: a bigger jump of the
        minimum is a clock step, taken at once; settle_s: the offset follows the minimum freely
        (it only decreases) for this long after a (re)start."""
        self.window_s, self.slew, self.step_s, self.settle_s = window_s, slew_s_per_s, step_s, settle_s
        self.offset: Optional[float] = None
        self.resets = 0
        self._win: deque = deque()             # (arrival, candidate offset)
        self._last_ms: Optional[float] = None
        self._t_start = self._t_last = None
        self._high = 0                         # consecutive candidates above offset + step_s

    def reset(self) -> None:
        self.offset, self._last_ms, self._t_start, self._t_last, self._high = None, None, None, None, 0
        self._win.clear()
        self.resets += 1

    def update(self, arrival_s: float, last_cam_ms: float) -> None:
        """One packet: host time it arrived, camera ms of its last record."""
        if self._last_ms is not None and last_cam_ms < self._last_ms - 1000.0:
            self.reset()                       # the camera restarted (its ms clock begins again)
        cand = arrival_s - last_cam_ms / 1000.0
        self._last_ms = last_cam_ms
        if self.offset is None:
            self.offset, self._t_start, self._t_last = cand, arrival_s, arrival_s
            self._win.append((arrival_s, cand))
            return
        if cand < self.offset - self.step_s:   # earlier than possible: the host clock stepped back
            self._step(arrival_s, cand)
            return
        self._high = self._high + 1 if cand > self.offset + self.step_s else 0
        if self._high >= 10:                   # 1 s of packets all too late: the host clock stepped forward
            self._step(arrival_s, cand)
            return
        self._win.append((arrival_s, cand))
        while self._win and self._win[0][0] < arrival_s - self.window_s:
            self._win.popleft()
        target = min(c for _, c in self._win)
        dt = max(0.0, arrival_s - self._t_last)
        self._t_last = arrival_s
        if arrival_s - self._t_start < self.settle_s and target < self.offset:
            self.offset = target
        else:
            lim = self.slew * dt
            self.offset += max(-lim, min(lim, target - self.offset))

    def _step(self, arrival_s: float, cand: float) -> None:
        self._win.clear()
        self._win.append((arrival_s, cand))
        self.offset, self._t_start, self._t_last, self._high = cand, arrival_s, arrival_s, 0
        self.resets += 1

    def to_host(self, cam_ms: float) -> Optional[float]:
        """Host seconds of a camera ms (None before the first packet)."""
        return None if self.offset is None else cam_ms / 1000.0 + self.offset


# ── gyro bias at rest ────────────────────────────────────────────────────
class BiasAtRest:
    """The gyro bias (rad/s), re-measured whenever the camera is at rest.

    At rest = over the last window the gyro and the accelerometer are quiet (per-axis std below
    gyro_std_dps / accel_std_g). The first rest window (2 s) sets the bias (the turn-on bias moves
    by tenths of deg/s between sessions); after that a 1 s rest window whose mean is within
    max_step_dps of the bias pulls it by 20 % (the field driver's rule: a slow steady turn is not
    taken for a bias)."""

    def __init__(self, bias0: Sequence[float], enabled: bool = True, rate_hz: float = 500.0,
                 gyro_std_dps: float = 0.15, accel_std_g: float = 0.004, max_step_dps: float = 0.3,
                 first_max_dps: float = 1.0):
        self.bias = np.asarray(bias0, float).copy()
        self.enabled, self.calibrated, self.updates = enabled, False, 0
        self.n_first, self.n_track = int(2.0 * rate_hz), int(1.0 * rate_hz)
        self.check_every = max(1, int(0.1 * rate_hz))
        self.gyro_std, self.accel_std = math.radians(gyro_std_dps), accel_std_g
        self.max_step, self.first_max = math.radians(max_step_dps), math.radians(first_max_dps)
        self._buf: deque = deque(maxlen=self.n_first)
        self._n = 0

    def add(self, w_raw: np.ndarray, a_g: np.ndarray) -> None:
        if not self.enabled:
            return
        self._buf.append(np.concatenate([w_raw, a_g]))
        self._n += 1
        if self._n % self.check_every:
            return
        n = self.n_track if self.calibrated else self.n_first
        if len(self._buf) < n:
            return
        x = np.array(list(self._buf)[-n:])
        if x[:, :3].std(axis=0).max() > self.gyro_std or x[:, 3:].std(axis=0).max() > self.accel_std:
            return
        m = x[:, :3].mean(axis=0)
        if not self.calibrated:
            if np.linalg.norm(m) < self.first_max:
                self.bias, self.calibrated, self.updates = m, True, self.updates + 1
        elif np.linalg.norm(m - self.bias) < self.max_step:
            self.bias = 0.8 * self.bias + 0.2 * m
            self.updates += 1


# ── samples ──────────────────────────────────────────────────────────────
@dataclass
class ImuSample:
    """One output sample: host time (s), body angular rate (rad/s), body specific force (m/s^2,
    gravity included: +9.81 up at rest, REP-145), the camera ms it stands for."""
    t: float
    gyro: np.ndarray
    accel: np.ndarray
    cam_ms: float


class ImuStream:
    """Camera packets in, body-frame ImuSample out (on the host clock)."""

    def __init__(self, R_body_cam: np.ndarray, decimation: int = 5, calibration=None,
                 clock: Optional[CameraClock] = None, bias_at_rest: bool = True, rate_hz: float = 500.0):
        acc_b, acc_s, gyr_b = calibration if calibration is not None else load_imu_calibration()
        self.R = np.asarray(R_body_cam, float)
        self.decimation = max(1, int(decimation))
        self.acc_bias, self.acc_scale = np.asarray(acc_b, float), np.asarray(acc_s, float)
        self.bias = BiasAtRest(gyr_b, enabled=bias_at_rest, rate_hz=rate_hz)
        self.clock = clock or CameraClock()
        self.records = self.packets = self.dropped_backwards = 0
        self._block: List[Tuple[float, np.ndarray, np.ndarray]] = []
        self._last_ms: Optional[float] = None
        self._last_t: Optional[float] = None

    def feed(self, arrival_s: float, packet: bytes) -> List[ImuSample]:
        """One camera packet (any kind) that arrived at host time arrival_s."""
        kind, _ = stream_kind(packet)
        if kind != KIND_IMU:
            return []
        recs = imu_records(packet)
        if not recs:
            return []
        self.packets += 1
        self.clock.update(arrival_s, float(recs[-1][0]))
        out = []
        for r in recs:
            ms = float(r[0])
            if self._last_ms is not None and ms < self._last_ms - 1000.0:
                self._block.clear()            # camera restarted: nothing spans the restart
                self._last_t = None
            self._last_ms = ms
            a = (np.array(r[1:4]) - self.acc_bias) / self.acc_scale
            w_raw = np.array(r[4:7])
            self.bias.add(w_raw, a)
            self._block.append((ms, w_raw - self.bias.bias, a))
            self.records += 1
            if len(self._block) >= self.decimation:
                s = self._emit()
                if s is not None:
                    out.append(s)
        return out

    def _emit(self) -> Optional[ImuSample]:
        ms = float(np.mean([b[0] for b in self._block]))
        w = np.mean([b[1] for b in self._block], axis=0)
        a = np.mean([b[2] for b in self._block], axis=0)
        self._block.clear()
        t = self.clock.to_host(ms)
        if t is None:
            return None
        if self._last_t is not None and t <= self._last_t:
            self.dropped_backwards += 1        # only while the clock settles or after a clock step back
            return None
        self._last_t = t
        return ImuSample(t, self.R @ w, self.R @ (a * G), ms)


def covariance_diag(sample_std: float, decimation: int) -> List[float]:
    """Row-major 3x3 covariance of a mean of `decimation` samples with this per-sample std."""
    v = sample_std * sample_std / max(1, int(decimation))
    return [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, v]


# ── sources ──────────────────────────────────────────────────────────────
def replay_packets(path: str, rate: float = 1.0, clock: str = "now", loop: bool = False,
                   stop: Optional[threading.Event] = None, now: Callable[[], float] = time.time,
                   sleep: Callable[[float], None] = time.sleep) -> Iterator[Tuple[float, bytes]]:
    """(host arrival, IMU packet) from a raw recording (folder of raw360_NNNN.bin, or one file).

    clock 'now': the recording's own timeline shifted so that it starts now (as if live);
    'recorded': the original arrival times. rate: 1 = real time, 2 = twice as fast, 0 = as fast as
    possible (pacing only: the stamps always follow the recording's timeline). loop: start again
    at the end (each pass shifted to start now)."""
    if clock not in ("now", "recorded"):
        raise ValueError(f"replay clock {clock!r}: expected 'now' or 'recorded'")
    while True:
        first = wall0 = shift = None
        for t, kind, _, p in read_raw(path):
            if stop is not None and stop.is_set():
                return
            if kind != KIND_IMU:
                continue
            if first is None:
                first, wall0 = t, now()
                shift = wall0 - t if clock == "now" else 0.0
            if rate > 0:
                wait = wall0 + (t - first) / rate - now()
                if wait > 0:
                    sleep(wait)
            yield t + shift, p
        if not loop or first is None:
            return


class UsbImuSource:
    """The live camera over USB (pyusb): starts the live stream (the only start command known to
    bring the IMU; its video is read and dropped), calls on_packet(host arrival, packet) for every
    packet, sends the keepalive and restarts the stream when the IMU goes silent (seen on the
    first starts after power-on). Only one process can hold the camera: not with the field server."""

    def __init__(self, on_packet: Callable[[float, bytes], None], usb_core=None, usb_util=None,
                 now: Callable[[], float] = time.time):
        if usb_core is None:
            import usb.core as usb_core
            import usb.util as usb_util
        self._core, self._util, self._now = usb_core, usb_util, now
        self.dev = usb_core.find(idVendor=VENDOR)
        if self.dev is None:
            raise RuntimeError("Insta360 not found in USB mode 'Android' (vendor 2e1a)")
        usb_util.claim_interface(self.dev, 0)
        self.on_packet = on_packet
        self.error: Optional[str] = None
        self.restarts = 0
        self._seq, self._lock, self._stop = 1, threading.Lock(), threading.Event()
        self._buf = bytearray()
        self._started, self._imu_t = now(), 0.0
        self._send(PKT_SYNC)
        self._message(CMD_START_LIVE, START_FULL)
        self._threads = [threading.Thread(target=f, daemon=True) for f in (self._read, self._keepalive)]
        for th in self._threads:
            th.start()

    def _send(self, payload: bytes) -> None:
        self.dev.write(EP_OUT, frame_packet(payload), timeout=1000)

    def _message(self, code: int, body: bytes) -> None:
        with self._lock:
            seq, self._seq = self._seq, self._seq + 1
        self._send(message_payload(code, seq, body))

    def imu_age(self) -> float:
        return self._now() - self._imu_t if self._imu_t else float("inf")

    def _read(self) -> None:
        while not self._stop.is_set():
            try:
                data = bytes(self.dev.read(EP_IN, 262144, timeout=500))
            except self._core.USBTimeoutError:
                continue
            except Exception as e:             # unplugged: reported, the node decides
                self.error = f"camera lost: {e}"
                self._stop.wait(0.5)
                continue
            self._buf += data
            t = self._now()
            for p in split_packets(self._buf):
                if stream_kind(p)[0] == KIND_IMU:
                    self._imu_t = t
                self.on_packet(t, p)

    def _keepalive(self) -> None:
        last_restart = 0.0
        while not self._stop.wait(1.0):
            try:
                self._send(PKT_KEEPALIVE)
                t = self._now()
                if t - self._started > 4.0 and self.imu_age() > 1.5 and t - last_restart > 3.0:
                    self._message(CMD_START_LIVE, START_FULL)
                    last_restart, self.restarts = t, self.restarts + 1
                    self.error = f"camera IMU silent: stream restarted ({self.restarts})"
            except Exception as e:
                self.error = f"keepalive: {e}"

    def close(self) -> None:
        try:
            self._message(CMD_STOP_LIVE, b"")
        except Exception:
            pass
        self._stop.set()
        for th in self._threads:
            th.join(timeout=2.0)
        for f in (lambda: self._util.release_interface(self.dev, 0), lambda: self._util.dispose_resources(self.dev)):
            try:
                f()
            except Exception:
                pass


# ── characterisation ─────────────────────────────────────────────────────
def allan_deviation(x: np.ndarray, fs: float, taus: Sequence[float]) -> np.ndarray:
    """Overlapping Allan deviation of a rate signal x (any unit) sampled at fs, at each tau (s);
    NaN where the record is too short (fewer than 2 tau)."""
    x = np.asarray(x, float)
    theta = np.concatenate([[0.0], np.cumsum(x)]) / fs
    out = []
    for tau in taus:
        m = int(round(tau * fs))
        if m < 1 or 2 * m >= len(x):
            out.append(float("nan"))
            continue
        d = theta[2 * m:] - 2.0 * theta[m:-m] + theta[:-2 * m]
        out.append(math.sqrt(float(np.mean(d * d)) / (2.0 * (m / fs) ** 2)))
    return np.array(out)


def raw_imu_rows(path: str) -> np.ndarray:
    """All IMU records of a recording: rows (camera ms, ax, ay, az g, wx, wy, wz rad/s)."""
    rows = [r for t, kind, _, p in read_raw(path) if kind == KIND_IMU for r in imu_records(p)]
    return np.array(rows, float).reshape(-1, 7)


def characterize(rows: np.ndarray, block_s: float = 0.2, quiet_factor: float = 1.6) -> dict:
    """Gyro/accelerometer noise of a recording at rest (deg/s, g). Blocks of block_s whose gyro std
    exceeds quiet_factor x the median block are bumps; the noise density is the Allan deviation at
    1 s over the longest stretch without bumps (white noise: ADEV(1 s) = N), the bias floor its
    minimum there, the bias creep the drift of 5 s means away from the first 2 s mean."""
    ms, a, w = rows[:, 0], rows[:, 1:4], np.degrees(rows[:, 4:7])
    span = (ms[-1] - ms[0]) / 1000.0
    fs = (len(ms) - 1) / span
    b = max(2, int(round(block_s * fs)))
    n = len(w) // b * b
    bs = w[:n].reshape(-1, b, 3).std(axis=1).max(axis=1)
    quiet = bs <= quiet_factor * np.median(bs)
    runs, s = [], None
    for i, ok in enumerate(list(quiet) + [False]):
        if ok and s is None:
            s = i
        elif not ok and s is not None:
            runs.append((s, i))
            s = None
    s, e = max(runs, key=lambda r: r[1] - r[0])
    seg = w[s * b:e * b]
    taus = [0.01, 0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0]
    adev = np.array([allan_deviation(seg[:, i], fs, taus) for i in range(3)]).T
    wq = w[:n].reshape(-1, b, 3)[quiet]
    aq = a[:n].reshape(-1, b, 3)[quiet]
    t = (ms - ms[0]) / 1000.0
    b0 = w[t < 2.0].mean(axis=0)
    creep = [np.abs(w[(t >= k) & (t < k + 5.0)].mean(axis=0) - b0) for k in range(0, int(span) - 4, 5)]
    return {
        "samples": int(len(ms)), "span_s": round(span, 2), "rate_hz": round(fs, 2),
        "bump_blocks": int((~quiet).sum()), "longest_quiet_s": round((e - s) * b / fs, 1),
        "gyro_sample_std_dps": (wq - wq.mean(axis=1, keepdims=True)).reshape(-1, 3).std(axis=0).round(4).tolist(),
        "accel_sample_std_g": (aq - aq.mean(axis=1, keepdims=True)).reshape(-1, 3).std(axis=0).round(5).tolist(),
        "taus_s": taus, "gyro_adev_dps": np.round(adev, 5).tolist(),
        "gyro_noise_dps_rthz": np.round(adev[taus.index(1.0)], 4).tolist(),
        "gyro_bias_floor_dps": np.round(np.nanmin(adev, axis=0), 4).tolist(),
        "gyro_turn_on_bias_dps": np.round(b0, 4).tolist(),
        "gyro_bias_creep_max_dps": np.round(np.max(creep, axis=0), 4).tolist() if creep else None,
        "accel_mean_g": np.round(a.mean(axis=0), 4).tolist(),
    }


def main(argv=None) -> None:
    """python3 -m camera_pkg.insta360_imu <raw folder or raw360_NNNN.bin> ...: the noise at rest."""
    import json
    import sys
    paths = sys.argv[1:] if argv is None else argv
    if not paths:
        sys.exit(main.__doc__)
    for p in paths:
        print(p)
        print(json.dumps(characterize(raw_imu_rows(p)), indent=1))


if __name__ == "__main__":
    main()

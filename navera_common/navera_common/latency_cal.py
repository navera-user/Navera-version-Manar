"""Online estimate of the camera frame delay (exposure -> arrival) against a trusted GPS.

A frame is dated `arrival - delay`. A wrong delay puts every vision fix speed x error
along the track (60 m at 60 m/s per second of error; Hikvision bench 2026-10-20: a 0.4 s
delay for a real ~1.0 s gave 69 m median at 60 m/s, 1.0 s gave 6.7 m). The delay was set
by hand per camera (Insta360 360 1.71 s, webcam strip 0.14 s, Hikvision RTSP ~1.0 s).

While the GPS is trusted, each accepted vision fix is compared with the GPS track
interpolated at `arrival - D` for every candidate delay D in [min_s, max_s]. The model is

    vision_i = gps(arrival_i - D) + b + noise

with b a constant east/north offset (map shift, camera mounting): it is fitted with D, so
a constant offset is never mistaken for a delay. D is then observable only from changes of
the velocity (heading or speed) over the samples: on a straight line at one speed it is
not, and the stated uncertainty says so (the estimate is then never applied).

* Samples are taken only in motion (>= min_speed_mps) and outside sharp turns
  (<= max_turn_dps over the delay window), with the GPS covering the whole window.
* Grid search (L1 cost, the offset per candidate = the coordinate-wise median), outliers
  beyond 4 robust sigmas trimmed, parabolic refinement.
* Uncertainty: the 3-parameter (b_e, b_n, D) least-squares covariance at the optimum,
  scaled by the robust residual spread and inflated for the residuals' time correlation
  (successive vision errors are not independent), plus a systematic term: the residual
  spread over the spread of the velocity vectors (a vision error that does not average
  out, e.g. a height/scale error, read as a delay through the velocity change).
* Stable = at least min_samples, sigma <= max_sigma_s, not on a bound, and the last
  `stable_count` estimates within max(2 sigma, 0.05 s) of each other. A stable estimate
  replaces the set (nominal) delay only when it differs from it by more than
  change_sigmas x sigma: a well-measured hand value is never traded for a noisier one
  (bench replay: a stable 1.59 +- 0.07 s against the 1.71 s fitted on 54 frames gave
  8.5 m instead of 3.3 m after the GPS loss at 60 m/s). `applied` is None while the set
  delay stands; it is kept (frozen) while the GPS is lost or untrusted, and on a loss the
  last rollback_s seconds of samples are dropped (a slow spoof is trusted until refused).
"""
import math
import threading
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

_M_PER_DEG = 111320.0


class LatencyCalibrator:
    """Camera delay (s) from accepted vision fixes vs the trusted GPS track."""

    def __init__(self, min_s: float = 0.0, max_s: float = 3.0, step_s: float = 0.02,
                 min_samples: int = 20, min_speed_mps: float = 5.0, max_turn_dps: float = 8.0,
                 max_sigma_s: float = 0.1, stable_count: int = 3, max_samples: int = 300,
                 gps_max_gap_s: float = 1.5, nominal_s: float = 0.0, change_sigmas: float = 3.0):
        if max_s <= min_s:
            raise ValueError("latency bounds: max_s must exceed min_s")
        self.grid = np.arange(min_s, max_s + 1e-9, step_s)
        self.min_s, self.max_s, self.step_s = float(min_s), float(max_s), float(step_s)
        self.min_samples, self.stable_count = int(min_samples), int(stable_count)
        self.min_speed, self.max_turn = float(min_speed_mps), float(max_turn_dps)
        self.max_sigma, self.gps_max_gap = float(max_sigma_s), float(gps_max_gap_s)
        self.nominal, self.change_sigmas = float(nominal_s), float(change_sigmas)
        self._gps: deque = deque(maxlen=4000)            # (t, lat, lon), time order
        self._pending: List[Tuple[float, float, float]] = []   # fixes waiting for GPS after them
        self._res: deque = deque(maxlen=max_samples)     # per sample: (n_grid, 2) residual e/n m
        self._vel: deque = deque(maxlen=max_samples)     # per sample: (n_grid, 2) GPS velocity m/s
        self._t: deque = deque(maxlen=max_samples)       # arrival times
        self._hist: deque = deque(maxlen=max(stable_count, 1))
        self._applied_at: deque = deque(maxlen=max_samples)   # (sample time, applied value)
        self.estimate: Optional[float] = None
        self.sigma: Optional[float] = None
        self.offset_m: Optional[Tuple[float, float]] = None
        self.applied: Optional[float] = None
        self.stable = False
        self.frozen = False
        self.rejected: Dict[str, int] = {}
        self.reason = "no samples yet"
        self._lock = threading.RLock()                   # GPS and frames arrive on other threads

    # ── inputs ──────────────────────────────────────────────────────────
    def add_gps(self, t: float, lat: float, lon: float) -> None:
        """A trusted GPS position at its measurement time (s)."""
        with self._lock:
            if self._gps and t <= self._gps[-1][0]:
                if t < self._gps[-1][0] - 1.0:               # clock stepped back: restart
                    self._gps.clear()
                    self._pending.clear()
                return
            self._gps.append((float(t), float(lat), float(lon)))
            self.frozen = False
            if self._pending:
                waiting = self._pending
                self._pending = []
                for p in waiting:
                    if not self._try(*p):
                        self._pending.append(p)

    def add_fix(self, t_arrival: float, lat: float, lon: float) -> None:
        """An accepted vision fix of a frame that arrived at t_arrival (s, same clock as the
        GPS stamps), taken while the GPS is trusted. Used once the GPS covers its instant.
        """
        with self._lock:
            if self.frozen:
                self._count("gps not trusted")
                return
            if not self._try(t_arrival, lat, lon):
                self._pending.append((t_arrival, lat, lon))
                del self._pending[:-20]

    def freeze(self, why: str = "GPS lost or not trusted", rollback_s: float = 0.0) -> None:
        """GPS lost or untrusted: no new samples. With rollback_s, the samples of the last
        rollback_s seconds before it are dropped and the applied value goes back to the one
        applied then: a slowly spoofed GPS is trusted until refused, and its drift leaks into
        the delay (bench replay, 3 m/s drift over 13 s: -0.1 s at 60 m/s).
        """
        with self._lock:
            if self.frozen:
                return
            self.frozen = True
            self._pending.clear()
            if rollback_s > 0 and self._t:
                cut = self._t[-1] - rollback_s
                keep = [i for i, t in enumerate(self._t) if t <= cut]
                for dq in (self._res, self._vel, self._t):
                    kept = [dq[i] for i in keep]
                    dq.clear()
                    dq.extend(kept)
                old = [a for t, a in self._applied_at if t <= cut]
                self.applied = old[-1] if old else None
                self._applied_at = deque((x for x in self._applied_at if x[0] <= cut), maxlen=self._applied_at.maxlen)
                self._hist.clear()
                self.estimate = self.sigma = self.offset_m = None
                self.stable = False
                if len(self._res) >= 3:
                    self._solve(apply=False)
            self.reason = f"frozen: {why}"

    # ── the fit ─────────────────────────────────────────────────────────
    def _count(self, why: str) -> None:
        self.rejected[why] = self.rejected.get(why, 0) + 1

    def _try(self, ta: float, lat: float, lon: float) -> bool:
        """Turn a fix into a sample; False = the GPS does not cover it yet (retry later)."""
        if not self._gps:
            return False
        g = np.asarray(self._gps)
        if g[-1, 0] < ta + 0.5:                          # the velocity at ta needs GPS after it
            if g[-1, 0] < ta - 5.0:
                self._count("no gps after the frame")
                return True                              # never coming: drop it
            return False
        lo = ta - self.max_s - 1.0
        if g[0, 0] > lo:
            self._count("gps history too short")
            return True
        w = g[(g[:, 0] >= lo - self.gps_max_gap) & (g[:, 0] <= ta + 0.5 + self.gps_max_gap)]
        if len(w) < 2 or np.max(np.diff(w[:, 0])) > self.gps_max_gap:
            self._count("gps gap")
            return True
        taus = ta - self.grid
        pos = self._interp(g, taus)
        vel = (self._interp(g, taus + 0.5) - self._interp(g, taus - 0.5))
        speed = np.hypot(vel[:, 0], vel[:, 1])
        if np.min(speed) < self.min_speed:
            self._count("too slow")
            return True
        # the turn rate over 1 s steps of the window: between neighbouring grid points (0.02 s) the
        # heading of a noisy GPS track jumps at every GPS sample — 0.3 m of receiver noise at 10 m/s
        # read as > 100 deg/s, and every sample of a straight copter leg was refused as "turning"
        # (Isaac Sim closed loop 2026-10-21: 21 of 21)
        hd = np.unwrap(np.arctan2(vel[:, 0], vel[:, 1]))
        stride = max(1, int(round(1.0 / self.step_s)))
        hs = hd[::stride]
        if len(hs) > 1 and np.max(np.abs(np.diff(hs))) / (stride * self.step_s) > math.radians(self.max_turn):
            self._count("turning")
            return True
        c = math.cos(math.radians(lat))
        res = np.stack([(lon - g[-1, 2]) * _M_PER_DEG * c - pos[:, 0],
                        (lat - g[-1, 1]) * _M_PER_DEG - pos[:, 1]], -1)
        self._res.append(res)
        self._vel.append(vel)
        self._t.append(ta)
        self._solve()
        return True

    @staticmethod
    def _interp(g: np.ndarray, ts: np.ndarray) -> np.ndarray:
        """GPS east/north (m) relative to the latest GPS point, interpolated at ts."""
        c = math.cos(math.radians(g[-1, 1]))
        e = (np.interp(ts, g[:, 0], g[:, 2]) - g[-1, 2]) * _M_PER_DEG * c
        n = (np.interp(ts, g[:, 0], g[:, 1]) - g[-1, 1]) * _M_PER_DEG
        return np.stack([e, n], -1)

    def _solve(self, apply: bool = True) -> None:
        n = len(self._res)
        if n < 3:
            self.reason = f"{n} samples"
            return
        R = np.stack(self._res, 1)                       # (grid, n, 2)
        V = np.stack(self._vel, 1)
        keep = np.ones(n, bool)
        for _ in range(2):                               # fit, trim outliers, fit again
            b = np.median(R[:, keep], axis=1)            # (grid, 2)
            cost = np.mean(np.linalg.norm(R[:, keep] - b[:, None], axis=2), axis=1)
            k = int(np.argmin(cost))
            r = np.linalg.norm(R[k] - b[k], axis=1)
            s = 1.4826 * np.median(r[keep]) / 1.1774 + 1e-3   # per-axis sigma from the norm
            new = r <= max(4.0 * s, 5.0)
            if new.sum() < 3 or np.array_equal(new, keep):
                break
            keep = new
        d = float(self.grid[k])
        if 0 < k < len(cost) - 1:                        # parabolic refinement
            den = cost[k - 1] - 2 * cost[k] + cost[k + 1]
            if den > 0:
                d += 0.5 * self.step_s * (cost[k - 1] - cost[k + 1]) / den
        e = R[k, keep] - b[k]
        v = V[k, keep]
        m = len(e)
        J = np.zeros((2 * m, 3))
        J[0::2, 0] = J[1::2, 1] = -1.0
        J[0::2, 2], J[1::2, 2] = v[:, 0], v[:, 1]
        s = 1.4826 * np.median(np.abs(e - np.median(e, 0)))
        try:
            var = (s * s * np.linalg.inv(J.T @ J))[2, 2]
        except np.linalg.LinAlgError:
            var = float("inf")
        # successive vision errors are correlated: lag-1 autocorrelation of the along-track part
        u = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-6)
        a = np.sum(e * u, axis=1)
        rho = 0.0
        if m > 4 and np.std(a) > 0:
            rho = float(np.clip(np.corrcoef(a[:-1], a[1:])[0, 1], 0.0, 0.9))
        stat = max(var, 0.0) * (1 + rho) / (1 - rho) if math.isfinite(var) else float("inf")
        # a slowly varying vision error (height/scale, weather) does not average out: as if all the
        # residual spread were one systematic error, separated from the offset only by the velocity's
        # own spread (bench 2026-10-20, 20 m/s over 38 deg: 1.33 s fitted for 1.7 s with a 0.075 s
        # statistical sigma; this term made it 0.5 s, i.e. not applied)
        spread = math.sqrt(float(np.mean(np.sum((v - v.mean(0)) ** 2, axis=1))))
        syst = (s / spread) ** 2 if spread > 1e-6 else float("inf")
        sig = math.sqrt(stat + syst)
        self.estimate, self.sigma = d, sig
        self.offset_m = (float(b[k, 0]), float(b[k, 1]))
        self._hist.append(d)
        on_bound = k == 0 or k == len(cost) - 1
        agree = len(self._hist) >= self.stable_count and \
            max(self._hist) - min(self._hist) <= max(2 * sig, 0.05)
        if m < self.min_samples:
            self.stable, self.reason = False, f"{m}/{self.min_samples} samples"
        elif on_bound:
            self.stable, self.reason = False, "estimate on a bound of the search range"
        elif not sig <= self.max_sigma:
            self.stable, self.reason = False, (f"sigma {sig:.2f} s > {self.max_sigma:.2f} s "
                                               "(too little heading/speed change to separate a delay from an offset)")
        elif not agree:
            self.stable, self.reason = False, "estimate still moving"
        else:
            self.stable = True
            if abs(d - self.nominal) <= self.change_sigmas * sig:
                self.reason, d = f"stable, within {self.change_sigmas:g} sigma of the set delay: kept", None
            else:
                self.reason = "stable"
            if apply:
                self.applied = d
                self._applied_at.append((self._t[-1], d))

    # ── outputs ─────────────────────────────────────────────────────────
    def delay(self) -> float:
        """The delay to date frames with: the applied estimate, else the set one."""
        return self.nominal if self.applied is None else self.applied

    def correction(self) -> float:
        """Seconds to subtract from a stamp already dated arrival - nominal."""
        return self.delay() - self.nominal

    @property
    def samples(self) -> int:
        return len(self._res)

    def state(self) -> dict:
        """For the status JSON."""
        with self._lock:
            rnd = (lambda x, k=3: None if x is None or not math.isfinite(x) else round(x, k))
            return {"estimate_s": rnd(self.estimate), "sigma_s": rnd(self.sigma), "applied_s": rnd(self.applied),
                    "nominal_s": rnd(self.nominal), "delay_s": rnd(self.delay()),
                    "samples": self.samples, "stable": self.stable, "frozen": self.frozen, "reason": self.reason,
                    "offset_m": None if self.offset_m is None else [round(x, 1) for x in self.offset_m],
                    "rejected": dict(self.rejected)}


def from_node(node) -> Tuple[LatencyCalibrator, bool, float]:
    """Declare the day node's camera-delay parameters; returns (calibrator, auto, rollback_s)."""
    from navera_common.params import declare_float
    declare_float(node, "camera_latency_s", 0.0,
                  "the delay the camera already subtracted from the frame stamps (its capture_latency_s)")
    node.declare_parameter("auto_latency", True)
    declare_float(node, "latency_min_s", 0.0, "camera delay search range, lower bound (s)")
    declare_float(node, "latency_max_s", 3.0, "camera delay search range, upper bound (s)")
    node.declare_parameter("latency_min_samples", 20)
    declare_float(node, "latency_max_sigma_s", 0.1, "a delay estimate is used only below this sigma (s)")
    declare_float(node, "latency_change_sigmas", 3.0,
                  "the estimate replaces camera_latency_s only when this many sigmas away from it")
    declare_float(node, "latency_min_speed_mps", 5.0, "no delay sample below this ground speed")
    declare_float(node, "latency_max_turn_dps", 8.0, "no delay sample in a turn faster than this")
    declare_float(node, "latency_rollback_s", 20.0,
                  "at a GPS loss/refusal, drop this many seconds of the last delay samples")
    p = (lambda n: node.get_parameter(n).value)
    cal = LatencyCalibrator(min_s=float(p("latency_min_s")), max_s=float(p("latency_max_s")),
                            min_samples=int(p("latency_min_samples")), min_speed_mps=float(p("latency_min_speed_mps")),
                            max_turn_dps=float(p("latency_max_turn_dps")), max_sigma_s=float(p("latency_max_sigma_s")),
                            nominal_s=float(p("camera_latency_s")), change_sigmas=float(p("latency_change_sigmas")))
    return cal, bool(p("auto_latency")), float(p("latency_rollback_s"))


def shift_meta(meta: dict, correction_s: float) -> dict:
    """Date a frame by the estimated delay: keeps the camera's stamp in image_stamp_raw_ns
    and moves image_stamp_ns back by correction_s (no stamp: unchanged).
    """
    ns = meta.get("image_stamp_ns")
    if ns is None:
        return meta
    raw = int(meta.setdefault("image_stamp_raw_ns", int(ns)))
    meta["image_stamp_ns"] = raw - int(round(correction_s * 1e9))
    return meta

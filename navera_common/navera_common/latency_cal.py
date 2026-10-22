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
* Staged apply while the delay is unknown (nominal 0): the delay then has a prior, N(0,
  prior_sigma_s) — the uncertainty the day node already adds to every stated fix — or a delay
  stored by an earlier flight with this camera (set_prior). Before the estimate is stable, it is
  combined with that prior (inverse-variance) once it has partial_min_samples, a sigma <=
  partial_max_sigma_s, is off the bounds and agrees with the previous estimates: the applied
  delay is that posterior, shrunk towards the prior as much as the estimate is uncertain, and
  applied_sigma is the posterior's sigma (what the stated fix accuracy then adds as speed x
  sigma). Isaac Sim closed loop 2026-10-21 (true delay 1.3 s): the plane's 72 samples gave
  1.34 +- 0.43 s, never applied (49 m median error at the stated time against 14 m at the
  exposure); applied as 1.13 +- 0.39 s it is 18 m. A stored prior the in-flight estimate
  contradicts (> 2 combined sigma) is dropped: another camera or stream setting.
"""
import math
import os
import re
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
                 gps_max_gap_s: float = 1.5, nominal_s: float = 0.0, change_sigmas: float = 3.0,
                 prior_sigma_s: float = 1.0, partial_max_sigma_s: float = 0.5, partial_min_samples: int = 10,
                 nominal_sigma_s: float = 0.1):
        if max_s <= min_s:
            raise ValueError("latency bounds: max_s must exceed min_s")
        self.grid = np.arange(min_s, max_s + 1e-9, step_s)
        self.min_s, self.max_s, self.step_s = float(min_s), float(max_s), float(step_s)
        self.min_samples, self.stable_count = int(min_samples), int(stable_count)
        self.min_speed, self.max_turn = float(min_speed_mps), float(max_turn_dps)
        self.max_sigma, self.gps_max_gap = float(max_sigma_s), float(gps_max_gap_s)
        self.nominal, self.change_sigmas = float(nominal_s), float(change_sigmas)
        self.partial_max_sigma, self.partial_min_samples = float(partial_max_sigma_s), int(partial_min_samples)
        self.nominal_sigma, self.prior_sigma = float(nominal_sigma_s), float(prior_sigma_s)
        # the prior of a delay nobody set: N(0, prior_sigma_s) (no prior, no staged apply: a set delay)
        self._unknown_prior = (0.0, float(prior_sigma_s)) if self.nominal == 0.0 and prior_sigma_s > 0 else None
        self.prior: Optional[Tuple[float, float]] = self._unknown_prior
        self.prior_source = "unknown delay" if self.prior else None
        self._start: Tuple[Optional[float], Optional[float]] = (None, None)   # applied at the start (stored)
        self._gps: deque = deque(maxlen=4000)            # (t, lat, lon), time order
        self._pending: List[Tuple[float, float, float]] = []   # fixes waiting for GPS after them
        self._res: deque = deque(maxlen=max_samples)     # per sample: (n_grid, 2) residual e/n m
        self._vel: deque = deque(maxlen=max_samples)     # per sample: (n_grid, 2) GPS velocity m/s
        self._t: deque = deque(maxlen=max_samples)       # arrival times
        self._hist: deque = deque(maxlen=max(stable_count, 1))
        self._applied_at: deque = deque(maxlen=max_samples)   # (sample time, applied value, its sigma)
        self.estimate: Optional[float] = None
        self.sigma: Optional[float] = None
        self.offset_m: Optional[Tuple[float, float]] = None
        self.applied: Optional[float] = None
        self.applied_sigma: Optional[float] = None
        self.stable = False
        self.frozen = False
        self.rejected: Dict[str, int] = {}
        self.reason = "no samples yet"
        self._lock = threading.RLock()                   # GPS and frames arrive on other threads
        self.store_key: Optional[str] = None             # persist(): where this camera's delay is kept
        self._stored: Tuple[Optional[float], Optional[float]] = (None, None)

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
                old = [(a, sa) for t, a, sa in self._applied_at if t <= cut]
                self.applied, self.applied_sigma = old[-1] if old else self._start
                self._applied_at = deque((x for x in self._applied_at if x[0] <= cut), maxlen=self._applied_at.maxlen)
                self._hist.clear()
                self.estimate = self.sigma = self.offset_m = None
                self.stable = False
                if len(self._res) >= 3:
                    self._solve(apply=False)
            self.reason = f"frozen: {why}"

    def set_prior(self, delay_s: float, sigma_s: float, source: str = "stored") -> bool:
        """Start from a delay measured earlier with this camera (an earlier flight): applied at
        once with its sigma, and the prior the in-flight estimate is combined with. Only while the
        delay is unknown (nominal 0) and the value is inside the search range; False otherwise.
        """
        with self._lock:
            if self._unknown_prior is None or not (self.min_s <= delay_s <= self.max_s) or not sigma_s > 0:
                return False
            self.prior, self.prior_source = (float(delay_s), float(sigma_s)), source
            self.applied, self.applied_sigma = self.prior
            self._start = self.prior
            self.reason = f"started from the {source} delay {delay_s:.2f} +- {sigma_s:.2f} s"
            return True

    def set_nominal(self, nominal_s: float, why: str = "camera") -> bool:
        """The delay the camera already subtracted (measured on the bench: the calibration file's
        latency_s, NAVERA_CAMERA_LATENCY_S), learned from the frames: it replaces a stored or
        staged value and the unknown prior. Only before the first sample (a change of the
        reference under samples would mix two datings); True when taken.
        """
        with self._lock:
            nominal_s = float(nominal_s)
            if nominal_s == self.nominal or self._res or not (self.min_s <= nominal_s <= self.max_s):
                return False
            self.nominal = nominal_s
            self._unknown_prior = None if nominal_s != 0.0 else (0.0, self.prior_sigma)
            self.prior = self._unknown_prior
            self.prior_source = None if self.prior is None else "unknown delay"
            self.applied = self.applied_sigma = None
            self._start, self.store_key = (None, None), (self.store_key if nominal_s == 0.0 else None)
            self._applied_at.clear()
            self._hist.clear()
            self.reason = f"set delay {nominal_s:.3f} s ({why})"
            return True

    def delay_sigma(self) -> Optional[float]:
        """1-sigma (s) of delay() when known: the applied posterior's, nominal_sigma_s for a set
        delay (bench-measured), None while unknown (nominal 0 and nothing applied).
        """
        if self.applied is not None:
            return self.applied_sigma if self.applied_sigma is not None else self.nominal_sigma
        return self.nominal_sigma if self.nominal != 0.0 else None

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
            if self.prior is not None:
                self.reason = "stable"
                self._apply_posterior(d, sig, apply)
                return
            if abs(d - self.nominal) <= self.change_sigmas * sig:
                self.reason, d = f"stable, within {self.change_sigmas:g} sigma of the set delay: kept", None
            else:
                self.reason = "stable"
            if apply:
                self.applied, self.applied_sigma = d, (None if d is None else sig)
                self._applied_at.append((self._t[-1], self.applied, self.applied_sigma))
            return
        # not stable: a partial correction (the posterior with the prior) when well enough measured
        if self.prior is not None and m >= self.partial_min_samples and not on_bound and agree \
                and sig <= self.partial_max_sigma:
            self.reason += f" — partial: {sig:.2f} s <= {self.partial_max_sigma:.2f} s"
            self._apply_posterior(d, sig, apply)

    def _apply_posterior(self, d: float, sig: float, apply: bool) -> None:
        """Apply the inverse-variance combination of the estimate with the prior."""
        mu0, s0 = self.prior
        # a stored delay the estimate contradicts is dropped at 2 combined sigma: keeping a stale one
        # costs far more than falling back to the unknown prior
        if self.prior is not self._unknown_prior and abs(d - mu0) > 2.0 * math.hypot(sig, s0) \
                and self._unknown_prior is not None:
            self.reason += f"; the {self.prior_source} delay {mu0:.2f} s contradicted: dropped"
            self.prior, self.prior_source = self._unknown_prior, "unknown delay"
            mu0, s0 = self.prior
        w = s0 * s0 / (s0 * s0 + sig * sig)
        post, psig = mu0 + w * (d - mu0), math.sqrt(w) * sig
        if apply:
            self.applied, self.applied_sigma = post, psig
            self._applied_at.append((self._t[-1], post, psig))

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
                    "applied_sigma_s": rnd(self.applied_sigma),
                    "prior": None if self.prior is None else
                    [rnd(self.prior[0]), rnd(self.prior[1]), self.prior_source],
                    "nominal_s": rnd(self.nominal), "delay_s": rnd(self.delay()),
                    "samples": self.samples, "stable": self.stable, "frozen": self.frozen, "reason": self.reason,
                    "offset_m": None if self.offset_m is None else [round(x, 1) for x in self.offset_m],
                    "rejected": dict(self.rejected)}

    # ── kept across flights ─────────────────────────────────────────────

    def persist(self) -> bool:
        """Keep the delay measured in flight for the next flight with this camera (store_key):
        written when the applied value changes and was measured here (not the stored start), and
        written back to the start value when a rollback undid it. True when written.
        """
        with self._lock:
            if self.store_key is None or self.prior is None:
                return False
            cur = (self.applied, self.applied_sigma)
            if cur[0] is None or cur == self._start:
                cur = self._start                         # nothing measured (or undone): what we started from
            if cur == self._stored or (cur == self._start and self._stored == (None, None)):
                return False
            self._stored = cur
            return save_stored(self.store_key, *cur)


def _store_name(key: str) -> str:
    return "camera_delay_" + re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:80]


def save_stored(key: str, delay_s: Optional[float], sigma_s: Optional[float],
                directory: Optional[str] = None) -> bool:
    """Write this camera's delay (None: forget it) to the NAVERA state dir (navera_common.state_store)."""
    from navera_common import state_store
    return state_store.save(_store_name(key), {"key": key, "delay_s": delay_s, "sigma_s": sigma_s}, directory)


def load_stored(key: str, max_age_s: float, directory: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """(delay_s, sigma_s) kept for this camera if younger than max_age_s, else None."""
    from navera_common import state_store
    d = state_store.load(_store_name(key), max_age_s, directory)
    try:
        if d is None or d.get("key") != key or d.get("delay_s") is None:
            return None
        delay, sigma = float(d["delay_s"]), float(d["sigma_s"])
    except (TypeError, ValueError):
        return None
    return (delay, sigma) if math.isfinite(delay) and math.isfinite(sigma) and sigma > 0 else None


def store_key(param: str = "") -> str:
    """The camera a stored delay belongs to: latency_store_key, else the calibration (lens) file's
    name (NAVERA_CAMERA_CALIBRATION), else 'camera'.
    """
    return param.strip() or os.path.basename(os.environ.get("NAVERA_CAMERA_CALIBRATION", "").strip()) or "camera"


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
    declare_float(node, "camera_latency_sigma_s", 0.1,
                  "1-sigma of a set (bench-measured) camera delay, added as speed x sigma to stated fixes")
    declare_float(node, "latency_rollback_s", 20.0,
                  "at a GPS loss/refusal, drop this many seconds of the last delay samples")
    declare_float(node, "latency_partial_max_sigma_s", 0.5,
                  "unknown delay: below this sigma the estimate is applied combined with the prior (staged)")
    node.declare_parameter("latency_partial_min_samples", 10)
    node.declare_parameter("latency_store", True)
    node.declare_parameter("latency_store_key", "")
    declare_float(node, "latency_store_max_age_days", 60.0, "a stored camera delay older than this is ignored")
    declare_float(node, "latency_store_min_sigma_s", 0.1,
                  "a stored delay starts the next flight with at least this sigma (the stream may change)")
    p = (lambda n: node.get_parameter(n).value)
    prior_sigma = float(p("unknown_delay_sigma_s")) if node.has_parameter("unknown_delay_sigma_s") else 1.0
    cal = LatencyCalibrator(min_s=float(p("latency_min_s")), max_s=float(p("latency_max_s")),
                            min_samples=int(p("latency_min_samples")), min_speed_mps=float(p("latency_min_speed_mps")),
                            max_turn_dps=float(p("latency_max_turn_dps")), max_sigma_s=float(p("latency_max_sigma_s")),
                            nominal_s=float(p("camera_latency_s")), change_sigmas=float(p("latency_change_sigmas")),
                            prior_sigma_s=prior_sigma, partial_max_sigma_s=float(p("latency_partial_max_sigma_s")),
                            partial_min_samples=int(p("latency_partial_min_samples")),
                            nominal_sigma_s=float(p("camera_latency_sigma_s")))
    auto = bool(p("auto_latency"))
    if auto and bool(p("latency_store")) and cal.prior is not None:
        cal.store_key = store_key(str(p("latency_store_key")))
        kept = load_stored(cal.store_key, float(p("latency_store_max_age_days")) * 86400.0)
        if kept is not None:
            cal.set_prior(kept[0], math.hypot(kept[1], float(p("latency_store_min_sigma_s"))),
                          f"stored ({cal.store_key})")
    return cal, auto, float(p("latency_rollback_s"))


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

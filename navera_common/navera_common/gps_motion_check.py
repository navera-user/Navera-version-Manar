"""Slow-spoof detection on RELATIVE motion: GPS displacement against visual-odometry displacement.

A spoofer pulling GPS at v m/s adds v x T to every GPS displacement over T seconds; visual odometry
(the ground's shift between consecutive frames, day_pkg.frame_odometry) does not see it. The
absolute vision fixes that GpsDriftTrend compares with have 15-37 m errors; a VO displacement over a
few seconds is good to about a metre, so the drift shows much earlier in the motion than in the
position.

Two systematic VO errors look like a drift and are handled explicitly:
  * the scale (height above ground, sub-pixel bias) and the heading: VO measures the true
    displacement / c, c a complex gain (scale and rotation). c is learned from the independent
    map fixes only: least squares of the fixes on the VO track, one intercept per contiguous VO run
    (the map's bias cancels), over calib_window_s, its error widened by what calib_recent_s alone says
    (the height the VO uses changed). GPS plays no part, so a spoof cannot teach it. What is left of
    c's uncertainty (eps, at least eps_floor) is allowed per step as eps x the step's length; no
    test before c is learned (calib_min_spread_m of VO track with fixes on it).
  * a lock on what does not move in the image (overlays, the vehicle's own parts) or a wrong
    correlation peak: a step far from the VO's own recent velocity breaks the VO track (judged on
    VO alone); against GPS, a step near zero while GPS moves, or off by more than gross_mps /
    gross_frac, is not used (a faster spoof is the size rules' and the jump gate's business).

The test (one per VO step, the step's GPS displacement interpolated at the frame instants):
residual r = GPS displacement - c x VO displacement (east, north), projected on n_dirs
directions; per direction a CUSUM on the residual in its own measured noise (the robust spread
of differences of successive residuals and of block_n-step sums: a constant drift does not change
it; a noisier VO widens the test by itself), each projection clipped at clip_sigmas:
    y = (r.u - eps |c VO| - bias_mps dt) / sigma - k ;  S = max(0, S + y)
Refused when S >= h and the drift accumulated since S last left 0 is >= min_growth_m. While
S >= h / 2 in some direction the GPS is "in doubt". Pure Python, times in seconds, positions in
a local east/north frame (metres, any fixed origin).
"""
import bisect
import cmath
import math
from collections import deque
from statistics import median
from typing import Optional, Tuple


def _q50(v):
    return median(v) if v else 0.0


class GpsMotionCheck:
    """GPS displacement vs visual-odometry displacement: a directional CUSUM against slow spoofing."""

    def __init__(self, n_dirs: int = 8, h: float = 12.0, k: float = 0.25, min_growth_m: float = 12.0,
                 bias_mps: float = 0.5, min_sigma_m: float = 0.5, noise_n: int = 40, min_noise_n: int = 12,
                 prior_eps: float = 0.1, eps_floor: float = 0.03, eps_sigmas: float = 3.0,
                 calib_min_spread_m: float = 300.0, calib_decorr_s: float = 10.0,
                 calib_window_s: float = 600.0, calib_recent_s: float = 60.0,
                 lock_frac: float = 0.3, lock_min_m: float = 5.0, gross_mps: float = 10.0,
                 gross_frac: float = 0.5, clip_sigmas: float = 4.0, max_gap_s: float = 30.0,
                 block_n: int = 4, require_calibration: bool = True):
        self.n_dirs = max(4, int(n_dirs))
        self.dirs = [cmath.exp(2j * math.pi * i / self.n_dirs) for i in range(self.n_dirs)]
        self.h, self.k, self.min_growth = float(h), float(k), float(min_growth_m)
        self.bias_mps, self.min_sigma = float(bias_mps), float(min_sigma_m)
        self.noise_n, self.min_noise_n = max(4, int(noise_n)), max(2, int(min_noise_n))
        self.prior_eps, self.eps_floor, self.eps_sigmas = float(prior_eps), float(eps_floor), float(eps_sigmas)
        self.cal_min_m, self.cal_decorr_s = float(calib_min_spread_m), float(calib_decorr_s)
        self.cal_window_s, self.cal_recent_s = float(calib_window_s), float(calib_recent_s)
        self.lock_frac, self.lock_min = float(lock_frac), float(lock_min_m)
        self.gross_mps, self.gross_frac = float(gross_mps), float(gross_frac)
        self.clip_sigmas, self.max_gap_s = float(clip_sigmas), float(max_gap_s)
        self.block_n, self.require_calibration = max(2, int(block_n)), bool(require_calibration)
        self._steps = deque()    # VO track: (t0, t1, d complex, segment id, cumulative complex at t1)
        self._fixes = deque()    # independent map fixes: (t, complex position, offset GPS - fix or None)
        self._seg = 0
        self._vrec = deque(maxlen=5)  # velocities of the last accepted VO steps
        self._vrej = 0
        self.gain = (1.0 + 0j, self.prior_eps, 0)   # (c, eps, pairs) VO -> ground
        self.reset()

    # ------------------------------------------------------------------ state

    def reset(self) -> None:
        """Forget the test (a new GPS track); the VO calibration is kept (it owes nothing to GPS)."""
        self._s = [0.0] * self.n_dirs           # CUSUM per direction (noise units)
        self._m = [0.0] * self.n_dirs           # drift accumulated since S left 0 (metres)
        self._t_start = [None] * self.n_dirs    # when S left 0
        self._resid = deque(maxlen=self.noise_n)   # residuals of the used steps (noise estimate)
        self._last_used_t = None
        self.used = self.skipped = 0
        self.last = None                         # diagnostics of the last step
        self.refused_baseline = None             # (east, north, growth m) of GPS - fix before the drift

    @property
    def in_doubt(self) -> bool:
        """Some direction half way to the refusal threshold."""
        return max(self._s) >= 0.5 * self.h

    @property
    def sigma(self) -> Optional[float]:
        """The measured per-step noise of the residual (m), None while too few steps: the larger of the
        spread of successive differences and of differences of sums of block_n steps (an error that
        persists over a few steps, e.g. a VO slowly losing the ground, is not white: one-step
        differences alone call it small).
        """
        r = list(self._resid)
        if len(r) < self.min_noise_n:
            return None
        d1 = [abs(x) for a, b in zip(r, r[1:]) for x in ((b - a).real, (b - a).imag)]
        s = 1.4826 * _q50(sorted(d1)) / math.sqrt(2.0)
        b = self.block_n
        if len(r) >= 2 * b + 4:
            sums = [sum(r[i:i + b]) for i in range(len(r) - b + 1)]
            db = [abs(x) for a, c in zip(sums, sums[b:]) for x in ((c - a).real, (c - a).imag)]
            s = max(s, 1.4826 * _q50(sorted(db)) / math.sqrt(2.0 * b))
        return max(self.min_sigma, s)

    # ------------------------------------------------------------ calibration

    def add_fix(self, t: float, east_m: float, north_m: float,
                offset: Optional[Tuple[float, float]] = None) -> None:
        """An independent (map) fix at its measurement instant t; offset: GPS - fix (east, north m) at
        that instant if known (the position to come back to after a refusal).
        """
        if not all(math.isfinite(v) for v in (t, east_m, north_m)):
            return
        if self._fixes and t <= self._fixes[-1][0]:
            return
        self._fixes.append((t, complex(east_m, north_m), offset))
        while self._fixes and t - self._fixes[0][0] > self.cal_window_s:
            self._fixes.popleft()
        self._calibrate()

    def _vo_track(self, times):
        """[(run id, cumulative VO position) or None] at each of times (ascending), by interpolation
        inside one step; None between runs or outside the track.
        """
        steps = list(self._steps)
        ends = [x[1] for x in steps]
        out = []
        for t in times:
            i = bisect.bisect_left(ends, t - 1e-6)
            if i < len(steps) and steps[i][0] - 1e-6 <= t:
                t0, t1, d, seg, cum = steps[i]
                w = 0.0 if t1 <= t0 else min(1.0, max(0.0, (t - t0) / (t1 - t0)))
                out.append((seg, cum - d * (1.0 - w)))
            else:
                out.append(None)
        return out

    @staticmethod
    def _fit(runs, decorr_s):
        """(c, 1-sigma of c, VO spread m, fixes kept) of fix = b_run + c x VO over runs {id: [(t, fix, vo)]},
        or None. Fixes off by more than 3 x the robust residual are left out (wrong matches).
        """
        keep = {s: pts for s, pts in runs.items() if len(pts) >= 2}
        best = None
        for _ in range(3):
            num, den, res = 0j, 0.0, []
            means = {}
            for s, pts in keep.items():
                means[s] = (sum(x[2] for x in pts) / len(pts), sum(x[1] for x in pts) / len(pts))
                for _, p, v in pts:
                    num += (v - means[s][0]).conjugate() * (p - means[s][1])
                    den += abs(v - means[s][0]) ** 2
            if den <= 0.0:
                break
            c, spread = num / den, math.sqrt(den)
            for s, pts in keep.items():
                mv, mp = means[s]
                res += [(s, i, abs(p - mp - c * (v - mv))) for i, (_, p, v) in enumerate(pts)]
            sig_axis = max(_q50(sorted(r for _, _, r in res)) / 1.1774, 1e-3)   # Rayleigh median
            dur = sum(pts[-1][0] - pts[0][0] for pts in keep.values())
            n_eff = max(1.0, min(len(res), dur / decorr_s + len(keep)))
            best = (c, sig_axis / spread * math.sqrt(len(res) / n_eff), spread, len(res))
            bad = {(s, i) for s, i, r in res if r > 3.0 * 1.4826 * sig_axis}
            if not bad:
                break
            keep = {s: [x for i, x in enumerate(pts) if (s, i) not in bad] for s, pts in keep.items()}
            keep = {s: pts for s, pts in keep.items() if len(pts) >= 2}
        return best

    def _calibrate(self) -> None:
        """Learn c (VO -> ground) by least squares of the map fixes on the VO track (GPS plays no part).

        Inside each contiguous VO run, fix_j = b_run + c x VO(t_j) + e_j: one intercept per run (the
        map's bias and the run's VO origin cancel), one c for all. c's 1-sigma from the residual spread
        over the VO spread, the residuals counted one per calib_decorr_s (the map bias wanders slowly).
        eps (what is allowed of c's error) is eps_sigmas x that, at least eps_floor, and at least the
        difference with c fitted on the last calib_recent_s alone plus that one's sigma (the VO scale
        changes when the height it uses does: the window's c must not hide it).
        """
        fixes = list(self._fixes)
        track = self._vo_track([f[0] for f in fixes])
        runs, recent = {}, {}
        for (t, p, _), v in zip(fixes, track):
            if v is not None:
                runs.setdefault(v[0], []).append((t, p, v[1]))
                if fixes[-1][0] - t <= self.cal_recent_s:
                    recent.setdefault(v[0], []).append((t, p, v[1]))
        fit = self._fit(runs, self.cal_decorr_s)
        if fit is None or fit[2] < self.cal_min_m or abs(fit[0]) <= 0.0:
            self.gain = (1.0 + 0j, self.prior_eps, 0)
            return
        c = fit[0]
        eps = max(self.eps_floor, self.eps_sigmas * fit[1] / abs(c))
        rf = self._fit(recent, self.cal_decorr_s)
        if rf is not None and rf[2] >= self.cal_min_m:
            # the scale may have changed lately (the height the VO uses): what the recent c says
            # beyond the window's is allowed too
            eps = max(eps, (abs(rf[0] - c) + rf[1]) / abs(c))
        if eps >= self.prior_eps:
            self.gain = (1.0 + 0j, self.prior_eps, 0)
            return
        self.gain = (c, eps, fit[3])

    # ------------------------------------------------------------------ test

    def add_step(self, t0: float, t1: float, vo_east: float, vo_north: float,
                 gps_east: float, gps_north: float) -> Optional[str]:
        """One VO step (frame instants t0 -> t1, displacement east/north m) and the GPS displacement over
        the same instants. The refusal reason, or None.
        """
        if not all(math.isfinite(v) for v in (t0, t1, vo_east, vo_north, gps_east, gps_north)) or t1 <= t0:
            return None
        d = complex(vo_east, vo_north)
        if self._vo_outlier(d / (t1 - t0)):
            self.skipped += 1
            self.last = {"t": t1, "skipped": "odometry off its own recent velocity"}
            return None                                  # not chained either: the VO track breaks here
        if self._steps and abs(self._steps[-1][1] - t0) < 1e-3:
            seg, cum = self._steps[-1][3], self._steps[-1][4] + d
        elif self._steps and t0 < self._steps[-1][1]:
            return None                                  # out of order
        else:
            self._seg += 1
            seg, cum = self._seg, d
        self._steps.append((t0, t1, d, seg, cum))
        while self._steps and t1 - self._steps[0][1] > self.cal_window_s:
            self._steps.popleft()
        return self._test(t0, t1, d, complex(gps_east, gps_north))

    def _vo_outlier(self, v: complex) -> bool:
        """A step whose velocity is far from the median of the last accepted ones (a lock on what does
        not move in the image reads ~0 at speed; a wrong correlation peak reads anything). Judged on the
        odometry alone, so the calibration never depends on GPS; after 3 refusals in a row the
        velocity is taken as it is (the vehicle did change speed).
        """
        if len(self._vrec) >= 3:
            vm = complex(_q50(sorted(x.real for x in self._vrec)), _q50(sorted(x.imag for x in self._vrec)))
            if abs(v - vm) > max(self.gross_mps, self.gross_frac * abs(vm)) and self._vrej < 3:
                self._vrej += 1
                return True
        if self._vrej >= 3:
            self._vrec.clear()
        self._vrej = 0
        self._vrec.append(v)
        return False

    def _test(self, t0, t1, d, g) -> Optional[str]:
        dt = t1 - t0
        c, eps, _ = self.gain
        v = c * d
        r = g - v
        lock = abs(v) < self.lock_frac * abs(g) and abs(g) > self.lock_min
        gross = abs(r) > max(self.gross_mps * dt, self.gross_frac * abs(g))
        self.last = {"t": t1, "dt": dt, "resid_e": r.real, "resid_n": r.imag, "eps": eps,
                     "skipped": "static lock" if lock else ("gross" if gross else None)}
        if lock or gross:
            self.skipped += 1
            return None
        if self._last_used_t is not None and t0 - self._last_used_t > self.max_gap_s:
            self.reset()
        self._last_used_t = t1
        self.used += 1
        self._resid.append(r)
        sigma = self.sigma
        if sigma is None or (self.require_calibration and self.gain[2] == 0):
            return None
        allow = eps * abs(v) + self.bias_mps * dt
        clip = self.clip_sigmas * sigma + allow
        best = None
        for i, u in enumerate(self.dirs):
            p = r.real * u.real + r.imag * u.imag
            p = max(-clip, min(clip, p))
            s = self._s[i] + (p - allow) / sigma - self.k
            if s <= 0.0:
                self._s[i], self._m[i], self._t_start[i] = 0.0, 0.0, None
                continue
            if self._t_start[i] is None:
                self._t_start[i] = t0
            self._s[i] = s
            self._m[i] += p - allow
            if best is None or s > self._s[best]:
                best = i
        self.last.update(sigma=sigma, s_max=max(self._s))
        if best is None or self._s[best] < self.h or self._m[best] < self.min_growth:
            return None
        growth, since = self._m[best], self._t_start[best]
        u = self.dirs[best]
        rate = growth / max(t1 - since, 1e-3)
        offs = [o for t, _, o in self._fixes if o is not None and t <= since][-8:]
        base = (_q50(sorted(o[0] for o in offs)), _q50(sorted(o[1] for o in offs))) if offs else None
        self.reset()
        if base is not None:
            self.refused_baseline = (base[0], base[1], growth)
        heading = math.degrees(math.atan2(u.real, u.imag)) % 360.0
        return (f"GPS moved {growth:.0f} m more than visual odometry in {t1 - since:.0f} s "
                f"({rate:.1f} m/s towards {heading:.0f} deg, odometry noise {sigma:.1f} m/step, "
                f"scale/heading allowance {100 * eps:.0f} %)")

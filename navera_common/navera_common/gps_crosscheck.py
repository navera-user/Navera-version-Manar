"""Trusted GPS against an independent position of stated accuracy: when to refuse GPS.

One rule, used by the arbiter (navera_estimator) and by the bench (screen_flight), so the bench
measures what the product does. Pure Python, times in seconds.

A trusted GPS is refused ("possible spoofing") when the independent source
  * disagrees beyond 3 sigma at STREAK_N distinct measurements in a row (slow drift: caught
    before the wide window, while the autopilot has followed the GPS less far), or
  * disagrees beyond the wide tolerance (gps_crosscheck_sigmas x sigma + slack) for persist_s,
    with at least two distinct measurements (one wrong vision fix stays fresh for seconds).
  * or, with a GpsDriftTrend attached and the GPS-minus-fix offset given as a vector, when that
    offset GROWS steadily (slow spoofing: the trend is the signal, not the size of one sample;
    see GpsDriftTrend).
Two measurements in a row beyond 3 sigma, or one growth window passing, put GPS "in doubt"
(still used, accuracy widened).

False streak odds: for a 2-D Gaussian error with the stated per-axis sigma, P(r > 3 sigma) =
exp(-4.5) = 1.1 % per measurement (the 1-D figure, 0.27 %, does not apply to a distance);
STREAK_N = 5 independent ones in a row: 1.2e-2 ** 5 = 1.7e-10.
"""
import math
from collections import deque
from statistics import median
from typing import Optional, Sequence, Tuple

STREAK_N = 5


class GpsCrossCheck:
    """The refusal state of one trusted GPS against independent fixes."""

    def __init__(self, persist_s: float = 3.0, streak_n: int = STREAK_N, forget_s: float = 10.0,
                 trend: Optional["GpsDriftTrend"] = None):
        self.persist_s, self.streak_n, self.forget_s = persist_s, streak_n, forget_s
        self.trend = trend
        # (east, north, growth m) of the offset before a growth refusal: the GPS comes back only once
        # the offset has returned closer to it than half the growth (agreeing within 3 sigma is not
        # enough: the growth test refuses well inside 3 sigma). Kept across reset().
        self.baseline: Optional[Tuple[float, float, float]] = None
        self.reset()

    def reset(self) -> None:
        self._since: Optional[float] = None     # first disagreement beyond the wide tolerance
        self._refs = set()                      # distinct measurements disagreeing (wide)
        self.streak = set()                     # distinct measurements beyond 3 sigma in a row
        if self.trend is not None:
            self.trend.reset()

    def no_reference(self, t: float) -> None:
        """No independent fix this time: the disagreement is kept between fixes (vision checks every
        few seconds) and forgotten only when one agrees, or after forget_s.
        """
        if self._since is not None and t - self._since > self.forget_s + self.persist_s:
            self._since, self._refs = None, set()

    def update(self, t: float, d: float, tol: float, tol_strict: float, ref_id, name: str = "source",
               sample: Optional[Tuple[float, float, float, float]] = None) -> Optional[str]:
        """One independent measurement (ref_id distinguishes measurements) d metres from the GPS of its
        instant; tol / tol_strict: the wide and the 3-sigma tolerances. sample: (measurement time s,
        east m, north m, combined sigma m) of GPS minus that measurement, for the growth test (only
        when the GPS of the measurement's own instant is known). The refusal reason, or None.
        """
        trend_reason = None
        if self.trend is not None and sample is not None:
            trend_reason = self.trend.add(*sample, ref_id=ref_id)
        reason = self._size_rule(t, d, tol, tol_strict, ref_id, name)
        if reason is None and trend_reason is not None:
            reason = f"GPS drifting away from {name}: {trend_reason} — possible slow spoofing"
            self.baseline = self.trend.refused_baseline
        elif reason is not None:
            self.baseline = None
        if reason is not None:
            self.reset()
        return reason

    def back_to_baseline(self, sample: Optional[Tuple[float, float, float, float]]) -> bool:
        """After a growth refusal: True once the offset of sample (t, east, north, sigma) is back closer
        to the offset before the growth than half the growth. True when no growth refusal is pending;
        False without a sample (GPS of the fix's instant unknown).
        """
        if self.baseline is None:
            return True
        if sample is None:
            return False
        e, n, growth = self.baseline
        return math.hypot(sample[1] - e, sample[2] - n) <= 0.5 * growth

    def _size_rule(self, t, d, tol, tol_strict, ref_id, name) -> Optional[str]:
        """The 3-sigma streak and the wide-tolerance rules (the size of the disagreement)."""
        if d > tol_strict:
            self.streak.add(ref_id)
        else:
            self.streak = set()
        if len(self.streak) >= self.streak_n:
            return (f"GPS drifting away from {name}: {self.streak_n} independent fixes in a row "
                    f"beyond 3 sigma ({d:.0f} m apart now, 3 sigma {tol_strict:.0f} m) — possible spoofing")
        if d <= tol:
            self._since, self._refs = None, set()
            return None
        if self._since is None:
            self._since = t
        self._refs.add(ref_id)
        if t - self._since < self.persist_s or len(self._refs) < 2:
            return None
        return (f"GPS drifting away from {name}: {d:.0f} m apart for {self.persist_s:.0f} s "
                f"(tolerance {tol:.0f} m) — possible spoofing")

    @property
    def in_doubt(self) -> bool:
        """Two measurements in a row beyond 3 sigma, or the growth test passing (not confirmed yet)."""
        return len(self.streak) >= 2 or (self.trend is not None and self.trend.in_doubt)


# the 80th percentile of |r| for a 2-D Gaussian of per-axis sigma s is s * sqrt(2 ln 5): the jitter
# from it, not from the median, so a vision flipping between two candidate matches (a minority of
# fixes tens of metres away) widens the noise instead of hiding behind the majority
_P80_2D = math.sqrt(2.0 * math.log(5.0))
# standard error of a sample median / of a sample mean (Gaussian): sqrt(pi / 2)
_MEDIAN_EFF = math.sqrt(math.pi / 2.0)


def _median2(pts) -> Tuple[float, float]:
    return median(p[0] for p in pts), median(p[1] for p in pts)


class GpsDriftTrend:
    """Slow-spoof detector: the GROWTH of the GPS-minus-vision offset, not its size.

    A spoofer pulling GPS at v m/s makes the offset (GPS - independent fix, east/north metres)
    grow linearly at v; a good GPS leaves it at the vision error: a bias that wanders slowly and
    a frame-to-frame jitter, with now and then a wrong fix (or a run of them, a step). One sample
    per distinct independent fix, with the GPS position of that fix's instant.

    At each sample, for every window length in windows_s ending now, the window's fixes are cut in
    three parts (first quarter, middle half, last quarter, each at least min_part_fixes) and the
    robust (median) offset of each part compared:
      * growth G = |m3 - m1| (m1, m3: medians of the first and last quarter), direction u;
      * consistent growth: both halves (m2 - m1).u and (m3 - m2).u at least mono_frac x G — a
        step (a run of wrong fixes) or one outlier puts all the growth in one half: rejected;
      * significant: G - bias_rate_mps x dt >= z x its noise, the noise from the jitter measured
        around the line m1 -> m3 (80th percentile, floored at min_jitter_m), fixes decorrelated over
        decorr_s at most: a smooth vision tightens the test, a noisy one widens it on its own;
      * beyond what the sources admit: G - bias_rate_mps x dt >= min_growth_sigmas x the combined
        sigma (vision and GPS stated sigmas) — an offset change inside the stated accuracy is
        never a refusal;
      * each part holds >= min_part_fixes (3: the median of two is their mean, one wrong fix
        moves it) and the window >= min_fixes (several agreeing fixes).
    Refused when that holds at confirm_n distinct fixes in a row (a sequential test: one lucky
    window never refuses). Pure Python, times in seconds.
    """

    def __init__(self, windows_s: Sequence[float] = (8.0, 12.0, 16.0, 24.0, 32.0, 48.0, 64.0, 96.0, 128.0),
                 z: float = 6.0,
                 min_growth_sigmas: float = 1.5, bias_rate_mps: float = 0.2, min_jitter_m: float = 3.0,
                 decorr_s: float = 1.0, mono_frac: float = 0.25, min_fixes: int = 6, confirm_n: int = 3,
                 min_part_fixes: int = 3):
        self.windows_s = sorted(float(w) for w in windows_s if w > 0.0)
        self.z, self.min_growth_sigmas, self.bias_rate = z, min_growth_sigmas, bias_rate_mps
        self.min_jitter, self.decorr_s, self.mono_frac = min_jitter_m, decorr_s, mono_frac
        self.min_fixes, self.confirm_n = max(6, int(min_fixes)), max(1, int(confirm_n))
        self.min_part = max(2, int(min_part_fixes))
        self.reset()

    def reset(self) -> None:
        self._hist = deque()          # (t, east, north, combined sigma)
        self._ids = deque(maxlen=16)  # recent sample ids (one sample per independent fix)
        self.pending = 0              # windows passing at this many distinct fixes in a row
        self.last = None              # dict of the best window at the last sample (diagnostics)
        self.refused_baseline = None  # (east, north, growth m): the offset before the growth refused

    def add(self, t: float, east_m: float, north_m: float, sigma_m: float, ref_id=None) -> Optional[str]:
        """One independent fix at time t (its measurement instant), offset GPS - fix (east, north) m,
        sigma_m the combined 1-sigma of the two. The refusal reason, or None.
        """
        if ref_id is not None:
            if ref_id in self._ids:
                return None
            self._ids.append(ref_id)
        if not all(math.isfinite(v) for v in (t, east_m, north_m, sigma_m)):
            return None
        if self._hist and t <= self._hist[-1][0]:
            return None                # out of order: the windows assume time order
        self._hist.append((t, east_m, north_m, max(sigma_m, 0.0)))
        while self._hist and t - self._hist[0][0] > self.windows_s[-1]:
            self._hist.popleft()
        best = None
        prev_n = None
        for w in self.windows_s:
            pts = [p for p in self._hist if t - p[0] <= w]
            if len(pts) == prev_n:
                continue               # same fixes as the shorter window
            prev_n = len(pts)
            ev = self._window(pts)
            if ev is not None and (best is None or ev["score"] > best["score"]):
                best = ev
        self.last = best
        if best is None or not best["pass"]:
            self.pending = 0
            return None
        self.pending += 1
        if self.pending < self.confirm_n:
            return None
        self.pending = 0
        self._hist.clear()
        self.refused_baseline = (best["from_e"], best["from_n"], best["growth_m"])
        return (f"offset grew {best['growth_m']:.0f} m in {best['dt_s']:.0f} s ({best['rate_mps']:.1f} m/s, "
                f"{best['n']} fixes, {best['z']:.1f} x its noise, {best['sigmas']:.1f} x the stated sigma)")

    def _window(self, pts):
        """The evaluation of one window (dict, 'pass' and a score), or None if too few fixes."""
        if len(pts) < self.min_fixes:
            return None
        t0, t1 = pts[0][0], pts[-1][0]
        span = t1 - t0
        if span <= 0.0:
            return None
        k = max(self.min_part, len(pts) // 4)
        parts = (pts[:k], pts[k:len(pts) - k], pts[len(pts) - k:])
        if len(parts[1]) < self.min_part:
            return None
        m = [_median2([(p[1], p[2]) for p in x]) for x in parts]
        ta, tc = median(p[0] for p in parts[0]), median(p[0] for p in parts[2])
        dt = tc - ta
        ge, gn = m[2][0] - m[0][0], m[2][1] - m[0][1]
        growth = math.hypot(ge, gn)
        if dt <= 0.0 or growth <= 0.0:
            return None
        ue, un = ge / growth, gn / growth
        i1 = (m[1][0] - m[0][0]) * ue + (m[1][1] - m[0][1]) * un
        i2 = (m[2][0] - m[1][0]) * ue + (m[2][1] - m[1][1]) * un
        # jitter around the line m1 -> m3 (per axis, robust)
        res = [math.hypot(p[1] - m[0][0] - ge * (p[0] - ta) / dt, p[2] - m[0][1] - gn * (p[0] - ta) / dt)
               for p in pts]
        res.sort()
        jitter = max(res[int(0.8 * (len(res) - 1) + 0.5)] / _P80_2D, self.min_jitter)

        def n_eff(x):
            return max(1.0, min(len(x), (x[-1][0] - x[0][0]) / self.decorr_s + 1.0))
        noise = _MEDIAN_EFF * jitter * math.sqrt(1.0 / n_eff(parts[0]) + 1.0 / n_eff(parts[2]))
        sigma = median(p[3] for p in pts)
        excess = growth - self.bias_rate * dt
        z = excess / noise
        sigmas = excess / sigma if sigma > 0.0 else float("inf")
        mono = min(i1, i2) >= self.mono_frac * growth
        ok = mono and z >= self.z and sigmas >= self.min_growth_sigmas
        return {"pass": ok, "score": min(z / self.z, sigmas / max(self.min_growth_sigmas, 1e-9))
                if mono else -1.0, "growth_m": growth, "dt_s": dt, "rate_mps": growth / dt, "n": len(pts),
                "z": z, "sigmas": sigmas, "jitter_m": jitter, "monotone": mono,
                "from_e": m[0][0], "from_n": m[0][1]}

    @property
    def in_doubt(self) -> bool:
        """The growth test passed at the last fix but is not confirmed yet."""
        return self.pending >= 1

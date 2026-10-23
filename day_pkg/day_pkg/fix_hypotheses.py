"""A small multi-hypothesis track for the day output: two agreeing wrong fixes are not a position (D17).

The gap it closes (2026-10-23): while the carried position is uncertain (sigma 35-50 m, or lost) a
confident wrong match passes the 3-sigma gate, the track moves to it, and the next frame — the same
ground against the same map window, so the same wrong place, moving with the vehicle — agrees. The
consistency rules (day_pkg.fix_consistency) cannot tell such a pair from a real jump: both move with
the vehicle. Only the THIRD and later fixes can, and until they do the output must say it does not know.

Here, besides the current track (the "main" hypothesis: the carried position the caller predicts),
up to max_alts alternative hypotheses are kept, each as an OFFSET from the main track. All of them
are carried by the same carry (autopilot velocity, gyro, VO: whatever the caller's prediction uses),
so an offset stays an offset; when the main track is moved by a believed fix the offsets are moved
back by as much (accepted()).

- A fix is judged against the main track first: day_pkg.fix_consistency's doubt() (the gate), and,
  while the carried position is uncertain (ambiguous_sigma_m < sigma <= far_max_sigma_m), a fix
  further from it than far_k x its own sigma (far_floor_m: the carried error is unknown) and than
  far_min_m is "far". Beyond far_max_sigma_m (250 m; the output is unavailable past 300 m) an in-gate
  fix re-acquires as before: refusing them there cost 3 % availability on the recorded missions.
  Neither: believed (the alternatives lose a vote).
- A doubted or far fix that agrees with an alternative (carried) supports it; else it spawns one
  (the weakest is dropped beyond max_alts). The fix is refused.
- The hypotheses are scored on the fixes since the alternative appeared (the last hist_n, window_s):
  the log-likelihood of each fix under each, a Gaussian of the fix's sigma and the hypothesis' own
  (the main track: its carried sigma at that fix) mixed with an outlier floor (outlier_p over an
  outlier_radius_m disc: wrong matches happen). An alternative becomes the track only when at least switch_n fixes agree with it AND it
  leads every other hypothesis by switch_llr: two agreeing fixes alone never move the track. The old
  track is kept as an alternative then.
- An alternative is pruned prune_s after the last fix that agreed with it, or once prune_n fixes in a
  row were believed on the main track and it scores below it.
- While an alternative is alive the published sigma covers it (cover_sigma): 3 sigma reach it.

Pure Python: the day node (day_subscriber._check_local_fix) and the bench (VisionNavigator) use it.
"""
import math
from collections import deque
from typing import Optional, Tuple

M_PER_DEG = 111_320.0


def _en(p: Tuple[float, float], ref: Tuple[float, float]) -> Tuple[float, float]:
    return ((p[1] - ref[1]) * M_PER_DEG * math.cos(math.radians(ref[0])), (p[0] - ref[0]) * M_PER_DEG)


class FixHypotheses:
    """The main track's alternatives, as offsets (east, north m) from it."""

    def __init__(self, consistency, max_alts: int = 2, ambiguous_sigma_m: float = 30.0, far_k: float = 3.0,
                 far_floor_m: float = 15.0, far_min_m: float = 80.0, switch_n: int = 3, switch_llr: float = 5.0,
                 outlier_p: float = 0.05, outlier_radius_m: float = 600.0, window_s: float = 30.0,
                 hist_n: int = 10, prune_s: float = 20.0, prune_n: int = 3,
                 far_max_sigma_m: float = 250.0):
        self.cons = consistency
        self.max_alts, self.ambiguous_sigma_m = int(max_alts), ambiguous_sigma_m
        self.far_k, self.far_floor_m, self.far_min_m = far_k, far_floor_m, far_min_m
        self.far_max_sigma_m = far_max_sigma_m
        self.switch_n, self.switch_llr = max(3, int(switch_n)), switch_llr
        self.log_out = math.log(outlier_p / (math.pi * outlier_radius_m ** 2))
        self.log_in = math.log(1.0 - outlier_p)
        self.window_s, self.prune_s, self.prune_n = window_s, prune_s, int(prune_n)
        self.alts = []                      # dict(o=[de, dn], sig, t, n): an alternative track
        self.hist = deque(maxlen=int(hist_n))   # [t, de, dn, sig, carried sigma]: fixes, from the main track
        self._move = None                   # the residual of the fix just let through (accepted())
        self._main_run = 0                  # fixes believed on the main track in a row
        self.spawned = self.switched = self.refused = 0     # statistics

    # ── scoring ──────────────────────────────────────────────────────────
    def _ll(self, a, since: float) -> float:
        """Log-likelihood of the fixes since `since` under hypothesis a (None: the main track, its
        carried sigma at each fix; an alternative: its own sigma), robust (outlier floor)."""
        s = 0.0
        for t, de, dn, sig, P in self.hist:
            if t < since:
                continue
            o, sh = ((0.0, 0.0), P) if a is None else (a["o"], a["sig"])
            var = sig * sig + sh * sh
            m2 = ((de - o[0]) ** 2 + (dn - o[1]) ** 2) / var
            g = self.log_in - math.log(2.0 * math.pi * var) - 0.5 * m2
            s += max(g, self.log_out) + math.log1p(math.exp(-abs(g - self.log_out)))
        return s

    def _agrees(self, r, a, sig: float, t: float, speed: float) -> bool:
        gap = math.hypot(r[0] - a["o"][0], r[1] - a["o"][1])
        return gap <= max(3.0 * math.hypot(sig, a["sig"]), 15.0) + 0.3 * speed * max(0.0, t - a["t"])

    def _expire(self, t: float) -> None:
        while self.hist and t - self.hist[0][0] > self.window_s:
            self.hist.popleft()
        self.alts = [a for a in self.alts if t - a["t"] <= self.prune_s]

    # ── a fix ────────────────────────────────────────────────────────────
    def judge(self, t: float, lat: float, lon: float, sig: float, inliers: int, pred,
              vel: Optional[Tuple[float, float]]):
        """A fix at t against the carried position pred (lat, lon, sigma). (believe, why, switched):
        believe False — refused, why says so; switched True — an alternative won, the fix moves the
        track to it (a re-acquisition). When believed the caller calls accepted() once the track holds it."""
        self._move = None
        self._expire(t)
        r = _en((lat, lon), pred[:2])
        d, P = math.hypot(*r), float(pred[2])
        speed = math.hypot(*vel) if vel is not None else 0.0
        doubt = self.cons.doubt(d, P, sig, inliers)
        far = self.ambiguous_sigma_m < P <= self.far_max_sigma_m and d > max(self.far_k * math.hypot(sig, self.far_floor_m), self.far_min_m)
        entry = [t, r[0], r[1], sig, P]
        if doubt is None and not far:
            self.hist.append(entry)
            self._main_run += 1
            if self.alts and self._main_run >= self.prune_n:
                self.alts = [a for a in self.alts if self._ll(a, a["t0"]) > self._ll(None, a["t0"])]
            self._move = (r, sig)
            return True, None, False
        self._main_run = 0
        self.hist.append(entry)
        why = doubt or (f"{d:.0f} m from the carried position (±{P:.0f} m), its own sigma {sig:.0f} m: "
                        "ambiguous")
        best = None
        for a in self.alts:
            if self._agrees(r, a, sig, t, speed):
                g = math.hypot(r[0] - a["o"][0], r[1] - a["o"][1])
                if best is None or g < best[0]:
                    best = (g, a)
        if best is not None:
            a = best[1]
            w = a["sig"] ** -2 / (a["sig"] ** -2 + sig ** -2)
            a["o"] = [w * a["o"][0] + (1 - w) * r[0], w * a["o"][1] + (1 - w) * r[1]]
            a["sig"], a["t"], a["n"] = min(a["sig"], sig), t, a["n"] + 1
            lla = self._ll(a, a["t0"])
            others = [self._ll(None, a["t0"])] + [self._ll(b, a["t0"]) for b in self.alts if b is not a]
            lead = lla - max(others)
            if a["n"] >= self.switch_n and lead >= self.switch_llr:
                self.alts.remove(a)
                self.alts.append(dict(o=[0.0, 0.0], sig=P, t=t, t0=t, n=0))     # the old track, an alternative now
                self.alts = self.alts[-self.max_alts:]
                self.switched += 1
                self._move = (r, sig)
                return True, f"{why} — {a['n']} fixes agree with it, it leads the carried track by " \
                             f"{lead:.0f} (log-likelihood): re-acquired", True
            self.refused += 1
            return False, f"{why} — {a['n']} of {self.switch_n} agreeing fixes" + \
                ("" if a["n"] < self.switch_n else f", lead {lead:.1f} < {self.switch_llr:.0f}") + \
                ": rejected", False
        if len(self.alts) >= self.max_alts:
            self.alts.sort(key=lambda b: self._ll(b, b["t0"]) - self._ll(None, b["t0"]))
            self.alts.pop(0)
        self.alts.append(dict(o=[r[0], r[1]], sig=sig, t=t, t0=t, n=1))
        self.spawned += 1
        self.refused += 1
        return False, why + ": rejected (an alternative hypothesis now; agreeing fixes that lead would move to it)", False

    def accepted(self) -> None:
        """The fix judge() let through now holds the track (the carry restarts from it): the
        alternatives and the recent fixes are moved back by its residual."""
        if self._move is None:
            return
        (de, dn), sig = self._move
        self._move = None
        for a in self.alts:
            a["o"][0] -= de
            a["o"][1] -= dn
        for h in self.hist:
            h[1] -= de
            h[2] -= dn

    def cover_sigma(self, t: float, sigma_m: Optional[float]) -> Optional[float]:
        """The published sigma: 3 sigma reach every live alternative (it may be where the vehicle is)."""
        if sigma_m is None:
            return None
        s = sigma_m
        for a in self.alts:
            if t - a["t"] <= self.prune_s:
                s = max(s, (math.hypot(*a["o"]) + 2.0 * a["sig"]) / 3.0)
        return s

    def clear(self) -> None:
        """GPS (or a reset): one hypothesis again."""
        self.alts, self._move, self._main_run = [], None, 0
        self.hist.clear()

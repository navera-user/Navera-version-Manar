"""Is a day fix consistent with the track — and if not, has the next fix confirmed it? (F16, D17)

A matcher can be confidently wrong: on the 2026-10-19 hand-tilt bench run, 100-228 inliers placed
fixes 100-650 m off, and once such a fix is believed it keeps the small sigma of its inliers (4 m
with a 300 m error, D17): the following right fixes then look wrong against it. The rules here
decide, for one fix, against the position carried from the last fixes (dead reckoning, its sigma):

- **gate**: a fix further from the carried position than gate_k x the two sigmas combined is doubted.
  Strong fixes (>= strong_inliers) have their own factor strong_gate_k (6 until 2026-10-22: a
  strong fix 3-6 sigma off was believed at once).
- **re-acquisition** (the carried position is lost: sigma > lost_sigma_m, after a gap): the gate
  is then hundreds of metres wide and anything in it would be believed. A fix with few inliers
  (< weak_inliers), or one further from the carried position than reacq_k x its own sigma
  (with reacq_floor_m: the carried position's error is unknown, not zero) is doubted too: right
  after a gap, one confident match is not yet a position.
- **confirmation**: a doubted fix is kept pending; it is believed when a later fix (within
  confirm_s, confirm_lost_s while lost: frames match rarely after a gap) agrees with it, carried
  by the velocity: two independent matches in the same wrong place are much rarer than one. The
  confirming fix is believed as well (both say the track is what was wrong: re-acquired).

A fix the gate leaves alone clears the pending one. Nothing here blocks a re-acquisition: a right
fix after a long gap costs one more matched frame. Pure Python: the day node and the bench
(VisionNavigator) use the same rules.
"""
import math
from typing import Optional, Tuple

M_PER_DEG = 111_320.0


def _dist_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    de = (a[1] - b[1]) * M_PER_DEG * math.cos(math.radians(b[0]))
    dn = (a[0] - b[0]) * M_PER_DEG
    return math.hypot(de, dn)


def _carry(p: Tuple[float, float], ve: float, vn: float, dt: float) -> Tuple[float, float]:
    return (p[0] + vn * dt / M_PER_DEG, p[1] + ve * dt / (M_PER_DEG * math.cos(math.radians(p[0]))))


class FixConsistency:
    """The doubt rule and the pending fix awaiting confirmation."""

    def __init__(self, gate_k: float = 3.0, strong_inliers: int = 100, strong_gate_k: float = 3.0,
                 lost_sigma_m: float = 50.0, weak_inliers: int = 40, reacq_k: float = 3.0,
                 reacq_floor_m: float = 15.0, confirm_s: float = 6.0, confirm_lost_s: float = 20.0,
                 reacquire_check: bool = True):
        self.gate_k, self.strong_inliers, self.strong_gate_k = gate_k, strong_inliers, strong_gate_k
        self.lost_sigma_m, self.weak_inliers = lost_sigma_m, weak_inliers
        self.reacq_k, self.reacq_floor_m = reacq_k, reacq_floor_m
        self.confirm_s, self.confirm_lost_s = confirm_s, confirm_lost_s
        self.reacquire_check = reacquire_check
        self.pending = None           # (t, lat, lon, sigma, lost) of the last doubted fix
        self.doubted = 0              # fixes doubted (statistics)
        self.confirmed = 0            # of them believed once a second fix agreed

    def doubt(self, d_m: float, pred_sigma_m: float, sigma_m: float, inliers: int) -> Optional[str]:
        """Why a fix d_m from the carried position (sigma pred_sigma_m) is doubted, or None."""
        strong = inliers >= self.strong_inliers
        lim = (self.strong_gate_k if strong else self.gate_k) * math.hypot(pred_sigma_m, sigma_m)
        if d_m > lim:
            return (f"strong fix ({inliers} inliers) " if strong else "") + \
                f"{d_m:.0f} m from the carried position (> {lim:.0f} m, {inliers} inliers)"
        if pred_sigma_m > self.lost_sigma_m:
            if inliers < self.weak_inliers:
                return f"weak fix ({inliers} inliers) while the position is uncertain (±{pred_sigma_m:.0f} m)"
            lim = self.reacq_k * math.hypot(sigma_m, self.reacq_floor_m)
            if self.reacquire_check and d_m > lim:
                return (f"re-acquisition: {d_m:.0f} m from the carried position (±{pred_sigma_m:.0f} m), "
                        f"> {lim:.0f} m for its own sigma")
        return None

    def confirm(self, t: float, lat: float, lon: float, sigma_m: float,
                vel: Optional[Tuple[float, float]], lost: bool) -> bool:
        """A doubted fix at t: True when the pending one (an earlier doubted fix) agrees with it once
        carried by vel (east, north m/s; None: standing); else it becomes the pending one."""
        pend, self.pending = self.pending, (t, lat, lon, sigma_m, lost)
        self.doubted += 1
        if pend is None:
            return False
        dt = t - pend[0]
        window = self.confirm_lost_s if (lost or pend[4]) else self.confirm_s
        if not 0.0 < dt <= window:
            return False
        ve, vn = vel if vel is not None else (0.0, 0.0)
        gap = _dist_m((lat, lon), _carry(pend[1:3], ve, vn, dt))
        if gap <= max(3.0 * math.hypot(sigma_m, pend[3]), 15.0) + 0.3 * math.hypot(ve, vn) * dt:
            self.pending = None
            self.confirmed += 1
            return True
        return False

    def clear(self) -> None:
        """A fix the gate believed (or GPS): nothing is pending any more."""
        self.pending = None

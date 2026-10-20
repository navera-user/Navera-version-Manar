"""Trusted GPS against an independent position of stated accuracy: when to refuse GPS.

One rule, used by the arbiter (navera_estimator) and by the bench (screen_flight), so the bench
measures what the product does. Pure Python, times in seconds.

A trusted GPS is refused ("possible spoofing") when the independent source
  * disagrees beyond 3 sigma at STREAK_N distinct measurements in a row (slow drift: caught
    before the wide window, while the autopilot has followed the GPS less far), or
  * disagrees beyond the wide tolerance (gps_crosscheck_sigmas x sigma + slack) for persist_s,
    with at least two distinct measurements (one wrong vision fix stays fresh for seconds).
Two measurements in a row beyond 3 sigma put GPS "in doubt" (still used, accuracy widened).

False streak odds: for a 2-D Gaussian error with the stated per-axis sigma, P(r > 3 sigma) =
exp(-4.5) = 1.1 % per measurement (the 1-D figure, 0.27 %, does not apply to a distance);
STREAK_N = 5 independent ones in a row: 1.2e-2 ** 5 = 1.7e-10.
"""
from typing import Optional

STREAK_N = 5


class GpsCrossCheck:
    """The refusal state of one trusted GPS against independent fixes."""

    def __init__(self, persist_s: float = 3.0, streak_n: int = STREAK_N, forget_s: float = 10.0):
        self.persist_s, self.streak_n, self.forget_s = persist_s, streak_n, forget_s
        self.reset()

    def reset(self) -> None:
        self._since: Optional[float] = None     # first disagreement beyond the wide tolerance
        self._refs = set()                      # distinct measurements disagreeing (wide)
        self.streak = set()                     # distinct measurements beyond 3 sigma in a row

    def no_reference(self, t: float) -> None:
        """No independent fix this time: the disagreement is kept between fixes (vision checks every
        few seconds) and forgotten only when one agrees, or after forget_s."""
        if self._since is not None and t - self._since > self.forget_s + self.persist_s:
            self._since, self._refs = None, set()

    def update(self, t: float, d: float, tol: float, tol_strict: float, ref_id, name: str = "source") -> Optional[str]:
        """One independent measurement (ref_id distinguishes measurements) d metres from the GPS of its
        instant; tol / tol_strict: the wide and the 3-sigma tolerances. The refusal reason, or None."""
        if d > tol_strict:
            self.streak.add(ref_id)
        else:
            self.streak = set()
        if len(self.streak) >= self.streak_n:
            reason = (f"GPS drifting away from {name}: {self.streak_n} independent fixes in a row "
                      f"beyond 3 sigma ({d:.0f} m apart now, 3 sigma {tol_strict:.0f} m) — possible spoofing")
            self.reset()
            return reason
        if d <= tol:
            self._since, self._refs = None, set()
            return None
        if self._since is None:
            self._since = t
        self._refs.add(ref_id)
        if t - self._since < self.persist_s or len(self._refs) < 2:
            return None
        reason = (f"GPS drifting away from {name}: {d:.0f} m apart for {self.persist_s:.0f} s "
                  f"(tolerance {tol:.0f} m) — possible spoofing")
        self.reset()
        return reason

    @property
    def in_doubt(self) -> bool:
        """Two measurements in a row beyond 3 sigma."""
        return len(self.streak) >= 2

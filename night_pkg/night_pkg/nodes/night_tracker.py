"""Night track state: the anchor (last retained position), the motion gate and dead reckoning.

Pure Python (no ROS): night_subscriber delegates to it, and the track bench
(navera_tools/bench/night_track.py) runs the very same logic offline. Times are
seconds on one clock (the node uses wall time, the bench simulated time).

The anchor is the last position the node retained: GPS (vetted by the arbiter), a
night STHN fix, or a dead-reckoned position. A night fix is accepted only if it lies
within the distance the vehicle can have travelled since the last MEASURED position
(max_speed_mps x elapsed + gate_margin_m; dead reckoning does not reset that clock, B16)
and, alone, not farther than max_single_jump_m from the anchor: STHN can return a
confident wrong place.
"""
import math
from typing import Optional, Tuple

from navera_common.geo import dead_reckon, haversine_m

LatLon = Tuple[float, float]


class NightTracker:
    """Anchor + motion gate + dead reckoning of the night pipeline."""

    def __init__(self, max_speed_mps: float = 30.0, gate_margin_m: float = 30.0,
                 max_dead_reckon_s: float = 30.0, max_single_jump_m: Optional[float] = 150.0,
                 reacquire_n: int = 3, reacquire_window_s: float = 10.0,
                 reacquire_confirmed_n: int = 5, dead_reckon_rel_err: float = 0.1,
                 fresh_s: float = 3.0, support_cap: int = 15):
        """max_single_jump_m: a fix farther than this from the anchor is never taken on
        its own, even when the gate's reach (which grows while no fix comes) would allow
        it; it needs reacquire_n mutually consistent fixes (None: no limit).
        reacquire_n / reacquire_window_s: that many consecutive fixes refused by the gate
        within the window that agree with each other (along the measured motion)
        re-anchor the track — the way out of a wrong anchor (B16). An anchor confirmed by
        reacquire_n agreeing fixes in a row (or GPS) needs reacquire_confirmed_n.
        dead_reckon_rel_err: share of the dead-reckoned distance added to max_single_jump_m
        (the dead-reckoned anchor drifts).
        fresh_s / support_cap: a consensus that starts within fresh_s of the last measured
        position contradicts a track that was just confirmed: it must outnumber that track's
        own recent agreeing fixes (counted up to support_cap) — a burst of mutually consistent
        wrong matches (a repetitive pattern, a locked wrong lock) no longer re-anchors the track
        (D22). After a gap (dead reckoning) the plain reacquire_* counts apply (B16).
        """
        self.max_speed_mps = float(max_speed_mps)
        self.gate_margin_m = float(gate_margin_m)
        self.max_dead_reckon_s = float(max_dead_reckon_s)
        self.max_single_jump_m = None if max_single_jump_m is None else float(max_single_jump_m)
        self.reacquire_n = int(reacquire_n)
        self.reacquire_confirmed_n = max(int(reacquire_confirmed_n), self.reacquire_n)
        self.reacquire_window_s = float(reacquire_window_s)
        self.dead_reckon_rel_err = float(dead_reckon_rel_err)
        self.fresh_s = float(fresh_s)
        self.support_cap = max(int(support_cap), self.reacquire_confirmed_n)
        self.reset()

    # ── state ──────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Forget the track (mission rewind)."""
        self.anchor: Optional[LatLon] = None
        self.anchor_time: Optional[float] = None
        self.last_measured_time: Optional[float] = None
        self.measured: Optional[LatLon] = None     # the last measured position (GPS / night fix)
        self.gps_lost_at: Optional[float] = None
        self._dr_m = 0.0                 # distance dead-reckoned since the last measured position
        self._candidates = []            # fixes refused by the gate: (t, lat, lon, heading, speed)
        self.reacquired_from: Optional[LatLon] = None
        self._support = 0                # measured positions in a row that agree with the anchor
        self._support_long = 0           # the same, counted up to support_cap

    @property
    def has_anchor(self) -> bool:
        return self.anchor is not None

    @property
    def support(self) -> int:
        """Measured positions in a row that agree with the anchor (capped)."""
        return self._support

    def set_known(self, lat: float, lon: float, t: float) -> None:
        """A measured position from GPS (or replayed ground truth) becomes the anchor."""
        self._measured(lat, lon, t, support=self.reacquire_confirmed_n)
        self.gps_lost_at = None

    def _measured(self, lat: float, lon: float, t: float, support: int) -> None:
        self.anchor, self.anchor_time = (float(lat), float(lon)), float(t)
        self.last_measured_time = float(t)
        self.measured = (float(lat), float(lon))
        self._dr_m = 0.0
        self._candidates = []
        self._support = min(int(support), self.reacquire_confirmed_n)
        self._support_long = min(int(support), self.support_cap)
        self.reacquired_from = None      # the anchor a consensus replaced (this frame)

    def note_gps_lost(self, t: float) -> None:
        """First frame localised without GPS: remember when GPS stopped being the anchor."""
        if self.gps_lost_at is None:
            self.gps_lost_at = float(t)

    # ── per frame ──────────────────────────────────────────────────────────
    def search_centre(self, exposure_s: Optional[float], heading_deg, speed_mps) -> Optional[LatLon]:
        """The anchor carried to the frame's exposure along the measured motion (the
        anchor can be seconds stale); the anchor itself without measured motion.
        """
        if self.anchor is None:
            return None
        if exposure_s and self.anchor_time is not None:
            carried = dead_reckon(self.anchor[0], self.anchor[1], heading_deg, speed_mps,
                                  max(0.0, float(exposure_s) - self.anchor_time))
            if carried is not None:
                return carried
        return self.anchor

    def gate(self, lat: float, lon: float, t: float) -> Optional[str]:
        """None if a fix at (lat, lon) is reachable, else the reason.

        Reach: from the last MEASURED position (GPS or a night fix), max_speed_mps x the time
        since it + gate_margin_m — the distance the vehicle can have flown. Dead reckoning does
        not reset this clock (B16): it used to move the anchor and its time to every refused
        frame, so after one wrong fix the reach stayed ~1 s wide around the dead-reckoned wrong
        track and refused the true position until dead reckoning expired. The single-jump
        limit is still measured from the anchor (the dead-reckoned prediction): a fix far from
        where the track expects the vehicle is never taken alone.
        """
        if self.anchor is None or self.anchor_time is None:
            return None
        ref = self.measured if self.measured is not None else self.anchor
        t_ref = self.last_measured_time if self.last_measured_time is not None else self.anchor_time
        dist = haversine_m(ref[0], ref[1], lat, lon)
        elapsed = max(0.0, t - t_ref)
        reach = self.max_speed_mps * elapsed + self.gate_margin_m
        if dist > reach:
            return (f"implausible jump {dist:.0f} m in {elapsed:.1f} s since the last measured "
                    f"position (max {reach:.0f} m) — rejected, retrying from the last position")
        jump = haversine_m(self.anchor[0], self.anchor[1], lat, lon)
        limit = (None if self.max_single_jump_m is None
                 else self.max_single_jump_m + self.dead_reckon_rel_err * self._dr_m)
        if limit is not None and jump > limit:
            return (f"jump {jump:.0f} m from the track after {elapsed:.0f} s without a fix (> "
                    f"{limit:.0f} m): needs {self.reacquire_n} agreeing fixes")
        return None

    def offer(self, lat: float, lon: float, t: float, heading_deg=None, speed_mps=None) -> Optional[str]:
        """A night fix: accepted as the new anchor (returns None) or refused (the reason).

        A refused fix is kept as a candidate: when the last reacquire_n candidates
        (within reacquire_window_s) agree with each other, carried along the measured
        motion, the newest one re-anchors the track. One wrong fix that got in (e.g.
        after a long gap, when the reach is wide) then no longer locks the track while
        dead reckoning keeps the reach tight (B16), and a correct fix far from a drifted
        anchor is taken once it is confirmed.
        """
        why = self.gate(lat, lon, t)
        if why is None:
            # a fix after a long gap does not confirm the old anchor: support restarts
            recent = (self.last_measured_time is not None
                      and t - self.last_measured_time <= self.reacquire_window_s)
            self._measured(lat, lon, t, support=self._support_long + 1 if recent else 1)
            return None
        self._candidates = [c for c in self._candidates if t - c[0] <= self.reacquire_window_s]
        self._candidates.append((float(t), float(lat), float(lon), heading_deg, speed_mps))
        need = self.reacquire_confirmed_n if self._support >= self.reacquire_n else self.reacquire_n
        if (need >= 2 and len(self._candidates) >= need and self.last_measured_time is not None
                and self._candidates[-need][0] - self.last_measured_time <= self.fresh_s
                and self._support_long >= need):
            need = self._support_long + 1         # a fresh, well-supported track: outnumber it
        if need >= 2 and self._consistent(self._candidates[-need:], need):
            prev = self.anchor
            self._measured(lat, lon, t, support=need)
            self.reacquired_from = prev
            return None
        return why

    def _consistent(self, cands, need: int) -> bool:
        """`need` fixes, each where the previous one predicts it (measured motion, else
        anywhere within max speed), within the gate margin + 10 % of the motion.
        """
        if len(cands) < need:
            return False
        for a, b in zip(cands, cands[1:]):
            dt = b[0] - a[0]
            if dt <= 0.0:
                return False
            pred = dead_reckon(a[1], a[2], a[3], a[4], dt)
            if pred is not None:
                tol = self.gate_margin_m + 0.1 * float(a[4]) * dt
            else:
                pred, tol = (a[1], a[2]), self.gate_margin_m + self.max_speed_mps * dt
            if haversine_m(pred[0], pred[1], b[1], b[2]) > tol:
                return False
        return True

    def coast(self, t: float, heading_deg, speed_mps) -> Optional[LatLon]:
        """No fix this frame: dead-reckon the anchor along the measured motion, only for
        max_dead_reckon_s after the last measured position; None when not possible.
        """
        if (self.anchor is None or self.last_measured_time is None
                or t - self.last_measured_time > self.max_dead_reckon_s):
            return None
        p = dead_reckon(self.anchor[0], self.anchor[1], heading_deg, speed_mps,
                        t - self.anchor_time)
        if p is not None:
            self._dr_m += float(speed_mps) * (t - self.anchor_time)
            self.anchor, self.anchor_time = p, float(t)
        return p

    def seconds_since_gps_lost(self, t: float) -> float:
        return math.inf if self.gps_lost_at is None else t - self.gps_lost_at

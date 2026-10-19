"""Night track state: the anchor (last retained position), the motion gate and dead reckoning.

Pure Python (no ROS): night_subscriber delegates to it, and the track bench
(navera_tools/bench/night_track.py) runs the very same logic offline. Times are
seconds on one clock (the node uses wall time, the bench simulated time).

The anchor is the last position the node retained: GPS (vetted by the arbiter), a
night STHN fix, or a dead-reckoned position. A night fix is accepted only if it lies
within the distance the vehicle can have travelled since the anchor
(max_speed_mps x elapsed + gate_margin_m): STHN can return a confident wrong place.
"""
import math
from typing import Optional, Tuple

from navera_common.geo import dead_reckon, haversine_m

LatLon = Tuple[float, float]


class NightTracker:
    """Anchor + motion gate + dead reckoning of the night pipeline."""

    def __init__(self, max_speed_mps: float = 30.0, gate_margin_m: float = 30.0,
                 max_dead_reckon_s: float = 30.0):
        self.max_speed_mps = float(max_speed_mps)
        self.gate_margin_m = float(gate_margin_m)
        self.max_dead_reckon_s = float(max_dead_reckon_s)
        self.reset()

    # ── state ──────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Forget the track (mission rewind)."""
        self.anchor: Optional[LatLon] = None
        self.anchor_time: Optional[float] = None
        self.last_measured_time: Optional[float] = None
        self.gps_lost_at: Optional[float] = None

    @property
    def has_anchor(self) -> bool:
        return self.anchor is not None

    def set_known(self, lat: float, lon: float, t: float) -> None:
        """A measured position from GPS (or replayed ground truth) becomes the anchor."""
        self.anchor, self.anchor_time = (float(lat), float(lon)), float(t)
        self.last_measured_time = float(t)
        self.gps_lost_at = None

    def note_gps_lost(self, t: float) -> None:
        """First frame localised without GPS: remember when GPS stopped being the anchor."""
        if self.gps_lost_at is None:
            self.gps_lost_at = float(t)

    # ── per frame ──────────────────────────────────────────────────────────
    def search_centre(self, exposure_s: Optional[float], heading_deg, speed_mps) -> Optional[LatLon]:
        """The anchor carried to the frame's exposure along the measured motion (the
        anchor can be seconds stale); the anchor itself without measured motion."""
        if self.anchor is None:
            return None
        if exposure_s and self.anchor_time is not None:
            carried = dead_reckon(self.anchor[0], self.anchor[1], heading_deg, speed_mps,
                                  max(0.0, float(exposure_s) - self.anchor_time))
            if carried is not None:
                return carried
        return self.anchor

    def gate(self, lat: float, lon: float, t: float) -> Optional[str]:
        """None if a fix at (lat, lon) is reachable from the anchor, else the reason."""
        if self.anchor is None or self.anchor_time is None:
            return None
        jump = haversine_m(self.anchor[0], self.anchor[1], lat, lon)
        elapsed = max(0.0, t - self.anchor_time)
        reach = self.max_speed_mps * elapsed + self.gate_margin_m
        if jump > reach:
            return (f"implausible jump {jump:.0f} m in {elapsed:.1f} s "
                    f"(max {reach:.0f} m) — rejected, retrying from the last position")
        return None

    def offer(self, lat: float, lon: float, t: float, heading_deg=None, speed_mps=None) -> Optional[str]:
        """A night fix: accepted as the new anchor (returns None) or refused (the reason)."""
        why = self.gate(lat, lon, t)
        if why is None:
            self.anchor, self.anchor_time = (float(lat), float(lon)), float(t)
            self.last_measured_time = float(t)
        return why

    def coast(self, t: float, heading_deg, speed_mps) -> Optional[LatLon]:
        """No fix this frame: dead-reckon the anchor along the measured motion, only for
        max_dead_reckon_s after the last measured position; None when not possible."""
        if (self.anchor is None or self.last_measured_time is None
                or t - self.last_measured_time > self.max_dead_reckon_s):
            return None
        p = dead_reckon(self.anchor[0], self.anchor[1], heading_deg, speed_mps,
                        t - self.anchor_time)
        if p is not None:
            self.anchor, self.anchor_time = p, float(t)
        return p

    def seconds_since_gps_lost(self, t: float) -> float:
        return math.inf if self.gps_lost_at is None else t - self.gps_lost_at

"""The mission-area guard's message to the autopilot / ground station (MAVLink STATUSTEXT).

navera_estimator reports in NavStatus how far the vehicle is from the edge of the mission's map
(map_area, map_edge_m: navera_common.map_area). Past that edge day vision has nothing to match
and NAVERA soon gives no position at all. vehicle_output_node passes the flag on as a
STATUSTEXT, which the autopilot logs and forwards to the ground station (Mission Planner / QGC
show it to the operator): when it changes, and again every repeat_s while the vehicle stays
near or beyond the edge. NAVERA only reports: what to do (turn back, RTL, a geofence loaded
before flight — navera_tools/map_geofence.py) is the operator's and the autopilot's decision.
"""
import math
from typing import Optional, Tuple

# NavStatus.map_area (navera_msgs/NavStatus.msg)
UNKNOWN, INSIDE, NEAR_EDGE, OUTSIDE = 0, 1, 2, 3
# MAV_SEVERITY
SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_NOTICE = 2, 4, 5


class MapGuard:
    """Decides when to send the map-area STATUSTEXT (at most 50 characters)."""

    def __init__(self, repeat_s: float = 30.0):
        self.repeat_s = float(repeat_s)
        self._flag = None
        self._last_t = None

    def update(self, map_area: int, edge_m: float, t: float) -> Optional[Tuple[int, str]]:
        """(severity, text) to send now, or None. t: a monotonic clock (s)."""
        if map_area == UNKNOWN:
            return None                      # no map, no position: nothing to say
        changed = map_area != self._flag
        due = self._last_t is None or t - self._last_t >= self.repeat_s
        prev, self._flag = self._flag, map_area
        if map_area == INSIDE:
            if changed and prev in (NEAR_EDGE, OUTSIDE):
                self._last_t = t
                return SEVERITY_NOTICE, "NAVERA: back inside the map"
            return None
        if not (changed or due):
            return None
        self._last_t = t
        d = abs(edge_m) if math.isfinite(edge_m) else float("nan")
        if map_area == OUTSIDE:
            return SEVERITY_CRITICAL, f"NAVERA: {d:.0f} m OUTSIDE map, no vision fix"
        return SEVERITY_WARNING, f"NAVERA: map edge in {d:.0f} m"

"""Height of the camera above the ground (AGL), from the sources a vehicle may have.

Vision needs the height above the GROUND to know how much ground a frame covers.
Sources, best first:
  1. a measured height: rangefinder / lidar, or the vehicle's own AGL (autopilot over
     MAVLink or ROS) — `add_measured`;
  2. the image: each map match measures the height from its scale (`add_vision`);
     between matches it is carried by the GPS altitude change, or held with a growing
     uncertainty once GPS is lost;
  3. GPS altitude minus the ground altitude (the site's elevation, or the altitude of
     the first fix, taken as the ground at power-on) — `add_gps`.
`estimate(t)` returns (agl_m, sigma_m, source) or None.
"""
import math
from typing import Optional, Tuple

from navera_common.sensor_history import History


class AltitudeEstimator:
    def __init__(self, ground_altitude_m: Optional[float] = None, gps_sigma_m: float = 10.0,
                 measured_timeout_s: float = 1.0, vision_hold_s: float = 120.0,
                 vision_drift_mps: float = 0.5):
        self.ground = ground_altitude_m if ground_altitude_m is not None and math.isfinite(ground_altitude_m) else None
        self.ground_source = "configured" if self.ground is not None else None
        self.gps = History(max_gap_s=1.5)              # GPS altitude above the ellipsoid
        self.measured = History(max_gap_s=measured_timeout_s)
        self.gps_sigma_m = gps_sigma_m
        self.vision_hold_s, self.vision_drift_mps = vision_hold_s, vision_drift_mps
        self._vision: Optional[Tuple[float, float, float, Optional[float]]] = None   # t, agl, sigma, gps alt at t

    def add_gps(self, t: float, altitude_m: float) -> None:
        if not math.isfinite(altitude_m):
            return
        if self.ground is None:                         # power-on on the ground
            self.ground, self.ground_source = altitude_m, "first GPS fix"
        self.gps.add(t, altitude_m)

    def add_measured(self, t: float, agl_m: float, sigma_m: float = 1.0) -> None:
        if math.isfinite(agl_m) and agl_m > 0:
            self.measured.add(t, (agl_m, sigma_m))

    def add_vision(self, t: float, agl_m: float, sigma_m: float) -> None:
        """A height measured from a map match's scale."""
        if math.isfinite(agl_m) and agl_m > 0:
            self._vision = (t, agl_m, sigma_m, self.gps.at(t))

    def estimate(self, t: float) -> Optional[Tuple[float, float, str]]:
        m = self.measured.at(t)
        if m is not None:
            return m[0], m[1], "measured"
        gps_t = self.gps.at(t)
        if self._vision is not None and abs(t - self._vision[0]) <= self.vision_hold_s:
            tv, agl, sig, gps_tv = self._vision
            if gps_t is not None and gps_tv is not None:  # carried by the GPS altitude change
                return agl + (gps_t - gps_tv), math.hypot(sig, 2.0), "image + GPS"
            return agl, sig + self.vision_drift_mps * abs(t - tv), "image (held)"
        if gps_t is not None and self.ground is not None:
            return gps_t - self.ground, self.gps_sigma_m, "GPS - ground"
        return None

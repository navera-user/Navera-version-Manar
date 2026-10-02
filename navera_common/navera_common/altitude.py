"""Height of the camera above the ground (AGL), from the sources a vehicle may have.

Vision needs the height above the GROUND to know how much ground a frame covers.
Sources, best first:
  1. a measured height: rangefinder / lidar, or the vehicle's own height above terrain
     — `add_measured`;
  2. the image: each map match measures the height from its scale (`add_vision`);
     between matches it is carried by the change of a reference altitude (below), or
     held with a growing uncertainty when there is none;
  3. a reference altitude, assuming the ground stays at the reference's level (wrong
     over hills: the uncertainty grows with height):
       - the vehicle's height above its home (barometer, autopilot) — `add_relative`:
         it keeps working after GPS loss;
       - GPS altitude minus the ground altitude (site elevation, or the first fix,
         taken as the ground at power-on) — `add_gps`.
`estimate(t)` returns (agl_m, sigma_m, source) or None.
"""
import math
from typing import Dict, Optional, Tuple

from navera_common.sensor_history import History

REF_LABEL = {"vehicle": "vehicle altitude above home", "gps": "GPS - ground"}
CARRY_LABEL = {"vehicle": "image + vehicle altitude", "gps": "image + GPS"}


class AltitudeEstimator:
    def __init__(self, ground_altitude_m: Optional[float] = None, gps_sigma_m: float = 10.0,
                 relative_sigma_m: float = 3.0, terrain_fraction: float = 0.25,
                 measured_timeout_s: float = 1.0, vision_hold_s: float = 120.0,
                 vision_drift_mps: float = 0.5):
        self.ground = ground_altitude_m if ground_altitude_m is not None and math.isfinite(ground_altitude_m) else None
        self.ground_source = "configured" if self.ground is not None else None
        self.gps = History(max_gap_s=1.5)              # GPS altitude above the ellipsoid
        self.relative = History(max_gap_s=1.5)         # vehicle height above its home
        self.measured = History(max_gap_s=measured_timeout_s)
        # a reference altitude assumes the ground under the vehicle is at the reference's
        # level: over hills that is wrong by a fraction of the height
        self.sigma = {"gps": gps_sigma_m, "vehicle": relative_sigma_m}
        self.terrain_fraction = terrain_fraction
        self.vision_hold_s, self.vision_drift_mps = vision_hold_s, vision_drift_mps
        self._vision: Optional[Tuple[float, float, float, Dict[str, float]]] = None  # t, agl, sigma, refs at t

    def add_gps(self, t: float, altitude_m: float) -> None:
        if not math.isfinite(altitude_m):
            return
        if self.ground is None:                         # power-on on the ground
            self.ground, self.ground_source = altitude_m, "first GPS fix"
        self.gps.add(t, altitude_m)

    def add_relative(self, t: float, height_above_home_m: float) -> None:
        if math.isfinite(height_above_home_m):
            self.relative.add(t, height_above_home_m)

    def add_measured(self, t: float, agl_m: float, sigma_m: float = 1.0) -> None:
        if math.isfinite(agl_m) and agl_m > 0:
            self.measured.add(t, (agl_m, sigma_m))

    def add_vision(self, t: float, agl_m: float, sigma_m: float) -> None:
        """A height measured from a map match's scale."""
        if math.isfinite(agl_m) and agl_m > 0:
            self._vision = (t, agl_m, sigma_m, self._refs(t))

    def _refs(self, t: float) -> Dict[str, float]:
        refs = {}
        r = self.relative.at(t)
        if r is not None:
            refs["vehicle"] = r
        g = self.gps.at(t)
        if g is not None and self.ground is not None:
            refs["gps"] = g - self.ground
        return refs

    def estimate(self, t: float) -> Optional[Tuple[float, float, str]]:
        m = self.measured.at(t)
        if m is not None:
            return m[0], m[1], "measured"
        refs = self._refs(t)
        if self._vision is not None and abs(t - self._vision[0]) <= self.vision_hold_s:
            tv, agl, sig, refs_v = self._vision
            for kind in ("vehicle", "gps"):             # carried by the same reference's change
                if kind in refs and kind in refs_v:
                    return agl + (refs[kind] - refs_v[kind]), math.hypot(sig, 2.0), CARRY_LABEL[kind]
            return agl, sig + self.vision_drift_mps * abs(t - tv), "image (held)"
        for kind in ("vehicle", "gps"):
            if kind in refs:
                agl = refs[kind]
                return agl, math.hypot(self.sigma[kind], self.terrain_fraction * abs(agl)), REF_LABEL[kind]
        return None

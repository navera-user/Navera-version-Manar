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
from typing import Callable, Dict, Optional, Tuple

from navera_common.geo import haversine_m
from navera_common.sensor_history import History

REF_LABEL = {"vehicle": "vehicle altitude above home", "gps": "GPS - ground"}
CARRY_LABEL = {"vehicle": "image + vehicle altitude", "gps": "image + GPS"}


class AltitudeEstimator:
    def __init__(self, ground_altitude_m: Optional[float] = None, gps_sigma_m: float = 10.0,
                 relative_sigma_m: float = 3.0, terrain_fraction: float = 0.02,
                 terrain_sigma_m: float = 30.0,
                 measured_timeout_s: float = 1.0, vision_hold_s: float = 120.0,
                 vision_drift_mps: float = 0.5, ref_hold_s: float = 300.0,
                 saved_ground: Optional[dict] = None, on_ground: Optional[Callable[[dict], None]] = None):
        """saved_ground: {altitude_m, lat, lon} written by a previous run (on_ground is
        called with that dict whenever the ground altitude is (re)determined): reused after
        a restart in the same place — in the air the first fix is NOT the ground."""
        self.ground = ground_altitude_m if ground_altitude_m is not None and math.isfinite(ground_altitude_m) else None
        self.ground_source = "configured" if self.ground is not None else None
        self._saved_ground, self._on_ground = saved_ground, on_ground
        self.gps = History(max_gap_s=1.5)              # GPS altitude above the ellipsoid
        self.relative = History(max_gap_s=1.5)         # vehicle height above its home
        self.measured = History(max_gap_s=measured_timeout_s)
        # a reference altitude assumes the ground under the vehicle is at the reference's
        # level: over hills that is wrong by the relief (terrain_sigma_m, metres — relief does
        # not grow with the flight height) plus a small fraction of the height. (It was 25 %
        # of the height: no reference could ever pass night vision's 15 % gate — 2026-10-07.)
        self.sigma = {"gps": gps_sigma_m, "vehicle": relative_sigma_m}
        self.terrain_fraction, self.terrain_sigma_m = terrain_fraction, terrain_sigma_m
        self.vision_hold_s, self.vision_drift_mps = vision_hold_s, vision_drift_mps
        # a reference that stops (GPS jammed, box without barometer) is held: vehicles
        # mostly keep their altitude; the uncertainty grows like an image height held
        self.ref_hold_s = ref_hold_s
        self._vision: Optional[Tuple[float, float, float, Dict[str, float]]] = None  # t, agl, sigma, refs at t

    def add_gps(self, t: float, altitude_m: float, lat: Optional[float] = None,
                lon: Optional[float] = None) -> None:
        if not math.isfinite(altitude_m):
            return
        self.gps.add(t, altitude_m)
        if self._ground_from_home(t):
            return
        if self.ground is None:
            s = self._saved_ground
            if s is not None and lat is not None and lon is not None and \
                    haversine_m(lat, lon, s["lat"], s["lon"]) < 2000.0:
                # a restart (in the air or not) near where the ground was taken
                self.ground, self.ground_source = float(s["altitude_m"]), "saved ground (restart)"
            else:                                       # power-on on the ground
                self.ground, self.ground_source = altitude_m, "first GPS fix"
                if self._on_ground and lat is not None and lon is not None:
                    self._on_ground(dict(altitude_m=altitude_m, lat=lat, lon=lon))

    def add_relative(self, t: float, height_above_home_m: float) -> None:
        if math.isfinite(height_above_home_m):
            self.relative.add(t, height_above_home_m)
            self._ground_from_home(t)

    def _ground_from_home(self, t: float) -> bool:
        """With the vehicle's height above its home AND a GPS altitude at the same instant,
        the home ground is GPS - height, right even when NAVERA starts in the air."""
        if self.ground_source == "configured":
            return False
        g, r = self.gps.at(t), self.relative.at(t)
        if g is None or r is None:
            return False
        self.ground, self.ground_source = g - r, "GPS - height above home"
        return True

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
                return agl, self._ref_sigma(kind, agl), REF_LABEL[kind]
        held = self._held_ref(t)
        if held is not None:
            agl, age, kind = held
            sigma = self._ref_sigma(kind, agl) + self.vision_drift_mps * age
            return agl, sigma, REF_LABEL[kind] + " (held)"
        return None

    def _ref_sigma(self, kind: str, agl: float) -> float:
        return math.sqrt(self.sigma[kind] ** 2 + self.terrain_sigma_m ** 2 + (self.terrain_fraction * agl) ** 2)

    def _held_ref(self, t: float):
        """The last reference value before t, if not older than ref_hold_s."""
        best = None
        for kind, hist, offset in (("vehicle", self.relative, 0.0),
                                   ("gps", self.gps, self.ground if self.ground is not None else None)):
            last = hist.latest()
            if last is None or offset is None or not (0.0 <= t - last[0] <= self.ref_hold_s):
                continue
            cand = (last[1] - offset, t - last[0], kind)
            if best is None or cand[1] < best[1]:
                best = cand
        return best

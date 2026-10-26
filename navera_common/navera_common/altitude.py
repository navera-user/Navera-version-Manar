"""Height of the camera above the ground (AGL), from the sources a vehicle may have.

Vision needs the height above the GROUND to know how much ground a frame covers.
Sources, best first:
  1. a measured height: rangefinder / lidar, or the vehicle's own height above terrain
     — `add_measured`;
  2. the image: each map match measures the height from its scale (`add_vision`);
     between matches it is carried by the change of a reference altitude (below), or
     held with a growing uncertainty when there is none;
  3. with the corridor's DEM (navera_common.terrain, stored with the map) and the vehicle's
     position (`set_terrain`, `add_position`): the reference altitude below minus the terrain
     height under the position, both relative to the home ground. The DEM's datum is tied to
     the reference by anchors: the home position (`set_home`, or the first GPS fix on the
     ground) and every image height (2.) taken where the position is known. Used when its
     uncertainty (anchor, DEM, slope x position sigma) is below the other sources';
  4. a reference altitude, assuming the ground stays at the reference's level (wrong
     over hills: the uncertainty grows with height):
       - the vehicle's height above its home (barometer, autopilot) — `add_relative`:
         it keeps working after GPS loss;
       - GPS altitude minus the ground altitude (site elevation, or the first fix,
         taken as the ground at power-on) — `add_gps`.
`estimate(t)` returns (agl_m, sigma_m, source) or None.
"""
import math
from collections import deque
from typing import Callable, Dict, Optional, Tuple

from navera_common.geo import haversine_m
from navera_common.sensor_history import History

REF_LABEL = {"vehicle": "vehicle altitude above home", "gps": "GPS - ground"}
CARRY_LABEL = {"vehicle": "image + vehicle altitude", "gps": "image + GPS"}
DEM_LABEL = {"vehicle": "vehicle altitude - DEM", "gps": "GPS - DEM"}


def _valid_ground(s) -> Optional[dict]:
    """A saved ground {altitude_m, lat, lon} with finite numbers, else None (a damaged state file
    after a power cut must not stop the altitude: the first GPS fix is used instead)."""
    if not isinstance(s, dict):
        return None
    try:
        out = {k: float(s[k]) for k in ("altitude_m", "lat", "lon")}
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in out.values()) or abs(out["lat"]) > 90 or abs(out["lon"]) > 180:
        return None
    return out


class AltitudeEstimator:
    def __init__(self, ground_altitude_m: Optional[float] = None, gps_sigma_m: float = 10.0,
                 relative_sigma_m: float = 3.0, terrain_fraction: float = 0.02,
                 terrain_sigma_m: float = 30.0,
                 measured_timeout_s: float = 1.0, vision_hold_s: float = 120.0,
                 vision_drift_mps: float = 0.5, ref_hold_s: float = 300.0,
                 terrain_rate_mps: float = 1.0,
                 saved_ground: Optional[dict] = None, on_ground: Optional[Callable[[dict], None]] = None,
                 terrain=None, position_max_age_s: float = 60.0, home_sigma_m: float = 1.0,
                 position_point_sigma_m: float = 20.0):
        """saved_ground: {altitude_m, lat, lon} written by a previous run (on_ground is
        called with that dict whenever the ground altitude is (re)determined): reused after
        a restart in the same place — in the air the first fix is NOT the ground.
        terrain: a navera_common.terrain.Terrain (the corridor's DEM) or None; positions older
        than position_max_age_s are not used for it (younger ones are moved on at their velocity,
        their sigma growing); home_sigma_m: how far the home ground may be from the DEM's surface
        besides the DEM's own sigma; above position_point_sigma_m the ground is the DEM's mean over
        the disc the position may be in (its spread in the sigma), below it the point's height
        (slope x position sigma in the sigma).
        """
        self.ground = ground_altitude_m if ground_altitude_m is not None and math.isfinite(ground_altitude_m) else None
        self.ground_source = "configured" if self.ground is not None else None
        self._saved_ground, self._on_ground = _valid_ground(saved_ground), on_ground
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
        # an image height carried by the reference's change follows the vehicle, not the ground
        # under it: the ground there may have risen or fallen since the image measured it. That
        # part of its uncertainty grows at terrain_rate_mps (about slope x ground speed: 10 % at
        # 10 m/s) up to the terrain relief a reference assumes. Real flight over a valley
        # (MARS-LVIG AMvalley03, 2026-10-21): carried with its image sigma only (~4 m), the
        # height was 30 m off at the median, 126 m at most, 28 % within 2 sigma.
        self.terrain_rate_mps = terrain_rate_mps
        # a reference that stops (GPS jammed, box without barometer) is held: vehicles
        # mostly keep their altitude; the uncertainty grows like an image height held
        self.ref_hold_s = ref_hold_s
        self._vision: Optional[Tuple[float, float, float, Dict[str, float]]] = None  # t, agl, sigma, refs at t
        # the DEM: the vehicle's positions (lat, lon, sigma_m), the home position, and the
        # anchors tying the DEM's datum to the references (home ground height in DEM terms)
        self.terrain = terrain
        self.positions = History(maxlen=600, max_gap_s=2.5)
        self.position_max_age_s, self.home_sigma_m = position_max_age_s, home_sigma_m
        self.position_point_sigma_m = position_point_sigma_m
        self._home: Optional[Tuple[float, float]] = None
        self._anchors: Dict[str, deque] = {"vehicle": deque(maxlen=12), "gps": deque(maxlen=12)}

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
                self.set_home(float(s["lat"]), float(s["lon"]))
            else:                                       # power-on on the ground
                self.ground, self.ground_source = altitude_m, "first GPS fix"
                if lat is not None and lon is not None:
                    self.set_home(lat, lon)
                if self._on_ground and lat is not None and lon is not None:
                    self._on_ground(dict(altitude_m=altitude_m, lat=lat, lon=lon))

    def add_relative(self, t: float, height_above_home_m: float) -> None:
        if math.isfinite(height_above_home_m):
            self.relative.add(t, height_above_home_m)
            self._ground_from_home(t)

    def _ground_from_home(self, t: float) -> bool:
        """With the vehicle's height above its home AND a GPS altitude at the same instant,
        the home ground is GPS - height, right even when NAVERA starts in the air.
        """
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
        """A height measured from a map match's scale (with a known position: a DEM anchor)."""
        if math.isfinite(agl_m) and agl_m > 0:
            refs = self._refs(t)
            self._vision = (t, agl_m, sigma_m, refs)
            g = self._ground_at(t)
            if g is not None:
                h, h_sig = g
                for kind, ref in refs.items():           # home ground = image height - ref + DEM
                    self._anchors[kind].append((t, agl_m - ref + h, math.hypot(sigma_m, h_sig)))

    def forget_vision(self) -> None:
        """The image heights measured so far no longer apply (the camera's lens changed: a height from a
        map match's scale is made with the lens). The references carry on; the next match measures again."""
        self._vision = None

    # ── the DEM ──────────────────────────────────────────────────────────
    def set_terrain(self, terrain) -> None:
        """The corridor's DEM (navera_common.terrain.Terrain), or None."""
        self.terrain = terrain
        self._anchor_home()

    def set_home(self, lat: float, lon: float) -> None:
        """The position where the vehicle's height above home is 0 (its take-off / home point):
        the DEM there is the home ground.
        """
        if math.isfinite(lat) and math.isfinite(lon):
            self._home = (float(lat), float(lon))
            self._anchor_home()

    def add_position(self, t: float, lat: float, lon: float, sigma_m: float) -> None:
        """The vehicle's position (the arbiter's output: GPS, or vision after its loss)."""
        if math.isfinite(lat) and math.isfinite(lon) and math.isfinite(sigma_m):
            self.positions.add(t, (float(lat), float(lon), max(0.0, float(sigma_m))))

    def _anchor_home(self) -> None:
        if self.terrain is None or self._home is None:
            return
        g = self.terrain.height(*self._home)
        if g is None:
            return
        for kind in self._anchors:                     # both references are 0 at home
            anchors = [a for a in self._anchors[kind] if a[0] != -math.inf]
            self._anchors[kind] = deque([(-math.inf, g[0], math.hypot(g[1], self.home_sigma_m))] + anchors,
                                        maxlen=self._anchors[kind].maxlen)

    def _position_at(self, t: float) -> Optional[Tuple[float, float, float]]:
        """(lat, lon, sigma_m) at t: interpolated, or the last one moved on at its velocity (its
        sigma grown by half the distance) when it is at most position_max_age_s old.
        """
        last = self.positions.latest()
        if last is None:
            return None
        if t <= last[0]:
            return self.positions.at(t)
        if t - last[0] > self.position_max_age_s:
            return None
        (tl, (lat, lon, sig)), age = last, t - last[0]
        prev = self.positions.at(tl - 1.0)
        if prev is None:
            return lat, lon, sig + 30.0 * age               # speed unknown: up to 30 m/s
        k = math.cos(math.radians(lat))
        vn, ve = (lat - prev[0]) * 111_320.0, (lon - prev[1]) * 111_320.0 * k
        return lat + (lat - prev[0]) * age, lon + (lon - prev[1]) * age, sig + 0.5 * math.hypot(vn, ve) * age

    def _ground_at(self, t: float) -> Optional[Tuple[float, float]]:
        """(terrain height, its sigma incl. the position's uncertainty times the slope) under the
        vehicle at t, or None.
        """
        if self.terrain is None:
            return None
        p = self._position_at(t)
        if p is None:
            return None
        g = self.terrain.height(p[0], p[1])
        if g is None:
            return None
        if p[2] <= self.position_point_sigma_m:
            return g[0], math.hypot(g[1], g[2] * p[2])
        st = self.terrain.height_stats(p[0], p[1], 2.0 * p[2])
        if st is None:
            return None
        return st[0], math.hypot(g[1], st[1])

    def _home_ground(self, kind: str) -> Optional[Tuple[float, float]]:
        """The home ground's height in DEM terms (weighted mean of the anchors, the ones more than
        3 sigma from the median dropped), and its sigma (never below the spread of the anchors).
        """
        a = list(self._anchors[kind])
        if not a:
            return None
        if len(a) >= 3:
            med = sorted(x[1] for x in a)[len(a) // 2]
            a = [x for x in a if abs(x[1] - med) <= 3.0 * max(x[2], 2.0)] or a
        w = [1.0 / max(x[2], 1.0) ** 2 for x in a]
        mean = sum(wi * x[1] for wi, x in zip(w, a)) / sum(w)
        spread = math.sqrt(sum(wi * (x[1] - mean) ** 2 for wi, x in zip(w, a)) / sum(w))
        return mean, max(math.sqrt(1.0 / sum(w)), spread, 1.0)

    def _dem_estimate(self, t: float, refs: Dict[str, float]) -> Optional[Tuple[float, float, str]]:
        g = self._ground_at(t)
        if g is None:
            return None
        for kind in ("vehicle", "gps"):
            h0 = self._home_ground(kind) if kind in refs else None
            if h0 is not None:
                agl = refs[kind] + h0[0] - g[0]
                sigma = math.sqrt(h0[1] ** 2 + self.sigma[kind] ** 2 + g[1] ** 2)
                return agl, sigma, DEM_LABEL[kind]
        return None

    def _refs(self, t: float) -> Dict[str, float]:
        refs = {}
        r = self.relative.at(t)
        if r is not None:
            refs["vehicle"] = r
        g = self.gps.at(t)
        if g is not None and self.ground is not None:
            refs["gps"] = g - self.ground
        return refs

    def reference(self, t: float) -> Optional[Tuple[float, float, str]]:
        """(agl, sigma, source) from the sources that do not come from the image: a rangefinder, else the
        vehicle's height above home, else GPS minus the ground — the height the in-flight lens calibration
        needs (an image height is computed with the lens being calibrated: a lens 10 % off read the
        height 10 % off and the fit kept the error, Isaac Sim 2026-10-26). None when none is known."""
        m = self.measured.at(t)
        if m is not None:
            return m[0], m[1], "measured"
        refs = self._refs(t)
        for kind in ("vehicle", "gps"):
            if kind in refs:
                return refs[kind], self._ref_sigma(kind, refs[kind]), REF_LABEL[kind]
        return None

    def estimate(self, t: float) -> Optional[Tuple[float, float, str]]:
        m = self.measured.at(t)
        if m is not None:
            return m[0], m[1], "measured"
        refs = self._refs(t)
        # the DEM, once tied to the reference, knows the relief the other sources assume flat (an
        # image carried 20 s over a valley by the barometer: 100 m off, stated 30 m — MARS-LVIG)
        dem = self._dem_estimate(t, refs) if self.terrain is not None else None
        return dem if dem is not None else self._without_dem(t, refs)

    def _without_dem(self, t: float, refs: Dict[str, float]) -> Optional[Tuple[float, float, str]]:
        """The image carried by a reference, a reference alone, or held."""
        if self._vision is not None and abs(t - self._vision[0]) <= self.vision_hold_s:
            tv, agl, sig, refs_v = self._vision
            for kind in ("vehicle", "gps"):             # carried by the same reference's change
                if kind in refs and kind in refs_v:
                    now = agl + (refs[kind] - refs_v[kind])
                    terrain = min(self.terrain_rate_mps * abs(t - tv),
                                  math.hypot(self.terrain_sigma_m, self.terrain_fraction * now))
                    return now, math.sqrt(sig * sig + 4.0 + terrain * terrain), CARRY_LABEL[kind]
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

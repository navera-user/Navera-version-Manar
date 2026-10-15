"""What NAVERA tells the vehicle — the one place that decides it.

The vehicle's autopilot treats whatever NAVERA sends as a GPS. The rules:

* FIX (a measured position with a known, small uncertainty — GPS today) is sent
  as a fix with its real accuracy.
* DEGRADED (vision / celestial: uncertainty unknown, or dead-reckoned) is NOT
  sent as a position unless the integrator explicitly enables it and declares
  the accuracy to report (degraded_sigma_m). It is then flagged "estimated"
  (NMEA quality 6), never as a satellite fix. When the source states a worse
  accuracy itself (e.g. celestial, tens of km), the worse one is sent.
* Anything else — NO_FIX, INITIALIZING, the arbiter silent, the position
  stale, non-finite, or not from the active source — is sent as "no fix".
  A position is never repeated after it stops being current.
* A position is sent stamped with the instant it was MEASURED (the camera
  exposure for vision), never the sending instant, and not at all when it was
  measured more than max_measurement_age_s ago: a 3 s old vision fix sent as
  current is 45 m wrong at 15 m/s, and the autopilot cannot know it.
* Velocity is sent only with a GPS position, from the receiver's own velocity
  (RMC), and only while that velocity is current. Vision and celestial fixes
  carry no velocity.
* A short gap in the vision positions is bridged, never longer than bridge_max_s:
  the last forwarded estimate is carried along its velocity and sent again about
  once a second, its accuracy growing with the time (velocity error, unseen
  acceleration, or max_speed_mps x time without a velocity). An autopilot lands
  on a 5 s silence (simulator, 2026-10-15) although the vehicle has hardly moved
  from where it was last seen. Past the bound, or once the grown accuracy exceeds
  max_forward_sigma_m, it is "no fix" again. Only a forwarded estimate is bridged
  (never a GPS fix), only while the arbiter is alive.
"""
import json
import math

from navera_common.geo import dead_reckon
from dataclasses import dataclass
from typing import Optional

# navera_msgs NavStatus states (kept literal so this module needs no ROS).
STATE_NO_FIX = 1
STATE_FIX = 2
STATE_DEGRADED = 3
SOURCE_GPS = 1

KIND_FIX = "fix"              # satellite-grade fix
KIND_ESTIMATED = "estimated"  # non-GNSS position, forwarded by configuration
KIND_NONE = "none"            # no position


@dataclass
class Output:
    kind: str
    reason: str = ""
    lat: float = math.nan
    lon: float = math.nan
    alt_ellipsoid_m: float = math.nan   # WGS84 ellipsoidal height, NaN if unknown
    geoid_sep_m: float = math.nan       # ellipsoid - MSL, NaN if unknown
    sigma_h_m: float = math.nan         # 1-sigma horizontal accuracy
    sigma_v_m: float = math.nan
    satellites: Optional[int] = None    # None = unknown / not applicable
    age_s: float = 0.0                  # measurement age when decided (stamp = now - age_s)
    gnss: bool = False                  # the position comes from a satellite receiver
    vel_n_mps: float = math.nan         # ground velocity north / east, NaN if unknown
    vel_e_mps: float = math.nan
    soft: bool = False                  # kind NONE only because no NEW position came: may be bridged
    bridged: bool = False               # a held position carried to now (see bridge())

    @property
    def has_velocity(self) -> bool:
        return math.isfinite(self.vel_n_mps) and math.isfinite(self.vel_e_mps)

    @property
    def alt_msl_m(self) -> float:
        if math.isfinite(self.alt_ellipsoid_m) and math.isfinite(self.geoid_sep_m):
            return self.alt_ellipsoid_m - self.geoid_sep_m
        return math.nan


@dataclass
class Config:
    forward_degraded: bool = False
    degraded_sigma_m: float = math.nan  # required when forward_degraded
    # A position coarser than this is never given to the autopilot, even with
    # forward_degraded: a celestial fix (tens of km) moved a SITL autopilot's
    # own position by 125 km.
    max_forward_sigma_m: float = 1000.0
    position_timeout_s: float = 5.0
    nav_status_timeout_s: float = 2.0
    # older measurements are not sent (vision: photo to position 0.5-2.5 s; a non-GPS one
    # is carried to the present with its accuracy grown by its age)
    max_measurement_age_s: float = 5.0
    # a non-GPS position is carried to the present along the measured ground velocity;
    # without one, its accuracy grows by this speed x its age
    max_speed_mps: float = 30.0
    # a gap in the forwarded vision positions is bridged this long at most (0 = never)
    bridge_max_s: float = 10.0
    # the bridge starts when the last send is older than this, then repeats every bridge_period_s
    bridge_after_s: float = 2.5
    bridge_period_s: float = 1.0
    # unseen acceleration of the vehicle in a bridged gap (as navera_common.track, 0.5)
    bridge_accel_mps2: float = 0.5
    bridge_heading_sigma_deg: float = 5.0

    def validate(self) -> None:
        if self.forward_degraded and not (math.isfinite(self.degraded_sigma_m)
                                          and self.degraded_sigma_m > 0):
            raise ValueError("forward_degraded requires degraded_sigma_m > 0: the accuracy "
                             "sent to the vehicle must be stated, not invented")
        if not (self.bridge_max_s >= 0 and self.bridge_after_s > 0 and self.bridge_period_s > 0
                and self.bridge_accel_mps2 >= 0 and self.bridge_heading_sigma_deg >= 0):
            raise ValueError("bridge_max_s >= 0, bridge_after_s > 0, bridge_period_s > 0 and the "
                             "bridge accel / heading sigma >= 0 are required")
        if self.forward_degraded and self.degraded_sigma_m > self.max_forward_sigma_m:
            raise ValueError(f"degraded_sigma_m {self.degraded_sigma_m:g} m > max_forward_sigma_m "
                             f"{self.max_forward_sigma_m:g} m: nothing would ever be forwarded")


def _details(pos) -> dict:
    try:
        d = json.loads(pos.details_json or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def decide(cfg: Config, state: Optional[int], status_age_s: Optional[float],
           pos, pos_age_s: Optional[float], active_source: Optional[int],
           gps_vel_ne: Optional[tuple] = None, measured_age_s: Optional[float] = None,
           ground_vel: Optional[tuple] = None) -> Output:
    """The output for this instant.

    state / status_age_s: last NavStatus state and its age (None = never heard).
    pos / pos_age_s: last /navera/position and its age (None = never heard).
    active_source: NavStatus.active_source (the position must come from it).
    gps_vel_ne: the GPS receiver's current (north, east) velocity in m/s, or
        None when it is not current. Used only with a GPS position.
    measured_age_s: now - the position's measurement instant (None = unknown: 0).
    ground_vel: (east m/s, north m/s, 1-sigma speed error) measured from the recent
        positions, or None. A vision / celestial position describes where its photo was
        taken (0.5-2.5 s ago): it is carried to now along it (its accuracy grows by the
        speed error x age), or, without it, sent stamped when measured with its accuracy
        grown by max_speed_mps x age — never presented as current and as accurate.
    """
    if state is None or status_age_s is None or status_age_s > cfg.nav_status_timeout_s:
        return Output(KIND_NONE, "arbiter silent")
    if state not in (STATE_FIX, STATE_DEGRADED):
        return Output(KIND_NONE, "no fix", soft=state == STATE_NO_FIX)
    if pos is None or pos_age_s is None or pos_age_s > cfg.position_timeout_s:
        return Output(KIND_NONE, "position not current", soft=True)
    if pos.source != active_source:
        return Output(KIND_NONE, "position not from the active source")
    age = 0.0 if measured_age_s is None or not math.isfinite(measured_age_s) else float(measured_age_s)
    if age > cfg.max_measurement_age_s:
        return Output(KIND_NONE, f"position measured {age:.1f} s ago (max {cfg.max_measurement_age_s:.1f} s)",
                      soft=True)
    if age < -1.0:
        return Output(KIND_NONE, f"position stamped {-age:.1f} s in the future: clocks disagree")
    age = max(0.0, age)
    lat, lon = float(pos.latitude), float(pos.longitude)
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return Output(KIND_NONE, "position not finite")

    cov = list(pos.position_covariance)
    alt = float(pos.altitude)
    details = _details(pos)
    sep = details.get("geo_sep_m")
    sats = details.get("num_sats")
    lag_sigma = 0.0
    if pos.source != SOURCE_GPS and age > 0.0:
        if ground_vel is not None and all(math.isfinite(v) for v in ground_vel):
            ve, vn, sig_v = ground_vel
            speed = math.hypot(ve, vn)
            if speed > 0.05:
                carried = dead_reckon(lat, lon, math.degrees(math.atan2(ve, vn)) % 360.0, speed, age)
                if carried is not None:
                    lat, lon = carried
            lag_sigma, age = sig_v * age, 0.0                  # now a position of the present
        else:
            lag_sigma = cfg.max_speed_mps * age
    common = dict(lat=lat, lon=lon, alt_ellipsoid_m=alt, age_s=age, gnss=pos.source == SOURCE_GPS,
                  geoid_sep_m=float(sep) if isinstance(sep, (int, float)) else math.nan)

    if (gps_vel_ne is not None and pos.source == SOURCE_GPS
            and all(math.isfinite(v) for v in gps_vel_ne)):
        common.update(vel_n_mps=float(gps_vel_ne[0]), vel_e_mps=float(gps_vel_ne[1]))

    if state == STATE_FIX:
        return Output(KIND_FIX, "fix", sigma_h_m=math.sqrt(max(cov[0], cov[4])) + lag_sigma,
                      sigma_v_m=math.sqrt(cov[8]) if cov[8] > 0 else math.nan,
                      satellites=int(sats) if isinstance(sats, int) else None, **common)
    if not cfg.forward_degraded:
        return Output(KIND_NONE, "degraded position not forwarded (forward_degraded=false)")
    known = getattr(pos, "position_covariance_type", 0) != 0          # 0 = UNKNOWN
    stated = math.sqrt(max(cov[0], cov[4])) if known else math.nan
    candidates = [x for x in (cfg.degraded_sigma_m, stated) if math.isfinite(x) and x > 0]
    if not candidates:
        return Output(KIND_NONE, "degraded position with no stated accuracy")
    sigma = max(candidates) + lag_sigma
    if sigma > cfg.max_forward_sigma_m:
        return Output(KIND_NONE, f"position too coarse for the autopilot "
                                 f"(±{sigma / 1000:.1f} km > {cfg.max_forward_sigma_m / 1000:.1f} km)")
    return Output(KIND_ESTIMATED, "estimated", sigma_h_m=sigma,
                  sigma_v_m=math.nan, satellites=0, **common)


@dataclass
class Held:
    """The last forwarded estimated position, for bridging a gap after it."""
    lat: float
    lon: float
    sigma_h_m: float
    t: float                                  # monotonic instant the position describes (the send)
    ground_vel: Optional[tuple] = None        # (east m/s, north m/s, 1-sigma speed error) at that time


def hold(out: Output, t: float, ground_vel: Optional[tuple]) -> Optional[Held]:
    """What to remember of a decision: only a forwarded estimate (not a GPS fix)."""
    if out.kind != KIND_ESTIMATED or not (math.isfinite(out.lat) and math.isfinite(out.lon)
                                          and math.isfinite(out.sigma_h_m)):
        return None
    gv = tuple(float(v) for v in ground_vel) if ground_vel is not None and all(
        math.isfinite(v) for v in ground_vel) else None
    return Held(out.lat, out.lon, out.sigma_h_m, t, gv)


def bridge(cfg: Config, held: Optional[Held], now: float) -> Output:
    """The held position carried to `now`, its accuracy grown by the time; "no fix" when it cannot be
    done honestly: no held estimate, the gap longer than bridge_max_s, or the grown accuracy coarser
    than max_forward_sigma_m.

    With the ground velocity measured when it was held, the position moves along it and the
    accuracy grows by the velocity error, the heading error x speed and half the unseen
    acceleration x t^2. Without one the position stays and the accuracy grows by
    max_speed_mps x t: the vehicle can have gone that far, in any direction."""
    if held is None or not cfg.forward_degraded or cfg.bridge_max_s <= 0:
        return Output(KIND_NONE, "no position to bridge")
    dt = now - held.t
    if dt < 0:
        return Output(KIND_NONE, "bridge: clock went backwards")
    if dt > cfg.bridge_max_s:
        return Output(KIND_NONE, f"gap of {dt:.0f} s longer than the bridge ({cfg.bridge_max_s:.0f} s)")
    lat, lon = held.lat, held.lon
    if held.ground_vel is not None:
        ve, vn, sig_v = held.ground_vel
        speed = math.hypot(ve, vn)
        if speed > 0.05:
            carried = dead_reckon(lat, lon, math.degrees(math.atan2(ve, vn)) % 360.0, speed, dt)
            if carried is not None:
                lat, lon = carried
        grow = (sig_v * dt + math.radians(cfg.bridge_heading_sigma_deg) * speed * dt
                + 0.5 * cfg.bridge_accel_mps2 * dt * dt)
    else:
        grow = cfg.max_speed_mps * dt
    sigma = held.sigma_h_m + grow
    if sigma > cfg.max_forward_sigma_m:
        return Output(KIND_NONE, f"bridged position too coarse (±{sigma / 1000:.1f} km > "
                                 f"{cfg.max_forward_sigma_m / 1000:.1f} km)")
    return Output(KIND_ESTIMATED, f"bridged {dt:.1f} s", lat=lat, lon=lon, sigma_h_m=sigma,
                  satellites=0, age_s=0.0, bridged=True)


def for_nmea(out: Output, allow_degraded: bool = False) -> Output:
    """What goes out over NMEA. NMEA carries no accuracy an autopilot uses (ArduPilot fuses
    GGA/RMC with its own ~0.5 m GPS noise): an estimated (vision) position is sent as
    "no fix" unless explicitly allowed."""
    if out.kind == KIND_ESTIMATED and not allow_degraded:
        return Output(KIND_NONE, "degraded position not sent over NMEA (no accuracy field)")
    return out

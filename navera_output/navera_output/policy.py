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
"""
import json
import math

from navera_common.geo import dead_reckon
from dataclasses import dataclass
from typing import Optional

# navera_msgs NavStatus states (kept literal so this module needs no ROS).
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
    vel_n_mps: float = math.nan         # ground velocity north / east, NaN if unknown
    vel_e_mps: float = math.nan

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

    def validate(self) -> None:
        if self.forward_degraded and not (math.isfinite(self.degraded_sigma_m)
                                          and self.degraded_sigma_m > 0):
            raise ValueError("forward_degraded requires degraded_sigma_m > 0: the accuracy "
                             "sent to the vehicle must be stated, not invented")
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
        return Output(KIND_NONE, "no fix")
    if pos is None or pos_age_s is None or pos_age_s > cfg.position_timeout_s:
        return Output(KIND_NONE, "position not current")
    if pos.source != active_source:
        return Output(KIND_NONE, "position not from the active source")
    age = 0.0 if measured_age_s is None or not math.isfinite(measured_age_s) else float(measured_age_s)
    if age > cfg.max_measurement_age_s:
        return Output(KIND_NONE, f"position measured {age:.1f} s ago (max {cfg.max_measurement_age_s:.1f} s)")
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
    common = dict(lat=lat, lon=lon, alt_ellipsoid_m=alt, age_s=age,
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
    sigma = max(cfg.degraded_sigma_m, stated) if math.isfinite(stated) else cfg.degraded_sigma_m
    sigma += lag_sigma
    if sigma > cfg.max_forward_sigma_m:
        return Output(KIND_NONE, f"position too coarse for the autopilot "
                                 f"(±{sigma / 1000:.1f} km > {cfg.max_forward_sigma_m / 1000:.1f} km)")
    return Output(KIND_ESTIMATED, "estimated", sigma_h_m=sigma,
                  sigma_v_m=math.nan, satellites=0, **common)


def for_nmea(out: Output, allow_degraded: bool = False) -> Output:
    """What goes out over NMEA. NMEA carries no accuracy an autopilot uses (ArduPilot fuses
    GGA/RMC with its own ~0.5 m GPS noise): an estimated (vision) position is sent as
    "no fix" unless explicitly allowed."""
    if out.kind == KIND_ESTIMATED and not allow_degraded:
        return Output(KIND_NONE, "degraded position not sent over NMEA (no accuracy field)")
    return out

"""What NAVERA tells the vehicle — the one place that decides it.

The vehicle's autopilot treats whatever NAVERA sends as a GPS. The rules:

* FIX (a measured position with a known, small uncertainty — GPS today) is sent
  as a fix with its real accuracy.
* DEGRADED (vision / celestial: uncertainty unknown, or dead-reckoned) is NOT
  sent as a position unless the integrator explicitly enables it and declares
  the accuracy to report (degraded_sigma_m). It is then flagged "estimated"
  (NMEA quality 6), never as a satellite fix.
* Anything else — NO_FIX, INITIALIZING, the arbiter silent, the position
  stale, non-finite, or not from the active source — is sent as "no fix".
  A position is never repeated after it stops being current.
"""
import json
import math
from dataclasses import dataclass
from typing import Optional

# navera_msgs NavStatus states (kept literal so this module needs no ROS).
STATE_FIX = 2
STATE_DEGRADED = 3

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

    @property
    def alt_msl_m(self) -> float:
        if math.isfinite(self.alt_ellipsoid_m) and math.isfinite(self.geoid_sep_m):
            return self.alt_ellipsoid_m - self.geoid_sep_m
        return math.nan


@dataclass
class Config:
    forward_degraded: bool = False
    degraded_sigma_m: float = math.nan  # required when forward_degraded
    position_timeout_s: float = 2.0
    nav_status_timeout_s: float = 2.0

    def validate(self) -> None:
        if self.forward_degraded and not (math.isfinite(self.degraded_sigma_m)
                                          and self.degraded_sigma_m > 0):
            raise ValueError("forward_degraded requires degraded_sigma_m > 0: the accuracy "
                             "sent to the vehicle must be stated, not invented")


def _details(pos) -> dict:
    try:
        d = json.loads(pos.details_json or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def decide(cfg: Config, state: Optional[int], status_age_s: Optional[float],
           pos, pos_age_s: Optional[float], active_source: Optional[int]) -> Output:
    """The output for this instant.

    state / status_age_s: last NavStatus state and its age (None = never heard).
    pos / pos_age_s: last /navera/position and its age (None = never heard).
    active_source: NavStatus.active_source (the position must come from it).
    """
    if state is None or status_age_s is None or status_age_s > cfg.nav_status_timeout_s:
        return Output(KIND_NONE, "arbiter silent")
    if state not in (STATE_FIX, STATE_DEGRADED):
        return Output(KIND_NONE, "no fix")
    if pos is None or pos_age_s is None or pos_age_s > cfg.position_timeout_s:
        return Output(KIND_NONE, "position not current")
    if pos.source != active_source:
        return Output(KIND_NONE, "position not from the active source")
    lat, lon = float(pos.latitude), float(pos.longitude)
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return Output(KIND_NONE, "position not finite")

    cov = list(pos.position_covariance)
    alt = float(pos.altitude)
    details = _details(pos)
    sep = details.get("geo_sep_m")
    sats = details.get("num_sats")
    common = dict(lat=lat, lon=lon, alt_ellipsoid_m=alt,
                  geoid_sep_m=float(sep) if isinstance(sep, (int, float)) else math.nan)

    if state == STATE_FIX:
        return Output(KIND_FIX, "fix", sigma_h_m=math.sqrt(max(cov[0], cov[4])),
                      sigma_v_m=math.sqrt(cov[8]) if cov[8] > 0 else math.nan,
                      satellites=int(sats) if isinstance(sats, int) else None, **common)
    if not cfg.forward_degraded:
        return Output(KIND_NONE, "degraded position not forwarded (forward_degraded=false)")
    return Output(KIND_ESTIMATED, "estimated", sigma_h_m=cfg.degraded_sigma_m,
                  sigma_v_m=math.nan, satellites=0, **common)

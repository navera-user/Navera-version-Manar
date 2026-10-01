"""Vehicle settings shared by the NAVERA launch files (one value for every node).

The vehicle's maximum speed bounds what NAVERA accepts as a real movement: the
estimator's GPS plausibility gate (anti-jump / anti-spoofing) and the day and
night vision motion gates. It is set once per installation, in km/h, by
NAVERA_MAX_SPEED_KMH in /etc/navera/navera.env — a drone, a boat and an
aircraft differ by an order of magnitude.
"""
import os
from typing import Optional

ENV_MAX_SPEED_KMH = "NAVERA_MAX_SPEED_KMH"
MAX_SPEED_KMH_RANGE = (4.0, 1890.0)


def max_speed_mps_from_env(environ=None) -> Optional[float]:
    """The vehicle's maximum speed in m/s from NAVERA_MAX_SPEED_KMH, or None when unset.

    Raises ValueError on a value that is not a number in MAX_SPEED_KMH_RANGE: a
    wrong limit would silently refuse real positions (too low) or accept spoofed
    ones (too high), so the node must not start with it.
    """
    env = os.environ if environ is None else environ
    raw = str(env.get(ENV_MAX_SPEED_KMH, "")).strip()
    if not raw:
        return None
    try:
        kmh = float(raw)
    except ValueError:
        raise ValueError(f"{ENV_MAX_SPEED_KMH}={raw!r} is not a number (km/h)") from None
    lo, hi = MAX_SPEED_KMH_RANGE
    if not lo <= kmh <= hi:
        raise ValueError(f"{ENV_MAX_SPEED_KMH}={kmh:g} km/h is outside {lo:g}-{hi:g} km/h")
    return kmh / 3.6


ENV_IMU_MOUNT_RPY = "NAVERA_IMU_MOUNT_RPY"          # "roll,pitch,yaw" deg
ENV_DECLINATION_DEG = "NAVERA_DECLINATION_DEG"      # deg, east positive


def imu_params(environ=None) -> dict:
    """imu_node parameters from the installation's settings (mounting, declination),
    or {} for what is unset (the yaml/node defaults apply). Raises ValueError."""
    env = os.environ if environ is None else environ
    out = {}
    raw = str(env.get(ENV_IMU_MOUNT_RPY, "")).strip()
    if raw:
        parts = raw.split(",")
        try:
            r, p, y = (float(v) for v in parts)
        except ValueError:
            raise ValueError(f"{ENV_IMU_MOUNT_RPY}={raw!r}: expected roll,pitch,yaw in degrees") from None
        if not all(-180.0 <= a <= 180.0 for a in (r, p, y)):
            raise ValueError(f"{ENV_IMU_MOUNT_RPY}={raw!r}: angles must be within ±180°")
        out.update(mount_roll_deg=r, mount_pitch_deg=p, mount_yaw_deg=y)
    raw = str(env.get(ENV_DECLINATION_DEG, "")).strip()
    if raw:
        try:
            d = float(raw)
        except ValueError:
            raise ValueError(f"{ENV_DECLINATION_DEG}={raw!r} is not a number") from None
        if not -90.0 <= d <= 90.0:
            raise ValueError(f"{ENV_DECLINATION_DEG}={d:g} is outside ±90°")
        out["declination_deg"] = d
    return out


def max_speed_params(environ=None) -> dict:
    """{'max_speed_mps': value} for a launch file's parameters, or {} when unset
    (the node keeps its own default; the launch file warns)."""
    v = max_speed_mps_from_env(environ)
    return {} if v is None else {"max_speed_mps": v}

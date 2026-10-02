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


# ── where the live camera takes the vehicle's attitude, position and height ──
ENV_SENSOR_SOURCE = "NAVERA_SENSOR_SOURCE"     # box | vehicle | ros
SENSOR_SOURCES = ("box", "vehicle", "ros")


def sensor_topics(environ=None) -> dict:
    """Topics the live camera reads, by NAVERA_SENSOR_SOURCE:
      box      NAVERA's own BNO085 and Neo-M8N (imu_node, gps_node)
      vehicle  the autopilot's sensors over MAVLink (vehicle_link_node): attitude,
               rangefinder, height above home; GPS from NAVERA's receiver if fitted
      ros      the vehicle's ROS topics: NAVERA_ROS_IMU_TOPIC (sensor_msgs/Imu, ENU),
               NAVERA_ROS_GPS_TOPIC (NavSatFix), NAVERA_ROS_ALTITUDE_TOPIC (Range, AGL)
    Raises ValueError on an unknown source or a missing ROS IMU topic."""
    env = os.environ if environ is None else environ
    src = str(env.get(ENV_SENSOR_SOURCE, "") or "box").strip().lower()
    if src not in SENSOR_SOURCES:
        raise ValueError(f"{ENV_SENSOR_SOURCE}={src!r}: expected one of {', '.join(SENSOR_SOURCES)}")
    t = {"sensor_source": src, "imu_topic": "/navera/sensors/imu", "gps_topic": "/navera/sensors/gps_fix",
         "altitude_topic": "/navera/sensors/altitude_agl", "relative_altitude_topic": "/navera/vehicle/relative_alt",
         "attitude_source": "imu"}
    if src == "vehicle":
        t.update(imu_topic="/navera/vehicle/imu", altitude_topic="/navera/vehicle/altitude_agl",
                 attitude_source="vehicle")
    elif src == "ros":
        imu = str(env.get("NAVERA_ROS_IMU_TOPIC", "")).strip()
        if not imu:
            raise ValueError("NAVERA_SENSOR_SOURCE=ros needs NAVERA_ROS_IMU_TOPIC (the vehicle's attitude)")
        t.update(imu_topic=imu, attitude_source="vehicle ROS",
                 gps_topic=str(env.get("NAVERA_ROS_GPS_TOPIC", "") or t["gps_topic"]).strip(),
                 altitude_topic=str(env.get("NAVERA_ROS_ALTITUDE_TOPIC", "") or t["altitude_topic"]).strip())
    return t


def live_camera_params(environ=None) -> dict:
    """live_camera parameters from the installation settings (NAVERA_CAMERA_*)."""
    env = os.environ if environ is None else environ
    get = lambda k, d="": str(env.get(k, "") or d).strip()     # noqa: E731
    size = get("NAVERA_CAMERA_SIZE", "1920x1080").lower().split("x")
    if len(size) != 2 or not all(s.isdigit() for s in size):
        raise ValueError(f"NAVERA_CAMERA_SIZE={get('NAVERA_CAMERA_SIZE')!r}: expected WIDTHxHEIGHT, e.g. 1920x1080")
    p = {"input": get("NAVERA_CAMERA_INPUT", "usb"), "device": get("NAVERA_CAMERA_DEVICE", "/dev/video0"),
         "input_topic": get("NAVERA_CAMERA_TOPIC", "/vehicle/camera/image_raw"),
         "width": int(size[0]), "height": int(size[1]),
         "fps": float(get("NAVERA_CAMERA_FPS", "1.0")),
         "capture_latency_s": float(get("NAVERA_CAMERA_LATENCY_S", "0.0")),
         "calibration_file": get("NAVERA_CAMERA_CALIBRATION"),
         "max_tilt_deg": float(get("NAVERA_CAMERA_MAX_TILT_DEG", "45")),
         "gimbal": get("NAVERA_CAMERA_GIMBAL", "false").lower() in ("1", "true", "yes")}
    if p["input"] not in ("usb", "csi", "ros"):
        raise ValueError(f"NAVERA_CAMERA_INPUT={p['input']!r}: expected usb, csi or ros")
    hfov = get("NAVERA_CAMERA_HFOV_DEG")
    if hfov:
        p["camera_hfov_deg"] = float(hfov)
    if not p["calibration_file"] and not hfov:
        raise ValueError("set NAVERA_CAMERA_CALIBRATION (navera_tools/calibrate_camera.py) "
                         "or at least NAVERA_CAMERA_HFOV_DEG")
    rpy = get("NAVERA_CAMERA_MOUNT_RPY")
    if rpy:
        try:
            r, pi, y = (float(v) for v in rpy.split(","))
        except ValueError:
            raise ValueError(f"NAVERA_CAMERA_MOUNT_RPY={rpy!r}: expected roll,pitch,yaw in degrees") from None
        p.update(mount_roll_deg=r, mount_pitch_deg=pi, mount_yaw_deg=y)
    g = get("NAVERA_GROUND_ALTITUDE_M")
    if g:
        p["ground_altitude_m"] = float(g)
    t = sensor_topics(env)
    p.update({k: v for k, v in t.items() if k != "sensor_source"})
    return p

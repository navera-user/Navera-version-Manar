"""Vehicle settings shared by the NAVERA launch files (one value for every node).

The vehicle's maximum speed bounds what NAVERA accepts as a real movement: the
estimator's GPS plausibility gate (anti-jump / anti-spoofing) and the day and
night vision motion gates. It is set once per installation, in km/h, by
NAVERA_MAX_SPEED_KMH in /etc/navera/navera.env — a drone, a boat and an
aircraft differ by an order of magnitude.
"""
import math
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
    or {} for what is unset (the yaml/node defaults apply). Raises ValueError.
    """
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
    (the node keeps its own default; the launch file warns).
    """
    v = max_speed_mps_from_env(environ)
    return {} if v is None else {"max_speed_mps": v}


# ── where the live camera takes the vehicle's attitude, position and height ──
ENV_SENSOR_SOURCE = "NAVERA_SENSOR_SOURCE"     # box | vehicle | ros | insta360
SENSOR_SOURCES = ("box", "vehicle", "ros", "insta360")
# the Insta360 kit (camera_pkg insta360_node: the One R in USB Android mode is the camera AND the IMU)
INSTA360_IMU_TOPIC = "/navera/sensors/insta360/imu"
INSTA360_IMAGE_TOPIC = "/navera/sensors/insta360/nadir/image_raw"
INSTA360_STATUS_TOPIC = "/navera/sensors/insta360/status"
INSTA360_DEFAULT_MOUNT_AXES = "+x,+z,-y"       # lying, the LEFT lens looking down, camera top to the nose


def sensor_topics(environ=None) -> dict:
    """Topics the live camera reads, by NAVERA_SENSOR_SOURCE:
      box      the box's own sensors: /navera/sensors/imu (imu_node: an optional BNO085 — the
               reference kit's Insta360 One R IMU is the insta360 source below) and the
               box GPS receiver (gps_node, any NMEA serial receiver)
      vehicle  the autopilot's sensors over MAVLink (vehicle_link_node): attitude,
               rangefinder, height above home (the GPS source is NAVERA_GPS_SOURCE)
      ros      the vehicle's ROS topics: NAVERA_ROS_IMU_TOPIC (sensor_msgs/Imu, ENU),
               NAVERA_ROS_GPS_TOPIC (NavSatFix), NAVERA_ROS_ALTITUDE_TOPIC (Range, AGL)
      insta360 the Insta360 One R's own IMU (the Insta360 kit, navera-insta360): attitude from its
               gyro + accelerometer; GPS and height as box (NAVERA's receiver; no rangefinder)
    Raises ValueError on an unknown source or a missing ROS IMU topic.
    """
    env = os.environ if environ is None else environ
    src = str(env.get(ENV_SENSOR_SOURCE, "") or "box").strip().lower()
    if src == "auto":                       # not decided by navera-discover: the box's sensors
        src = "box"
    if src not in SENSOR_SOURCES:
        raise ValueError(f"{ENV_SENSOR_SOURCE}={src!r}: expected one of {', '.join(SENSOR_SOURCES)}")
    t = {"sensor_source": src, "imu_topic": "/navera/sensors/imu", "gps_topic": "/navera/sensors/gps_fix",
         "altitude_topic": "/navera/sensors/altitude_agl", "relative_altitude_topic": "/navera/vehicle/relative_alt",
         "attitude_source": "imu"}
    if src == "vehicle":
        t.update(imu_topic="/navera/vehicle/imu", altitude_topic="/navera/vehicle/altitude_agl",
                 attitude_source="vehicle")
    elif src == "insta360":
        t.update(imu_topic=INSTA360_IMU_TOPIC, attitude_source="insta360")
    elif src == "ros":
        imu = str(env.get("NAVERA_ROS_IMU_TOPIC", "")).strip()
        if not imu:
            raise ValueError("NAVERA_SENSOR_SOURCE=ros needs NAVERA_ROS_IMU_TOPIC (the vehicle's attitude)")
        t.update(imu_topic=imu, attitude_source="vehicle ROS",
                 gps_topic=str(env.get("NAVERA_ROS_GPS_TOPIC", "") or t["gps_topic"]).strip(),
                 altitude_topic=str(env.get("NAVERA_ROS_ALTITUDE_TOPIC", "") or t["altitude_topic"]).strip())
    return t


def live_camera_params(environ=None, prefix: str = "NAVERA_CAMERA_") -> dict:
    """live_camera parameters from the installation settings (NAVERA_CAMERA_*; the star
    camera of the celestial pipeline: prefix NAVERA_STAR_CAMERA_).
    """
    env = os.environ if environ is None else environ
    get = lambda k, d="": str(env.get(k, "") or d).strip()     # noqa: E731
    # "auto": the camera's own size, from its first frame (a network stream, a ROS topic)
    size = get(prefix + "SIZE", "1920x1080").lower()
    size = ["0", "0"] if size == "auto" else size.split("x")
    if len(size) != 2 or not all(s.isdigit() for s in size):
        raise ValueError(f"{prefix}SIZE={get(prefix + 'SIZE')!r}: expected WIDTHxHEIGHT (e.g. 1920x1080) or auto")
    if get(prefix + "INPUT").lower() == "insta360":
        return insta360_camera_params(env, prefix)
    p = {"input": get(prefix + "INPUT", "usb").lower().replace("auto", "usb"),
         "device": get(prefix + "DEVICE", "/dev/video0"),
         "input_topic": get(prefix + "TOPIC", "/vehicle/camera/image_raw"),
         "width": int(size[0]), "height": int(size[1]),
         "fourcc": get(prefix + "FOURCC", "MJPG"),
         "fps": float(get(prefix + "FPS", "1.0")),
         "capture_latency_s": float(get(prefix + "LATENCY_S", "0.0")),
         "calibration_file": get(prefix + "CALIBRATION"),
         "max_tilt_deg": float(get(prefix + "MAX_TILT_DEG", "45")),
         "max_rate_dps": float(get(prefix + "MAX_RATE_DPS", "30")),
         "gimbal": get(prefix + "GIMBAL", "false").lower() in ("1", "true", "yes"),
         # only part of the picture looks at the ground (a 360 camera's two lenses)
         "crop": get(prefix + "CROP")}
    auto_size = p["width"] == 0 and p["height"] == 0
    for key, k, lo, hi in (() if auto_size else ((prefix + "SIZE", "width", 64, 8192),
                                                 (prefix + "SIZE", "height", 64, 8192))) + (
                           (prefix + "FPS", "fps", 0.05, 30.0),
                           (prefix + "LATENCY_S", "capture_latency_s", 0.0, 2.0),
                           (prefix + "MAX_TILT_DEG", "max_tilt_deg", 5.0, 80.0),
                           (prefix + "MAX_RATE_DPS", "max_rate_dps", 1.0, 360.0)):
        if not (math.isfinite(p[k]) and lo <= p[k] <= hi):
            raise ValueError(f"{key}: {k} {p[k]:g} out of range [{lo:g}, {hi:g}]")
    from navera_common.camera_model import parse_crop
    try:
        if auto_size and p["crop"]:
            raise ValueError("a crop needs the camera's size: set the SIZE")
        if not auto_size:
            parse_crop(p["crop"], p["width"], p["height"])
    except ValueError as e:
        raise ValueError(f"{prefix}CROP: {e}") from None
    if p["input"] not in ("usb", "csi", "gst", "aravis", "ros"):
        raise ValueError(f"{prefix}INPUT={p['input']!r}: expected usb, csi, gst, aravis, ros or insta360")
    p["gst_pipeline"] = get(prefix + "GST_PIPELINE")
    p["start_url"] = get(prefix + "START_URL")
    if p["input"] == "aravis":
        p["device"] = get(prefix + "DEVICE")                 # an Aravis camera id, "" = the first one
    if auto_size and p["input"] in ("usb", "csi"):
        raise ValueError(f"{prefix}SIZE=auto is for a network stream or a ROS topic: a {p['input']} camera "
                         "needs its WIDTHxHEIGHT (navera-discover writes it)")
    if p["input"] == "gst" and "name=sink" not in p["gst_pipeline"]:
        raise ValueError(f"{prefix}INPUT=gst needs {prefix}GST_PIPELINE ending in "
                         "'appsink name=sink' (BGR frames)")
    hfov = get(prefix + "HFOV_DEG")
    if hfov:
        p["camera_hfov_deg"] = float(hfov)
        if not (math.isfinite(p["camera_hfov_deg"]) and 5.0 <= p["camera_hfov_deg"] <= 170.0):
            raise ValueError(f"{prefix}HFOV_DEG={hfov}: expected 5-170 deg")
    if not p["calibration_file"] and not hfov:
        raise ValueError(f"set {prefix}CALIBRATION (navera_tools/calibrate_camera.py) "
                         f"or at least {prefix}HFOV_DEG")
    rpy = get(prefix + "MOUNT_RPY")
    if rpy:
        try:
            r, pi, y = (float(v) for v in rpy.split(","))
        except ValueError:
            raise ValueError(f"{prefix}MOUNT_RPY={rpy!r}: expected roll,pitch,yaw in degrees") from None
        p.update(mount_roll_deg=r, mount_pitch_deg=pi, mount_yaw_deg=y)
    g = get("NAVERA_GROUND_ALTITUDE_M")
    if g:
        p["ground_altitude_m"] = float(g)
    t = sensor_topics(env)
    p.update({k: v for k, v in t.items() if k != "sensor_source"})
    return p


def _size(raw: str, key: str):
    size = raw.lower().split("x")
    if len(size) != 2 or not all(s.isdigit() for s in size):
        raise ValueError(f"{key}={raw!r}: expected WIDTHxHEIGHT, e.g. 1200x900")
    w, h = int(size[0]), int(size[1])
    if not (64 <= w <= 4096 and 64 <= h <= 4096):
        raise ValueError(f"{key}={raw!r}: 64-4096 pixels each way")
    return w, h


def insta360_kit_params(environ=None) -> dict:
    """insta360_node parameters (the Insta360 kit) from the installation settings.

    NAVERA_INSTA360_MOUNT_AXES: camera IMU axes along body x,y,z (default +x,+z,-y: lying, the
    LEFT lens looking down, the camera's top towards the nose); NAVERA_INSTA360_MOUNT_RPY: a small
    trim roll,pitch,yaw (deg) after the axes; NAVERA_INSTA360_VIEW_SIZE: the straight-down view
    WIDTHxHEIGHT (default 1200x900); NAVERA_INSTA360_VIEW_HFOV_DEG: its width in degrees (default
    100); NAVERA_INSTA360_LENS / NAVERA_INSTA360_IMU: lens / IMU calibration files (default: the
    box's /var/lib/navera/insta360_lens.json, then the ~/.navera_sim/ files). Raises ValueError.
    """
    env = os.environ if environ is None else environ
    get = lambda k, d="": str(env.get(k, "") or d).strip()     # noqa: E731
    axes = get("NAVERA_INSTA360_MOUNT_AXES", INSTA360_DEFAULT_MOUNT_AXES).replace(" ", "")
    parts = axes.lower().split(",")
    names = [x.lstrip("+-") for x in parts]
    if len(parts) != 3 or sorted(names) != ["x", "y", "z"]:
        raise ValueError(f"NAVERA_INSTA360_MOUNT_AXES={axes!r}: three signed camera axes along body x,y,z, "
                         f"each axis once, e.g. {INSTA360_DEFAULT_MOUNT_AXES}")
    # a rotation, not a mirror: the permutation's parity times the signs must be +1
    perm = ["xyz".index(n) for n in names]
    parity = 1 if perm in ([0, 1, 2], [1, 2, 0], [2, 0, 1]) else -1
    signs = 1
    for x in parts:
        signs *= -1 if x.startswith("-") else 1
    if parity * signs != 1:
        raise ValueError(f"NAVERA_INSTA360_MOUNT_AXES={axes!r} is a mirror, not a rotation: flip one sign")
    p = {"mount_axes": axes}
    rpy = get("NAVERA_INSTA360_MOUNT_RPY")
    if rpy:
        try:
            r, pi, y = (float(v) for v in rpy.split(","))
        except ValueError:
            raise ValueError(f"NAVERA_INSTA360_MOUNT_RPY={rpy!r}: expected roll,pitch,yaw in degrees") from None
        if not all(-30.0 <= a <= 30.0 for a in (r, pi, y)):
            raise ValueError(f"NAVERA_INSTA360_MOUNT_RPY={rpy!r}: a trim within +-30 deg (turn the axes for more)")
        p.update(mount_roll_deg=r, mount_pitch_deg=pi, mount_yaw_deg=y)
    p["view_width"], p["view_height"] = _size(get("NAVERA_INSTA360_VIEW_SIZE", "1200x900"), "NAVERA_INSTA360_VIEW_SIZE")
    hfov = float(get("NAVERA_INSTA360_VIEW_HFOV_DEG", "100"))
    if not (math.isfinite(hfov) and 30.0 <= hfov <= 140.0):
        raise ValueError(f"NAVERA_INSTA360_VIEW_HFOV_DEG={hfov:g}: expected 30-140 deg")
    p["view_hfov_deg"] = hfov
    p["lens_file"] = get("NAVERA_INSTA360_LENS")
    p["calibration_file"] = get("NAVERA_INSTA360_IMU")
    return p


def insta360_camera_params(environ=None, prefix: str = "NAVERA_CAMERA_") -> dict:
    """live_camera parameters for NAVERA_CAMERA_INPUT=insta360: the kit's straight-down view (an
    image topic stamped at the exposure, an ideal lens of NAVERA_INSTA360_VIEW_HFOV_DEG, the mount
    already applied by the kit: NAVERA_CAMERA_MOUNT_RPY / _CROP / _CALIBRATION do not apply).
    """
    env = os.environ if environ is None else environ
    get = lambda k, d="": str(env.get(k, "") or d).strip()     # noqa: E731
    for k in ("MOUNT_RPY", "CROP", "CALIBRATION"):
        v = get(prefix + k)
        if k == "MOUNT_RPY" and v.replace(" ", "") in ("0,0,0", "0.0,0.0,0.0"):
            continue                                      # the example's default: nothing to apply
        if v:
            raise ValueError(f"{prefix}INPUT=insta360: {prefix}{k} does not apply (the kit cuts a straight "
                             f"view from the calibrated 360 lenses; its mount is NAVERA_INSTA360_MOUNT_AXES / _RPY)")
    kit = insta360_kit_params(env)
    p = {"input": "insta360", "device": "", "input_topic": INSTA360_IMAGE_TOPIC,
         "width": kit["view_width"], "height": kit["view_height"], "camera_hfov_deg": kit["view_hfov_deg"],
         "fps": float(get(prefix + "FPS", "1.0")),
         "capture_latency_s": float(get(prefix + "LATENCY_S", "0.0")),       # the kit stamps exposures
         "calibration_file": "", "crop": "",
         "max_tilt_deg": float(get(prefix + "MAX_TILT_DEG", "45")),
         "max_rate_dps": float(get(prefix + "MAX_RATE_DPS", "30")),
         "gimbal": get(prefix + "GIMBAL", "false").lower() in ("1", "true", "yes"),
         "gst_pipeline": ""}
    for key, k, lo, hi in ((prefix + "FPS", "fps", 0.05, 2.0), (prefix + "LATENCY_S", "capture_latency_s", -1.0, 2.0),
                           (prefix + "MAX_TILT_DEG", "max_tilt_deg", 5.0, 80.0),
                           (prefix + "MAX_RATE_DPS", "max_rate_dps", 1.0, 360.0)):
        if not (math.isfinite(p[k]) and lo <= p[k] <= hi):
            raise ValueError(f"{key}: {k} {p[k]:g} out of range [{lo:g}, {hi:g}]")
    g = get("NAVERA_GROUND_ALTITUDE_M")
    if g:
        p["ground_altitude_m"] = float(g)
    t = sensor_topics(env)
    p.update({k: v for k, v in t.items() if k != "sensor_source"})
    return p


def camera_mount_advice(vehicle_type: str, max_speed_mps, gimbal: bool):
    """None, or a warning when a FIXED camera will often be too tilted to use: a
    multirotor leans forward to fly fast (the simulator's quad: 45 deg at 43 km/h), and
    frames tilted over 45 deg are dropped. A plane banks in turns only; boats and
    robots stay roughly level.
    """
    if gimbal or str(vehicle_type).lower() != "drone" or not max_speed_mps:
        return None
    if max_speed_mps > 10.0:
        return (f"fixed camera on a multirotor flying up to {max_speed_mps * 3.6:.0f} km/h: it leans "
                f"30-45 deg at speed and frames over 45 deg are dropped — fit a gimbal, or cruise "
                f"under ~36 km/h")
    return None


def camera_identity(device: str, by_id_dir: str = "/dev/v4l/by-id"):
    """The stable name of a V4L2 camera (its /dev/v4l/by-id link: maker, model and
    serial number), or None. /dev/videoN numbers change with plug order; a lens
    calibration belongs to ONE camera.
    """
    try:
        target = os.path.realpath(device)
        for name in sorted(os.listdir(by_id_dir)):
            if os.path.realpath(os.path.join(by_id_dir, name)) == target:
                return name
    except OSError:
        pass
    return None


def imu_topic_params(environ=None) -> dict:
    """{"imu_topic": ...} for any node reading the attitude (night heading, star camera,
    estimator liveness): the box's IMU, the vehicle's (MAVLink) or its ROS topic, by
    NAVERA_SENSOR_SOURCE. A wrong setting is reported by the live camera; here the box
    IMU is kept so these pipelines still start.
    """
    try:
        return {"imu_topic": sensor_topics(environ)["imu_topic"]}
    except ValueError:
        return {"imu_topic": "/navera/sensors/imu"}


def shadow_mode_from_env(environ=None) -> str:
    """'true' when NAVERA_SHADOW_MODE asks the pipelines to run beside a working GPS,
    publishing their own positions for comparison (field recording).
    """
    env = os.environ if environ is None else environ
    return "true" if str(env.get("NAVERA_SHADOW_MODE", "")).strip().lower() in ("1", "true", "yes") else "false"

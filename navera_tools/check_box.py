#!/usr/bin/env python3
"""Pre-flight check of a NAVERA box: is everything a test needs present and alive?

    source /opt/ros/humble/setup.bash; source install/setup.bash
    set -a; . /etc/navera/navera.env; . /var/lib/navera/settings.env 2>/dev/null; . /var/lib/navera/discovered.env 2>/dev/null; set +a
    python3 navera_tools/check_box.py            # services running: checks for 15 s
    python3 navera_tools/check_box.py --camera   # also opens the camera itself (stop navera-pipeline-* first)

Each line is PASS, WARN (works, but check it) or FAIL (fix before testing). Exit code
0 = no FAIL. Nothing is changed on the box.
"""
import argparse
import glob
import json
import math
import os
import shutil
import sys
import threading
import time

OK, WARN, FAIL = "PASS", "WARN", "FAIL"
results = []


def report(level, what, detail=""):
    results.append(level)
    print(f"{level:4s}  {what}" + (f" — {detail}" if detail else ""))


def load_discovered():
    """The services read /var/lib/navera/discovered.env after navera.env: so does this check
    (else it would judge settings the box does not run with)."""
    from navera_common.state_store import state_dir
    path = os.path.join(state_dir(), "discovered.env")
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                from navera_common.atomic_io import unquote_env
                os.environ[k] = unquote_env(v)
    except OSError:
        pass


def check_discovery():
    """What navera-discover found at the last boot (settings left to "auto")."""
    from navera_common.state_store import state_dir
    path = os.path.join(state_dir(), "discovery.json")
    try:
        d = json.load(open(path))
    except (OSError, ValueError):
        report(WARN, "discovery", f"no report ({path}): navera-discover has not run — "
                                  "`sudo systemctl restart navera-discover` or set the sources by hand")
        return
    for line in d.get("report", []):
        missing = " NO " in f" {line} " or "CHECK" in line
        report(WARN if missing else OK, "discovery", line)


def check_settings():
    from navera_common.vehicle import live_camera_params, max_speed_mps_from_env, sensor_topics
    try:
        t = sensor_topics()
        report(OK, "sensor source", f"{t['sensor_source']}: attitude from {t['imu_topic']}")
    except ValueError as e:
        report(FAIL, "sensor source", str(e))
        t = None
    try:
        v = max_speed_mps_from_env()
        report(OK if v else WARN, "vehicle maximum speed",
               f"{v * 3.6:.0f} km/h" if v else "NAVERA_MAX_SPEED_KMH not set: node defaults are used")
    except ValueError as e:
        report(FAIL, "vehicle maximum speed", str(e))
    cam = None
    if os.environ.get("NAVERA_CAMERA", "replay") != "live":
        report(WARN, "camera", "NAVERA_CAMERA is not 'live': the pipelines replay recorded frames")
        return t, None                                  # camera settings unused in replay
    try:
        cam = live_camera_params()
    except ValueError as e:
        report(FAIL, "camera settings", str(e))
    if cam:
        if cam["calibration_file"]:
            try:
                import yaml
                from navera_common.camera_model import CameraModel
                c = yaml.safe_load(open(cam["calibration_file"]))
                m = CameraModel.from_calibration(c)
                # with a crop (one lens of a 360 camera) the calibration is of the cropped part
                from navera_common.camera_model import parse_crop
                crop = parse_crop(cam.get("crop"), cam["width"], cam["height"])
                used = (crop[2], crop[3]) if crop else (cam["width"], cam["height"])
                if m.size != used:
                    report(FAIL, "lens calibration", f"made for {m.size[0]}x{m.size[1]}, the camera gives "
                                                     f"{used[0]}x{used[1]}" + (f" (crop {list(crop)})" if crop else ""))
                elif list(c.get("crop") or []) != list(crop or []):
                    report(FAIL, "lens calibration", f"made with crop {c.get('crop')}, the camera uses "
                                                     f"{list(crop) if crop else 'the whole picture'}: calibrate again")
                else:
                    rms = c.get("rms_px")
                    report(OK if rms is not None and rms < 0.5 else WARN, "lens calibration",
                           f"{c.get('model')} RMS {rms} px, {m.out_hfov_deg:.1f} deg wide ({cam['calibration_file']})")
            except Exception as e:                                # noqa: BLE001
                report(FAIL, "lens calibration", f"{cam['calibration_file']}: {e}")
        elif cam["input"] == "insta360":
            report(OK, "lens calibration", "Insta360 kit: a computed straight view (ideal lens); the 360 "
                                           "lenses' calibration is checked below")
        else:
            report(*lens_state(cam, os.environ))
        from navera_common.vehicle import camera_mount_advice
        try:
            v = max_speed_mps_from_env()
        except ValueError:
            v = None
        advice = camera_mount_advice(os.environ.get("NAVERA_VEHICLE_TYPE", ""), v, cam["gimbal"])
        report(WARN if advice else OK, "camera mount",
               advice or ("gimbal (level)" if cam["gimbal"] else "fixed: tilt fine for this vehicle and speed"))
    return t, cam


def lens_state(cam, env):
    """(level, "lens calibration", detail) of a camera without a calibration file: the lens calibrated in
    flight for it (day_pkg.lens_selfcal, state lens_auto_*), else the starting value it flies with."""
    from navera_common import state_store
    kept = []
    for f in sorted(glob.glob(os.path.join(state_store.state_dir(), "lens_auto_*.json"))):
        d = state_store.load(os.path.basename(f)[:-5], float("inf")) or {}
        lens = d.get("lens") or {}
        if lens.get("image_width") and (cam["width"] in (0, lens["image_width"])):
            kept.append(d)
    src = str(env.get("NAVERA_CAMERA_LENS_SOURCE", "") or "").strip()
    start = f"{cam.get('camera_hfov_deg', float('nan')):g} deg " + (
        "(from the camera database)" if src == "database" else "(a guess: camera not known)" if src == "guess"
        else "(NAVERA_CAMERA_HFOV_DEG)")
    if kept:
        d = max(kept, key=lambda x: x.get("saved_at", 0))
        return (OK, "lens calibration", f"calibrated in flight {d.get('date')}: {d['lens'].get('model')}, "
                                         f"{d.get('hfov_deg')} deg, {d.get('rms_px')} px over {d.get('views')} views; "
                                         f"starting value {start}")
    return (WARN, "lens calibration", f"not calibrated yet: starts with {start} — calibrated automatically "
                                      "during the first flight's GPS phase (needs ~1 min of flight with GPS over "
                                      "mapped ground, best with a turn); or navera_tools/calibrate_camera.py")


def check_other_cameras(env=None):
    """The thermal and star cameras' lens (the jobs navera-discover gave are in its report above)."""
    env = os.environ if env is None else env
    for role, pre in (("thermal", "NAVERA_THERMAL_CAMERA_"), ("star", "NAVERA_STAR_CAMERA_")):
        if str(env.get(pre + "INPUT", "") or "").strip() and \
                str(env.get(pre + "LENS_SOURCE", "") or "").strip() == "guess":
            report(WARN, f"{role} camera lens",
                   (f"field of view guessed ({env.get(pre + 'HFOV_DEG')} deg): set {pre}HFOV_DEG from the lens "
                    "datasheet (night vision scales the thermal picture with it)") if role == "thermal" else
                   "field of view unknown: measured from the stars on the first solved sky, then kept")


def insta360_used(env=None) -> bool:
    env = os.environ if env is None else env
    return "insta360" in (str(env.get(k, "")).strip().lower() for k in ("NAVERA_SENSOR_SOURCE", "NAVERA_CAMERA_INPUT"))


def usb_node_writable(sysdev: str, sysfs="/sys/bus/usb/devices", dev="/dev/bus/usb"):
    """True / False: the camera's /dev/bus/usb node is writable by this user; None: not found."""
    try:
        bus = int(open(os.path.join(sysfs, sysdev, "busnum")).read())
        num = int(open(os.path.join(sysfs, sysdev, "devnum")).read())
    except (OSError, ValueError):
        return None
    path = os.path.join(dev, f"{bus:03d}", f"{num:03d}")
    return os.access(path, os.W_OK) if os.path.exists(path) else None


def check_insta360():
    """The Insta360 kit (NAVERA_SENSOR_SOURCE or NAVERA_CAMERA_INPUT = insta360): its settings, the
    camera in USB Android mode (sysfs only: never opened here), its USB permission, the lens / IMU
    calibration files, the Python modules, and the day view's geometry for this mount."""
    if not insta360_used():
        return
    from navera_common.discovery import probe_insta360
    from navera_common.vehicle import insta360_kit_params
    try:
        kit = insta360_kit_params()
        report(OK, "Insta360 kit settings", f"mount {kit['mount_axes']}, view {kit['view_width']}x"
                                            f"{kit['view_height']} {kit['view_hfov_deg']:g} deg")
    except ValueError as e:
        report(FAIL, "Insta360 kit settings", str(e))
        return
    found = probe_insta360()
    if found:
        w = usb_node_writable(found[0])
        report(OK if w else WARN if w is None else FAIL, "Insta360 camera",
               "One R in USB Android mode" + ("" if w else " — its USB node is NOT writable: install "
                                              "deploy/udev/99-insta360.rules and replug" if w is False else ""))
    else:
        webcam = [p for p in os.listdir("/dev/v4l/by-id")] if os.path.isdir("/dev/v4l/by-id") else []
        webcam = [p for p in webcam if "insta360" in p.lower()]
        report(FAIL, "Insta360 camera", "in WEBCAM mode: set its USB mode to Android (camera menu), replug"
               if webcam else "no One R in USB Android mode (2e1a:0002) — plugged? powered? Android mode?")
    for mod, why in (("usb", "pyusb (USB Android mode)"), ("av", "PyAV (H.264 key frames)")):
        try:
            __import__(mod)
            report(OK, f"Python module {mod}", why)
        except ImportError:
            report(FAIL, f"Python module {mod}", f"missing: pip3 install --user {'pyusb' if mod == 'usb' else 'av'}")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "camera_pkg"))
    try:
        from camera_pkg.insta360_imu import mount_rotation
        from camera_pkg.insta360_view import NadirView, load_lenses
        lenses, src = load_lenses(kit["lens_file"])
        report(WARN if src.startswith("first guess") else OK, "Insta360 lens calibration",
               src if not src.startswith("first guess") else
               "none found: the view is only roughly straight — copy the calibrated file to "
               "/var/lib/navera/insta360_lens.json (NAVERA_INSTA360_LENS)")
        v = NadirView(lenses, mount_rotation(kit["mount_axes"], kit.get("mount_roll_deg", 0.0),
                                             kit.get("mount_pitch_deg", 0.0), kit.get("mount_yaw_deg", 0.0)),
                      kit["view_hfov_deg"], 160, 120)
        report(WARN if v.warning() else OK, "Insta360 day view", v.warning() or
               f"straight down through the {v.centre_lens} lens ({v.centre_theta_deg} deg off its axis), "
               f"{v.coverage:.0%} covered")
    except Exception as e:                                         # noqa: BLE001
        report(FAIL, "Insta360 day view", str(e))
    from camera_pkg.insta360_kit import imu_calibration_file
    cal = imu_calibration_file(kit["calibration_file"])
    report(OK if os.path.isfile(cal) else WARN, "Insta360 IMU calibration",
           cal if os.path.isfile(cal) else f"{cal} missing: neutral values (the gyro bias is still measured "
                                           "at every stop; the accelerometer's 6-position calibration is not)")


def check_files():
    for var in ("NAVERA_MBTILES", "DAY_DATASET_DIR"):
        p = os.environ.get(var, "")
        if not p:
            report(WARN, var, "not set")
        elif not os.path.exists(p):
            report(FAIL, var, f"{p} does not exist (data disk mounted?)")
        elif var == "NAVERA_MBTILES":
            report(*mbtiles_verdict(p))
        else:
            report(OK, var, p)
    d = os.environ.get("DAY_DATASET_DIR", "")
    if d and os.path.isdir(d):
        report(OK if os.path.exists(os.path.join(d, "descriptors_cache.npz")) else FAIL, "satellite map of the route",
               "prepared" if os.path.exists(os.path.join(d, "descriptors_cache.npz")) else
               "not prepared (page /mission: Generate, Activate)")
    free = shutil.disk_usage(os.environ.get("NAVERA_AREAS_DIR", "/") if os.path.exists(
        os.environ.get("NAVERA_AREAS_DIR", "/")) else "/").free / 2 ** 30
    report(OK if free > 5 else WARN, "free disk space", f"{free:.0f} GB")
    report(*swap_verdict(open_text(os.environ.get("NAVERA_SWAPS", "/proc/swaps")),
                         int(os.environ.get("NAVERA_MIN_SWAP_MB") or 4096)))


def open_text(path):
    """The file's text, '' when it cannot be read."""
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def swap_verdict(swaps_text, min_mb=4096):
    """(level, what, detail) for the swap on disk in /proc/swaps' text (F5: the day pipeline was
    OOM-killed on the 8 GB Jetson without it). zram lives in RAM and does not count."""
    kb = 0
    for line in swaps_text.splitlines()[1:]:
        f = line.split()
        if len(f) >= 3 and not f[0].startswith("/dev/zram") and f[2].isdigit():
            kb += int(f[2])
    mb = kb // 1024
    if mb >= min_mb:
        return OK, "swap on disk", f"{mb} MB"
    return WARN, "swap on disk", (f"{mb} MB, need {min_mb} MB (zram does not count): the day pipeline may be "
                                  "OOM-killed — sudo deploy/setup_swap.sh")


def mbtiles_verdict(path):
    """(level, what, detail) for the satellite map file: it must open and hold tiles."""
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            n, zmin, zmax = con.execute("SELECT count(*), min(zoom_level), max(zoom_level) FROM tiles").fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        return FAIL, "NAVERA_MBTILES", f"{path}: not a readable map ({e})"
    if not n:
        return FAIL, "NAVERA_MBTILES", f"{path}: no tiles"
    return OK, "NAVERA_MBTILES", f"{path}: {n} tiles, zoom {zmin}-{zmax}"


def config_findings(env):
    """Static mistakes in the settings, as [(level, what, detail)] (no hardware needed)."""
    out = []
    get = lambda k: str(env.get(k, "") or "").strip()                       # noqa: E731
    from navera_output import mavlink_url
    ports = {}

    def port_of(key, url):
        try:
            dev, baud = mavlink_url.parse(url)
        except ValueError as e:
            out.append((FAIL, key, str(e)))
            return
        if baud is not None:
            ports.setdefault(os.path.realpath(dev), []).append(key)
    for key in ("NAVERA_MAVLINK_URL", "NAVERA_VEHICLE_MAVLINK_URL"):
        if get(key) and get(key).lower() not in ("off", "none"):
            port_of(key, get(key))
    if get("NAVERA_GPS_SOURCE") == "serial":
        ports.setdefault(os.path.realpath(get("NAVERA_GPS_PORT") or "/dev/ttyTHS1"), []).append("NAVERA_GPS_PORT")
    if get("NAVERA_NMEA_PORT"):
        ports.setdefault(os.path.realpath(get("NAVERA_NMEA_PORT")), []).append("NAVERA_NMEA_PORT")
    for dev, keys in ports.items():
        if len(keys) > 1:
            out.append((FAIL, "serial ports", f"{dev} is used by {', '.join(keys)}: one program per port "
                                              "(one autopilot port: NAVERA_MAVLINK_URL=udpout:127.0.0.1:14650)"))
    gps = get("NAVERA_GPS_SOURCE")
    if gps in ("vehicle", "vehicle_gps1") and not get("NAVERA_VEHICLE_MAVLINK_URL"):
        out.append((FAIL, "GPS", f"NAVERA_GPS_SOURCE={gps} is read by navera-vehicle-link, but "
                                 "NAVERA_VEHICLE_MAVLINK_URL is empty"))
    if gps == "network":
        from navera_common.gnss import parse_stream_url
        try:
            parse_stream_url(get("NAVERA_GPS_URL"))
        except ValueError as e:
            out.append((FAIL, "NAVERA_GPS_URL", str(e)))
    if gps == "dronecan":
        iface = get("NAVERA_GPS_CAN_IFACE") or "can0"
        if ":" not in iface:
            try:
                up = int(open(f"/sys/class/net/{iface}/flags").read(), 16) & 1
            except (OSError, ValueError):
                up = None
            if not up:
                out.append((FAIL, "DroneCAN GPS", f"{iface} is {'missing' if up is None else 'down'}: "
                                                  f"sudo ip link set {iface} up type can bitrate 1000000 "
                                                  "(deploy/README.md, CAN bus)"))
        import importlib.util
        if importlib.util.find_spec("dronecan") is None:
            out.append((FAIL, "DroneCAN GPS", "the pip package dronecan is not installed"))
    url = get("NAVERA_MAVLINK_URL")
    if url.startswith("udpout:127.0.0.1:") and not get("NAVERA_VEHICLE_MAVLINK_URL"):
        out.append((FAIL, "MAVLink output", "goes to navera-vehicle-link's relay, but NAVERA_VEHICLE_MAVLINK_URL "
                                            "is empty: the autopilot would receive nothing"))
    fwd = get("NAVERA_FORWARD_DEGRADED").lower()
    if fwd in ("1", "true", "yes", "on"):
        try:
            sigma = float(get("NAVERA_DEGRADED_SIGMA_M"))
        except ValueError:
            out.append((FAIL, "forwarding", "NAVERA_FORWARD_DEGRADED without NAVERA_DEGRADED_SIGMA_M: the output "
                                            "will not start"))
        else:
            if sigma > 1000:
                out.append((FAIL, "forwarding", f"NAVERA_DEGRADED_SIGMA_M {sigma:g} m > 1000 m: nothing would be sent"))
            elif sigma > 100:
                out.append((WARN, "forwarding", f"NAVERA_DEGRADED_SIGMA_M {sigma:g} m: ArduPilot's EKF caps an "
                                                "accuracy at 100 m and will trust these positions more than stated"))
    elif fwd and fwd not in ("0", "false", "no", "off"):
        out.append((FAIL, "forwarding", f"NAVERA_FORWARD_DEGRADED={fwd!r}: expected true or false"))
    if get("NAVERA_NMEA_PORT") and get("NAVERA_NMEA_FORWARD_DEGRADED").lower() in ("1", "true", "yes", "on"):
        out.append((WARN, "forwarding", "NAVERA_NMEA_FORWARD_DEGRADED: NMEA carries no accuracy — the autopilot "
                                        "will trust vision positions as a precise GPS"))
    uses_ros = get("NAVERA_SENSOR_SOURCE") == "ros" or get("NAVERA_GPS_SOURCE") == "ros" or \
        get("NAVERA_CAMERA_INPUT") == "ros"
    if uses_ros and get("ROS_LOCALHOST_ONLY") == "1":
        out.append((FAIL, "ROS network", "ROS sources with ROS_LOCALHOST_ONLY=1: NAVERA cannot hear the "
                                         "vehicle's computer (set 0 and the vehicle's ROS_DOMAIN_ID)"))
    return out


def check_config():
    findings = config_findings(os.environ)
    for f in findings:
        report(*f)
    if not findings:
        report(OK, "settings", "no conflict found (ports, outputs, forwarding, ROS network)")


def check_camera_device(cam):
    import cv2
    if cam is None or cam["input"] != "usb":
        return
    cap = cv2.VideoCapture(cam["device"], cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam["width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam["height"])
    if not cap.isOpened():
        report(FAIL, "camera device", f"cannot open {cam['device']} (in use by the pipeline? unplugged?)")
        return
    n, t0, shape = 0, time.time(), None
    while time.time() - t0 < 3.0:
        ok, img = cap.read()
        if ok:
            n += 1
            shape = img.shape
    cap.release()
    if not n:
        report(FAIL, "camera device", f"{cam['device']} opens but sends no frame")
    elif (shape[1], shape[0]) != (cam["width"], cam["height"]):
        report(FAIL, "camera device", f"sends {shape[1]}x{shape[0]}, set to {cam['width']}x{cam['height']}")
    else:
        report(OK, "camera device", f"{cam['device']} {shape[1]}x{shape[0]} at {n / 3.0:.0f} frames/s")


def check_ros(topics, seconds):
    import rclpy
    from geometry_msgs.msg import PointStamped
    from navera_msgs.msg import NavStatus
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu, NavSatFix, Range
    from std_msgs.msg import String
    rclpy.init()
    node = rclpy.create_node("navera_check_box")
    got = {}
    lock = threading.Lock()

    def keep(name):
        def cb(m):
            with lock:
                got.setdefault(name, []).append((time.time(), m))
        return cb
    t = topics or {}
    subs = [(Imu, t.get("imu_topic", "/navera/sensors/imu"), "imu"),
            (NavSatFix, t.get("gps_topic", "/navera/sensors/gps_fix"), "gps"),
            (Range, t.get("altitude_topic", "/navera/sensors/altitude_agl"), "agl"),
            (PointStamped, "/navera/vehicle/relative_alt", "rel"),
            (String, "/navera/vehicle/status", "vlink"),
            (String, "/navera/sensors/rtc_status", "rtc"),
            (NavStatus, "/navera/nav_status", "nav"),
            (String, "/day/frame_meta", "meta"),
            (String, "/navera/sensors/insta360/status", "kit"),
            (String, "/thermal/frame_meta", "tmeta")]
    for typ, topic, name in subs:
        node.create_subscription(typ, topic, keep(name), qos_profile_sensor_data if typ is Imu else 10)
    end = time.time() + seconds
    while time.time() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    rate = lambda k: len(got.get(k, [])) / seconds                    # noqa: E731
    src = t.get("sensor_source", "box")
    # attitude
    r = rate("imu")
    if r == 0:
        report(FAIL, "attitude", f"nothing on {t.get('imu_topic')}")
    else:
        m = got["imu"][-1][1]
        q = m.orientation
        bad = not (0.9 < q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w < 1.1)
        lag = time.time() - (m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
        report(FAIL if bad or r < 10 else WARN if r < 25 or abs(lag) > 0.2 else OK, "attitude",
               f"{r:.0f} Hz on {t.get('imu_topic')}, stamps {lag * 1000:+.0f} ms from now"
               + (" — orientation not a unit quaternion" if bad else ""))
    # GPS
    if rate("gps") == 0:
        report(WARN, "GPS", "nothing received (no receiver, or no fix yet)")
    else:
        fixes = [m for _, m in got["gps"] if m.status.status >= 0 and math.isfinite(m.latitude)]
        report(OK if fixes else WARN, "GPS", f"{rate('gps'):.1f} Hz, {len(fixes)} fixes"
               + (f", last {fixes[-1].latitude:.5f}, {fixes[-1].longitude:.5f}" if fixes else " — no fix: outdoors?"))
    # heights
    if rate("agl"):
        report(OK, "measured height above ground", f"{got['agl'][-1][1].range:.1f} m ({rate('agl'):.0f} Hz)")
    if rate("rel"):
        report(OK, "vehicle height above home (barometer)", f"{got['rel'][-1][1].point.z:.1f} m")
    elif src == "box":
        report(WARN, "barometer", "none in box mode: after GPS loss the height comes from the image "
                                  "(matches) or is held")
    gps_src = os.environ.get("NAVERA_GPS_SOURCE", "")
    if src == "vehicle" or gps_src in ("vehicle", "vehicle_gps1"):
        if not rate("vlink"):
            report(FAIL, "vehicle link", "no /navera/vehicle/status (navera-vehicle-link service?)")
        else:
            st = json.loads(got["vlink"][-1][1].data)
            report(OK if st.get("link") else FAIL, "vehicle link",
                   f"{st.get('autopilot')} on {st.get('url')}" if st.get("link") else f"no autopilot on {st.get('url')}")
            if gps_src == "vehicle_gps1" and st.get("link"):
                report(OK if st.get("gps1_read") else FAIL, "autopilot's first GPS",
                       st.get("gps1") or "no answer about GPS1 (navera-vehicle-link older than the setting?)")
    if insta360_used():
        if not rate("kit"):
            report(FAIL, "Insta360 kit", "no /navera/sensors/insta360/status (navera-insta360 service? "
                                         "`journalctl -u navera-insta360 -n 50`)")
        else:
            k = json.loads(got["kit"][-1][1].data)
            age = k.get("imu_age_s")
            bad = k.get("error") or (age is not None and age > 1.0)
            err = f" — {k.get('error')}" if k.get("error") else ""
            report(WARN if bad else OK, "Insta360 kit",
                   f"{k.get('frames')} frames, tilt +-{k.get('tilt_sigma_deg')} deg, heading "
                   f"{k.get('heading_deg')} ({k.get('heading_source')}){err}"
                   + (f" — IMU silent {age} s" if age is not None and age > 1.0 else ""))
    if rate("rtc"):
        st = json.loads(got["rtc"][-1][1].data)
        report(OK if st.get("valid") else FAIL, "clock (RTC)", f"valid={st.get('valid')} drift={st.get('drift_s')}")
    else:
        report(WARN, "clock (RTC)", "no /navera/sensors/rtc_status")
    if rate("nav"):
        names = {0: "INITIALIZING", 1: "NO FIX", 2: "FIX", 3: "DEGRADED"}
        st = got["nav"][-1][1].state
        report(OK if st == 2 else WARN, "NAVERA", f"{names.get(st, '?')}: {got['nav'][-1][1].reason}"
               + ("" if st == 2 else " (before take-off NAVERA should have a GPS FIX)"))
    else:
        report(FAIL, "NAVERA", "no /navera/nav_status (navera-estimator service?)")
    # the live camera's frames
    meta = got.get("meta") or got.get("tmeta")
    if not meta:
        report(WARN, "camera frames to vision", "none on /day or /thermal frame_meta (camera not live, or "
                                                "waiting for the vision pipeline to be ready)")
    else:
        d = json.loads(meta[-1][1].data)
        issues = []
        if d.get("altitude_m") is None:
            issues.append("height above ground unknown")
        if d.get("attitude_source") in (None, "none"):
            issues.append("no attitude: frames not straightened")
        if d.get("usable") is False:
            issues.append(d.get("reason", "unusable"))
        if len(meta) / seconds < 0.7:
            issues.append("fewer than 0.7 frames/s reach vision: positions may arrive too far apart "
                          "(CPU load? camera fps?)")
        report(WARN if issues else OK, "camera frames to vision",
               f"{len(meta) / seconds:.1f}/s, height {d.get('altitude_m')} m ({d.get('altitude_source')}), "
               f"tilt {d.get('tilt_deg')} deg, {d.get('camera_hfov_deg')} deg wide"
               + ("; " + "; ".join(issues) if issues else ""))
    node.destroy_node()
    rclpy.shutdown()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=15.0, help="how long to listen to the topics")
    ap.add_argument("--camera", action="store_true", help="also open the camera device itself")
    ap.add_argument("--no-ros", action="store_true", help="settings and files only")
    a = ap.parse_args()
    print("NAVERA pre-flight check\n")
    load_discovered()
    check_discovery()
    check_config()
    topics, cam = check_settings()
    check_other_cameras()
    check_insta360()
    check_files()
    if a.camera and cam:
        check_camera_device(cam)
    if not a.no_ros:
        check_ros(topics, a.seconds)
    n_fail, n_warn = results.count(FAIL), results.count(WARN)
    print(f"\n{'READY' if not n_fail else 'NOT READY'}: {n_fail} fail, {n_warn} warning(s)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())

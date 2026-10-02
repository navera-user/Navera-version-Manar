#!/usr/bin/env python3
"""Pre-flight check of a NAVERA box: is everything a test needs present and alive?

    source /opt/ros/humble/setup.bash; source install/setup.bash
    set -a; . /etc/navera/navera.env; . /var/lib/navera/settings.env 2>/dev/null; set +a
    python3 navera_tools/check_box.py            # services running: checks for 15 s
    python3 navera_tools/check_box.py --camera   # also opens the camera itself (stop navera-pipeline-* first)

Each line is PASS, WARN (works, but check it) or FAIL (fix before testing). Exit code
0 = no FAIL. Nothing is changed on the box.
"""
import argparse
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
                if m.size != (cam["width"], cam["height"]):
                    report(FAIL, "lens calibration", f"made for {m.size[0]}x{m.size[1]}, the camera is set to "
                                                     f"{cam['width']}x{cam['height']}")
                else:
                    rms = c.get("rms_px")
                    report(OK if rms is not None and rms < 0.5 else WARN, "lens calibration",
                           f"{c.get('model')} RMS {rms} px, {m.out_hfov_deg:.1f} deg wide ({cam['calibration_file']})")
            except Exception as e:                                # noqa: BLE001
                report(FAIL, "lens calibration", f"{cam['calibration_file']}: {e}")
        else:
            report(WARN, "lens calibration", "none: the lens is taken as distortion-free "
                                             "(navera_tools/calibrate_camera.py)")
        from navera_common.vehicle import camera_mount_advice
        try:
            v = max_speed_mps_from_env()
        except ValueError:
            v = None
        advice = camera_mount_advice(os.environ.get("NAVERA_VEHICLE_TYPE", ""), v, cam["gimbal"])
        report(WARN if advice else OK, "camera mount",
               advice or ("gimbal (level)" if cam["gimbal"] else "fixed: tilt fine for this vehicle and speed"))
    return t, cam


def check_files():
    for var in ("NAVERA_MBTILES", "DAY_DATASET_DIR"):
        p = os.environ.get(var, "")
        if not p:
            report(WARN, var, "not set")
        elif not os.path.exists(p):
            report(FAIL, var, f"{p} does not exist (data disk mounted?)")
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
    if src == "vehicle":
        if not rate("vlink"):
            report(FAIL, "vehicle link", "no /navera/vehicle/status (navera-vehicle-link service?)")
        else:
            st = json.loads(got["vlink"][-1][1].data)
            report(OK if st.get("link") else FAIL, "vehicle link",
                   f"{st.get('autopilot')} on {st.get('url')}" if st.get("link") else f"no autopilot on {st.get('url')}")
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
    topics, cam = check_settings()
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

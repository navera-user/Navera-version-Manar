#!/usr/bin/env python3
"""Integration: live_camera with a vehicle camera on ROS, an IMU and a GPS.

A level straight-down scene is warped into what a camera tilted 10 deg nose-up and
6 deg right-wing-down sees; live_camera (input=ros) must publish it straightened —
the point under the vehicle back at the image centre — with the height above ground
from the GPS, corrected by an image-measured height, the attitude used, and the
exposure stamp; and wait for the localizer's ack before the next frame. Once the day node
says the camera delay is 1 s (camera_delay topic), a frame is straightened with the attitude of
1 s before its stamp (a banked plane's attitude at the exposure, F35), its stamp unchanged.
"""
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image, Imu, NavSatFix, NavSatStatus, Range
from std_msgs.msg import Bool, Int32, String

from navera_common.camera_model import CameraModel, camera_rotation, nadir_homography

W, H = 640, 480
NS = "/livetest"


def q_body(roll_deg, nose_up_deg, heading_deg):
    r, p, y = math.radians(roll_deg), -math.radians(nose_up_deg), math.radians(90.0 - heading_deg)
    cr, sr, cp, sp, cy, sy = (math.cos(r / 2), math.sin(r / 2), math.cos(p / 2), math.sin(p / 2),
                              math.cos(y / 2), math.sin(y / 2))
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def main():
    rng = np.random.default_rng(1)
    scene = cv2.GaussianBlur((rng.random((H, W)) * 255).astype(np.uint8), (0, 0), 3)
    cv2.circle(scene, (W // 2, H // 2), 6, 255, -1)
    q = q_body(6.0, 10.0, 40.0)
    Hn = nadir_homography(CameraModel.ideal(84.0, (W, H)).K_out, camera_rotation(q))
    tilted = cv2.cvtColor(cv2.warpPerspective(scene, np.linalg.inv(Hn), (W, H)), cv2.COLOR_GRAY2BGR)

    proc = subprocess.Popen(
        ["ros2", "run", "camera_pkg", "live_camera.py", "--ros-args", "-r", f"__ns:={NS}",
         "-p", "input:=ros", "-p", "input_topic:=/vehicle/cam", "-p", f"width:={W}", "-p", f"height:={H}",
         "-p", "camera_hfov_deg:=84.0", "-p", "fps:=5.0", "-p", "wait_for_ready:=true",
         "-p", "ready_topic:=/livetest_ready", "-p", "ack_timeout_s:=3.0",
         "-p", "imu_topic:=/livetest/imu", "-p", "gps_topic:=/livetest/gps",
         "-p", "vision_altitude_topic:=/livetest/vision_alt", "-p", "delay_topic:=/livetest/camera_delay"],
        stdout=open(os.environ.get('NAVERA_TEST_LOG', os.devnull), 'w'), stderr=subprocess.STDOUT, start_new_session=True)
    try:
        return _run(proc)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)


def _run(proc):
    rng = np.random.default_rng(1)
    scene = cv2.GaussianBlur((rng.random((H, W)) * 255).astype(np.uint8), (0, 0), 3)
    cv2.circle(scene, (W // 2, H // 2), 6, 255, -1)
    q = q_body(6.0, 10.0, 40.0)
    Hn = nadir_homography(CameraModel.ideal(84.0, (W, H)).K_out, camera_rotation(q))
    tilted = cv2.cvtColor(cv2.warpPerspective(scene, np.linalg.inv(Hn), (W, H)), cv2.COLOR_GRAY2BGR)
    rclpy.init()
    node = Node("live_camera_test")
    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
    pub_img = node.create_publisher(Image, "/vehicle/cam", qos_profile_sensor_data)
    pub_imu = node.create_publisher(Imu, "/livetest/imu", 50)
    pub_gps = node.create_publisher(NavSatFix, "/livetest/gps", 10)
    pub_valt = node.create_publisher(Range, "/livetest/vision_alt", 10)
    pub_ready = node.create_publisher(Bool, "/livetest_ready", latched)
    pub_ack = node.create_publisher(Int32, f"{NS}/frame_done", 10)
    pub_delay = node.create_publisher(String, "/livetest/camera_delay", latched)
    got_meta, got_img = [], []
    node.create_subscription(String, f"{NS}/frame_meta", lambda m: got_meta.append(json.loads(m.data)), 10)
    node.create_subscription(Image, f"{NS}/image_raw", got_img.append, 10)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    spinner = threading.Thread(target=ex.spin, daemon=True)
    spinner.start()
    bridge = CvBridge()
    failures = []

    def now():
        return node.get_clock().now().to_msg()

    state = {"gps_alt": 52.0, "run": True, "q": q}

    def sensors():                                     # IMU 50 Hz, GPS 5 Hz, as real sensors
        k = 0
        while state["run"]:
            st = now()
            imu = Imu(); imu.header.stamp = st
            e = 1e-6 * (k % 7)                          # sensor noise: a real attitude never repeats exactly
            qq = state["q"]
            imu.orientation.x, imu.orientation.y, imu.orientation.z, imu.orientation.w = qq[0] + e, qq[1], qq[2], qq[3]
            pub_imu.publish(imu)
            if k % 10 == 0:
                fx = NavSatFix(); fx.header.stamp = st; fx.status.status = NavSatStatus.STATUS_FIX
                fx.latitude, fx.longitude, fx.altitude = 35.8, 10.6, state["gps_alt"]
                pub_gps.publish(fx)
            k += 1
            time.sleep(0.02)

    threading.Thread(target=sensors, daemon=True).start()

    def feed(seconds, gps_alt, until=None):            # the vehicle camera, 10 Hz
        """Stream frames for `seconds`, or until `until()` (then at most 15 s: loaded machines)."""
        state["gps_alt"] = gps_alt
        end = time.time() + (15.0 if until else seconds)
        while time.time() < end and not (until and until()):
            im = bridge.cv2_to_imgmsg(tilted, "bgr8"); im.header.stamp = now()
            pub_img.publish(im)
            time.sleep(0.1)

    deadline = time.time() + 25
    while node.count_subscribers("/vehicle/cam") == 0 and time.time() < deadline:
        time.sleep(0.2)
    feed(1.5, 52.0)                                    # on the ground at power-on: ground = 52 m
    if os.environ.get("NAVERA_TEST_VERBOSE"):
        print("imu subscribers:", node.count_subscribers("/livetest/imu"), "gps subscribers:", node.count_subscribers("/livetest/gps"))
    if got_meta:
        failures.append("frames published before the localizer was ready")
    feed(1.5, 202.0)                                   # climbs: 150 m above the ground
    deadline = time.time() + 10                        # our receivers connected before frame 0
    while (node.count_publishers(f"{NS}/frame_meta") == 0 or node.count_publishers(f"{NS}/image_raw") == 0) \
            and time.time() < deadline:
        time.sleep(0.1)
    time.sleep(0.5)
    pub_ready.publish(Bool(data=True))
    feed(0, 202.0, until=lambda: len(got_meta) >= 1)
    feed(1.5, 202.0)                                   # no ack yet: no second frame
    if len(got_meta) != 1:
        failures.append(f"{len(got_meta)} frames without an ack, expected 1 (back-pressure)")
    if got_meta:
        m = got_meta[0]
        if os.environ.get("NAVERA_TEST_VERBOSE"):
            print("meta:", m)
        img = bridge.imgmsg_to_cv2(got_img[0], "mono8")
        blur = cv2.GaussianBlur(img, (0, 0), 2)[200:280, 280:360]
        yy, xx = np.unravel_index(np.argmax(blur), blur.shape)
        off = math.hypot(xx + 280 - W / 2, yy + 200 - H / 2)
        checks = [
            (abs(m.get("altitude_m", 0) - 150.0) < 1.0, f"altitude {m.get('altitude_m')} (expected 150, GPS - ground)"),
            (m.get("altitude_source") == "GPS - ground", f"altitude source {m.get('altitude_source')}"),
            (m.get("straightened") is True and abs(m.get("pitch_deg", 0) - 10.0) < 0.1
             and abs(m.get("roll_deg", 0) - 6.0) < 0.1, f"attitude {m.get('roll_deg')}/{m.get('pitch_deg')}"),
            (abs((m.get("heading_deg") or -1.0) - 40.0) < 0.1, f"heading {m.get('heading_deg')}"),
            (m.get("gps_valid") is False and m.get("gps_lat") == 35.8, "GPS must be recorded, never valid"),
            (off < 3.0, f"point under the vehicle {off:.1f} px from the centre after straightening"),
            (m["image_stamp_ns"] == got_img[0].header.stamp.sec * 10**9 + got_img[0].header.stamp.nanosec,
             "meta and image stamps differ"),
        ]
        failures += [why for ok, why in checks if not ok]
    # image-measured height: higher ground than the GPS assumes
    vr = Range(); vr.header.stamp = now(); vr.range, vr.field_of_view, vr.max_range = 137.0, 2.0, 1e4
    pub_valt.publish(vr)
    time.sleep(0.3)
    pub_ack.publish(Int32(data=got_meta[0]["frame_id"] if got_meta else 0))
    feed(0, 202.0, until=lambda: len(got_meta) >= 2)
    if len(got_meta) < 2:
        failures.append("no frame after the ack")
    elif got_meta[-1].get("altitude_source") != "image + GPS" or abs(got_meta[-1]["altitude_m"] - 137.0) > 1.0:
        failures.append(f"image-measured height not used: {got_meta[-1].get('altitude_m')} "
                        f"({got_meta[-1].get('altitude_source')})")
    elif got_meta[-1].get("attitude_delay_s") != 0.0 or not got_meta[-1].get("mount_id"):
        failures.append(f"meta without attitude_delay_s 0 / mount_id: {got_meta[-1]}")

    # the day node learned a 1 s camera delay; the vehicle then rolls the other way: the next frame's
    # exposure (1 s before its stamp) still had the old attitude
    pub_delay.publish(String(data=json.dumps({"correction_s": 1.0, "delay_s": 1.0, "sigma_s": 0.1,
                                              "nominal_s": 0.0, "auto": True, "stable": True})))
    state["q"] = q_body(-6.0, 10.0, 40.0)
    feed(0.5, 202.0)
    n2 = len(got_meta)
    pub_ack.publish(Int32(data=got_meta[-1]["frame_id"] if got_meta else 0))
    feed(0, 202.0, until=lambda: len(got_meta) > n2)
    if len(got_meta) <= n2:
        failures.append("no frame after the delay message")
    else:
        m3, im3 = got_meta[-1], got_img[-1]
        if os.environ.get("NAVERA_TEST_VERBOSE"):
            print("meta after the delay:", m3)
        if m3.get("attitude_delay_s") != 1.0 or abs(m3.get("roll_deg", 0) - 6.0) > 0.1:
            failures.append(f"attitude not taken 1 s before the stamp: shift {m3.get('attitude_delay_s')}, "
                            f"roll {m3.get('roll_deg')} (6 = at the exposure, -6 = at the arrival)")
        if m3["image_stamp_ns"] != im3.header.stamp.sec * 10**9 + im3.header.stamp.nanosec:
            failures.append("the stamp moved with the attitude (the day node dates it)")

    state["run"] = False
    os.killpg(proc.pid, signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
    ex.shutdown()
    spinner.join(timeout=5)
    node.destroy_node()
    rclpy.shutdown()
    for f in failures:
        print("FAIL", f)
    print("live_camera:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

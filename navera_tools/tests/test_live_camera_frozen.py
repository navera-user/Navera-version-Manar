#!/usr/bin/env python3
"""Integration: live_camera never hands a frozen camera picture to the localizers (D24 / H-01b).

live_camera (input=ros) is fed a vehicle camera that first works (a new picture every frame),
then freezes (the same picture again with new stamps: a stuck driver or a stalled RTSP stream),
then re-sends a frame with an old stamp, then recovers. Every frozen frame must be published
marked unusable with the reason "camera image frozen" (the localizers then publish no fix),
camera_health must say frozen, and the first new picture must be usable again.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import Int32, String

W, H = 320, 240
NS = "/frozentest"


def main():
    proc = subprocess.Popen(
        ["ros2", "run", "camera_pkg", "live_camera.py", "--ros-args", "-r", f"__ns:={NS}",
         "-p", "input:=ros", "-p", "input_topic:=/frozentest/vehicle_cam", "-p", f"width:={W}",
         "-p", f"height:={H}", "-p", "camera_hfov_deg:=84.0", "-p", "fps:=5.0", "-p", "wait_for_ready:=false",
         "-p", "require_attitude:=false", "-p", "ack_timeout_s:=1.0",
         "-p", "imu_topic:=/frozentest/imu", "-p", "gps_topic:=/frozentest/gps"],
        stdout=open(os.environ.get('NAVERA_TEST_LOG', os.devnull), 'w'), stderr=subprocess.STDOUT,
        start_new_session=True)
    try:
        return _run()
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)


def _run():
    rclpy.init()
    node = Node("live_camera_frozen_test")
    pub_img = node.create_publisher(Image, "/frozentest/vehicle_cam", qos_profile_sensor_data)
    pub_ack = node.create_publisher(Int32, f"{NS}/frame_done", 10)
    metas, health = [], []

    def on_meta(m):
        d = json.loads(m.data)
        metas.append(d)
        pub_ack.publish(Int32(data=int(d["frame_id"])))      # the localizer is done: next frame

    node.create_subscription(String, f"{NS}/frame_meta", on_meta, 10)
    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
    node.create_subscription(String, f"{NS}/camera_health", lambda m: health.append(json.loads(m.data)), latched)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()
    bridge = CvBridge()
    rng = np.random.default_rng(3)
    failures = []

    deadline = time.time() + 30
    while node.count_subscribers("/frozentest/vehicle_cam") == 0 and time.time() < deadline:
        time.sleep(0.2)

    def feed(picture, n_frames, stamp=None):
        """Publish at 10 Hz until n_frames more frames came out (at most 20 s: loaded machines)."""
        start, end = len(metas), time.time() + 20.0
        while len(metas) < start + n_frames and time.time() < end:
            im = bridge.cv2_to_imgmsg(picture() if callable(picture) else picture, "bgr8")
            im.header.stamp = stamp or node.get_clock().now().to_msg()
            pub_img.publish(im)
            time.sleep(0.1)
        return metas[start:]

    def fresh():
        return rng.integers(0, 256, (H, W, 3), dtype=np.uint8)

    working = feed(fresh, 3)
    if len(working) < 3 or not all(m.get("usable") for m in working):
        failures.append(f"working camera: {[(m.get('usable'), m.get('reason')) for m in working]}")
    stuck = fresh()
    frozen = feed(stuck, 3)[1:]                         # the first one is a new picture
    if len(frozen) < 2 or any(m.get("usable") is not False or "camera image frozen" not in str(m.get("reason"))
                              for m in frozen):
        failures.append(f"frozen pictures not refused: {[(m.get('usable'), m.get('reason')) for m in frozen]}")
    if not (health and health[-1].get("frozen") is True and health[-1].get("frozen_frames", 0) >= 2):
        failures.append(f"camera_health does not report the freeze: {health[-1:] or 'nothing received'}")
    old = working[0]["image_stamp_ns"] if working else 0
    replay = feed(fresh(), 1, stamp=rclpy.time.Time(nanoseconds=old).to_msg())
    if not replay or replay[-1].get("usable") is not False or "did not advance" not in str(replay[-1].get("reason")):
        failures.append(f"a frame with an old stamp was not refused: {replay[-1:] or 'none'}")
    recovered = feed(fresh, 3)[1:]
    if len(recovered) < 2 or not all(m.get("usable") for m in recovered):
        failures.append(f"no recovery: {[(m.get('usable'), m.get('reason')) for m in recovered]}")
    if not (health and health[-1].get("frozen") is False):
        failures.append(f"camera_health still frozen after recovery: {health[-1:]}")

    ex.shutdown()
    node.destroy_node()
    rclpy.shutdown()
    for f in failures:
        print("FAIL", f)
    print("live_camera frozen pictures:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

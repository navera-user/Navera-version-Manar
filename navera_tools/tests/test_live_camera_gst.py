#!/usr/bin/env python3
"""live_camera reads a GStreamer source (the path the Jetson's CSI cameras and IP cameras
take): a test pattern through input=gst must come out as NAVERA frames of the right size.
Exit code 0 = pass."""
import json
import os
import signal
import subprocess
import sys
import threading
import time

import rclpy
from cv_bridge import CvBridge
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, String

NS = "/gsttest"
PIPE = ("videotestsrc pattern=smpte ! video/x-raw,width=642,height=480,framerate=15/1 ! videoconvert ! "
        "video/x-raw,format=BGR ! appsink name=sink drop=true max-buffers=1 sync=false")


def main():
    proc = subprocess.Popen(
        ["ros2", "run", "camera_pkg", "live_camera.py", "--ros-args", "-r", f"__ns:={NS}",
         "-p", "input:=gst", "-p", f"gst_pipeline:={PIPE}", "-p", "width:=642", "-p", "height:=480",
         "-p", "camera_hfov_deg:=84.0", "-p", "fps:=5.0", "-p", "gimbal:=true",
         "-p", "wait_for_ready:=true", "-p", "ready_topic:=/gsttest_ready",
         "-p", "imu_topic:=/gsttest/imu", "-p", "gps_topic:=/gsttest/gps"],
        stdout=open(os.environ.get("NAVERA_TEST_LOG", os.devnull), "w"), stderr=subprocess.STDOUT,
        start_new_session=True)
    rclpy.init()
    node = rclpy.create_node("gst_test")
    imgs, metas = [], []
    latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    pub_ready = node.create_publisher(Bool, "/gsttest_ready", latched)
    node.create_subscription(Image, f"{NS}/image_raw", imgs.append, 10)
    node.create_subscription(String, f"{NS}/frame_meta", lambda m: metas.append(json.loads(m.data)), 10)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    spinner = threading.Thread(target=ex.spin, daemon=True)
    spinner.start()
    failures = []
    try:
        deadline = time.time() + 30
        while node.count_publishers(f"{NS}/image_raw") == 0 and time.time() < deadline:
            time.sleep(0.1)
        pub_ready.publish(Bool(data=True))
        while not (imgs and metas) and time.time() < deadline:
            time.sleep(0.1)
        if not imgs:
            failures.append("no frame from the GStreamer source")
        else:
            img = CvBridge().imgmsg_to_cv2(imgs[0], "bgr8")
            if img.shape != (480, 642, 3):
                failures.append(f"frame {img.shape}, expected (480, 642, 3)")
            elif img.std() < 10:
                failures.append("frame is blank")
            if metas and metas[0].get("usable") is not True:
                failures.append(f"frame not usable: {metas[0].get('reason')}")
    finally:
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
    print("live_camera_gst:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Integration: a camera that stops sending frames ends the live camera within camera_stall_restart_s.

live_camera (input=gst) reads a GStreamer test source that sends 15 frames and stops (a camera
unplugged, a USB reset, a stalled stream). Before, the node waited for > 50 failed grabs (2 s
each here, 10 s each for a V4L2 device: minutes); now it must report "stalled" on camera_health
and exit within camera_stall_restart_s (3 s here) + margin, so systemd restarts and reopens it.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32, String

NS = "/stalltest"
PIPE = ("videotestsrc num-buffers=15 pattern=ball ! video/x-raw,width=320,height=240,framerate=10/1 ! "
        "videoconvert ! video/x-raw,format=BGR ! appsink name=sink drop=true max-buffers=1 sync=false")


def main():
    try:
        import gi  # noqa: F401
    except ImportError:
        print("live_camera stall: SKIP (no GStreamer python)")
        return 0
    rclpy.init()
    node = Node("live_camera_stall_test")
    pub_ack = node.create_publisher(Int32, f"{NS}/frame_done", 10)
    metas, health = [], []

    def on_meta(m):
        d = json.loads(m.data)
        metas.append(d)
        pub_ack.publish(Int32(data=int(d["frame_id"])))

    node.create_subscription(String, f"{NS}/frame_meta", on_meta, 10)
    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
    node.create_subscription(String, f"{NS}/camera_health", lambda m: health.append(json.loads(m.data)), latched)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()
    proc = subprocess.Popen(
        ["ros2", "run", "camera_pkg", "live_camera.py", "--ros-args", "-r", f"__ns:={NS}",
         "-p", "input:=gst", "-p", f"gst_pipeline:={PIPE}", "-p", "width:=320", "-p", "height:=240",
         "-p", "camera_hfov_deg:=84.0", "-p", "fps:=5.0", "-p", "wait_for_ready:=false",
         "-p", "require_attitude:=false", "-p", "ack_timeout_s:=1.0", "-p", "camera_stall_restart_s:=3.0",
         "-p", "imu_topic:=/stalltest/imu", "-p", "gps_topic:=/stalltest/gps"],
        stdout=open(os.environ.get('NAVERA_TEST_LOG', os.devnull), 'w'), stderr=subprocess.STDOUT,
        start_new_session=True)
    failures = []
    try:
        deadline = time.time() + 40
        while not metas and time.time() < deadline:
            time.sleep(0.1)
        if not metas:
            failures.append("no frame came out while the source was sending")
        t_frames = time.time()
        try:
            rc = proc.wait(timeout=20)
            took = time.time() - t_frames
        except subprocess.TimeoutExpired:
            rc, took = None, None
            failures.append("the node did not exit 20 s after the camera stopped (it waited for 50 failed grabs)")
        if rc is not None:
            print(f"exited {took:.1f} s after the last frames, code {rc}")
        time.sleep(0.5)
        if not any(h.get("stalled") for h in health):
            failures.append(f"camera_health did not report the stall: {health[-1:] or 'nothing'}")
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
        ex.shutdown()
        node.destroy_node()
        rclpy.shutdown()
    for f in failures:
        print("FAIL", f)
    print("live_camera stall:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

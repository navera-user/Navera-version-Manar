#!/usr/bin/env python3
# Lesson 20 — a stand-in for the camera and the IMU, so NAVERA's REAL live camera node can
# run without the hardware.
#
#   /vehicle/camera/image_raw  sensor_msgs/Image  the recorded Insta360 frames (1920x1080),
#                                                 stamped with the time they are sent
#   /navera/sensors/imu        sensor_msgs/Imu    a fake IMU at 50 Hz: the vehicle level,
#                                                 nose to the north (or tilted: --pitch/--roll)
#
#     python3 replay_camera.py                 # level
#     python3 replay_camera.py --pitch 15      # nose 15 degrees up
#     python3 replay_camera.py --turn-rate 40  # turning right at 40 deg/s
# Stop with Ctrl+C. You don't need to change this file.
import argparse
import glob
import math
import os
import random

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Image, Imu

ap = argparse.ArgumentParser()
ap.add_argument("--frames", default="/data/academy/20-live-camera/frames")
ap.add_argument("--rate", type=float, default=2.0, help="pictures per second")
ap.add_argument("--roll", type=float, default=0.0, help="deg, right wing down")
ap.add_argument("--pitch", type=float, default=0.0, help="deg, nose up")
ap.add_argument("--heading", type=float, default=0.0, help="deg clockwise from north")
ap.add_argument("--turn-rate", type=float, default=0.0, help="deg/s: the heading turns at this rate")
a = ap.parse_args()


def quat_from_rpy(roll, pitch, yaw):
    """(x, y, z, w) of fixed-axis roll, pitch, yaw (rad) — as imu_pkg/orientation.py."""
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


class Replay(Node):
    def __init__(self):
        super().__init__("replay_camera")
        self.files = sorted(glob.glob(a.frames + "/*.jpg"))
        if not self.files:
            raise SystemExit(f"no frames in {a.frames}")
        self.images = [cv2.imread(f) for f in self.files]
        self.bridge, self.i = CvBridge(), 0
        self.pub_img = self.create_publisher(Image, "/vehicle/camera/image_raw", 2)
        self.pub_imu = self.create_publisher(Imu, "/navera/sensors/imu", 10)
        # ROS body frame (REP-103): x forward, y LEFT, z up. Nose up = negative rotation
        # about y; right wing down = positive rotation about x. ENU yaw is counter-clockwise
        # from EAST: heading 0 (north) = yaw 90 deg.
        self.t_start = self.get_clock().now().nanoseconds * 1e-9
        self.create_timer(1.0 / 50.0, self.send_imu)
        self.create_timer(1.0 / a.rate, self.send_image)
        self.get_logger().info(f"{len(self.files)} recorded frames at {a.rate} /s, IMU roll {a.roll} "
                               f"pitch {a.pitch} heading {a.heading} deg, turning {a.turn_rate} deg/s")

    def send_imu(self):
        m = Imu()
        now = self.get_clock().now()
        heading = a.heading + a.turn_rate * (now.nanoseconds * 1e-9 - self.t_start)
        q = quat_from_rpy(math.radians(a.roll), -math.radians(a.pitch), math.radians(90.0 - heading))
        m.header.stamp = now.to_msg()
        m.header.frame_id = "imu_link"
        # a REAL sensor is never perfectly still: live_camera.py treats 50 identical
        # samples in a row as a frozen IMU and stops using it. So: a tiny noise.
        x, y, z, w = (c + random.gauss(0.0, 1e-5) for c in q)
        n = math.sqrt(x * x + y * y + z * z + w * w)
        m.orientation.x, m.orientation.y, m.orientation.z, m.orientation.w = x / n, y / n, z / n, w / n
        self.pub_imu.publish(m)

    def send_image(self):
        msg = self.bridge.cv2_to_imgmsg(self.images[self.i % len(self.images)], "bgr8")
        msg.header.stamp = self.get_clock().now().to_msg()     # "the driver received it now"
        msg.header.frame_id = "camera_link"
        self.pub_img.publish(msg)
        self.i += 1


def main():
    rclpy.init()
    node = None
    try:
        node = Replay()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException, RCLError):
        pass                                   # Ctrl+C (even during start-up): just stop
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    os._exit(0)                                # quiet exit (no rclpy clean-up warnings)


if __name__ == "__main__":
    main()

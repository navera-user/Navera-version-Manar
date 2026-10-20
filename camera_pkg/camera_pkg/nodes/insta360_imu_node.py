#!/usr/bin/env python3
"""insta360_imu_node — the Insta360 One R's own IMU as sensor_msgs/Imu.

Reads the camera's IMU stream (USB Android mode, ~500 Hz), live from the camera or replayed from
a field raw recording (raw360_NNNN.bin), and publishes it in the VEHICLE body frame:

    <topic> (default /navera/sensors/insta360/imu)   sensor_msgs/Imu, RELIABLE depth 50

  angular_velocity     rad/s, body x forward / y left / z up (REP-103), gyro bias removed
                       (calibration file, then re-measured whenever the camera is at rest)
  linear_acceleration  m/s^2, specific force WITH gravity (REP-145: +9.81 on z at rest)
  orientation          not given: orientation_covariance[0] = -1 (consumers then use the body
                       z rate, e.g. day_subscriber's gyro heading carry on a level vehicle)
  covariances          diagonal, from the per-sample noise measured at rest, / decimation
  header.stamp         host time (time.time(), the clock NAVERA frames are stamped with) of the
                       sample: the camera's ms clock mapped by the least-delayed IMU packet
                       (camera_pkg.insta360_imu.CameraClock)
  header.frame_id      frame_id parameter (default insta360_imu_link): a frame ALIGNED WITH THE
                       VEHICLE BODY at the camera — the mount rotation is already applied

Mount: mount_axes gives the camera IMU axes along body x, y, z (camera IMU frame: +x up when the
camera stands, +y the LEFT fisheye circle's optical axis, +z = x cross y). Default '+y,+z,+x':
camera standing, left circle looking forward. mount_roll/pitch/yaw_deg: a small trim after it.

Only one process can hold the camera: the live source cannot run beside the field server.
"""
import math
import threading
import time

import rclpy
from navera_common.insta360_protocol import IMU_CALIBRATION, load_imu_calibration
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu

from camera_pkg.insta360_imu import (
    MEASURED_ACCEL_SAMPLE_STD_G, MEASURED_GYRO_SAMPLE_STD_DPS, G, ImuStream, UsbImuSource, covariance_diag,
    mount_rotation, replay_packets)

# RELIABLE reaches RELIABLE and BEST_EFFORT (navera_common.qos.SENSOR_QOS) subscribers alike
IMU_QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
                     history=HistoryPolicy.KEEP_LAST, depth=50)
STATUS_PERIOD_S = 10.0


class Insta360ImuNode(Node):
    """Publishes the Insta360 IMU (live camera or raw recording) as body-frame sensor_msgs/Imu."""

    def __init__(self, **kwargs) -> None:
        super().__init__("insta360_imu", **kwargs)
        self.declare_parameter("source", "replay")
        self.declare_parameter("replay_path", "")
        declare_float(self, "replay_rate", 1.0, "1 real time, 0 as fast as possible (pacing only)")
        self.declare_parameter("replay_loop", False)
        self.declare_parameter("replay_clock", "now")
        self.declare_parameter("exit_at_end", True)
        self.declare_parameter("topic", "/navera/sensors/insta360/imu")
        self.declare_parameter("frame_id", "insta360_imu_link")
        self.declare_parameter("mount_axes", "+y,+z,+x")
        declare_float(self, "mount_roll_deg", 0.0)
        declare_float(self, "mount_pitch_deg", 0.0)
        declare_float(self, "mount_yaw_deg", 0.0)
        self.declare_parameter("decimation", 5)
        self.declare_parameter("bias_at_rest", True)
        self.declare_parameter("calibration_file", "")
        declare_float(self, "gyro_sample_std_dps", MEASURED_GYRO_SAMPLE_STD_DPS)
        declare_float(self, "accel_sample_std_g", MEASURED_ACCEL_SAMPLE_STD_G)

        p = lambda n: self.get_parameter(n).value          # noqa: E731
        self.source = str(p("source")).strip().lower()
        if self.source not in ("live", "replay"):
            raise ValueError(f"source {self.source!r}: expected 'live' or 'replay'")
        self.frame_id = str(p("frame_id"))
        R = mount_rotation(str(p("mount_axes")), float(p("mount_roll_deg")), float(p("mount_pitch_deg")),
                           float(p("mount_yaw_deg")))
        dec = max(1, int(p("decimation")))
        cal_path = str(p("calibration_file")).strip() or IMU_CALIBRATION
        self.stream = ImuStream(R, dec, load_imu_calibration(cal_path), bias_at_rest=bool(p("bias_at_rest")))
        self.gyro_cov = covariance_diag(math.radians(float(p("gyro_sample_std_dps"))), dec)
        self.accel_cov = covariance_diag(float(p("accel_sample_std_g")) * G, dec)
        self.pub = self.create_publisher(Imu, str(p("topic")), IMU_QOS)
        self.published = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._usb = None
        self.finished = threading.Event()
        self.get_logger().info(
            f"Insta360 IMU ({self.source}) -> {p('topic')} [{self.frame_id}], mount_axes {p('mount_axes')} "
            f"trim r/p/y {p('mount_roll_deg')}/{p('mount_pitch_deg')}/{p('mount_yaw_deg')} deg, "
            f"{500 // dec} Hz (decimation {dec}), calibration {cal_path}")
        if self.source == "replay":
            path = str(p("replay_path")).strip()
            if not path:
                raise ValueError("source 'replay' needs replay_path (a raw folder or a raw360_NNNN.bin file)")
            args = (path, float(p("replay_rate")), str(p("replay_clock")), bool(p("replay_loop")))
            self._thread = threading.Thread(target=self._replay, args=args, daemon=True)
            self._thread.start()
        else:
            self._usb = UsbImuSource(self._on_packet)
        self.create_timer(STATUS_PERIOD_S, self._status)

    def _on_packet(self, arrival: float, packet: bytes) -> None:
        with self._lock:
            samples = self.stream.feed(arrival, packet)
        for s in samples:
            self.pub.publish(self._msg(s))
            self.published += 1

    def _msg(self, s) -> Imu:
        m = Imu()
        m.header.stamp.sec, m.header.stamp.nanosec = divmod(int(round(s.t * 1e9)), 1_000_000_000)
        m.header.frame_id = self.frame_id
        m.orientation_covariance[0] = -1.0
        m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z = (float(v) for v in s.gyro)
        m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z = (float(v) for v in s.accel)
        m.angular_velocity_covariance = self.gyro_cov
        m.linear_acceleration_covariance = self.accel_cov
        return m

    def _replay(self, path: str, rate: float, clock: str, loop: bool) -> None:
        try:
            for t, pkt in replay_packets(path, rate, clock, loop, stop=self._stop):
                self._on_packet(t, pkt)
            self.get_logger().info(f"replay finished: {self.published} samples published")
        except Exception as e:                     # bad path or file: said, then the node ends
            self.get_logger().error(f"replay {path}: {e}")
        self.finished.set()

    def _status(self) -> None:
        st = self.stream
        err = self._usb.error if self._usb is not None else None
        self.get_logger().info(
            f"{self.published} published, {st.records} records; clock offset {st.clock.offset} "
            f"(resets {st.clock.resets}); gyro bias {[round(math.degrees(b), 4) for b in st.bias.bias]} deg/s "
            f"({'at rest ' + str(st.bias.updates) + 'x' if st.bias.calibrated else 'calibration file'})"
            + (f"; {err}" if err else ""))

    def close(self) -> None:
        self._stop.set()
        if self._usb is not None:
            self._usb.close()


def main(args=None):
    die_with_parent()
    rclpy.init(args=args)
    node = Insta360ImuNode()
    exit_at_end = bool(node.get_parameter("exit_at_end").value)
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
            if exit_at_end and node.finished.is_set():
                break
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.close()
        time.sleep(0.1)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

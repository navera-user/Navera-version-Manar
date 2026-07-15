#!/usr/bin/env python3
"""
imu_node.py — NAVERA IMU driver for the BNO085 (9-DoF with on-chip sensor fusion).

Reads the BNO085 over I2C through the Adafruit Blinka / CircuitPython stack and
publishes:
    /navera/sensors/imu   sensor_msgs/Imu

The BNO085 fuses accelerometer + gyroscope + magnetometer on-chip and outputs an
absolute orientation quaternion (rotation vector), so no host-side filter is needed.

Wiring (Jetson Orin Nano, 40-pin header, I2C bus 1):
    BNO085 SDA -> pin 27      SCL -> pin 28
    BNO085 VIN -> pin 1 (3V3) GND -> pin 6

Parameters:
    i2c_bus                     (default 1)       — 1 (pins 27/28) or 7 (pins 3/5)
    i2c_address                 (default 74=0x4A) — 0x4B if the address pin is pulled high
    publish_rate                (default 50.0)    — Hz
    frame_id                    (default "imu_link")
    gravity_compensated         (default True)    — True: gravity-free linear acceleration
                                                    False: raw accelerometer (includes gravity)
    orientation_stddev          (default 0.02)    — rad
    angular_velocity_stddev     (default 0.005)   — rad/s
    linear_acceleration_stddev  (default 0.08)    — m/s^2

The BNO085 reports no uncertainty, so the *_stddev parameters are conservative
datasheet-derived estimates, NOT values measured on NAVERA hardware. Re-characterize
them against real flight data before feeding this IMU into a fused estimator.

Note on `gravity_compensated`: REP-145 expects Imu.linear_acceleration to include
gravity. NAVERA defaults to the gravity-free report because it feeds inertial
dead-reckoning; set the parameter to False for any consumer that follows REP-145.
"""
from typing import Optional, Tuple

import rclpy
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Imu

import board
import busio
from adafruit_bno08x import (
    BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_GYROSCOPE,
    BNO_REPORT_LINEAR_ACCELERATION,
    BNO_REPORT_ROTATION_VECTOR,
)
from adafruit_bno08x.i2c import BNO08X_I2C

# I2C bus number -> (SCL pin, SDA pin) on the Jetson 40-pin header.
# Blinka addresses the bus by pin pair, not by /dev/i2c-N number.
_BUS_PINS = {
    1: ("SCL_1", "SDA_1"),  # pins 28 / 27
    7: ("SCL", "SDA"),      # pins  5 /  3
}

# Consecutive read failures tolerated before the sensor is re-initialized.
_MAX_READ_FAILURES = 10


class IMUNode(Node):
    """Publishes BNO085 orientation, angular velocity and linear acceleration."""

    def __init__(self) -> None:
        super().__init__("imu_node")

        self.declare_parameter("i2c_bus", 1)
        self.declare_parameter("i2c_address", 0x4A)
        self.declare_parameter("publish_rate", 50.0)
        self.declare_parameter("frame_id", "imu_link")
        self.declare_parameter("gravity_compensated", True)
        self.declare_parameter("orientation_stddev", 0.02)
        self.declare_parameter("angular_velocity_stddev", 0.005)
        self.declare_parameter("linear_acceleration_stddev", 0.08)

        self.bus_num = int(self.get_parameter("i2c_bus").value)
        self.address = int(self.get_parameter("i2c_address").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.gravity_compensated = bool(self.get_parameter("gravity_compensated").value)
        rate = float(self.get_parameter("publish_rate").value)

        self.accel_report = (
            BNO_REPORT_LINEAR_ACCELERATION if self.gravity_compensated
            else BNO_REPORT_ACCELEROMETER
        )

        # Diagonal covariances built once from the stddev parameters.
        self.orientation_cov = self._diag(self.get_parameter("orientation_stddev").value)
        self.angular_cov = self._diag(self.get_parameter("angular_velocity_stddev").value)
        self.linear_cov = self._diag(self.get_parameter("linear_acceleration_stddev").value)

        self.pub_imu = self.create_publisher(Imu, "/navera/sensors/imu", 10)

        self.bno: Optional[BNO08X_I2C] = None
        self.read_failures = 0
        self.sample_count = 0

        self._connect()
        self.timer = self.create_timer(1.0 / rate, self.publish_imu)
        self.get_logger().info(
            f"IMU node running at {rate:.1f} Hz "
            f"(linear_acceleration = {'gravity-free' if self.gravity_compensated else 'raw, incl. gravity'})"
        )

    @staticmethod
    def _diag(stddev: float) -> list:
        """Build a 3x3 row-major diagonal covariance matrix from a scalar stddev."""
        var = float(stddev) ** 2
        return [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, var]

    def _connect(self) -> bool:
        """Open the I2C bus and enable the BNO085 reports. Returns True on success."""
        if self.bus_num not in _BUS_PINS:
            self.get_logger().error(
                f"Unsupported i2c_bus={self.bus_num}; expected one of {sorted(_BUS_PINS)}"
            )
            return False

        scl_name, sda_name = _BUS_PINS[self.bus_num]
        try:
            i2c = busio.I2C(getattr(board, scl_name), getattr(board, sda_name))
            bno = BNO08X_I2C(i2c, address=self.address)
            bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)
            bno.enable_feature(BNO_REPORT_GYROSCOPE)
            bno.enable_feature(self.accel_report)
        except Exception as exc:  # I2C bus, wiring or address failure
            self.get_logger().error(
                f"BNO085 init failed on I2C bus {self.bus_num} @ 0x{self.address:02X}: {exc}"
            )
            self.bno = None
            return False

        self.bno = bno
        self.read_failures = 0
        self.get_logger().info(
            f"BNO085 ready on I2C bus {self.bus_num} ({scl_name}/{sda_name}) @ 0x{self.address:02X}"
        )
        return True

    def _read(self) -> Optional[Tuple[tuple, tuple, tuple]]:
        """Read one sample. Returns (quaternion, gyro, accel) or None if the read failed."""
        try:
            quat = self.bno.quaternion  # (i, j, k, real) == (x, y, z, w)
            gyro = self.bno.gyro  # rad/s
            accel = (
                self.bno.linear_acceleration if self.gravity_compensated
                else self.bno.acceleration
            )  # m/s^2
        except Exception as exc:  # transient I2C / SHTP packet errors are common
            self.read_failures += 1
            self.get_logger().warn(
                f"BNO085 read error ({self.read_failures}/{_MAX_READ_FAILURES}): {exc}",
                throttle_duration_sec=2.0,
            )
            return None

        if quat is None or gyro is None or accel is None:
            self.read_failures += 1
            self.get_logger().warn(
                f"BNO085 returned an incomplete sample "
                f"({self.read_failures}/{_MAX_READ_FAILURES})",
                throttle_duration_sec=2.0,
            )
            return None

        self.read_failures = 0
        return quat, gyro, accel

    def publish_imu(self) -> None:
        """Timer callback: read the BNO085 and publish one sensor_msgs/Imu."""
        if self.bno is None:
            self.get_logger().warn(
                "BNO085 not connected, retrying init...", throttle_duration_sec=5.0
            )
            self._connect()
            return

        sample = self._read()
        if sample is None:
            if self.read_failures >= _MAX_READ_FAILURES:
                self.get_logger().error(
                    f"{self.read_failures} consecutive read failures — reinitializing BNO085"
                )
                self.bno = None
            return

        quat, gyro, accel = sample

        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id

        msg.orientation.x = float(quat[0])
        msg.orientation.y = float(quat[1])
        msg.orientation.z = float(quat[2])
        msg.orientation.w = float(quat[3])
        msg.orientation_covariance = self.orientation_cov

        msg.angular_velocity.x = float(gyro[0])
        msg.angular_velocity.y = float(gyro[1])
        msg.angular_velocity.z = float(gyro[2])
        msg.angular_velocity_covariance = self.angular_cov

        msg.linear_acceleration.x = float(accel[0])
        msg.linear_acceleration.y = float(accel[1])
        msg.linear_acceleration.z = float(accel[2])
        msg.linear_acceleration_covariance = self.linear_cov

        self.pub_imu.publish(msg)

        self.sample_count += 1
        if self.sample_count == 1 or self.sample_count % 250 == 0:
            self.get_logger().info(
                f"IMU #{self.sample_count}: "
                f"quat=({quat[0]:+.3f},{quat[1]:+.3f},{quat[2]:+.3f},{quat[3]:+.3f}) "
                f"gyro=({gyro[0]:+.3f},{gyro[1]:+.3f},{gyro[2]:+.3f}) rad/s "
                f"accel=({accel[0]:+.2f},{accel[1]:+.2f},{accel[2]:+.2f}) m/s^2"
            )


def main(args=None) -> None:
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    """
    die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
    rclpy.init(args=args)
    node = IMUNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""my_source.py — your own position source, speaking NAVERA's contract.

It publishes a navera_msgs/PositionEstimate once per second on /navera/estimate/day:
the arbiter's day-vision mailbox, which we borrow because no day vision runs here.

    python3 my_source.py              a good, honest estimate
    python3 my_source.py stale        the same, with a fault on purpose (see FAULTS)

Watch NAVERA's verdict in another terminal (with the estimator running):
    ros2 topic echo /navera/nav_status --field reason
"""
import math
import sys

import rclpy
from builtin_interfaces.msg import Time
from navera_msgs.msg import PositionEstimate
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

TOPIC = "/navera/estimate/day"
LAT, LON = 35.8256, 10.6084          # where our pretend camera says we are
SIGMA_M = 15.0                       # the accuracy it states (1 sigma, metres)
FAULTS = ["none", "nan", "bad_cov", "stale", "invalid", "replayed", "unknown_cov"]


def build_estimate(lat, lon, sigma_m, stamp):
    """A complete, honest PositionEstimate for a position measured at `stamp`."""
    est = PositionEstimate()
    est.header.stamp = stamp
    est.header.frame_id = "student_camera"
    est.latitude = float(lat)
    est.longitude = float(lon)
    est.altitude = math.nan                          # we don't know it: NaN, never 0.0
    var = sigma_m ** 2
    est.position_covariance = [var, 0.0, 0.0,
                               0.0, var, 0.0,
                               0.0, 0.0, 0.0]
    est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
    est.source = PositionEstimate.SOURCE_DAY_VISION
    est.mode = PositionEstimate.MODE_MEASURED
    est.valid = True
    est.confidence = 0.0
    est.reason = ""
    est.sensor_stamp = stamp
    est.producer = "my_source"
    est.model_id = "lesson12"
    est.frame_index = -1
    est.details_json = "{}"
    return est


def apply_fault(est, fault):
    """Break `est` on purpose, the way `fault` says. Returns the message."""
    if fault == "nan":
        est.latitude = math.nan
    elif fault == "bad_cov":
        est.position_covariance[0] = -est.position_covariance[0] - 1.0
    elif fault == "stale":
        old = Time(sec=est.header.stamp.sec - 10, nanosec=est.header.stamp.nanosec)
        est.header.stamp = old
        est.sensor_stamp = old
    elif fault == "invalid":
        est.valid = False
        est.reason = "lens covered"
    elif fault == "replayed":
        est.mode = PositionEstimate.MODE_REPLAYED
    elif fault == "unknown_cov":
        est.position_covariance = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
    return est


class MySource(Node):
    def __init__(self, fault):
        super().__init__("my_source")
        self.fault = fault
        self.pub = self.create_publisher(PositionEstimate, TOPIC, 10)
        self.create_timer(1.0, self.on_timer)
        self.get_logger().info(f"publishing on {TOPIC}, fault: {fault}")

    def on_timer(self):
        now = self.get_clock().now().to_msg()
        est = apply_fault(build_estimate(LAT, LON, SIGMA_M, now), self.fault)
        self.pub.publish(est)


# ---- you don't need to change anything below this line ----
def main():
    fault = sys.argv[1] if len(sys.argv) > 1 else "none"
    if fault not in FAULTS:
        sys.exit(f"unknown fault {fault!r}; choose one of {FAULTS}")
    rclpy.init()
    node = MySource(fault)
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

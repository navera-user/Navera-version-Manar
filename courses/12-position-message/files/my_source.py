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
    est.latitude = float(lat)
    est.longitude = float(lon)
    # TODO 1: fill every other field of the contract (the lesson's table explains each one):
    #   header.stamp (publication) and sensor_stamp (measurement) -> both `stamp` here
    #   header.frame_id = "student_camera"
    #   altitude      -> we don't know it: math.nan (never 0.0, which is sea level!)
    #   position_covariance -> sigma_m squared at places 0 and 4 (east, north), 0.0 elsewhere
    #   position_covariance_type -> PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
    #   source -> PositionEstimate.SOURCE_DAY_VISION     mode -> PositionEstimate.MODE_MEASURED
    #   valid -> True      reason -> ""       confidence -> 0.0
    #   producer -> "my_source"   model_id -> "lesson12"   frame_index -> -1   details_json -> "{}"
    return est


def apply_fault(est, fault):
    """Break `est` on purpose, the way `fault` says. Returns the message."""
    # TODO 2: one `if` / `elif` per fault. Change ONLY what the fault says:
    #   "nan"         latitude = math.nan
    #   "bad_cov"     a NEGATIVE variance: position_covariance[0] = -(its value) - 1.0
    #   "stale"       header.stamp AND sensor_stamp 10 seconds in the past:
    #                 Time(sec=est.header.stamp.sec - 10, nanosec=est.header.stamp.nanosec)
    #   "invalid"     valid = False, with a reason for humans, e.g. "lens covered"
    #   "replayed"    mode = PositionEstimate.MODE_REPLAYED
    #   "unknown_cov" all 9 covariance numbers 0.0, and COVARIANCE_TYPE_UNKNOWN
    #   "none"        nothing to change
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

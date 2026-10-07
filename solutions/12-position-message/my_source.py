#!/usr/bin/env python3
"""my_source.py — your own position source, speaking NAVERA's contract.

It publishes a navera_msgs/PositionEstimate once per second on /navera/estimate/day: the arbiter's
day-vision mailbox, which we borrow because no day vision runs in your sandbox.

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
LAT, LON = 35.8277, 10.6388          # where our pretend camera says we are (Sousse, NAVERA's test area)
SIGMA_ALONG_M = 15.0                 # 1-sigma error along the track
SIGMA_CROSS_M = 6.0                  # 1-sigma error across the track
HEADING_DEG = 30.0                   # direction of the track, clockwise from north
SIGMA_UP_M = 6.0
FAULTS = ["none", "nan", "not_psd", "stale", "latency", "future", "invalid", "replayed", "held",
          "propagated", "unknown_cov", "big_sigma", "tilted"]


def enu_covariance(sigma_along_m, sigma_cross_m, heading_deg, sigma_up_m=0.0):
    """The 9 floats (ENU, row-major, m²) of an error ellipse with semi-axes sigma_along (along the
    heading) and sigma_cross, heading clockwise from north; independent vertical error sigma_up."""
    h = math.radians(heading_deg)
    s, c = math.sin(h), math.cos(h)
    a2, c2 = float(sigma_along_m) ** 2, float(sigma_cross_m) ** 2
    ee = a2 * s * s + c2 * c * c
    nn = a2 * c * c + c2 * s * s
    en = (a2 - c2) * s * c
    return [ee, en, 0.0,
            en, nn, 0.0,
            0.0, 0.0, float(sigma_up_m) ** 2]


def is_psd_2x2(cov):
    """True if the horizontal 2x2 block of `cov` (9 numbers) is a covariance: finite, symmetric
    (|Σ_EN − Σ_NE| ≤ 1e-9·scale), non-negative variances and a non-negative determinant."""
    a, b, b2, c = cov[0], cov[1], cov[3], cov[4]
    if not all(math.isfinite(x) for x in (a, b, b2, c)):
        return False
    tol = 1e-9 * max(1.0, a, c)
    return a >= 0.0 and c >= 0.0 and abs(b - b2) <= tol and a * c - b * b2 >= -tol


def error_ellipse(cov):
    """(semi_major_m, semi_minor_m, heading_deg of the major axis in [0, 180)) of the horizontal block."""
    a, b, c = cov[0], cov[1], cov[4]
    m = (a + c) / 2.0
    r = math.sqrt(((a - c) / 2.0) ** 2 + b * b)
    heading = math.degrees(0.5 * math.atan2(2.0 * b, c - a)) % 180.0
    return math.sqrt(m + r), math.sqrt(max(m - r, 0.0)), heading


def build_estimate(lat, lon, cov, cov_type, stamp):
    """A complete, honest PositionEstimate measured (and published) at `stamp`."""
    est = PositionEstimate()
    est.latitude = float(lat)
    est.longitude = float(lon)
    est.header.stamp = stamp
    est.sensor_stamp = stamp
    est.header.frame_id = "student_camera"
    est.altitude = math.nan
    est.position_covariance = [float(x) for x in cov]
    est.position_covariance_type = cov_type
    est.source = PositionEstimate.SOURCE_DAY_VISION
    est.mode = PositionEstimate.MODE_MEASURED
    est.valid, est.reason, est.confidence = True, "", 0.0
    est.producer, est.model_id, est.frame_index, est.details_json = "my_source", "lesson12", -1, "{}"
    return est


def shifted(t, seconds):
    """A builtin_interfaces/Time moved by `seconds` (may be negative)."""
    ns = t.sec * 1_000_000_000 + t.nanosec + int(round(seconds * 1e9))
    return Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)


def apply_fault(est, fault):
    """Break `est` on purpose, the way `fault` says, changing ONLY that. Returns the message."""
    P = PositionEstimate
    if fault == "nan":
        est.latitude = math.nan
    elif fault == "not_psd":
        cov = list(est.position_covariance)
        cov[1] = cov[3] = 2.0 * math.sqrt(cov[0] * cov[4])
        est.position_covariance = cov
    elif fault == "stale":
        est.sensor_stamp = shifted(est.sensor_stamp, -10.0)
    elif fault == "latency":
        est.sensor_stamp = shifted(est.sensor_stamp, -2.0)
    elif fault == "future":
        est.header.stamp = shifted(est.header.stamp, 5.0)
        est.sensor_stamp = shifted(est.sensor_stamp, 5.0)
    elif fault == "invalid":
        est.valid, est.reason = False, "lens covered"
    elif fault == "replayed":
        est.mode = P.MODE_REPLAYED
    elif fault == "held":
        est.mode = P.MODE_HELD
    elif fault == "propagated":
        est.mode = P.MODE_PROPAGATED
    elif fault == "unknown_cov":
        est.position_covariance = [0.0] * 9
        est.position_covariance_type = P.COVARIANCE_TYPE_UNKNOWN
    elif fault == "big_sigma":
        est.position_covariance = enu_covariance(30.0, 30.0, HEADING_DEG, SIGMA_UP_M)
    elif fault == "tilted":
        est.position_covariance = enu_covariance(30.0, 5.0, 45.0, SIGMA_UP_M)
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
        cov = enu_covariance(SIGMA_ALONG_M, SIGMA_CROSS_M, HEADING_DEG, SIGMA_UP_M)
        est = build_estimate(LAT, LON, cov, PositionEstimate.COVARIANCE_TYPE_APPROXIMATED, now)
        self.pub.publish(apply_fault(est, self.fault))


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

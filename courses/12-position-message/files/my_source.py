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
LAT, LON = 23.5880, 58.3829          # where our pretend camera says we are (Muscat)
SIGMA_ALONG_M = 15.0                 # 1-sigma error along the track
SIGMA_CROSS_M = 6.0                  # 1-sigma error across the track
HEADING_DEG = 30.0                   # direction of the track, clockwise from north
SIGMA_UP_M = 6.0
FAULTS = ["none", "nan", "not_psd", "stale", "latency", "future", "invalid", "replayed", "held",
          "propagated", "unknown_cov", "big_sigma", "tilted"]


def enu_covariance(sigma_along_m, sigma_cross_m, heading_deg, sigma_up_m=0.0):
    """The 9 floats (ENU, row-major, m²) of an error ellipse with semi-axes sigma_along (along the
    heading) and sigma_cross, heading clockwise from north; independent vertical error sigma_up."""
    # TODO 1: with h in radians, s = sin(h), c = cos(h), A = sigma_along², C = sigma_cross²:
    #   Σ_EE = A·s² + C·c²     Σ_NN = A·c² + C·s²     Σ_EN = Σ_NE = (A − C)·s·c
    #   Σ_UU = sigma_up², everything else 0.0. Return the 9 numbers row after row, as floats.
    return [0.0] * 9


def is_psd_2x2(cov):
    """True if the horizontal 2x2 block of `cov` (9 numbers) is a covariance: finite, symmetric
    (|Σ_EN − Σ_NE| ≤ 1e-9·scale), non-negative variances and a non-negative determinant."""
    # TODO 2: a, b, b2, c = cov[0], cov[1], cov[3], cov[4]
    #   all four finite; a >= 0 and c >= 0; |b - b2| <= 1e-9 * max(1, a, c); a*c - b*b2 >= -1e-9 * max(1, a, c)
    return True


def error_ellipse(cov):
    """(semi_major_m, semi_minor_m, heading_deg of the major axis in [0, 180)) of the horizontal block."""
    # TODO 3: a, b, c = cov[0], cov[1], cov[4]
    #   m = (a + c) / 2 ;  r = sqrt(((a - c) / 2)² + b²) ;  λ1 = m + r ;  λ2 = m - r
    #   heading = degrees(0.5 * atan2(2b, c - a)) modulo 180
    #   return sqrt(λ1), sqrt(max(λ2, 0.0)), heading
    return 0.0, 0.0, 0.0


def build_estimate(lat, lon, cov, cov_type, stamp):
    """A complete, honest PositionEstimate measured (and published) at `stamp`."""
    est = PositionEstimate()
    est.latitude = float(lat)
    est.longitude = float(lon)
    # TODO 4: fill every other field of the contract (the lesson's tables explain each one):
    #   header.stamp (publication) and sensor_stamp (measurement) -> both `stamp` here
    #   header.frame_id = "student_camera"
    #   altitude -> unknown: math.nan (never 0.0, which is sea level!)
    #   position_covariance = cov (a list of 9 floats)   position_covariance_type = cov_type
    #   source = PositionEstimate.SOURCE_DAY_VISION     mode = PositionEstimate.MODE_MEASURED
    #   valid = True      reason = ""       confidence = 0.0
    #   producer = "my_source"   model_id = "lesson12"   frame_index = -1   details_json = "{}"
    return est


def shifted(t, seconds):
    """A builtin_interfaces/Time moved by `seconds` (may be negative)."""
    ns = t.sec * 1_000_000_000 + t.nanosec + int(round(seconds * 1e9))
    return Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)


def apply_fault(est, fault):
    """Break `est` on purpose, the way `fault` says, changing ONLY that. Returns the message."""
    # TODO 5: one `if` / `elif` per fault (FAULTS lists them):
    #   "nan"         latitude = math.nan
    #   "not_psd"     Σ_EN and Σ_NE (indices 1 and 3) = 2·sqrt(Σ_EE·Σ_NN): a correlation of 2
    #   "stale"       sensor_stamp 10 s in the past (header.stamp unchanged: published now!)  -> shifted()
    #   "latency"     sensor_stamp 2 s in the past (header.stamp unchanged)
    #   "future"      header.stamp AND sensor_stamp 5 s in the future
    #   "invalid"     valid = False and reason = "lens covered"
    #   "replayed"    mode = MODE_REPLAYED          "held"        mode = MODE_HELD
    #   "propagated"  mode = MODE_PROPAGATED
    #   "unknown_cov" nine 0.0 and COVARIANCE_TYPE_UNKNOWN
    #   "big_sigma"   enu_covariance(30, 30, HEADING_DEG, SIGMA_UP_M)          (a 30 m circle)
    #   "tilted"      enu_covariance(30, 5, 45.0, SIGMA_UP_M)                  (thin, at 45°)
    #   "none"        nothing
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

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
    # TODO 1: build Σ = R·diag(σ_along², σ_cross²)·Rᵀ for the horizontal block — course section 2,
    #   "Building a covariance from an error ellipse". Careful: math.sin/cos want radians.
    #   Input: two sigmas (m), a heading (deg, clockwise from north), sigma_up (m).
    #   Output: a list of 9 floats, row-major (E, N, U), with Σ_UU = sigma_up² and no E/N–U correlation.
    #   Test: enu_covariance(15, 6, 30, 6) gives the course's worked example (83.25, 81.84, 177.75 ...).
    return [0.0] * 9


def is_psd_2x2(cov):
    """True if the horizontal 2x2 block of `cov` (9 numbers) is a covariance: finite, symmetric
    (|Σ_EN − Σ_NE| ≤ 1e-9·scale), non-negative variances and a non-negative determinant."""
    # TODO 2: the two properties of a real covariance — course section 2 (symmetric, PSD).
    #   Input: 9 numbers; only the horizontal block (indices 0, 1, 3, 4) matters.
    #   Output: True or False. Use the tolerance tol = 1e-9 * max(1, Σ_EE, Σ_NN) for the two
    #   comparisons that involve rounding (symmetry, determinant). NaN or inf -> False.
    return True


def error_ellipse(cov):
    """(semi_major_m, semi_minor_m, heading_deg of the major axis in [0, 180)) of the horizontal block."""
    # TODO 3: the inverse of TODO 1 — course section 2, "From a covariance back to the ellipse".
    #   Input: 9 numbers. Output: (semi_major_m, semi_minor_m, heading_deg in [0, 180)).
    #   The semi-axes are the square roots of the two eigenvalues (protect the smaller one against a
    #   tiny negative rounding error). Test: error_ellipse(enu_covariance(15, 6, 30)) ≈ (15, 6, 30).
    return 0.0, 0.0, 0.0


def build_estimate(lat, lon, cov, cov_type, stamp):
    """A complete, honest PositionEstimate measured (and published) at `stamp`."""
    est = PositionEstimate()
    est.latitude = float(lat)
    est.longitude = float(lon)
    # TODO 4: fill every other field of the contract. Course section 1 (the form: where, how sure,
    #   who, how, usable, when, traceability) and section 5 (the two stamps) say what each field means.
    #   Our pretend camera measures and publishes at the same instant `stamp`, it does not know its
    #   altitude, and it is an honest, usable, measured day-vision fix.
    #   The values the checker expects for the free-text fields:
    #     header.frame_id "student_camera", producer "my_source", model_id "lesson12",
    #     frame_index -1, details_json "{}", reason "", confidence 0.0.
    #   The constants (SOURCE_..., MODE_...) are attributes of PositionEstimate.
    return est


def shifted(t, seconds):
    """A builtin_interfaces/Time moved by `seconds` (may be negative)."""
    ns = t.sec * 1_000_000_000 + t.nanosec + int(round(seconds * 1e9))
    return Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)


def apply_fault(est, fault):
    """Break `est` on purpose, the way `fault` says, changing ONLY that. Returns the message."""
    # TODO 5: one `if` / `elif` per fault (FAULTS lists them). What each fault must change:
    #   "nan"         the latitude becomes NaN
    #   "not_psd"     Σ_EN and Σ_NE (indices 1 and 3) become 2·sqrt(Σ_EE·Σ_NN): a correlation of 2
    #   "stale"       the MEASUREMENT stamp is 10 s in the past; the publication stamp does not change
    #   "latency"     the same, 2 s in the past
    #   "future"      BOTH stamps 5 s in the future
    #   "invalid"     not usable, with the reason "lens covered"
    #   "replayed", "held", "propagated"   the matching mode
    #   "unknown_cov" no accuracy stated: nine zeros and the matching covariance type (course section 4)
    #   "big_sigma"   a 30 m circle (along 30, cross 30, HEADING_DEG, SIGMA_UP_M)
    #   "tilted"      a thin ellipse: along 30, cross 5, heading 45°, SIGMA_UP_M
    #   "none"        nothing
    #   shifted() below moves a stamp. position_covariance is an array: build a new list of 9 floats.
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

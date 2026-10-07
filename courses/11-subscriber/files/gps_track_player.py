#!/usr/bin/env python3
"""gps_track_player.py — a ready-made GPS source for this lab (you don't need to change it).

It drives a pretend vehicle along a small route in Sousse at 6 m/s and publishes its
position as sensor_msgs/NavSatFix on /fake_gps/fix, 2 times per second — the same topic
and message as your fake GPS of lesson 10. At the end of the route it starts again.

    python3 gps_track_player.py
"""
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

TOPIC = "/fake_gps/fix"
RATE_HZ = 2.0
SPEED_MPS = 6.0
SIGMA_M = 3.0
R = 6_371_000.0
# The route: (north, east) in metres from the start point, corner after corner.
START = (35.8240, 10.6300)
ROUTE_M = [(0, 0), (0, 400), (300, 400), (300, 900), (0, 900), (0, 0)]


def route_point(d):
    """(north, east) metres after travelling d metres along ROUTE_M (looping)."""
    legs = list(zip(ROUTE_M[:-1], ROUTE_M[1:]))
    total = sum(math.dist(a, b) for a, b in legs)
    d %= total
    for a, b in legs:
        length = math.dist(a, b)
        if d <= length:
            f = d / length
            return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
        d -= length
    return ROUTE_M[-1]


class TrackPlayer(Node):
    def __init__(self):
        super().__init__("gps_track_player")
        self.pub = self.create_publisher(NavSatFix, TOPIC, 10)
        self.t0 = self.get_clock().now()
        self.create_timer(1.0 / RATE_HZ, self.tick)
        self.get_logger().info(f"playing a {SPEED_MPS:.0f} m/s drive on {TOPIC} at {RATE_HZ:.0f} Hz")

    def tick(self):
        now = self.get_clock().now()
        t = (now - self.t0).nanoseconds / 1e9
        north, east = route_point(SPEED_MPS * t)
        m = NavSatFix()
        m.header.stamp = now.to_msg()
        m.header.frame_id = "gps"
        m.status = NavSatStatus(status=NavSatStatus.STATUS_FIX, service=NavSatStatus.SERVICE_GPS)
        m.latitude = START[0] + math.degrees(north / R)
        m.longitude = START[1] + math.degrees(east / (R * math.cos(math.radians(START[0]))))
        m.altitude = 35.0
        m.position_covariance = [SIGMA_M ** 2, 0.0, 0.0, 0.0, SIGMA_M ** 2, 0.0, 0.0, 0.0, (2 * SIGMA_M) ** 2]
        m.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        self.pub.publish(m)


def main():
    rclpy.init()
    node = TrackPlayer()
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

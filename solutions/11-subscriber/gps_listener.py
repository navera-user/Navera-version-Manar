#!/usr/bin/env python3
"""gps_listener.py — your first subscriber: a trip computer for a GPS.

It listens to sensor_msgs/NavSatFix on /fake_gps/fix and, for every fix, prints the
distance travelled since the start and the current speed.

    python3 gps_listener.py          (with a GPS source running in another terminal)
"""
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix

TOPIC = "/fake_gps/fix"


def haversine_m(lat1, lon1, lat2, lon2):
    """Distance in metres between two points (lesson 6) — the same formula as NAVERA's geo.py."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))


class Tracker:
    """Remembers the trip: how many fixes, how far, how fast. Plain Python, no ROS inside."""

    def __init__(self):
        self.count = 0              # fixes received
        self.distance_m = 0.0       # distance travelled since the first fix
        self.speed_mps = None       # speed between the last two fixes (None = not known yet)
        self.last = None            # the previous fix: (lat, lon, t) — None before the first one

    def update(self, lat, lon, t):
        """Add one fix (t in seconds). Returns the speed since the previous fix, or None."""
        self.count += 1
        speed = None
        if self.last is not None:
            lat0, lon0, t0 = self.last
            step = haversine_m(lat0, lon0, lat, lon)
            self.distance_m += step
            dt = t - t0
            if dt > 0:
                speed = step / dt
        self.last = (lat, lon, t)
        self.speed_mps = speed
        return speed


class GpsListener(Node):
    def __init__(self):
        super().__init__("gps_listener")
        self.tracker = Tracker()
        self.create_subscription(NavSatFix, TOPIC, self.on_fix, 10)
        self.get_logger().info(f"listening to {TOPIC}")

    def on_fix(self, msg):
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        speed = self.tracker.update(msg.latitude, msg.longitude, t)
        speed_text = "?" if speed is None else f"{speed:.1f}"
        self.get_logger().info(
            f"fix {self.tracker.count}: distance {self.tracker.distance_m:.1f} m, speed {speed_text} m/s")


# ---- you don't need to change anything below this line ----
def main():
    rclpy.init()
    node = GpsListener()
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

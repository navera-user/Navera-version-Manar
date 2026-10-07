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
# Do the TODOs in order (1 -> 3). TODO 1 is plain Python: test it before using ROS (see the lab).


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
        # TODO 1: keep the trip up to date.
        #   - add 1 to self.count
        #   - if there was a previous fix (self.last is not None):
        #       step = the distance between the previous fix and this one (haversine_m)
        #       add step to self.distance_m
        #       dt = the time between the two fixes; if dt > 0, speed = step / dt
        #   - remember this fix in self.last, as (lat, lon, t), for the next call
        #   - store the speed in self.speed_mps and return it (None when it cannot be computed)
        return None


class GpsListener(Node):
    def __init__(self):
        super().__init__("gps_listener")
        self.tracker = Tracker()
        # TODO 2: subscribe to NavSatFix messages on TOPIC (queue depth 10), with the callback self.on_fix
        self.get_logger().info(f"listening to {TOPIC}")

    def on_fix(self, msg):
        """Called by ROS for every NavSatFix received. `msg` is the message."""
        # TODO 3: compute t, the stamp of the message in seconds (header.stamp.sec + nanosec * 1e-9),
        #         give the fix to self.tracker.update(...), then log one line EXACTLY like:
        #             fix 12: distance 66.0 m, speed 6.0 m/s
        #         (write "?" instead of the speed when it is None). Use self.get_logger().info(text).
        pass


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

#!/usr/bin/env python3
"""gps_listener.py — a subscriber with memory: a trip computer for a GNSS receiver.

It listens to sensor_msgs/NavSatFix on /fake_gps/fix and, for every fix, logs the distance
travelled, the instantaneous speed and a speed averaged over a window of fixes. Bad fixes are
rejected and counted, like NAVERA does.

    python3 gps_listener.py          (with a GNSS source running in another terminal)

Do the TODOs in order. TODO 1 and 2 are plain Python: test them without ROS (see the lab).
"""
import math
from collections import deque

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import NavSatFix

TOPIC = "/fake_gps/fix"
WINDOW = 10                               # fixes used by the averaged speed

# The reasons a fix is rejected (use these exact strings).
NO_FIX = "no fix"                         # status.status < 0 (STATUS_NO_FIX)
NOT_FINITE = "not finite"                 # NaN or infinite latitude, longitude or time
NULL_ISLAND = "null island"               # exactly (0.0, 0.0): a position nobody filled
NOT_NEWER = "not newer"                   # stamp older than, or equal to, the last accepted fix


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (lesson 06) — the same formula as NAVERA's geo.py."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))


class Tracker:
    """The trip computer's state. Plain Python, no ROS inside: testable in one line."""

    def __init__(self, window=WINDOW):
        self.count = 0                     # accepted fixes
        self.rejected = {}                 # reason -> number of rejected fixes
        self.distance_m = 0.0              # sum of the steps between accepted fixes
        self.speed_mps = None              # last step / its dt (None until two fixes)
        self.window_speed_mps = None       # straight distance oldest->newest in the window / time span
        self.last = None                   # the last accepted fix (lat, lon, t), None at first
        self.history = deque(maxlen=window)  # the last `window` accepted fixes (lat, lon, t)

    def check(self, lat, lon, t, status=0):
        """'' if the fix may be used, else the reason (one of the constants above), tested in
        this order: NO_FIX, NOT_FINITE, NULL_ISLAND, NOT_NEWER."""
        if status < 0:
            return NO_FIX
        if not all(math.isfinite(x) for x in (lat, lon, t)):
            return NOT_FINITE
        if lat == 0.0 and lon == 0.0:
            return NULL_ISLAND
        if self.last is not None and t <= self.last[2]:
            return NOT_NEWER
        return ""

    def update(self, lat, lon, t, status=0):
        """Add one fix (t in seconds). Returns the instantaneous speed, or None (first fix or rejected)."""
        reason = self.check(lat, lon, t, status)
        if reason:
            self.rejected[reason] = self.rejected.get(reason, 0) + 1
            return None
        self.count += 1
        if self.last is not None:
            plat, plon, pt = self.last
            step = haversine_m(plat, plon, lat, lon)
            self.distance_m += step
            self.speed_mps = step / (t - pt)
        self.history.append((lat, lon, t))
        if len(self.history) >= 2:
            (alat, alon, at), (blat, blon, bt) = self.history[0], self.history[-1]
            self.window_speed_mps = haversine_m(alat, alon, blat, blon) / (bt - at)
        self.last = (lat, lon, t)
        return self.speed_mps


class GpsListener(Node):
    def __init__(self):
        super().__init__("gps_listener")
        self.tracker = Tracker()
        self.create_subscription(NavSatFix, TOPIC, self.on_fix, qos_profile_sensor_data)
        self.get_logger().info(f"listening to {TOPIC}")

    def on_fix(self, msg):
        """Called by ROS for every NavSatFix received. `msg` is the message."""
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        tr = self.tracker
        reason = tr.check(msg.latitude, msg.longitude, t, msg.status.status)
        speed = tr.update(msg.latitude, msg.longitude, t, msg.status.status)
        if reason:
            self.get_logger().info(f"rejected ({reason}), {tr.rejected[reason]} so far")
        else:
            self.get_logger().info(f"fix {tr.count}: distance {tr.distance_m:.1f} m, speed {fmt(speed)} m/s, "
                                   f"window {fmt(tr.window_speed_mps)} m/s")


# ---- you don't need to change anything below this line ----
def fmt(x):
    """A speed for the log: one decimal, or '?' when unknown."""
    return "?" if x is None else f"{x:.1f}"


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

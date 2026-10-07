#!/usr/bin/env python3
"""fake_gps.py — your first ROS 2 publisher: a pretend GPS receiver.

When it is finished, it publishes a sensor_msgs/NavSatFix on the topic /fake_gps/fix,
2 times per second, for a vehicle that drives in a straight line from a start point.

Run it:                   python3 fake_gps.py
Watch it (2nd terminal):  ros2 topic echo /fake_gps/fix
Stop it:                  Ctrl+C

Do the TODOs in order (1 → 5). After each one, run the file again.
"""
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

# ---- the settings of our pretend drive ----
TOPIC = "/fake_gps/fix"
RATE_HZ = 2.0                         # messages per second
START_LAT = 35.8256                   # start point: Sousse (degrees)
START_LON = 10.6084
ALTITUDE_M = 40.0                     # above the WGS84 ellipsoid
EAST_SPEED_MPS = 3.0                  # metres per second towards the east
NORTH_SPEED_MPS = 4.0                 # metres per second towards the north (so 5 m/s in total)
SIGMA_M = 3.0                         # how precise our pretend GPS says it is (1 sigma, metres)

EARTH_RADIUS_M = 6_371_000.0          # the same value as NAVERA's navera_common/geo.py


def meters_to_degrees(north_m, east_m, lat_deg):
    """Turn a small move in metres (north, east) into (dlat, dlon) in degrees.

    1 degree of latitude is always the same length: 2*pi*R / 360 = about 111 195 m.
    1 degree of longitude gets shorter towards the poles: multiply by cos(latitude).
    """
    # TODO 1: compute and return (dlat, dlon). You did this in lesson 6.
    #   m_per_deg_lat = ...
    #   m_per_deg_lon = ...   (do not forget math.radians() inside math.cos())
    return 0.0, 0.0


def position_at(t_s):
    """Where the vehicle is t_s seconds after the start: (lat, lon) in degrees."""
    # TODO 2: distance travelled north and east = speed x time, then use meters_to_degrees()
    #         and add the result to START_LAT / START_LON.
    return START_LAT, START_LON


def make_fix(lat, lon, stamp):
    """Fill one NavSatFix message. `stamp` is a builtin_interfaces/Time (from the node's clock)."""
    msg = NavSatFix()
    msg.header.stamp = stamp
    msg.header.frame_id = "gps"
    # TODO 3: fill the message (see the lesson's NavSatFix table):
    #   - status.status  = we have a fix         (NavSatStatus.STATUS_FIX)
    #   - status.service = the American GPS      (NavSatStatus.SERVICE_GPS)
    #   - latitude, longitude, altitude (ALTITUDE_M)
    #   - position_covariance: 9 numbers, SIGMA_M squared for east and north (places 0 and 4),
    #     (2 * SIGMA_M) squared for up (place 8), 0.0 everywhere else
    #   - position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
    return msg


class FakeGps(Node):
    def __init__(self):
        super().__init__("fake_gps")             # the node's name in the ROS graph
        # TODO 4: create a publisher of NavSatFix on TOPIC (queue depth 10) -> self.pub
        self.pub = None
        # TODO 5: create a timer that calls self.on_timer every 1.0 / RATE_HZ seconds
        self.start_time = self.get_clock().now()
        self.count = 0
        self.get_logger().info(f"fake GPS publishing on {TOPIC} at {RATE_HZ} Hz")

    def on_timer(self):
        """Called by the timer: compute where we are now and publish it."""
        now = self.get_clock().now()
        t = (now - self.start_time).nanoseconds / 1e9      # seconds since the start
        lat, lon = position_at(t)
        self.pub.publish(make_fix(lat, lon, now.to_msg()))
        self.count += 1
        if self.count % 10 == 1:
            self.get_logger().info(f"fix {self.count}: lat {lat:.6f}  lon {lon:.6f}")


# ---- you don't need to change anything below this line ----
def main():
    rclpy.init()
    node = FakeGps()
    try:
        rclpy.spin(node)                         # wait for timers / messages, forever
    except (KeyboardInterrupt, ExternalShutdownException):     # Ctrl+C
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

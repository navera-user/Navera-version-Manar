#!/usr/bin/env python3
"""fake_gps.py — your first ROS 2 publisher: a pretend GPS receiver.

It publishes a sensor_msgs/NavSatFix on the topic /fake_gps/fix, 2 times per second,
for a vehicle that drives in a straight line from a start point.

Run it:            python3 fake_gps.py
Watch it (2nd terminal):  ros2 topic echo /fake_gps/fix
Stop it:           Ctrl+C
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
    m_per_deg_lat = 2 * math.pi * EARTH_RADIUS_M / 360.0
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat_deg))
    return north_m / m_per_deg_lat, east_m / m_per_deg_lon


def position_at(t_s):
    """Where the vehicle is t_s seconds after the start: (lat, lon) in degrees."""
    north_m = NORTH_SPEED_MPS * t_s
    east_m = EAST_SPEED_MPS * t_s
    dlat, dlon = meters_to_degrees(north_m, east_m, START_LAT)
    return START_LAT + dlat, START_LON + dlon


def make_fix(lat, lon, stamp):
    """Fill one NavSatFix message. `stamp` is a builtin_interfaces/Time (from the node's clock)."""
    msg = NavSatFix()
    msg.header.stamp = stamp
    msg.header.frame_id = "gps"
    msg.status.status = NavSatStatus.STATUS_FIX
    msg.status.service = NavSatStatus.SERVICE_GPS
    msg.latitude = lat
    msg.longitude = lon
    msg.altitude = ALTITUDE_M
    var = SIGMA_M ** 2
    msg.position_covariance = [var, 0.0, 0.0,
                               0.0, var, 0.0,
                               0.0, 0.0, (2 * SIGMA_M) ** 2]
    msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
    return msg


class FakeGps(Node):
    def __init__(self):
        super().__init__("fake_gps")
        self.pub = self.create_publisher(NavSatFix, TOPIC, 10)
        self.timer = self.create_timer(1.0 / RATE_HZ, self.on_timer)
        self.start_time = self.get_clock().now()
        self.count = 0
        self.get_logger().info(f"fake GPS publishing on {TOPIC} at {RATE_HZ} Hz")

    def on_timer(self):
        now = self.get_clock().now()
        t = (now - self.start_time).nanoseconds / 1e9
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
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):     # Ctrl+C
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""fake_gps_params.py — the fake GPS of lesson 10, with its settings as ROS parameters.

    python3 fake_gps_params.py                                   default settings
    python3 fake_gps_params.py --ros-args -p rate_hz:=5.0        one setting changed
    python3 fake_gps_params.py --ros-args --params-file my_gps.yaml

While it runs:  ros2 param list /fake_gps     ros2 param set /fake_gps speed_mps 12.0
"""
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

EARTH_RADIUS_M = 6_371_000.0


def meters_to_degrees(north_m, east_m, lat_deg):
    """Lesson 6 / lesson 10: a small move in metres -> (dlat, dlon) in degrees."""
    m_per_deg_lat = 2 * math.pi * EARTH_RADIUS_M / 360.0
    return north_m / m_per_deg_lat, east_m / (m_per_deg_lat * math.cos(math.radians(lat_deg)))


class FakeGps(Node):
    def __init__(self):
        super().__init__("fake_gps")
        # Parameters: name and default value. The type comes from the default (2.0 is a float).
        self.declare_parameter("topic", "/fake_gps/fix")
        self.declare_parameter("rate_hz", 2.0)
        self.declare_parameter("start_lat", 35.8256)
        self.declare_parameter("start_lon", 10.6084)
        self.declare_parameter("speed_mps", 5.0)
        self.declare_parameter("heading_deg", 37.0)      # 0 = north, 90 = east (clockwise)
        self.declare_parameter("sigma_m", 3.0)

        topic = self.get_parameter("topic").value
        rate = self.get_parameter("rate_hz").value
        self.lat = self.get_parameter("start_lat").value
        self.lon = self.get_parameter("start_lon").value
        self.sigma = self.get_parameter("sigma_m").value

        self.pub = self.create_publisher(NavSatFix, topic, 10)
        self.create_timer(1.0 / rate, self.on_timer)
        self.last_time = self.get_clock().now()
        self.get_logger().info(f"fake GPS on {topic} at {rate} Hz from ({self.lat}, {self.lon})")

    def on_timer(self):
        now = self.get_clock().now()
        dt = (now - self.last_time).nanoseconds / 1e9
        self.last_time = now
        # read at every tick, so that `ros2 param set` takes effect while the node runs
        speed = self.get_parameter("speed_mps").value
        heading = math.radians(self.get_parameter("heading_deg").value)
        dlat, dlon = meters_to_degrees(speed * dt * math.cos(heading), speed * dt * math.sin(heading), self.lat)
        self.lat += dlat
        self.lon += dlon

        msg = NavSatFix()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = "gps"
        msg.status.status = NavSatStatus.STATUS_FIX
        msg.status.service = NavSatStatus.SERVICE_GPS
        msg.latitude, msg.longitude, msg.altitude = self.lat, self.lon, 40.0
        var = self.sigma ** 2
        msg.position_covariance = [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, 4 * var]
        msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        self.pub.publish(msg)


# ---- you don't need to change anything below this line ----
def main():
    rclpy.init()
    node = FakeGps()
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

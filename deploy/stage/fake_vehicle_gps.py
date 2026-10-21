#!/usr/bin/env python3
"""fake_vehicle_gps.py — a simulated vehicle GPS for the staged boot test (deploy/stage_check.sh).

Publishes a stamped sensor_msgs/NavSatFix (3D fix, 2 m sigma, the vehicle circling slowly over
Sousse) on the topic given (default /navera/stage/vehicle_gps) at 5 Hz. The staged navera-gps
unit reads it through NAVERA's real ROS GPS source (NAVERA_GPS_SOURCE=ros, gps_pkg
ros_gps_node.py), so the real estimator gets a real GPS estimate without a receiver.

Refuses to run unless NAVERA_ALLOW_SIM=1 and ROS_DOMAIN_ID is set to something other than 0:
it must never feed a box in service.
"""
import math
import os
import sys

if os.environ.get('NAVERA_ALLOW_SIM') != '1' or os.environ.get('ROS_DOMAIN_ID', '0') in ('', '0'):
    sys.exit('refusing to run: set NAVERA_ALLOW_SIM=1 and a test ROS_DOMAIN_ID (not 0)')

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from sensor_msgs.msg import NavSatFix, NavSatStatus  # noqa: E402

LAT0, LON0, RADIUS_M, PERIOD_S = 35.8288, 10.6360, 150.0, 240.0


class FakeVehicleGps(Node):
    """Stamped simulated fixes on one NavSatFix topic."""

    def __init__(self, topic: str) -> None:
        super().__init__('navera_stage_fake_gps')
        self.pub = self.create_publisher(NavSatFix, topic, 10)
        self.t0 = self.get_clock().now().nanoseconds * 1e-9
        self.create_timer(0.2, self.tick)
        self.get_logger().info(f'SIMULATED vehicle GPS on {topic} (staged test only)')

    def tick(self) -> None:
        """Publish the simulated position of now."""
        now = self.get_clock().now()
        a = 2 * math.pi * ((now.nanoseconds * 1e-9 - self.t0) / PERIOD_S)
        m = NavSatFix()
        m.header.stamp = now.to_msg()
        m.header.frame_id = 'stage_gps'
        m.status.status = NavSatStatus.STATUS_FIX
        m.status.service = NavSatStatus.SERVICE_GPS
        m.latitude = LAT0 + RADIUS_M * math.sin(a) / 111_320.0
        m.longitude = LON0 + RADIUS_M * math.cos(a) / (111_320.0 * math.cos(math.radians(LAT0)))
        m.altitude = 120.0
        m.position_covariance = [4.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 16.0]
        m.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        self.pub.publish(m)


def main() -> None:
    """Spin until stopped."""
    rclpy.init()
    node = FakeVehicleGps(sys.argv[1] if len(sys.argv) > 1 else '/navera/stage/vehicle_gps')
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()

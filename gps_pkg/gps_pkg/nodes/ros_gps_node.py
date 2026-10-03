#!/usr/bin/env python3
"""
ros_gps_node.py — a GPS that is not NAVERA's own receiver, as NAVERA's GPS source.

For installations without the box's GPS: the vehicle's ROS GPS (a boat's or robot's
NavSatFix) or the autopilot's second GPS read by vehicle_link (/navera/vehicle/gps2).
Republishes it exactly like gps_node:
    /navera/sensors/gps_fix    sensor_msgs/NavSatFix         (what the live camera reads)
    /navera/estimate/gps       navera_msgs/PositionEstimate  (the estimator's GPS source)

Never point it at a position NAVERA itself produces (the autopilot's fused position,
or a GPS fed by NAVERA's GPS_INPUT): NAVERA would check its own output against itself.

Parameters:
    fix_topic   (default /navera/vehicle/gps2) — sensor_msgs/NavSatFix input
"""
import json
import math

import rclpy
from navera_common.lifecycle import die_with_parent
from navera_msgs.msg import PositionEstimate
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import NavSatFix, NavSatStatus


def estimate_from_fix(m: NavSatFix) -> PositionEstimate:
    """The GPS source contract for one NavSatFix: valid only with a fix and a position."""
    est = PositionEstimate()
    est.header = m.header
    valid = m.status.status >= NavSatStatus.STATUS_FIX and math.isfinite(m.latitude) and \
        math.isfinite(m.longitude) and not (m.latitude == 0.0 and m.longitude == 0.0)
    est.latitude = float(m.latitude) if valid else math.nan
    est.longitude = float(m.longitude) if valid else math.nan
    est.altitude = float(m.altitude) if valid and math.isfinite(m.altitude) else math.nan
    # a stated accuracy only when it is one: a defined type, finite, and a horizontal
    # variance above (1 cm)^2 — zeros mean "not filled" (gps_node's HDOP > 0 rule)
    if valid and m.position_covariance_type in (NavSatFix.COVARIANCE_TYPE_APPROXIMATED,
                                                NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN,
                                                NavSatFix.COVARIANCE_TYPE_KNOWN) \
            and all(math.isfinite(c) for c in m.position_covariance) \
            and min(m.position_covariance[0], m.position_covariance[4]) >= 1e-4:
        est.position_covariance = list(m.position_covariance)
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
    else:
        est.position_covariance = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
    est.source, est.mode, est.valid = PositionEstimate.SOURCE_GPS, PositionEstimate.MODE_MEASURED, valid
    est.reason = "" if valid else "no fix"
    est.sensor_stamp = m.header.stamp
    est.producer, est.model_id, est.frame_index = "ros_gps_node", "navsatfix", -1
    est.details_json = json.dumps({"frame_id": m.header.frame_id})
    return est


class RosGps(Node):
    def __init__(self):
        super().__init__("ros_gps")
        self.declare_parameter("fix_topic", "/navera/vehicle/gps2")
        topic = str(self.get_parameter("fix_topic").value)
        self.pub_fix = self.create_publisher(NavSatFix, "/navera/sensors/gps_fix", 10)
        self.pub_est = self.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)
        self.create_subscription(NavSatFix, topic, self._on_fix, qos_profile_sensor_data)
        self.get_logger().info(f"GPS from {topic}")

    def _on_fix(self, m: NavSatFix):
        if m.header.stamp.sec == 0 and m.header.stamp.nanosec == 0:
            m.header.stamp = self.get_clock().now().to_msg()      # unstamped driver: receipt time
        if self.pub_fix.topic_name != self.get_parameter("fix_topic").value:
            self.pub_fix.publish(m)
        self.pub_est.publish(estimate_from_fix(m))


def main(args=None):
    die_with_parent()
    rclpy.init(args=args)
    node = RosGps()
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

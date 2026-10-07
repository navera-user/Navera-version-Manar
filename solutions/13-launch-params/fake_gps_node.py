#!/usr/bin/env python3
"""fake_gps_node.py — lesson 10's fake GNSS receiver, made configurable like a product node.

    python3 fake_gps_node.py                                           defaults (Muscat, a car)
    python3 fake_gps_node.py --ros-args -p speed_mps:=12.0             one parameter
    python3 fake_gps_node.py --ros-args -r __ns:=/car --params-file my_gps.yaml
    ros2 param describe /fake_gps speed_mps                            its description and range

It publishes sensor_msgs/NavSatFix on /fake_gps/fix (an ABSOLUTE name: a launch file remaps it).
New in this lesson: every parameter has a description and limits (TODO 1), and a validation
callback refuses settings that do not make sense together (TODO 2).
"""
import math

import rclpy
from rcl_interfaces.msg import FloatingPointRange, ParameterDescriptor, SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

TOPIC = "/fake_gps/fix"
EARTH_RADIUS_M = 6_371_000.0
ALTITUDE_M = 40.0

# name -> (default, description, minimum, maximum, read_only). Strings have no range (None).
SPECS = {
    "rate_hz":     (2.0, "messages per second (fixed at start: the timer period)", 0.1, 50.0, True),
    "speed_mps":   (5.0, "ground speed, m/s", 0.0, 60.0, False),
    "heading_deg": (30.0, "direction of motion, degrees clockwise from north", 0.0, 360.0, False),
    "start_lat":   (23.5880, "start latitude, degrees WGS84", -90.0, 90.0, True),
    "start_lon":   (58.3829, "start longitude, degrees WGS84", -180.0, 180.0, True),
    "sigma_m":     (3.0, "stated horizontal 1-sigma accuracy, m", 0.01, 1000.0, False),
    "vehicle":     ("car", "kind of vehicle: car, drone or boat (limits the speed)", None, None, False),
}
MAX_SPEED_MPS = {"car": 40.0, "drone": 30.0, "boat": 15.0}


def make_descriptor(description, lo, hi, read_only):
    """A ParameterDescriptor with a description, read_only flag and, when lo/hi are given, a
    floating-point range [lo, hi]."""
    d = ParameterDescriptor(description=description, read_only=read_only)
    if lo is not None:
        d.floating_point_range = [FloatingPointRange(from_value=lo, to_value=hi, step=0.0)]
    return d


def check_settings(vehicle, speed_mps):
    """'' if (vehicle, speed) make sense together, else the reason, exactly:
        unknown vehicle 'tank' (car, drone or boat)
        speed 50.0 m/s too fast for a boat (max 15.0)"""
    if vehicle not in MAX_SPEED_MPS:
        return f"unknown vehicle '{vehicle}' (car, drone or boat)"
    if speed_mps > MAX_SPEED_MPS[vehicle]:
        return f"speed {speed_mps:.1f} m/s too fast for a {vehicle} (max {MAX_SPEED_MPS[vehicle]:.1f})"
    return ""


# ---- the motion and the message: lesson 10, complete ----
def velocity_ne(speed_mps, heading_deg):
    h = math.radians(heading_deg)
    return speed_mps * math.cos(h), speed_mps * math.sin(h)


def offset_to_latlon(lat0, lon0, north_m, east_m):
    return (lat0 + math.degrees(north_m / EARTH_RADIUS_M),
            lon0 + math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat0)))))


def make_fix(lat, lon, sigma_m, stamp):
    msg = NavSatFix()
    msg.header.stamp = stamp
    msg.header.frame_id = "gps"
    msg.status.status = NavSatStatus.STATUS_FIX
    msg.status.service = NavSatStatus.SERVICE_GPS
    msg.latitude, msg.longitude, msg.altitude = float(lat), float(lon), ALTITUDE_M
    h, v = float(sigma_m) ** 2, (2.0 * float(sigma_m)) ** 2
    msg.position_covariance = [h, 0.0, 0.0, 0.0, h, 0.0, 0.0, 0.0, v]
    msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
    return msg


class FakeGps(Node):
    def __init__(self):
        super().__init__("fake_gps")
        for name, (default, description, lo, hi, read_only) in SPECS.items():
            self.declare_parameter(name, default, make_descriptor(description, lo, hi, read_only))
        bad = check_settings(self.get_parameter("vehicle").value, self.get_parameter("speed_mps").value)
        if bad:
            raise ValueError(f"invalid settings at start: {bad}")
        self.add_on_set_parameters_callback(self.on_set_parameters)
        rate = self.get_parameter("rate_hz").value
        self.lat0 = self.get_parameter("start_lat").value
        self.lon0 = self.get_parameter("start_lon").value
        self.pub = self.create_publisher(NavSatFix, TOPIC, 10)
        self.create_timer(1.0 / rate, self.on_timer)
        self.north_m = self.east_m = 0.0
        self.last_t = None
        self.get_logger().info(f"fake GPS ({self.get_parameter('vehicle').value}) on "
                               f"{self.pub.topic_name} at {rate} Hz from ({self.lat0}, {self.lon0})")

    def on_set_parameters(self, params):
        """Called by ROS BEFORE new values are applied (ros2 param set, a launch file...). `params` is
        the list of rclpy Parameters being set. Return SetParametersResult(successful=..., reason=...)."""
        new = {p.name: p.value for p in params}
        vehicle = new.get("vehicle", self.get_parameter("vehicle").value)
        speed = new.get("speed_mps", self.get_parameter("speed_mps").value)
        reason = check_settings(vehicle, speed)
        return SetParametersResult(successful=(reason == ""), reason=reason)

    def on_timer(self):
        now = self.get_clock().now()
        t = now.nanoseconds / 1e9
        dt = 0.0 if self.last_t is None else t - self.last_t
        self.last_t = t
        v_n, v_e = velocity_ne(self.get_parameter("speed_mps").value, self.get_parameter("heading_deg").value)
        self.north_m += v_n * dt
        self.east_m += v_e * dt
        lat, lon = offset_to_latlon(self.lat0, self.lon0, self.north_m, self.east_m)
        self.pub.publish(make_fix(lat, lon, self.get_parameter("sigma_m").value, now.to_msg()))


# ---- you don't need to change anything below this line ----
def main():
    rclpy.init()
    try:
        node = FakeGps()
    except ValueError as e:
        print(e)
        rclpy.shutdown()
        raise SystemExit(1)
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

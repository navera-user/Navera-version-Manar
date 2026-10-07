#!/usr/bin/env python3
"""fake_gps.py — your first ROS 2 publisher: a fake GNSS receiver driving from Sousse.

When it is finished, it publishes sensor_msgs/NavSatFix on /fake_gps/fix (2 Hz by default) for a
vehicle that drives with a speed and a heading you can change while it runs:

    python3 fake_gps.py                                        default settings
    python3 fake_gps.py --ros-args -p speed_mps:=12.0          another speed (write 12.0, not 12!)
    ros2 param set /fake_gps heading_deg 90.0                  turn east while it runs
    ros2 topic echo /fake_gps/fix                              watch it (another terminal)

Do the TODOs in order (1 -> 7). TODO 1-4 are plain Python: test them without ROS (see the lab).
"""
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

TOPIC = "/fake_gps/fix"
EARTH_RADIUS_M = 6_371_000.0      # the same value as NAVERA's navera_common/geo.py
ALTITUDE_M = 40.0                 # metres above the WGS84 ellipsoid

# Default values of the node's parameters (TODO 5 turns them into ROS parameters).
DEFAULTS = {
    "rate_hz": 2.0,               # messages per second
    "speed_mps": 5.0,             # ground speed, metres per second
    "heading_deg": 30.0,          # direction of motion, clockwise from north (90 = east)
    "start_lat": 35.8277,         # near the Ribat of Sousse (NAVERA's test area)
    "start_lon": 10.6388,
    "sigma_m": 3.0,               # horizontal 1-sigma accuracy the receiver states, metres
}


def velocity_ne(speed_mps, heading_deg):
    """Velocity components (v_north, v_east) in m/s for a speed and a heading (clockwise from north)."""
    h = math.radians(heading_deg)
    return speed_mps * math.cos(h), speed_mps * math.sin(h)


def offset_to_latlon(lat0_deg, lon0_deg, north_m, east_m):
    """Local flat-Earth (equirectangular) conversion: a (north, east) offset in metres from
    (lat0, lon0) -> (lat, lon) in degrees. R = EARTH_RADIUS_M; longitude metres shrink by cos(lat0)."""
    lat = lat0_deg + math.degrees(north_m / EARTH_RADIUS_M)
    lon = lon0_deg + math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat0_deg))))
    return lat, lon


def make_covariance(sigma_h_m, sigma_v_m):
    """The 9 numbers of an ENU, row-major covariance with independent errors (FLOATS, in m^2):
    sigma_h^2 for East and North, sigma_v^2 for Up, 0.0 elsewhere."""
    h, v = float(sigma_h_m) ** 2, float(sigma_v_m) ** 2
    return [h, 0.0, 0.0,
            0.0, h, 0.0,
            0.0, 0.0, v]


def make_fix(lat, lon, alt_m, sigma_m, stamp):
    """One complete NavSatFix. `stamp` is a builtin_interfaces/Time (now.to_msg())."""
    msg = NavSatFix()
    msg.header.stamp = stamp
    msg.header.frame_id = "gps"
    msg.status.status = NavSatStatus.STATUS_FIX
    msg.status.service = NavSatStatus.SERVICE_GPS
    msg.latitude, msg.longitude, msg.altitude = float(lat), float(lon), float(alt_m)
    msg.position_covariance = make_covariance(sigma_m, 2 * sigma_m)
    msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
    return msg


class FakeGps(Node):
    def __init__(self):
        super().__init__("fake_gps")              # the node's name in the ROS graph
        for name, default in DEFAULTS.items():
            self.declare_parameter(name, default)        # the type (double) comes from the default
        rate = self.get_parameter("rate_hz").value
        self.lat0 = self.get_parameter("start_lat").value
        self.lon0 = self.get_parameter("start_lon").value

        self.pub = self.create_publisher(NavSatFix, TOPIC, 10)
        self.timer = self.create_timer(1.0 / rate, self.on_timer)

        self.north_m = 0.0                         # offset from the start, metres
        self.east_m = 0.0
        self.last_t = None                         # time of the previous tick (seconds), None at first
        self.count = 0
        self.get_logger().info(f"fake GPS on {TOPIC} at {rate} Hz from ({self.lat0}, {self.lon0})")

    def on_timer(self):
        """Called by the timer: move the vehicle by v * dt, then publish where it is now."""
        now = self.get_clock().now()
        t = now.nanoseconds / 1e9
        dt = 0.0 if self.last_t is None else t - self.last_t
        self.last_t = t
        v_n, v_e = velocity_ne(self.get_parameter("speed_mps").value,
                               self.get_parameter("heading_deg").value)
        self.north_m += v_n * dt
        self.east_m += v_e * dt

        lat, lon = offset_to_latlon(self.lat0, self.lon0, self.north_m, self.east_m)
        sigma = self.get_parameter("sigma_m").value if self.has_parameter("sigma_m") else DEFAULTS["sigma_m"]
        self.pub.publish(make_fix(lat, lon, ALTITUDE_M, sigma, now.to_msg()))
        self.count += 1
        if self.count % 10 == 1:                   # log one fix in ten, not to flood the terminal
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

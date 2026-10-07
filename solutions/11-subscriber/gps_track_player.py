#!/usr/bin/env python3
"""gps_track_player.py — a ready-made GNSS source for this lab (you don't need to change it).

It drives a pretend vehicle around a loop near the Ribat of Sousse (NAVERA's test area), at a known
speed and publishes sensor_msgs/NavSatFix on /fake_gps/fix (2 Hz) — the same topic and message as
your fake GPS of lesson 10. Parameters (doubles unless noted):

    speed_mps 6.0     rate_hz 2.0     noise_m 0.0 (Gaussian position noise, 1 sigma, per axis)
    seed 1 (int)      faults false (bool: every few fixes, publish a bad one on purpose)

    python3 gps_track_player.py
    python3 gps_track_player.py --ros-args -p noise_m:=3.0
    python3 gps_track_player.py --ros-args -p faults:=true

The plain functions route_point() and to_latlon() are also used by noise_study.py.
"""
import math
import random

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

TOPIC = "/fake_gps/fix"
R = 6_371_000.0
START = (35.8277, 10.6388)                 # near the Ribat of Sousse, NAVERA's test area
# The loop: (north, east) in metres from START, corner after corner (2 400 m in total).
ROUTE_M = [(0, 0), (0, 400), (300, 400), (300, 900), (0, 900), (0, 0)]
SIGMA_STATED_M = 3.0                       # the accuracy the receiver states in its covariance


def route_length():
    return sum(math.dist(a, b) for a, b in zip(ROUTE_M[:-1], ROUTE_M[1:]))


def route_point(d):
    """(north, east) in metres after travelling d metres along ROUTE_M (looping)."""
    d %= route_length()
    for a, b in zip(ROUTE_M[:-1], ROUTE_M[1:]):
        length = math.dist(a, b)
        if d <= length:
            f = d / length
            return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
        d -= length
    return ROUTE_M[-1]


def to_latlon(north, east):
    """Local flat-Earth conversion around START (lesson 10)."""
    return (START[0] + math.degrees(north / R),
            START[1] + math.degrees(east / (R * math.cos(math.radians(START[0])))))


class TrackPlayer(Node):
    def __init__(self):
        super().__init__("gps_track_player")
        self.declare_parameter("speed_mps", 6.0)
        self.declare_parameter("rate_hz", 2.0)
        self.declare_parameter("noise_m", 0.0)
        self.declare_parameter("seed", 1)
        self.declare_parameter("faults", False)
        self.speed = float(self.get_parameter("speed_mps").value)
        self.noise = float(self.get_parameter("noise_m").value)
        self.faults = bool(self.get_parameter("faults").value)
        self.rng = random.Random(int(self.get_parameter("seed").value))
        rate = float(self.get_parameter("rate_hz").value)
        self.pub = self.create_publisher(NavSatFix, TOPIC, 10)
        self.t0 = self.get_clock().now()
        self.n = 0
        self.prev_stamp = None
        self.create_timer(1.0 / rate, self.tick)
        self.get_logger().info(f"playing a {self.speed:.1f} m/s drive around Sousse on {TOPIC} at {rate:.1f} Hz"
                               f" (noise {self.noise:.1f} m, faults {'on' if self.faults else 'off'})")

    def tick(self):
        now = self.get_clock().now()
        t = (now - self.t0).nanoseconds / 1e9
        north, east = route_point(self.speed * t)
        north += self.rng.gauss(0.0, self.noise) if self.noise > 0 else 0.0
        east += self.rng.gauss(0.0, self.noise) if self.noise > 0 else 0.0
        lat, lon = to_latlon(north, east)
        m = NavSatFix()
        m.header.stamp = now.to_msg()
        m.header.frame_id = "gps"
        m.status = NavSatStatus(status=NavSatStatus.STATUS_FIX, service=NavSatStatus.SERVICE_GPS)
        m.latitude, m.longitude, m.altitude = lat, lon, 35.0
        s2 = SIGMA_STATED_M ** 2
        m.position_covariance = [s2, 0.0, 0.0, 0.0, s2, 0.0, 0.0, 0.0, 4.0 * s2]
        m.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        self.n += 1
        if self.faults:
            k = self.n % 12
            if k == 3:                                   # the receiver lost the satellites
                m.status.status = NavSatStatus.STATUS_NO_FIX
                m.latitude = m.longitude = math.nan
            elif k == 6:                                 # a driver that never filled the position
                m.latitude = m.longitude = 0.0
            elif k == 9 and self.prev_stamp is not None:  # an old fix delivered late
                m.header.stamp = self.prev_stamp
        if not (self.faults and self.n % 12 == 9):
            self.prev_stamp = m.header.stamp
        self.pub.publish(m)


def main():
    rclpy.init()
    node = TrackPlayer()
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

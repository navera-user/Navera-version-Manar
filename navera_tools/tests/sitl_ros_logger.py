#!/usr/bin/env python3
"""Records what NAVERA says during a simulator run (ROS domain of the simulator, default 79).

Run it next to the simulator (same ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY=1); it writes one JSON
line per message, with the wall-clock time, to the file given as argument:

    ROS_DOMAIN_ID=79 ROS_LOCALHOST_ONLY=1 python3 navera_tools/tests/sitl_ros_logger.py OUT.jsonl

Recorded: /navera/position and /navera/estimate/* (source, mode, valid, lat/lon, altitude,
the covariance sigma, reason, details), /navera/nav_status, /navera/fix (what vehicle_output
decided to send: status, sigma, altitude) and the day pipeline's status JSON. The campaign
driver (sitl_fault_campaign.py) writes the truth CSV; sitl_fault_analyse.py joins both by
wall time. SIMULATED runs only.
"""
import json
import math
import sys
import time

import rclpy
from navera_msgs.msg import NavStatus, PositionEstimate
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, Range
from std_msgs.msg import String


def _f(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


class Logger(Node):
    def __init__(self, path):
        super().__init__("sitl_ros_logger")
        self.out = open(path, "w", buffering=1)
        for src in ("gps", "day", "night", "cn"):
            self.create_subscription(PositionEstimate, f"/navera/estimate/{src}",
                                     lambda m, s=src: self.est("estimate/" + s, m), 10)
        self.create_subscription(PositionEstimate, "/navera/position", lambda m: self.est("position", m), 10)
        self.create_subscription(NavStatus, "/navera/nav_status", self.status, 10)
        self.create_subscription(NavSatFix, "/navera/fix", self.fix, 10)
        self.create_subscription(Range, "/navera/vision/altitude_agl", self.rng, 10)
        self.create_subscription(String, "/day/day_status", self.day_status, 10)

    def w(self, **d):
        d["wall"] = round(time.time(), 3)
        self.out.write(json.dumps(d, default=str) + "\n")

    def est(self, topic, m):
        c = list(m.position_covariance)
        sig = math.sqrt(max(c[0], c[4])) if m.position_covariance_type and c[0] > 0 else None
        try:
            det = json.loads(m.details_json or "{}")
        except ValueError:
            det = {}
        self.w(t=topic, src=m.source, mode=m.mode, valid=m.valid, lat=_f(m.latitude), lon=_f(m.longitude),
               alt=_f(m.altitude), sigma=sig, cov_type=m.position_covariance_type, reason=m.reason[:200],
               stamp=m.sensor_stamp.sec + m.sensor_stamp.nanosec * 1e-9, frame=m.frame_index,
               det={k: det.get(k) for k in ("src", "score", "jump_m", "reason", "geo_sep_m")})

    def status(self, m):
        self.w(t="nav_status", state=m.state, active=m.active_source, reason=m.reason[:200])

    def fix(self, m):
        c = list(m.position_covariance)
        self.w(t="fix", status=m.status.status, lat=_f(m.latitude), lon=_f(m.longitude), alt=_f(m.altitude),
               sigma=_f(math.sqrt(c[0])) if m.position_covariance_type else None,
               stamp=m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)

    def rng(self, m):
        self.w(t="vision_agl", range=_f(m.range), sigma=_f(m.field_of_view))

    def day_status(self, m):
        self.w(t="day_status", raw=m.data[:600])


def main():
    rclpy.init()
    n = Logger(sys.argv[1])
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

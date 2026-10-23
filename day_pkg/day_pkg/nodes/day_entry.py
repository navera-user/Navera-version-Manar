#!/usr/bin/env python3
"""Entry point of day_subscriber.py: an early bridge, then the day node (B23).

A day node restarted alone in flight needs seconds before it publishes anything: its imports (OpenCV,
PyTorch, the matchers: 3 s on the Jetson, 14 s on the Isaac Sim PC under load) and its matcher (6 s
there). The 2-hour Isaac Sim endurance flight with a mid-flight kill (fin_endur_2h, 2026-10-23) went
21 s without a day position: the output's 10 s bridge ended and the autopilot's EKF failed safe.

So the process first starts a light node, before any heavy import: it reads the persisted track
(navera_common.state_store "day_track", day_pkg.carry_state) and publishes its last output carried to
now — PROPAGATED, its stated accuracy growing with the time since the last measured fix, within the
same limits as the node (max_dead_reckon_s, dead_reckon_max_sigma_m) — once a second, until the day
node is constructed. Nothing persisted, or too old: it publishes nothing.
"""
import json
import logging
import math
import threading
import time

import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node

from day_pkg.carry_state import TRACK_STATE, restore_track, watchdog_carry
from navera_common import state_store
from navera_common.lifecycle import die_with_parent
from navera_common.track import TrackVelocity
from navera_msgs.msg import PositionEstimate


class EarlyBridge(Node):
    """Publishes the persisted carried position while the day node starts."""

    def __init__(self):
        super().__init__("day_subscriber_early")
        self.declare_parameter("estimate_topic", "/navera/estimate/day")
        self.declare_parameter("max_dead_reckon_s", 120.0)
        self.declare_parameter("dead_reckon_max_sigma_m", 900.0)
        self.declare_parameter("dead_reckon_accel_mps2", 0.25)
        p = lambda n: self.get_parameter(n).value               # noqa: E731
        self.max_dr_s, self.max_sigma_m = float(p("max_dead_reckon_s")), float(p("dead_reckon_max_sigma_m"))
        self.track = TrackVelocity(accel_mps2=float(p("dead_reckon_accel_mps2")))
        r = restore_track(state_store.load(TRACK_STATE, self.max_dr_s + 5.0), time.time(), self.max_dr_s)
        self.snap = r["snap"] if r is not None else None
        self.published = 0
        self.pub = self.create_publisher(PositionEstimate, str(p("estimate_topic")), 10)
        if self.snap is not None:
            self.get_logger().warn(f"[day] restart: carrying the persisted position "
                                   f"({time.time() - self.snap.t_meas:.0f} s after its last measured fix) "
                                   "while the day node starts")
            self.tick()
            self.create_timer(1.0, self.tick)

    def tick(self) -> bool:
        """Publish the snapshot carried to now; False when there is none or a limit is reached."""
        p, why = watchdog_carry(self.snap, time.time(), self.track, self.max_dr_s, self.max_sigma_m)
        if p is None:
            return False
        lat, lon, sigma = p
        est = PositionEstimate()
        est.header.stamp = self.get_clock().now().to_msg()
        est.header.frame_id = "day_camera_link"
        est.latitude, est.longitude, est.altitude = float(lat), float(lon), math.nan
        var = float(sigma) ** 2
        est.position_covariance = [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, 0.0]
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        est.source = PositionEstimate.SOURCE_DAY_VISION
        est.mode = PositionEstimate.MODE_PROPAGATED
        est.valid = True
        est.confidence = 0.0
        est.sensor_stamp = est.header.stamp
        est.producer = "day_subscriber"
        est.model_id = "dead_reckon"
        est.frame_index = -1
        est.details_json = json.dumps({"src": "dead_reckon", "early_bridge": True,
                                       "reason": "day node restarting: persisted track carried on"})
        self.pub.publish(est)
        self.published += 1
        return True


def main(args=None):
    """The early bridge in its own thread, then the day node (day_subscriber.main without its init)."""
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] [%(name)s]: %(message)s")
    die_with_parent()
    rclpy.init(args=args)
    early, ex = None, None
    try:
        early = EarlyBridge()
        ex = SingleThreadedExecutor()
        ex.add_node(early)
        threading.Thread(target=ex.spin, daemon=True).start()
    except Exception as e:                       # noqa: BLE001 — the bridge must never stop the node
        logging.getLogger("day_entry").warning(f"early bridge not started: {e}")

    def stop_early():
        if ex is not None:
            ex.shutdown(timeout_sec=1.0)
        if early is not None:
            early.destroy_node()

    try:
        from day_pkg.nodes import day_subscriber    # the heavy imports happen here
    except (KeyboardInterrupt, ExternalShutdownException):
        stop_early()
        if rclpy.ok():
            rclpy.shutdown()
        return
    day_subscriber.main(args, init=False, before_spin=stop_early)


if __name__ == "__main__":
    main()

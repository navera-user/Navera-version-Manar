#!/usr/bin/env python3
"""Demonstration scenario: a simulated mission with GPS jamming (no hardware).

    NAVERA_ALLOW_SIM=1 python3 navera_tools/demo_mission.py [--profile measured|target]

Everything this node publishes is SIMULATED and labelled so (producer
"demo_mission", details_json {"simulated": true}); the operator view shows a
SIMULATION banner while it runs. The real arbiter (navera_estimator), web
bridge and vehicle output process it exactly as they would live data.

The vehicle follows a loop over Sousse at --speed m/s. One cycle:
    GPS OK        --gps-ok-s      GPS fixes at 5 Hz
    GPS JAMMED    --jammed-s      the receiver reports no fix
    GPS RESTORED  --restored-s
then the cycle repeats. Day vision publishes an estimate every second the whole
time, with a SIMULATED error:
    measured  error drawn to match what day vision measures today on real
              labelled frames (median ~440 m, docs/VALIDATION_STATUS.md);
              uncertainty unknown -> the arbiter reports DEGRADED
    target    the product accuracy target (sigma 15 m per axis, stated) ->
              the arbiter reports FIX. NOT a measured performance.
The true position is published on /navera/sim/truth so the operator view can
draw it and show the error of what NAVERA outputs.
"""
import argparse
import json
import math
import os
import random
import sys
import time

if os.environ.get("NAVERA_ALLOW_SIM") != "1":
    sys.exit("refusing to run: this publishes simulated data on the real NAVERA "
             "topics. Set NAVERA_ALLOW_SIM=1 on a test machine to allow it.")

import rclpy  # noqa: E402
from geometry_msgs.msg import TwistStamped  # noqa: E402
from rclpy.node import Node  # noqa: E402
from sensor_msgs.msg import Imu, NavSatFix, NavSatStatus, TimeReference  # noqa: E402
from std_msgs.msg import String  # noqa: E402

from navera_msgs.msg import NavStatus, PositionEstimate  # noqa: E402

# Loop over Sousse (lat, lon), inside the onboard map.
ROUTE = [(35.8256, 10.6385), (35.8420, 10.6230), (35.8560, 10.6010),
         (35.8450, 10.5820), (35.8250, 10.5900), (35.8150, 10.6150)]
ALT_M = 300.0
GPS_SIGMA_M = 1.5
M_PER_DEG = 111_320.0
# Rayleigh median = sigma * sqrt(2 ln 2): per-axis sigma giving a 440 m median.
MEASURED_SIGMA_M = 440.0 / math.sqrt(2.0 * math.log(2.0))
TARGET_SIGMA_M = 15.0

PHASE_OK, PHASE_JAMMED, PHASE_RESTORED = "GPS OK", "GPS JAMMED", "GPS RESTORED"


def to_en(lat, lon):
    return ((lon - ROUTE[0][1]) * M_PER_DEG * math.cos(math.radians(ROUTE[0][0])),
            (lat - ROUTE[0][0]) * M_PER_DEG)


def to_ll(east, north):
    return (ROUTE[0][0] + north / M_PER_DEG,
            ROUTE[0][1] + east / (M_PER_DEG * math.cos(math.radians(ROUTE[0][0]))))


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))


class Route:
    """Constant-speed travel along the closed ROUTE loop."""

    def __init__(self, speed):
        self.speed = speed
        self.pts = [to_en(*p) for p in ROUTE]
        self.legs = []
        for i, a in enumerate(self.pts):
            b = self.pts[(i + 1) % len(self.pts)]
            self.legs.append((a, b, math.hypot(b[0] - a[0], b[1] - a[1])))
        self.length = sum(leg[2] for leg in self.legs)

    def at(self, t):
        """(lat, lon, v_east, v_north) at time t."""
        d = (self.speed * t) % self.length
        for a, b, n in self.legs:
            if d <= n:
                ue, un = (b[0] - a[0]) / n, (b[1] - a[1]) / n
                lat, lon = to_ll(a[0] + ue * d, a[1] + un * d)
                return lat, lon, ue * self.speed, un * self.speed
            d -= n
        lat, lon = to_ll(*self.pts[0])
        return lat, lon, 0.0, 0.0


class DemoMission(Node):
    def __init__(self, a):
        super().__init__("demo_mission")
        self.a = a
        self.route = Route(a.speed)
        self.rng = random.Random(a.seed)
        self.cycle = a.gps_ok_s + a.jammed_s + a.restored_s
        self.pub_gps = self.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)
        self.pub_day = self.create_publisher(PositionEstimate, "/navera/estimate/day", 10)
        self.pub_fix = self.create_publisher(NavSatFix, "/navera/sensors/gps_fix", 10)
        self.pub_vel = self.create_publisher(TwistStamped, "/navera/sensors/gps_vel", 10)
        self.pub_imu = self.create_publisher(Imu, "/navera/sensors/imu", 10)
        self.pub_rtc = self.create_publisher(TimeReference, "/navera/sensors/rtc_time", 10)
        self.pub_rtcs = self.create_publisher(String, "/navera/sensors/rtc_status", 10)
        self.pub_truth = self.create_publisher(NavSatFix, "/navera/sim/truth", 10)
        self.create_subscription(PositionEstimate, "/navera/position", self._on_position, 10)
        self.create_subscription(NavStatus, "/navera/nav_status", self._on_status, 10)
        self.t0 = time.monotonic()
        self.phase = None
        self.state = "?"
        self.errors = {}          # phase -> [output error m]
        self.create_timer(0.2, self.tick_gps)
        self.create_timer(1.0, self.tick_day)
        self.create_timer(0.05, self.tick_imu)
        self.create_timer(1.0, self.tick_rtc)
        self.create_timer(5.0, self.report)
        self.get_logger().warning(
            f"SIMULATION [PID {os.getpid()}] profile={a.profile} route {self.route.length / 1000:.1f} km "
            f"@ {a.speed:.0f} m/s; cycle: GPS OK {a.gps_ok_s:.0f} s, JAMMED {a.jammed_s:.0f} s, "
            f"RESTORED {a.restored_s:.0f} s")

    def elapsed(self):
        return time.monotonic() - self.t0

    def phase_at(self, t):
        c = t % self.cycle
        if c < self.a.gps_ok_s:
            return PHASE_OK
        return PHASE_JAMMED if c < self.a.gps_ok_s + self.a.jammed_s else PHASE_RESTORED

    def _base(self, source, lat, lon, sigma, known, now):
        m = PositionEstimate()
        m.header.stamp = now
        m.sensor_stamp = now
        m.latitude, m.longitude, m.altitude = lat, lon, ALT_M
        if known:
            m.position_covariance = [sigma ** 2, 0.0, 0.0, 0.0, sigma ** 2, 0.0,
                                     0.0, 0.0, (2 * sigma) ** 2]
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_DIAGONAL_KNOWN
        else:
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        m.source = source
        m.mode = PositionEstimate.MODE_MEASURED
        m.producer = "demo_mission"
        m.model_id = f"sim-{self.a.profile}"
        m.frame_index = -1
        return m

    def tick_gps(self):
        t = self.elapsed()
        phase = self.phase_at(t)
        if phase != self.phase:
            self.get_logger().warning(f"t={t:5.0f} s  >>> {phase}")
            self.phase = phase
        lat, lon, ve, vn = self.route.at(t)
        now = self.get_clock().now().to_msg()

        truth = NavSatFix()
        truth.header.stamp = now
        truth.header.frame_id = "sim_truth"
        truth.latitude, truth.longitude, truth.altitude = lat, lon, ALT_M
        self.pub_truth.publish(truth)

        fix = NavSatFix()
        fix.header.stamp = now
        fix.header.frame_id = "gps_link"
        jammed = phase == PHASE_JAMMED
        if jammed:
            est = self._base(PositionEstimate.SOURCE_GPS, math.nan, math.nan, 0, False, now)
            est.valid = False
            est.reason = "no fix (simulated jamming)"
            est.details_json = json.dumps({"simulated": True, "num_sats": 0})
            fix.status.status = NavSatStatus.STATUS_NO_FIX
            fix.latitude = fix.longitude = fix.altitude = math.nan
        else:
            e, n = to_en(lat, lon)
            glat, glon = to_ll(e + self.rng.gauss(0, GPS_SIGMA_M), n + self.rng.gauss(0, GPS_SIGMA_M))
            est = self._base(PositionEstimate.SOURCE_GPS, glat, glon, GPS_SIGMA_M, True, now)
            est.valid = True
            est.confidence = 0.95
            est.details_json = json.dumps({"simulated": True, "num_sats": 12, "hdop": 0.7,
                                           "geo_sep_m": 33.0})
            fix.status.status = NavSatStatus.STATUS_FIX
            fix.latitude, fix.longitude, fix.altitude = glat, glon, ALT_M
        est.header.frame_id = "gps_link"
        fix.status.service = NavSatStatus.SERVICE_GPS
        self.pub_gps.publish(est)
        self.pub_fix.publish(fix)
        if not jammed:
            vel = TwistStamped()
            vel.header.stamp = now
            vel.header.frame_id = "gps_link"
            vel.twist.linear.x, vel.twist.linear.y = ve, vn
            self.pub_vel.publish(vel)

    def tick_day(self):
        lat, lon, _, _ = self.route.at(self.elapsed())
        target = self.a.profile == "target"
        sigma = TARGET_SIGMA_M if target else MEASURED_SIGMA_M
        e, n = to_en(lat, lon)
        vlat, vlon = to_ll(e + self.rng.gauss(0, sigma), n + self.rng.gauss(0, sigma))
        now = self.get_clock().now().to_msg()
        m = self._base(PositionEstimate.SOURCE_DAY_VISION, vlat, vlon, sigma, target, now)
        m.header.frame_id = "day_camera"
        m.valid = True
        m.confidence = 0.9 if target else 0.3
        m.details_json = json.dumps({"simulated": True, "profile": self.a.profile})
        self.pub_day.publish(m)

    def tick_imu(self):
        _, _, ve, vn = self.route.at(self.elapsed())
        yaw = math.atan2(vn, ve)
        imu = Imu()
        imu.header.stamp = self.get_clock().now().to_msg()
        imu.header.frame_id = "imu_link"
        imu.orientation.z, imu.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        imu.linear_acceleration.z = 9.81
        self.pub_imu.publish(imu)

    def tick_rtc(self):
        now = self.get_clock().now().to_msg()
        tr = TimeReference()
        tr.header.stamp = now
        tr.time_ref = now
        tr.source = "demo_mission"
        self.pub_rtc.publish(tr)
        self.pub_rtcs.publish(String(data=json.dumps({"valid": True, "simulated": True})))

    def _on_status(self, msg):
        self.state = {NavStatus.STATE_FIX: "FIX", NavStatus.STATE_DEGRADED: "DEGRADED",
                      NavStatus.STATE_NO_FIX: "NO_FIX"}.get(msg.state, "INITIALIZING")

    def _on_position(self, msg):
        lat, lon, _, _ = self.route.at(self.elapsed())
        err = haversine_m(lat, lon, msg.latitude, msg.longitude)
        self.errors.setdefault(self.phase, []).append(err)

    def report(self):
        parts = []
        for phase in (PHASE_OK, PHASE_JAMMED, PHASE_RESTORED):
            v = sorted(self.errors.get(phase, []))
            if v:
                parts.append(f"{phase}: median {v[len(v) // 2]:.0f} m (n={len(v)})")
        self.get_logger().info(f"t={self.elapsed():5.0f} s  {self.phase}  NAVERA {self.state}  "
                               f"output error vs truth — " + ("; ".join(parts) or "none yet"))


def main():
    ap = argparse.ArgumentParser(description="NAVERA demonstration scenario (SIMULATED data)")
    ap.add_argument("--profile", choices=["measured", "target"], default="measured")
    ap.add_argument("--speed", type=float, default=25.0, help="vehicle speed, m/s")
    ap.add_argument("--gps-ok-s", type=float, default=40.0)
    ap.add_argument("--jammed-s", type=float, default=90.0)
    ap.add_argument("--restored-s", type=float, default=30.0)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rclpy.init()
    probe = rclpy.create_node("demo_mission_probe")
    t_end = time.monotonic() + 3.0                 # DDS discovery
    while time.monotonic() < t_end and probe.count_publishers("/navera/sim/truth") == 0:
        rclpy.spin_once(probe, timeout_sec=0.2)
    others = probe.count_publishers("/navera/sim/truth")
    probe.destroy_node()
    if others:
        rclpy.shutdown()
        sys.exit("another simulation is already running on this ROS domain: two simulated "
                 "vehicles would be mixed. Stop it first.")
    node = DemoMission(a)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.report()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

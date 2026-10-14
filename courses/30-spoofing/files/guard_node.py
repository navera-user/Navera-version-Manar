"""guard_node.py — the judge of mission 29 with YOUR spoofing guard in front of it, as a ROS 2 node named "arbiter".

    python3 guard_node.py --ros-args --params-file navera_lite.yaml -p max_speed_mps:=30.0 &

Same topics as every NAVERA Lite judge (relative names):
  subscribes  navera_lite/fix/{gps,day,night,celestial}   sensor_msgs/NavSatFix
  publishes   navera_lite/position   NavSatFix, the winning measurement (once per new measurement)
              navera_lite/status     diagnostic_msgs/DiagnosticStatus (latched): state, source, sigma_m, age_s,
                                     gps_guard (TRUSTED / IN_DOUBT / REFUSED), guard_reason
Parameters: every key of navera_lite.yaml, plus p_fa (the guard's false-alarm probability per test, 0.01).
Stop it with `kill %1` (or Ctrl+C if it runs in the foreground).
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import sys

from diagnostic_msgs.msg import DiagnosticStatus
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix

from navera_lite.estimate import SOURCES, stated_sigma
from navera_lite.ros.convert import from_navsatfix, make_status, to_navsatfix
from navera_lite.ros.qos import FIX_QOS, STATUS_QOS
from navera_lite.ros.runner import run_node
from navera_lite.settings import DEFAULTS
from navera_lite.spoof import GUARD_DEFAULTS, GuardedArbiter, SpoofGuard

try:
    from navera_lite.arbiter import Arbiter
except ImportError as e:
    sys.exit(f"navera_lite/arbiter.py (mission 29's judge) cannot be imported: {e}")


def field(d, name):
    return d.get(name) if isinstance(d, dict) else getattr(d, name, None)


class GuardNode(Node):
    def __init__(self):
        super().__init__("arbiter")
        for key, value in DEFAULTS.items():
            self.declare_parameter(key, value)
        self.declare_parameter("p_fa", GUARD_DEFAULTS["p_fa"])
        self.cfg = {key: self.get_parameter(key).value for key in DEFAULTS}
        self.cfg["p_fa"] = float(self.get_parameter("p_fa").value)
        self.guard = SpoofGuard(self.cfg)
        self.judge = GuardedArbiter(Arbiter(self.cfg), self.guard)
        for name in SOURCES:
            self.create_subscription(NavSatFix, f"navera_lite/fix/{name}",
                                     lambda msg, name=name: self.on_fix(name, msg), FIX_QOS)
        self.pub_position = self.create_publisher(NavSatFix, "navera_lite/position", FIX_QOS)
        self.pub_status = self.create_publisher(DiagnosticStatus, "navera_lite/status", STATUS_QOS)
        self.last_sent, self.last_log, self.last_verdict = None, None, None
        self.create_timer(1.0 / float(self.cfg["tick_hz"]), self.step)
        self.create_timer(5.0, self.count_judges)
        self.get_logger().info(f"judge + spoofing guard started (top speed {self.cfg['max_speed_mps']} m/s, "
                               f"p_fa {self.cfg['p_fa']})")
        self.step()

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_fix(self, name, msg):
        now = self.now_s()
        try:
            verdict, why = self.judge.receive(from_navsatfix(msg, source=name, now_s=now), now)
        except Exception as e:                      # noqa: BLE001 — one plain line, the node keeps running
            self.get_logger().error(f"the guard or the judge stopped on a {name} fix: {type(e).__name__}: {e}")
            return
        if name == "gps" and (verdict, why) != self.last_verdict:
            if verdict != "TRUSTED":
                self.get_logger().warn(f"GPS {verdict}: {why}")
            self.last_verdict = (verdict, why)
        self.step()

    def step(self):
        now = self.now_s()
        d = self.judge.step(now)
        state, source, est = field(d, "state"), field(d, "source"), field(d, "estimate")
        sigma = None if est is None else stated_sigma(est, self.cfg)
        values = {"source": source or "", "sigma_m": "" if sigma is None else f"{sigma:.2f}",
                  "age_s": "" if est is None else f"{now - est.stamp_s:.2f}",
                  "gps_guard": self.guard.state, "guard_reason": self.guard.reason}
        self.pub_status.publish(make_status(state, field(d, "reason") or "", values))
        if (state, source, self.guard.state) != self.last_log:
            self.get_logger().info(f"{state} {source or ''} · GPS {self.guard.state}")
            self.last_log = (state, source, self.guard.state)
        if est is not None and state in ("FIX", "DEGRADED"):
            key = (est.source, est.stamp_s, est.lat, est.lon)
            if key != self.last_sent:
                self.pub_position.publish(to_navsatfix(est))
                self.last_sent = key

    def count_judges(self):
        topic = self.resolve_topic_name("navera_lite/status")
        n = self.count_publishers(topic)
        if n > 1:
            self.get_logger().error(f"{n} judges publish on {topic}: stop the extra one (`jobs`, then `kill %N`)")


def main(args=None):
    run_node(GuardNode, args)


if __name__ == "__main__":
    main()

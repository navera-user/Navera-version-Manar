#!/usr/bin/env python3
"""compute_health_node.py — the Jetson's compute health for NAVERA (hazard H-11).

Every `period_s` it reads temperatures, memory, swap, GPU load and thermal throttling from the
kernel files tegrastats uses (no root; navera_common.compute_health) and publishes:

    /diagnostics                 diagnostic_msgs/DiagnosticArray  one status "navera: compute health"
                                                                  (OK / WARN; ERROR when degraded)
    /navera/compute_health       std_msgs/String (JSON)           the full sample, for the operator view
    /navera/compute/degraded     std_msgs/Bool (latched)          true while hot or short of memory: the
                                                                  localizers skip optional heavy retries

At start it reports a box without swap (F5: a day pipeline without swap was OOM-killed after
4.6 min). A failure of this node never stops the arbiter (launched with respawn, not Shutdown).

Parameters: period_s (2.0), temp_warn_c (85), temp_degrade_c (95), mem_warn_pct (15),
mem_degrade_pct (8), root ("/": a fake tree for tests).
"""
import json

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from navera_common.compute_health import ComputeHealthMonitor, DEGRADED_TOPIC, Thresholds
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, String

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)


class ComputeHealthNode(Node):
    """Publishes the compute health and the degraded flag."""

    def __init__(self, **kwargs):
        super().__init__("compute_health", **kwargs)
        declare_float(self, "period_s", 2.0)
        declare_float(self, "temp_warn_c", 85.0)
        declare_float(self, "temp_degrade_c", 95.0)
        declare_float(self, "mem_warn_pct", 15.0)
        declare_float(self, "mem_degrade_pct", 8.0)
        self.declare_parameter("root", "/")
        g = lambda n: self.get_parameter(n).value       # noqa: E731
        self.monitor = ComputeHealthMonitor(
            Thresholds(temp_warn_c=float(g("temp_warn_c")), temp_degrade_c=float(g("temp_degrade_c")),
                       mem_warn_pct=float(g("mem_warn_pct")), mem_degrade_pct=float(g("mem_degrade_pct"))),
            root=str(g("root")))
        self.pub_diag = self.create_publisher(DiagnosticArray, "/diagnostics", 10)
        self.pub_json = self.create_publisher(String, "/navera/compute_health", 10)
        self.pub_degraded = self.create_publisher(Bool, DEGRADED_TOPIC, LATCHED)
        self._last_level, self._last_degraded = None, None
        self.swap_warning = self.monitor.swap_report()
        if self.swap_warning:
            self.get_logger().warn(self.swap_warning)
        self.create_timer(float(g("period_s")), self.tick)
        self.tick()

    def tick(self):
        """Sample, publish, and log level changes."""
        h = self.monitor.sample()
        d = h.as_dict()
        if self.swap_warning:
            d["swap_warning"] = self.swap_warning
        self.pub_json.publish(String(data=json.dumps(d)))
        st = DiagnosticStatus(name="navera: compute health", hardware_id="jetson",
                              level={"OK": DiagnosticStatus.OK, "WARN": DiagnosticStatus.WARN}.get(
                                  h.level, DiagnosticStatus.ERROR),
                              message="; ".join(h.messages) or "ok")
        st.values = [KeyValue(key=k, value=str(v)) for k, v in (
            ("max_temp_c", d["max_temp_c"]), ("mem_available_pct", d["mem_available_pct"]),
            ("swap_mb", d["swap_mb"]), ("gpu_load_pct", d["gpu_load_pct"]),
            ("throttling", ", ".join(h.throttling) or "none"), ("degraded", h.degraded))]
        arr = DiagnosticArray(status=[st])
        arr.header.stamp = self.get_clock().now().to_msg()
        self.pub_diag.publish(arr)
        if h.degraded != self._last_degraded:
            self.pub_degraded.publish(Bool(data=h.degraded))
            self._last_degraded = h.degraded
        if h.level != self._last_level:
            msg = f"compute health {h.level}: {st.message}"
            if h.level == "OK":
                self.get_logger().info(msg)
            elif h.level == "WARN":
                self.get_logger().warn(msg)
            else:
                self.get_logger().error(msg)
            self._last_level = h.level
        return h


def main(args=None):
    """Entry point."""
    die_with_parent()
    rclpy.init(args=args)
    node = ComputeHealthNode()
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

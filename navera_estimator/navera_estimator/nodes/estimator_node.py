#!/usr/bin/env python3
"""
estimator_node.py — NAVERA position arbiter (v1: GPS-only).

This is the node that answers the operator's one question: *do we have a usable
position right now, and who is providing it?* It consumes the typed per-source
contract (navera_msgs/PositionEstimate) and publishes the two authoritative
outputs:
    /navera/position    navera_msgs/PositionEstimate  — the WINNING estimate,
                        republished verbatim with producer rewritten. Emitted
                        ONLY when a source is contributing; never a held point.
    /navera/nav_status  navera_msgs/NavStatus         — the decisional summary
                        (state + who is alive), published every tick.

v1 scope is deliberately minimal — it validates the plumbing on ONE honest
source before the lying/fusing sources arrive:
  * Subscribes to /navera/estimate/gps ONLY (the sole arbitrated source).
  * Subscribes to /navera/sensors/imu for LIVENESS ONLY. The IMU reports
    alive=true / contributing=false — zero invented position, zero covariance.
  * Eligibility: valid==true AND mode in {MEASURED, PROPAGATED} AND fresh
    (header age < gps_timeout_s). Otherwise NO_FIX.
  * No hysteresis / dwell / jump-guard yet — those arrive in step 6 when there
    is more than one source to arbitrate between.

State machine (v1):
  INITIALIZING  no watched message has EVER arrived (transient, since boot).
  NO_FIX        running, but no source is currently usable. First-class.
  FIX           a fresh MEASURED GPS solution is being published.
  DEGRADED      an eligible but PROPAGATED (dead-reckoned) GPS solution — the
                honest reading of the contract: reduced trust, still published.

Parameters:
    publish_rate_hz (default 5.0) — decision + nav_status cadence
    gps_timeout_s   (default 3.0) — GPS freshness/liveness window
    imu_timeout_s   (default 1.0) — IMU liveness window
"""
from typing import Optional

import rclpy
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import Imu

from navera_msgs.msg import NavStatus, PositionEstimate, SourceHealth

# Modes that a source may contribute a position in. A HELD echo or REPLAYED
# ground-truth point is never eligible to win.
_ELIGIBLE_MODES = (PositionEstimate.MODE_MEASURED, PositionEstimate.MODE_PROPAGATED)


class EstimatorNode(Node):
    """Selects the winning position estimate and publishes the nav status."""

    def __init__(self) -> None:
        super().__init__("estimator_node")
        self.declare_parameter("publish_rate_hz", 5.0)
        self.declare_parameter("gps_timeout_s", 3.0)
        self.declare_parameter("imu_timeout_s", 1.0)
        rate = float(self.get_parameter("publish_rate_hz").value)
        self._gps_timeout = float(self.get_parameter("gps_timeout_s").value)
        self._imu_timeout = float(self.get_parameter("imu_timeout_s").value)

        # Latest snapshot from each watched source. None until first heard.
        self._gps_last: Optional[PositionEstimate] = None
        self._imu_last_stamp: Optional[Time] = None

        # RELIABLE depth 10, matching the sensor/estimate data topics (CLAUDE.md).
        self.sub_gps = self.create_subscription(
            PositionEstimate, "/navera/estimate/gps", self._on_gps, 10)
        self.sub_imu = self.create_subscription(
            Imu, "/navera/sensors/imu", self._on_imu, 10)

        self.pub_pos = self.create_publisher(PositionEstimate, "/navera/position", 10)
        self.pub_status = self.create_publisher(NavStatus, "/navera/nav_status", 10)

        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f"estimator up (v1 GPS-only): rate={rate:.1f}Hz "
            f"gps_timeout={self._gps_timeout:.1f}s imu_timeout={self._imu_timeout:.1f}s"
        )

    # ---------- inputs (store only; all decisions happen in _tick) ----------

    def _on_gps(self, msg: PositionEstimate) -> None:
        self._gps_last = msg

    def _on_imu(self, msg: Imu) -> None:
        # Liveness only: we keep the stamp, never the sample. The IMU feeds no
        # position in v1.
        self._imu_last_stamp = Time.from_msg(msg.header.stamp)

    # ---------- decision ----------

    def _age_s(self, now: Time, stamp: Time) -> float:
        """Seconds between ``stamp`` and ``now`` (>= 0; clamps future stamps)."""
        dt = (now - stamp).nanoseconds / 1e9
        return dt if dt > 0.0 else 0.0

    def _tick(self) -> None:
        now = self.get_clock().now()

        # --- GPS: liveness and eligibility ---
        gps_alive = False
        gps_eligible = False
        gps_age: Optional[float] = None
        if self._gps_last is not None:
            gps_age = self._age_s(now, Time.from_msg(self._gps_last.header.stamp))
            gps_alive = gps_age < self._gps_timeout
            gps_eligible = (
                gps_alive
                and self._gps_last.valid
                and self._gps_last.mode in _ELIGIBLE_MODES
            )

        # --- IMU: liveness only ---
        imu_alive = (
            self._imu_last_stamp is not None
            and self._age_s(now, self._imu_last_stamp) < self._imu_timeout
        )

        # --- pick a winner + resolve state ---
        ever_heard = self._gps_last is not None or self._imu_last_stamp is not None
        winner: Optional[PositionEstimate] = self._gps_last if gps_eligible else None

        if winner is not None:
            if winner.mode == PositionEstimate.MODE_PROPAGATED:
                state = NavStatus.STATE_DEGRADED
                reason = "GPS solution is dead-reckoned (propagated)"
            else:
                state = NavStatus.STATE_FIX
                reason = "GPS fix"
        elif not ever_heard:
            state = NavStatus.STATE_INITIALIZING
            reason = "waiting for first source message"
        else:
            state = NavStatus.STATE_NO_FIX
            reason = self._no_fix_reason(gps_age)

        self._publish_status(now, state, winner, gps_alive, gps_age, imu_alive, reason)
        if winner is not None:
            self._publish_position(now, winner)

    def _no_fix_reason(self, gps_age: Optional[float]) -> str:
        """Human-readable explanation of why no source is usable."""
        g = self._gps_last
        if g is None:
            return "no GPS estimate received yet"
        if gps_age is not None and gps_age >= self._gps_timeout:
            return f"GPS estimate stale ({gps_age:.1f}s > {self._gps_timeout:.1f}s)"
        if not g.valid:
            return f"GPS not valid ({g.reason})" if g.reason else "GPS not valid"
        if g.mode not in _ELIGIBLE_MODES:
            return f"GPS mode not usable (mode={g.mode})"
        return "no usable source"

    # ---------- outputs ----------

    def _publish_position(self, now: Time, winner: PositionEstimate) -> None:
        """Republish the winning estimate verbatim, re-stamped and re-attributed."""
        out = PositionEstimate()
        out.header.stamp = now.to_msg()          # publication instant of the arbiter
        out.header.frame_id = winner.header.frame_id
        out.latitude = winner.latitude
        out.longitude = winner.longitude
        out.altitude = winner.altitude
        out.position_covariance = winner.position_covariance
        out.position_covariance_type = winner.position_covariance_type
        out.source = winner.source
        out.mode = winner.mode
        out.valid = winner.valid
        out.confidence = winner.confidence
        out.reason = winner.reason
        out.sensor_stamp = winner.sensor_stamp   # keep the true measurement instant
        out.producer = "navera_estimator"        # rewritten: the arbiter emitted this
        out.model_id = winner.model_id
        out.frame_index = winner.frame_index
        out.details_json = winner.details_json
        self.pub_pos.publish(out)

    def _publish_status(
        self,
        now: Time,
        state: int,
        winner: Optional[PositionEstimate],
        gps_alive: bool,
        gps_age: Optional[float],
        imu_alive: bool,
        reason: str,
    ) -> None:
        status = NavStatus()
        status.header.stamp = now.to_msg()
        status.header.frame_id = "navera"
        status.state = state
        if winner is not None:
            status.active_source = winner.source
            status.active_mode = winner.mode
        else:
            status.active_source = NavStatus.SOURCE_UNKNOWN
            status.active_mode = NavStatus.MODE_MEASURED  # only meaningful when source != UNKNOWN
        status.sources = [
            self._gps_health(winner),
            self._imu_health(imu_alive),
        ]
        status.reason = reason
        self.pub_status.publish(status)

    def _gps_health(self, winner: Optional[PositionEstimate]) -> SourceHealth:
        h = SourceHealth()
        h.source = SourceHealth.SOURCE_GPS
        g = self._gps_last
        if g is None:
            h.alive = False
            h.last_seen = Time().to_msg()        # zero = never heard
            h.contributing = False
        else:
            now = self.get_clock().now()
            h.alive = self._age_s(now, Time.from_msg(g.header.stamp)) < self._gps_timeout
            h.last_seen = g.header.stamp
            h.contributing = winner is not None and winner.source == SourceHealth.SOURCE_GPS
        return h

    def _imu_health(self, imu_alive: bool) -> SourceHealth:
        h = SourceHealth()
        h.source = SourceHealth.SOURCE_INERTIAL
        h.alive = imu_alive
        h.last_seen = self._imu_last_stamp.to_msg() if self._imu_last_stamp else Time().to_msg()
        h.contributing = False                   # IMU feeds no position in v1
        return h


def main(args=None) -> None:
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    Mirrors the sensor nodes: rclpy installs its own signal handlers and closes
    the context, so spin() returns already shut down — hence the rclpy.ok()
    guard before rclpy.shutdown() to avoid a spurious RCLError.
    """
    die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
    rclpy.init(args=args)
    node = EstimatorNode()
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

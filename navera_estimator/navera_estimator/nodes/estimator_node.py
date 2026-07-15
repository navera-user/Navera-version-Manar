#!/usr/bin/env python3
"""
estimator_node.py — NAVERA position arbiter (v2: GPS > day).

This is the node that answers the operator's one question: *do we have a usable
position right now, and who is providing it?* It consumes the typed per-source
contract (navera_msgs/PositionEstimate) and publishes the two authoritative
outputs:
    /navera/position    navera_msgs/PositionEstimate  — the WINNING estimate,
                        republished verbatim with producer rewritten. Emitted
                        ONLY when a source is contributing; never a held point.
    /navera/nav_status  navera_msgs/NavStatus         — the decisional summary
                        (state + who is alive), published every tick.

Scope: honest single-winner arbitration across the LIVE sources.
  * Subscribes to /navera/estimate/gps and /navera/estimate/day.
    Priority GPS > day (CLAUDE.md §3: first reliable source wins).
  * Subscribes to /navera/sensors/imu for LIVENESS ONLY. The IMU reports
    alive=true / contributing=false — zero invented position, zero covariance.
  * Eligibility: valid==true AND mode in {MEASURED, PROPAGATED} AND fresh
    (header age < <source>_timeout_s). Generic — no per-source special-casing;
    the arbiter has NO knowledge of any source's quirks, it applies one rule.
  * No hysteresis / dwell / jump-guard yet — with GPS-invalid + day there is
    still only ONE contributor at a time, so nothing to ping-pong. Those land
    with the values measured under real concurrency.

State machine:
  INITIALIZING  no watched message has EVER arrived (transient, since boot).
  NO_FIX        running, but no source is currently usable. First-class.
  FIX           a fresh MEASURED solution whose uncertainty is BOUNDED
                (covariance_type != UNKNOWN) — e.g. GPS today.
  DEGRADED      a position is published but trust is reduced: a MEASURED fix
                with UNKNOWN uncertainty (e.g. day vision today), OR a
                PROPAGATED/HELD solution. See NavStatus.msg and _classify().

Parameters:
    publish_rate_hz (default 5.0) — decision + nav_status cadence
    gps_timeout_s   (default 3.0) — GPS freshness/liveness window
    day_timeout_s   (default 3.0) — day freshness/liveness window
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

# Human-readable names for reason strings only (never parsed downstream).
_SOURCE_NAME = {
    PositionEstimate.SOURCE_GPS: "GPS",
    PositionEstimate.SOURCE_DAY_VISION: "day vision",
    PositionEstimate.SOURCE_NIGHT_VISION: "night vision",
    PositionEstimate.SOURCE_CELESTIAL: "celestial",
    PositionEstimate.SOURCE_INERTIAL: "inertial",
}
_MODE_NAME = {
    PositionEstimate.MODE_MEASURED: "measured",
    PositionEstimate.MODE_PROPAGATED: "propagated",
    PositionEstimate.MODE_HELD: "held",
    PositionEstimate.MODE_REPLAYED: "replayed",
}


class EstimatorNode(Node):
    """Selects the winning position estimate and publishes the nav status."""

    def __init__(self) -> None:
        super().__init__("estimator_node")
        self.declare_parameter("publish_rate_hz", 5.0)
        self.declare_parameter("gps_timeout_s", 3.0)
        self.declare_parameter("day_timeout_s", 3.0)
        self.declare_parameter("imu_timeout_s", 1.0)
        rate = float(self.get_parameter("publish_rate_hz").value)
        self._gps_timeout = float(self.get_parameter("gps_timeout_s").value)
        self._day_timeout = float(self.get_parameter("day_timeout_s").value)
        self._imu_timeout = float(self.get_parameter("imu_timeout_s").value)

        # Latest snapshot from each watched source. None until first heard.
        self._gps_last: Optional[PositionEstimate] = None
        self._day_last: Optional[PositionEstimate] = None
        self._imu_last_stamp: Optional[Time] = None

        # RELIABLE depth 10, matching the sensor/estimate data topics (CLAUDE.md).
        self.sub_gps = self.create_subscription(
            PositionEstimate, "/navera/estimate/gps", self._on_gps, 10)
        self.sub_day = self.create_subscription(
            PositionEstimate, "/navera/estimate/day", self._on_day, 10)
        self.sub_imu = self.create_subscription(
            Imu, "/navera/sensors/imu", self._on_imu, 10)

        self.pub_pos = self.create_publisher(PositionEstimate, "/navera/position", 10)
        self.pub_status = self.create_publisher(NavStatus, "/navera/nav_status", 10)

        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f"estimator up (v2 GPS>day): rate={rate:.1f}Hz "
            f"gps_timeout={self._gps_timeout:.1f}s day_timeout={self._day_timeout:.1f}s "
            f"imu_timeout={self._imu_timeout:.1f}s"
        )

    # ---------- inputs (store only; all decisions happen in _tick) ----------

    def _on_gps(self, msg: PositionEstimate) -> None:
        self._gps_last = msg

    def _on_day(self, msg: PositionEstimate) -> None:
        self._day_last = msg

    def _on_imu(self, msg: Imu) -> None:
        # Liveness only: we keep the stamp, never the sample. The IMU feeds no
        # position in v1.
        self._imu_last_stamp = Time.from_msg(msg.header.stamp)

    # ---------- decision ----------

    def _age_s(self, now: Time, stamp: Time) -> float:
        """Seconds between ``stamp`` and ``now`` (>= 0; clamps future stamps)."""
        dt = (now - stamp).nanoseconds / 1e9
        return dt if dt > 0.0 else 0.0

    def _eval_source(self, now, last, timeout):
        """(alive, eligible, age) for a stored PositionEstimate, or (F, F, None).

        Generic — applied identically to GPS, day and every future source. The
        arbiter never special-cases a source: eligibility is one rule for all.
        """
        if last is None:
            return False, False, None
        age = self._age_s(now, Time.from_msg(last.header.stamp))
        alive = age < timeout
        eligible = alive and last.valid and last.mode in _ELIGIBLE_MODES
        return alive, eligible, age

    def _classify(self, winner):
        """State + reason for the winning source. See NavStatus.msg for semantics.

        FIX = a fresh MEASURED fix whose uncertainty is BOUNDED (covariance
        known). DEGRADED = published but reduced trust: MEASURED-but-unbounded,
        or PROPAGATED/HELD. FIX answers the operator's real question ("can I
        rely on this, error included?"), not "which algorithm ran" — a ~500 m
        unvalidated vision guess must not wear the same green label as a metric
        GPS lock.

        This rule is SELF-CORRECTING in the right direction: the day the step-6
        sigma work turns the day pipeline's MEASURED frames into a validated
        APPROXIMATED covariance, day is promoted to FIX automatically, with ZERO
        code change here. Promotion becomes the REWARD for doing the honest
        measurement — a structural incentive to measure trust, never to decree
        it. 'Single source' is intentionally NOT a DEGRADED trigger (it would
        make FIX unreachable while exactly one source contributes; see .msg).
        """
        name = _SOURCE_NAME.get(winner.source, "source")
        bounded = winner.position_covariance_type != PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        if winner.mode == PositionEstimate.MODE_MEASURED and bounded:
            return NavStatus.STATE_FIX, f"{name} fix"
        if winner.mode == PositionEstimate.MODE_MEASURED:
            return NavStatus.STATE_DEGRADED, f"{name} fix, uncertainty unknown"
        return NavStatus.STATE_DEGRADED, f"{name} solution is propagated (dead-reckoned)"

    def _tick(self) -> None:
        now = self.get_clock().now()

        gps_alive, gps_eligible, gps_age = self._eval_source(
            now, self._gps_last, self._gps_timeout)
        day_alive, day_eligible, day_age = self._eval_source(
            now, self._day_last, self._day_timeout)

        # --- IMU: liveness only ---
        imu_alive = (
            self._imu_last_stamp is not None
            and self._age_s(now, self._imu_last_stamp) < self._imu_timeout
        )

        # --- pick a winner + resolve state ---
        ever_heard = any(x is not None for x in
                         (self._gps_last, self._day_last, self._imu_last_stamp))
        # Priority GPS > day (CLAUDE.md §3). Exactly one winner, or none.
        if gps_eligible:
            winner: Optional[PositionEstimate] = self._gps_last
        elif day_eligible:
            winner = self._day_last
        else:
            winner = None

        if winner is not None:
            state, reason = self._classify(winner)
        elif not ever_heard:
            state = NavStatus.STATE_INITIALIZING
            reason = "waiting for first source message"
        else:
            state = NavStatus.STATE_NO_FIX
            reason = self._no_fix_reason(gps_age, day_age)

        self._publish_status(now, state, winner, imu_alive, reason)
        if winner is not None:
            self._publish_position(now, winner)

    def _no_fix_reason(self, gps_age, day_age) -> str:
        """Why no source is usable — one clause per watched estimate source."""
        parts = [
            self._source_reason("GPS", self._gps_last, gps_age, self._gps_timeout),
            self._source_reason("day", self._day_last, day_age, self._day_timeout),
        ]
        return "; ".join(p for p in parts if p) or "no usable source"

    def _source_reason(self, name, last, age, timeout) -> str:
        """One clause explaining why `last` is not contributing (empty if it is)."""
        if last is None:
            return f"{name}: none received"
        if age is not None and age >= timeout:
            return f"{name}: stale ({age:.1f}s>{timeout:.1f}s)"
        if not last.valid:
            return f"{name}: invalid ({last.reason})" if last.reason else f"{name}: invalid"
        if last.mode not in _ELIGIBLE_MODES:
            return f"{name}: {_MODE_NAME.get(last.mode, last.mode)} not usable"
        return ""

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
            self._estimate_health(SourceHealth.SOURCE_GPS, self._gps_last,
                                  self._gps_timeout, winner),
            self._estimate_health(SourceHealth.SOURCE_DAY_VISION, self._day_last,
                                  self._day_timeout, winner),
            self._imu_health(imu_alive),
        ]
        status.reason = reason
        self.pub_status.publish(status)

    def _estimate_health(self, source_const, last, timeout, winner) -> SourceHealth:
        """Liveness row for a PositionEstimate source (GPS, day, ... — generic)."""
        h = SourceHealth()
        h.source = source_const
        if last is None:
            h.alive = False
            h.last_seen = Time().to_msg()        # zero = never heard
            h.contributing = False
        else:
            now = self.get_clock().now()
            h.alive = self._age_s(now, Time.from_msg(last.header.stamp)) < timeout
            h.last_seen = last.header.stamp
            h.contributing = winner is not None and winner.source == source_const
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

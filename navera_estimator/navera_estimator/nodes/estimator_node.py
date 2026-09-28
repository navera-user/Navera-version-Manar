#!/usr/bin/env python3
"""
estimator_node.py — NAVERA position arbiter (v3: GPS > day > night > cn).

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
  * Subscribes to /navera/estimate/{gps,day,night,cn}.
    Priority GPS > day > night > cn (CLAUDE.md §3: first reliable source wins).
  * Subscribes to /navera/sensors/imu for LIVENESS ONLY. The IMU reports
    alive=true / contributing=false — zero invented position, zero covariance.
  * Eligibility: valid==true AND mode in {MEASURED, PROPAGATED} AND fresh
    (0 <= header age < <source>_timeout_s, a stamp more than
    future_tolerance_s ahead of the clock is refused) AND a finite, in-range
    position with a finite covariance. Generic — no per-source special-casing;
    the arbiter has NO knowledge of any source's quirks, it applies one rule.
  * Switch hold-off: while the active source stays eligible, a higher-priority
    source must have been continuously eligible for switch_holdoff_s before it
    takes over (a flapping GPS must not zig-zag the output between GPS and a
    ~500 m vision fix). Losing the active source switches immediately.
  * GPS kinematic plausibility gate (anti-jump / anti-spoofing): a GPS fix
    farther from the last trusted GPS fix than the vehicle could have
    travelled (max_speed_mps x elapsed + gps_jump_margin_m) is refused, and
    GPS stays refused until its claimed position becomes reachable again.
    This catches sudden jumps (a spoofer taking over, receiver glitches). It
    cannot detect a slow, gradual spoof: that needs an independent position
    source to compare with.
  * /navera/position carries each winning MEASUREMENT once: a new message is
    published only when the winner changes or sends a new estimate, never the
    same estimate re-stamped at every tick (a filter downstream would fuse it
    many times over).

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
    gps_timeout_s   (default 3.0)  — GPS freshness/liveness window
    day_timeout_s   (default 3.0)  — day freshness/liveness window
    night_timeout_s (default 5.0)  — night freshness/liveness window
    cn_timeout_s    (default 45.0) — celestial window (a solve takes ~15 s and
                     fixes are sparse; value is a starting point, to be MEASURED
                     under real cadence, not decreed — same rule as hysteresis)
    imu_timeout_s   (default 1.0)  — IMU liveness window
    future_tolerance_s (default 0.5) — clock skew tolerated on header stamps
    switch_holdoff_s   (default 2.0) — dwell before a recovering higher-priority
                     source pre-empts the active one
    max_speed_mps      (default 100.0) — fastest the vehicle can move (set per vehicle)
    fix_max_sigma_m    (default 25.0) — largest horizontal sigma still reported as FIX
    gps_jump_margin_m  (default 50.0) — GPS noise allowance in the plausibility gate
"""
import math
from typing import Optional

import rclpy
from navera_common.geo import is_finite_latlon
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import Imu

from navera_msgs.msg import NavStatus, PositionEstimate, SourceHealth

def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))


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
        self.declare_parameter("night_timeout_s", 5.0)
        self.declare_parameter("cn_timeout_s", 45.0)
        self.declare_parameter("imu_timeout_s", 1.0)
        self.declare_parameter("future_tolerance_s", 0.5)
        self.declare_parameter("switch_holdoff_s", 2.0)
        self.declare_parameter("max_speed_mps", 100.0)
        self.declare_parameter("gps_jump_margin_m", 50.0)
        # FIX also requires the stated horizontal sigma to be at most this.
        self.declare_parameter("fix_max_sigma_m", 25.0)
        rate = float(self.get_parameter("publish_rate_hz").value)
        if rate <= 0.0:
            raise ValueError(f"publish_rate_hz must be > 0 (got {rate})")
        self._future_tol = float(self.get_parameter("future_tolerance_s").value)
        self._holdoff = float(self.get_parameter("switch_holdoff_s").value)
        self._max_speed = float(self.get_parameter("max_speed_mps").value)
        self._jump_margin = float(self.get_parameter("gps_jump_margin_m").value)
        self._fix_max_sigma = float(self.get_parameter("fix_max_sigma_m").value)
        # Last GPS fix that passed the plausibility gate: (lat, lon, Time).
        self._gps_trusted = None
        self._gps_suspect: Optional[str] = None   # reason while GPS is refused
        # Hold-off / de-duplication state
        self._active_source: Optional[int] = None
        self._eligible_since = {}                 # source const -> Time
        self._last_published_key = None
        self._gps_timeout = float(self.get_parameter("gps_timeout_s").value)
        self._day_timeout = float(self.get_parameter("day_timeout_s").value)
        self._night_timeout = float(self.get_parameter("night_timeout_s").value)
        self._cn_timeout = float(self.get_parameter("cn_timeout_s").value)
        self._imu_timeout = float(self.get_parameter("imu_timeout_s").value)

        # Latest snapshot from each watched source. None until first heard.
        self._gps_last: Optional[PositionEstimate] = None
        self._day_last: Optional[PositionEstimate] = None
        self._night_last: Optional[PositionEstimate] = None
        self._cn_last: Optional[PositionEstimate] = None
        self._imu_last_stamp: Optional[Time] = None

        # RELIABLE depth 10, matching the sensor/estimate data topics (CLAUDE.md).
        self.sub_gps = self.create_subscription(
            PositionEstimate, "/navera/estimate/gps", self._on_gps, 10)
        self.sub_day = self.create_subscription(
            PositionEstimate, "/navera/estimate/day", self._on_day, 10)
        self.sub_night = self.create_subscription(
            PositionEstimate, "/navera/estimate/night", self._on_night, 10)
        self.sub_cn = self.create_subscription(
            PositionEstimate, "/navera/estimate/cn", self._on_cn, 10)
        self.sub_imu = self.create_subscription(
            Imu, "/navera/sensors/imu", self._on_imu, 10)

        self.pub_pos = self.create_publisher(PositionEstimate, "/navera/position", 10)
        self.pub_status = self.create_publisher(NavStatus, "/navera/nav_status", 10)

        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f"estimator up (v3 GPS>day>night>cn): rate={rate:.1f}Hz "
            f"gps_timeout={self._gps_timeout:.1f}s day_timeout={self._day_timeout:.1f}s "
            f"night_timeout={self._night_timeout:.1f}s cn_timeout={self._cn_timeout:.1f}s "
            f"imu_timeout={self._imu_timeout:.1f}s"
        )

    # ---------- inputs (store only; all decisions happen in _tick) ----------

    def _on_gps(self, msg: PositionEstimate) -> None:
        self._gps_last = msg
        self._check_gps_plausibility(msg)

    def _check_gps_plausibility(self, msg: PositionEstimate) -> None:
        """Kinematic gate: refuse a GPS fix the vehicle cannot have reached."""
        if not (msg.valid and msg.mode == PositionEstimate.MODE_MEASURED and self._sane(msg)):
            return                                  # invalid fixes are handled by eligibility
        stamp = Time.from_msg(msg.header.stamp)
        if self._gps_trusted is None:
            self._gps_trusted = (msg.latitude, msg.longitude, stamp)
            return
        lat0, lon0, t0 = self._gps_trusted
        dt = max(0.0, (stamp - t0).nanoseconds / 1e9)
        dist = _haversine_m(lat0, lon0, msg.latitude, msg.longitude)
        reachable = self._max_speed * dt + self._jump_margin
        if dist <= reachable:
            if self._gps_suspect:
                self.get_logger().warn("GPS plausible again — re-accepted")
            self._gps_suspect = None
            self._gps_trusted = (msg.latitude, msg.longitude, stamp)
        else:
            reason = (f"implausible jump {dist:.0f} m in {dt:.1f} s "
                      f"(max {reachable:.0f} m at {self._max_speed:.0f} m/s) — possible spoofing")
            if self._gps_suspect is None:
                self.get_logger().error(f"GPS refused: {reason}")
            self._gps_suspect = reason

    def _on_day(self, msg: PositionEstimate) -> None:
        self._day_last = msg

    def _on_night(self, msg: PositionEstimate) -> None:
        self._night_last = msg

    def _on_cn(self, msg: PositionEstimate) -> None:
        self._cn_last = msg

    def _on_imu(self, msg: Imu) -> None:
        # Liveness only: we keep the stamp, never the sample. The IMU feeds no
        # position in v1.
        self._imu_last_stamp = Time.from_msg(msg.header.stamp)

    # ---------- decision ----------

    def _age_s(self, now: Time, stamp: Time) -> float:
        """Seconds from ``stamp`` to ``now``. Negative = stamp in the future."""
        return (now - stamp).nanoseconds / 1e9

    @staticmethod
    def _measured_at(msg: PositionEstimate) -> Time:
        """Instant of the measurement (sensor_stamp), or the publication stamp
        for a producer that does not fill it. Freshness is judged on this: a
        fix computed slowly from an old image is as old as the image."""
        s = msg.sensor_stamp
        return Time.from_msg(s if (s.sec or s.nanosec) else msg.header.stamp)

    @staticmethod
    def _sane(msg: PositionEstimate) -> bool:
        """A usable position: finite and in range, finite non-negative variances."""
        if not is_finite_latlon(msg.latitude, msg.longitude):
            return False
        cov = list(msg.position_covariance)
        if not all(math.isfinite(c) for c in cov):
            return False
        return all(cov[i] >= 0.0 for i in (0, 4, 8))

    def _eval_source(self, now, last, timeout):
        """(alive, eligible, age) for a stored PositionEstimate, or (F, F, None).

        Generic — applied identically to GPS, day and every future source. The
        arbiter never special-cases a source: eligibility is one rule for all.
        A stamp from the future (clock stepped back, other clock domain) makes
        the source neither alive nor eligible: its age cannot be trusted.
        """
        if last is None:
            return False, False, None
        age = self._age_s(now, self._measured_at(last))
        alive = -self._future_tol <= age < timeout
        eligible = (alive and last.valid and last.mode in _ELIGIBLE_MODES
                    and self._sane(last))
        return alive, eligible, age

    def _select(self, now: Time, candidates):
        """Winner among [(source, eligible, msg)] in priority order, with hold-off."""
        for src, eligible, _ in candidates:
            if eligible:
                self._eligible_since.setdefault(src, now)
            else:
                self._eligible_since.pop(src, None)
        eligible = [(src, msg) for src, ok, msg in candidates if ok]
        if not eligible:
            self._active_source = None
            return None
        best_src, best_msg = eligible[0]
        active = next(((s, m) for s, m in eligible if s == self._active_source), None)
        if active is not None and best_src != self._active_source:
            dwell = (now - self._eligible_since[best_src]).nanoseconds / 1e9
            if dwell < self._holdoff:
                return active[1]                  # keep the active source for now
        self._active_source = best_src
        return best_msg

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
        sigma = math.sqrt(max(winner.position_covariance[0], winner.position_covariance[4]))
        if winner.mode == PositionEstimate.MODE_MEASURED and bounded and sigma > self._fix_max_sigma:
            return (NavStatus.STATE_DEGRADED,
                    f"{name} fix, uncertainty {sigma:.0f} m > {self._fix_max_sigma:.0f} m")
        if winner.mode == PositionEstimate.MODE_MEASURED and bounded:
            return NavStatus.STATE_FIX, f"{name} fix"
        if winner.mode == PositionEstimate.MODE_MEASURED:
            return NavStatus.STATE_DEGRADED, f"{name} fix, uncertainty unknown"
        return NavStatus.STATE_DEGRADED, f"{name} solution is propagated (dead-reckoned)"

    def _tick(self) -> None:
        now = self.get_clock().now()

        gps_alive, gps_eligible, gps_age = self._eval_source(
            now, self._gps_last, self._gps_timeout)
        gps_eligible = gps_eligible and self._gps_suspect is None
        day_alive, day_eligible, day_age = self._eval_source(
            now, self._day_last, self._day_timeout)
        night_alive, night_eligible, night_age = self._eval_source(
            now, self._night_last, self._night_timeout)
        cn_alive, cn_eligible, cn_age = self._eval_source(
            now, self._cn_last, self._cn_timeout)

        # --- IMU: liveness only ---
        imu_alive = (
            self._imu_last_stamp is not None
            and -self._future_tol <= self._age_s(now, self._imu_last_stamp) < self._imu_timeout
        )

        # --- pick a winner + resolve state ---
        ever_heard = any(x is not None for x in
                         (self._gps_last, self._day_last, self._night_last,
                          self._cn_last, self._imu_last_stamp))
        # Priority GPS > day > night > cn (CLAUDE.md §3). Exactly one winner, or none.
        winner: Optional[PositionEstimate] = self._select(now, [
            (PositionEstimate.SOURCE_GPS, gps_eligible, self._gps_last),
            (PositionEstimate.SOURCE_DAY_VISION, day_eligible, self._day_last),
            (PositionEstimate.SOURCE_NIGHT_VISION, night_eligible, self._night_last),
            (PositionEstimate.SOURCE_CELESTIAL, cn_eligible, self._cn_last),
        ])

        if winner is not None:
            state, reason = self._classify(winner)
        elif not ever_heard:
            state = NavStatus.STATE_INITIALIZING
            reason = "waiting for first source message"
        else:
            state = NavStatus.STATE_NO_FIX
            reason = self._no_fix_reason(gps_age, day_age, night_age, cn_age)

        self._publish_status(now, state, winner, imu_alive, reason)
        if winner is not None:
            key = (winner.source, winner.header.stamp.sec, winner.header.stamp.nanosec)
            if key != self._last_published_key:
                self._last_published_key = key
                self._publish_position(now, winner)

    def _no_fix_reason(self, gps_age, day_age, night_age, cn_age) -> str:
        """Why no source is usable — one clause per watched estimate source."""
        parts = [
            (f"GPS: {self._gps_suspect}" if self._gps_suspect else
             self._source_reason("GPS", self._gps_last, gps_age, self._gps_timeout)),
            self._source_reason("day", self._day_last, day_age, self._day_timeout),
            self._source_reason("night", self._night_last, night_age, self._night_timeout),
            self._source_reason("cn", self._cn_last, cn_age, self._cn_timeout),
        ]
        return "; ".join(p for p in parts if p) or "no usable source"

    def _source_reason(self, name, last, age, timeout) -> str:
        """One clause explaining why `last` is not contributing (empty if it is)."""
        if last is None:
            return f"{name}: none received"
        if age is not None and age < -self._future_tol:
            return f"{name}: timestamp {-age:.1f}s in the future (clock problem)"
        if age is not None and age >= timeout:
            return f"{name}: stale ({age:.1f}s>{timeout:.1f}s)"
        if not last.valid:
            return f"{name}: invalid ({last.reason})" if last.reason else f"{name}: invalid"
        if last.mode not in _ELIGIBLE_MODES:
            return f"{name}: {_MODE_NAME.get(last.mode, last.mode)} not usable"
        if not self._sane(last):
            return f"{name}: non-finite position or covariance"
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
            self._estimate_health(SourceHealth.SOURCE_NIGHT_VISION, self._night_last,
                                  self._night_timeout, winner),
            self._estimate_health(SourceHealth.SOURCE_CELESTIAL, self._cn_last,
                                  self._cn_timeout, winner),
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
            h.alive = -self._future_tol <= self._age_s(now, self._measured_at(last)) < timeout
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

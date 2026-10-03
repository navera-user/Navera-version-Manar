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
    While GPS is refused, "reachable again" alone would let a patient spoofer
    in: the reachable radius grows with time, so any fixed offset becomes
    "reachable" after offset / max_speed_mps seconds (found in the mission
    simulator: a 2 km spoof accepted after 33 s, then the true GPS locked
    out). So while refused, GPS is re-accepted only when it AGREES with an
    independent, fresh source of stated accuracy (vision / celestial with a
    known covariance): within gps_crosscheck_sigmas x its sigma +
    gps_jump_margin_m + max_speed_mps x the time between the two. Only when
    no such source exists does it fall back to reachability (a known,
    documented weakness while vision accuracy is not validated).
    The same cross-check applies when GPS RETURNS after an outage (no trusted
    fix within gps_timeout_s): "jam, then spoof" is the classic attack, and
    after a long outage almost any position is reachable.
    Slow spoofing: while GPS is trusted, it is also compared with that
    independent source at every fix; disagreeing beyond the tolerance for
    gps_crosscheck_persist_s refuses it ("drifting away"). This needs a source
    with a stated accuracy — with vision of unknown accuracy a gradual spoof
    is still not detected.
  * Decisions are taken when an estimate arrives (no added latency, no
    measurement skipped when two arrive between ticks) and every
    1/publish_rate_hz to notice sources going silent.
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
    gps_crosscheck_sigmas (default 5.0) — agreement needed with an independent
                     source (in its sigmas) to re-accept a refused GPS
    gps_crosscheck_persist_s (default 3.0) — a trusted GPS that keeps disagreeing
                     with that source this long is refused (gradual spoofing)
"""
import copy
import math
from collections import deque
from typing import Optional

import rclpy
from navera_common.geo import is_finite_latlon
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from navera_common.qos import SENSOR_QOS
from rclpy.duration import Duration
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


# a GPS in doubt (vision disagrees) gets an accuracy no better than the gap, up to this
# gap; beyond it a wrong vision match is more likely than a spoofer this patient
DOUBT_MAX_M = 500.0
# a stated horizontal accuracy below this is not one (0 = "not filled"); RTK is ~1 cm
MIN_STATED_SIGMA_M = 0.01
# distinct independent fixes in a row beyond 3 sigma that refuse GPS (chance: < 1e-12)
STREAK_N = 5

class EstimatorNode(Node):
    """Selects the winning position estimate and publishes the nav status."""

    def __init__(self) -> None:
        super().__init__("estimator_node")
        declare_float(self, "publish_rate_hz", 5.0)
        declare_float(self, "gps_timeout_s", 3.0)
        declare_float(self, "day_timeout_s", 3.0)
        declare_float(self, "night_timeout_s", 5.0)
        declare_float(self, "cn_timeout_s", 45.0)
        declare_float(self, "imu_timeout_s", 1.0)
        declare_float(self, "future_tolerance_s", 0.5)
        declare_float(self, "switch_holdoff_s", 2.0)
        declare_float(self, "max_speed_mps", 100.0)
        declare_float(self, "gps_jump_margin_m", 50.0)
        # the attitude NAVERA uses (box, vehicle or ROS IMU): liveness only
        self.declare_parameter("imu_topic", "/navera/sensors/imu")
        declare_float(self, "gps_crosscheck_sigmas", 5.0)
        declare_float(self, "gps_crosscheck_persist_s", 3.0)
        # FIX also requires the stated horizontal sigma to be at most this.
        declare_float(self, "fix_max_sigma_m", 25.0)
        rate = float(self.get_parameter("publish_rate_hz").value)
        if rate <= 0.0:
            raise ValueError(f"publish_rate_hz must be > 0 (got {rate})")
        self._future_tol = float(self.get_parameter("future_tolerance_s").value)
        self._holdoff = float(self.get_parameter("switch_holdoff_s").value)
        self._max_speed = float(self.get_parameter("max_speed_mps").value)
        self._jump_margin = float(self.get_parameter("gps_jump_margin_m").value)
        self._crosscheck_sigmas = float(self.get_parameter("gps_crosscheck_sigmas").value)
        self._crosscheck_persist = float(self.get_parameter("gps_crosscheck_persist_s").value)
        self._disagree_since: Optional[Time] = None   # trusted GPS vs independent source
        self._disagree_refs = set()                    # distinct independent fixes disagreeing
        self._confirm_needed_since: Optional[Time] = None  # refused by the cross-check
        self._last_ref_at = Time(seconds=0, clock_type=self.get_clock().clock_type)
        self._gps_hist = deque(maxlen=50)              # (stamp ns, lat, lon) of received GPS fixes
        self._streak = set()                           # distinct fixes beyond 3 sigma in a row
        self._gps_doubt = None                         # (gap m, source) while GPS is in doubt
        self._agree_refs = set()                       # distinct fixes agreeing (re-acceptance)
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
            Imu, str(self.get_parameter("imu_topic").value), self._on_imu, SENSOR_QOS)

        self.pub_pos = self.create_publisher(PositionEstimate, "/navera/position", 10)
        self.pub_status = self.create_publisher(NavStatus, "/navera/nav_status", 10)

        self.create_timer(1.0 / rate, self._tick)
        # Exactly one arbiter may speak on a ROS network: a second one (another
        # box on the same domain, a leftover test or demo) interleaves two
        # decisions on /navera/position. Checked every 5 s, reported loudly.
        self._rival_reported = False
        self.create_timer(5.0, self._check_single_arbiter)
        self.get_logger().info(
            f"estimator up (v3 GPS>day>night>cn): rate={rate:.1f}Hz "
            f"gps_timeout={self._gps_timeout:.1f}s day_timeout={self._day_timeout:.1f}s "
            f"night_timeout={self._night_timeout:.1f}s cn_timeout={self._cn_timeout:.1f}s "
            f"imu_timeout={self._imu_timeout:.1f}s"
        )

    # ---------- inputs (store only; all decisions happen in _tick) ----------

    def _on_gps(self, msg: PositionEstimate) -> None:
        # a fix stamped before the newest one received (link buffering, DDS reordering) is
        # old news: dropped — scored against the newer trusted fix with dt clamped to 0 it
        # looked like a jump ("possible spoofing") and refused a good GPS
        last = Time.from_msg(self._gps_last.header.stamp) if self._gps_last is not None else None
        if last is not None and Time.from_msg(msg.header.stamp) < last and \
                last <= self.get_clock().now() + Duration(seconds=0.5):   # a future stamp sets no order
            self.get_logger().info("GPS fix older than the last one received: dropped",
                                   throttle_duration_sec=10.0)
            return
        self._gps_last = msg
        if msg.valid and self._sane(msg):
            self._gps_hist.append((Time.from_msg(msg.header.stamp).nanoseconds, msg.latitude, msg.longitude))
        self._check_gps_plausibility(msg)
        self._tick()

    def _check_gps_plausibility(self, msg: PositionEstimate) -> None:
        """Kinematic gate: refuse a GPS fix the vehicle cannot have reached."""
        if not (msg.valid and msg.mode == PositionEstimate.MODE_MEASURED and self._sane(msg)):
            return                                  # invalid fixes are handled by eligibility
        stamp = Time.from_msg(msg.header.stamp)
        continuous = (self._gps_trusted is not None and self._gps_suspect is None
                      and (stamp - self._gps_trusted[2]).nanoseconds / 1e9 <= self._gps_timeout)
        if not continuous:
            ref = self._independent_reference(stamp, msg.latitude, msg.longitude)
            if ref is not None:
                name, d, tol, ref_stamp, tol_strict = ref
                # back only when it agrees within 3 sigma with two distinct independent
                # fixes: the 5-sigma window would "confirm" a GPS refused moments ago
                self._agree_refs = self._agree_refs | {ref_stamp} if d <= tol_strict else set()
                if len(self._agree_refs) >= 2:
                    self.get_logger().warn(
                        f"GPS confirmed by {name} ({d:.0f} m apart, 3 sigma {tol_strict:.0f} m, "
                        f"2 fixes) — re-accepted")
                    self._agree_refs = set()
                    self._confirm_needed_since = None
                    self._gps_suspect = None
                    self._gps_trusted = (msg.latitude, msg.longitude, stamp)
                elif d > tol_strict:
                    if self._gps_suspect is None:
                        self.get_logger().error(
                            f"GPS refused: {d:.0f} m from {name} (3 sigma {tol_strict:.0f} m)")
                    self._gps_suspect = (f"GPS {d:.0f} m from {name} (3 sigma {tol_strict:.0f} m) "
                                         f"— possible spoofing")
                return
            if self._confirm_needed_since is not None:
                # caught drifting by an independent source: comparing GPS with its own last
                # (already spoofed) position proves nothing — only an independent fix clears
                # it, or 120 s without any (the source itself may have been the wrong one)
                if (stamp - max(self._confirm_needed_since, self._last_ref_at)).nanoseconds / 1e9 < 120.0:
                    return
                self.get_logger().warn("no independent source for 120 s: GPS judged on its own again")
                self._confirm_needed_since = None
        if self._gps_trusted is None:
            self._gps_trusted = (msg.latitude, msg.longitude, stamp)
            return
        if continuous and self._drifting_away(msg, stamp):
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

    def _drifting_away(self, msg: PositionEstimate, stamp: Time) -> bool:
        """Trusted GPS vs an independent source of stated accuracy: True (and
        GPS refused) once they have disagreed for gps_crosscheck_persist_s."""
        ref = self._independent_reference(stamp, msg.latitude, msg.longitude)
        if ref is None:
            # between two independent fixes (vision checks every few seconds) the
            # disagreement is kept: forgotten only when a fix agrees, or after 10 s
            if self._disagree_since is not None and \
                    (stamp - self._disagree_since).nanoseconds / 1e9 > 10.0 + self._crosscheck_persist:
                self._disagree_since, self._disagree_refs = None, set()
            return False
        name, d, tol, ref_stamp, tol_strict = ref
        # slow drift: the same independent source disagreeing beyond 3 sigma at
        # STREAK_N distinct measurements in a row does not happen by chance — caught
        # before the 5-sigma gate, while the autopilot has followed the GPS less far
        if d > tol_strict:
            self._streak.add(ref_stamp)
        else:
            self._streak = set()
        # two independent fixes in a row beyond 3 sigma: GPS is in doubt — still used, but
        # with an accuracy no better than the gap (the operator sees it, the autopilot
        # weighs it less, and a later switch to vision is no jump outside its accuracy).
        # A gap over DOUBT_MAX_M is more likely a wrong vision match: not applied.
        self._gps_doubt = (d, name) if len(self._streak) >= 2 and d <= DOUBT_MAX_M else None
        if len(self._streak) >= STREAK_N:
            self._refuse(stamp, f"GPS drifting away from {name}: {STREAK_N} independent fixes in a row "
                                f"beyond 3 sigma ({d:.0f} m apart now, 3 sigma {tol_strict:.0f} m) — possible spoofing")
            return True
        if d <= tol:
            self._disagree_since = None
            self._disagree_refs = set()
            return False
        if self._disagree_since is None:
            self._disagree_since = stamp
        self._disagree_refs.add(ref_stamp)
        # one wrong vision fix stays "fresh" for seconds: never refuse GPS on a single
        # measurement — at least two distinct ones must disagree
        if (stamp - self._disagree_since).nanoseconds / 1e9 < self._crosscheck_persist \
                or len(self._disagree_refs) < 2:
            return False
        self._refuse(stamp, f"GPS drifting away from {name}: {d:.0f} m apart for "
                            f"{self._crosscheck_persist:.0f} s (tolerance {tol:.0f} m) — possible spoofing")
        return True

    def _refuse(self, stamp: Time, reason: str) -> None:
        """GPS refused by the cross-check: only an independent fix can clear it."""
        self._gps_suspect = reason
        self._disagree_since = None
        self._disagree_refs = set()
        self._streak = set()
        self._gps_doubt = None
        self._confirm_needed_since = stamp
        self.get_logger().error(f"GPS refused: {reason}")

    def _gps_near(self, t_ns: int, max_dt_s: float = 0.3):
        """(lat, lon, |dt| s) of the received GPS fix closest to t_ns, if within max_dt_s."""
        best = None
        for ts, lat, lon in self._gps_hist:
            dt = abs(ts - t_ns) / 1e9
            if dt <= max_dt_s and (best is None or dt < best[2]):
                best = (lat, lon, dt)
        return best

    def _independent_reference(self, gps_stamp: Time, gps_lat: float, gps_lon: float):
        """(name, distance_m, tolerance_m, ref_stamp_ns) between the most accurate fresh
        non-GPS source with a STATED accuracy and GPS, or None. A source of unknown
        accuracy cannot vouch for or against GPS. A vision fix describes the instant
        its photo was taken (0.5-1.5 s ago): it is compared with the GPS fix of THAT
        instant when one was received, else with this one plus max_speed x the gap."""
        now = self.get_clock().now()
        best = None
        for last, timeout in ((self._day_last, self._day_timeout),
                              (self._night_last, self._night_timeout),
                              (self._cn_last, self._cn_timeout)):
            _, eligible, _ = self._eval_source(now, last, timeout)
            sigma = self._stated_sigma(last) if eligible else None
            if sigma is None or last.mode != PositionEstimate.MODE_MEASURED:
                continue                   # a propagated position partly comes from GPS itself
            t_ref = self._measured_at(last)
            self._last_ref_at = now
            same = self._gps_near(t_ref.nanoseconds)
            if same is not None:
                glat, glon, gap = same
            else:
                glat, glon, gap = gps_lat, gps_lon, abs((gps_stamp - t_ref).nanoseconds) / 1e9
            tol = self._crosscheck_sigmas * sigma + self._jump_margin + self._max_speed * gap
            if best is None or tol < best[2]:
                best = (_SOURCE_NAME.get(last.source, "source"),
                        _haversine_m(last.latitude, last.longitude, glat, glon), tol, t_ref.nanoseconds,
                        3.0 * sigma + self._max_speed * gap)
        return best

    def _on_day(self, msg: PositionEstimate) -> None:
        self._day_last = msg
        self._tick()

    def _on_night(self, msg: PositionEstimate) -> None:
        self._night_last = msg
        self._tick()

    def _on_cn(self, msg: PositionEstimate) -> None:
        self._cn_last = msg
        self._tick()

    def _on_imu(self, msg: Imu) -> None:
        # Liveness only: we keep the stamp, never the sample. The IMU feeds no
        # position in v1.
        self._imu_last_stamp = Time.from_msg(msg.header.stamp)

    def _check_single_arbiter(self) -> None:
        n = self.count_publishers("/navera/position")
        if n > 1 and not self._rival_reported:
            self.get_logger().error(
                f"{n} publishers on /navera/position: another arbiter is running on this "
                f"ROS network (ROS_DOMAIN_ID). Two decisions are being interleaved — stop "
                f"the other one.")
        elif n <= 1 and self._rival_reported:
            self.get_logger().warn("only one arbiter on /navera/position again")
        self._rival_reported = n > 1

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
        """A usable position: finite and in range, and a covariance that is one: finite,
        non-negative variances, symmetric, horizontal block positive semi-definite (a
        consumer's filter would break on anything else)."""
        if not is_finite_latlon(msg.latitude, msg.longitude):
            return False
        cov = list(msg.position_covariance)
        if not all(math.isfinite(c) for c in cov):
            return False
        if not all(cov[i] >= 0.0 for i in (0, 4, 8)):
            return False
        tol = 1e-9 * max(1.0, cov[0], cov[4], cov[8])
        if any(abs(cov[i] - cov[j]) > tol for i, j in ((1, 3), (2, 6), (5, 7))):
            return False
        return cov[0] * cov[4] - cov[1] * cov[3] >= -tol

    @staticmethod
    def _stated_sigma(msg: PositionEstimate) -> Optional[float]:
        """The horizontal 1-sigma the source STATES, or None when it states none: covariance
        type not one of the defined bounded types (a garbage byte must not promote a
        position), or a sigma under 1 cm (zero is no accuracy, it is a missing one)."""
        if msg.position_covariance_type not in (PositionEstimate.COVARIANCE_TYPE_APPROXIMATED,
                                                PositionEstimate.COVARIANCE_TYPE_DIAGONAL_KNOWN,
                                                PositionEstimate.COVARIANCE_TYPE_KNOWN):
            return None
        sigma = math.sqrt(max(msg.position_covariance[0], msg.position_covariance[4]))
        return sigma if sigma >= MIN_STATED_SIGMA_M else None

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
        bounded = self._stated_sigma(winner) is not None
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

        if winner is not None and winner.source == PositionEstimate.SOURCE_GPS and self._gps_doubt:
            winner = self._in_doubt(winner, *self._gps_doubt)
        if winner is not None:
            state, reason = self._classify(winner)
            if winner.source == PositionEstimate.SOURCE_GPS and self._gps_doubt:
                reason = (f"{reason} — GPS IN DOUBT: {self._gps_doubt[1]} disagrees by "
                          f"{self._gps_doubt[0]:.0f} m (possible slow spoofing)")
            if winner.source != PositionEstimate.SOURCE_GPS and gps_alive and self._gps_suspect:
                # The operator must see WHY GPS is not used while it is still talking.
                reason = f"{reason} — GPS refused: {self._gps_suspect}"
        elif not ever_heard:
            state = NavStatus.STATE_INITIALIZING
            reason = "waiting for first source message"
        else:
            state = NavStatus.STATE_NO_FIX
            reason = self._no_fix_reason(gps_age, day_age, night_age, cn_age)

        self._publish_status(now, state, winner, imu_alive, reason)
        if winner is not None:
            # one publication per measurement: its stamps AND its content (a source holding
            # its header stamp while its position changes must not freeze the output)
            key = (winner.source, winner.header.stamp.sec, winner.header.stamp.nanosec,
                   winner.sensor_stamp.sec, winner.sensor_stamp.nanosec, winner.latitude,
                   winner.longitude, winner.position_covariance[0])
            if key != self._last_published_key:
                self._last_published_key = key
                self._publish_position(now, winner)

    @staticmethod
    def _in_doubt(msg: PositionEstimate, gap_m: float, name: str) -> PositionEstimate:
        """A copy of a GPS estimate whose horizontal accuracy is no better than gap_m."""
        out = copy.deepcopy(msg)
        cov = list(out.position_covariance)
        cov[0], cov[4] = max(cov[0], gap_m ** 2), max(cov[4], gap_m ** 2)
        out.position_covariance = cov
        if out.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_UNKNOWN:
            out.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        return out

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

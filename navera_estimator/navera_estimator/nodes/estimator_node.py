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
    The size rules above need the offset to exceed 3 sigma (~90 m with a 30 m vision sigma)
    before anything happens. The GROWTH test (navera_common.GpsDriftTrend) uses the trend
    instead: one sample per independent fix, GPS interpolated at the fix's own instant, offset
    GPS - fix as a vector; refused when the offset grows steadily (a window of 8-128 s cut in
    quarter / half / quarter, growing through both halves) by more than
    gps_trend_min_growth_sigmas x the combined stated sigma and gps_trend_z x the noise the
    fixes actually show, at gps_trend_confirm_n fixes in a row. Such a refusal is lifted only
    once the offset is back nearer its value before the growth (agreeing within 3 sigma is not
    enough: the growth test refuses inside 3 sigma).
    The RELATIVE-MOTION test (navera_common.GpsMotionCheck) compares, while GPS is trusted, the
    GPS displacement (interpolated at the frame instants) with the day node's visual-odometry
    displacement over the same instants (/navera/vision/odometry): a spoof adds v x T to the GPS
    displacement only. The odometry's scale and heading are learned from the day map fixes, never
    from GPS; a directional CUSUM in the residual's own measured noise refuses; the refusal is
    lifted as a growth refusal's is.
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
    day_timeout_s   (default 5.0)  — day freshness/liveness window (was 3 s: under load frames
                     come every 1-4 s and NAVERA flickered NO_FIX between good fixes, the
                     autopilot landed — e1d0674; the output carries the fix to the present)
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
    gps_trend_enabled (default true) — the growth test (slow spoofing) on top of the size rules
    gps_trend_z (6.0), gps_trend_min_growth_sigmas (1.5), gps_trend_bias_rate_mps (0.2),
    gps_trend_min_jitter_m (3.0), gps_trend_min_fixes (6), gps_trend_confirm_n (3),
    gps_trend_windows_s ([8, 12, 16, 24, 32, 48, 64, 96, 128]) — see navera_common.gps_crosscheck.GpsDriftTrend
    gps_motion_enabled (default true), gps_motion_topic (/navera/vision/odometry), gps_motion_h (12),
    gps_motion_k (0.25), gps_motion_min_growth_m (12), gps_motion_bias_mps (0.5),
    gps_motion_eps_floor (0.03) — see navera_common.gps_motion_check.GpsMotionCheck
    map_images_dir  (default "": $DAY_DATASET_DIR/images) — the mission's map tiles, for the
                     mission-area guard: NavStatus.map_area / map_edge_m from the published
                     position (the last one for map_hold_s after it, so NO_FIX past the edge
                     still says OUTSIDE). Reported only; NAVERA never acts on the vehicle.
    map_edge_warn_m (default 500.0) — closer to the map's edge than this: MAP_AREA_NEAR_EDGE
    map_hold_s      (default 60.0)
"""
import copy
import json
import math
import os
import time
from collections import deque
from typing import Optional

import rclpy
from navera_common.covariance import covariance_sane, horizontal_sigma
from navera_common.geo import is_finite_latlon
from navera_common.gps_crosscheck import STREAK_N, GpsCrossCheck, GpsDriftTrend
from navera_common.gps_motion_check import GpsMotionCheck
from navera_common.lifecycle import die_with_parent
from navera_common.map_area import MapArea, classify as map_classify
from navera_common.params import declare_float
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from navera_common.qos import SENSOR_QOS
from rclpy.duration import Duration
from rclpy.time import Time
from sensor_msgs.msg import Imu
from std_msgs.msg import String

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
# STREAK_N (navera_common.gps_crosscheck): distinct independent fixes in a row beyond 3 sigma that
# refuse GPS. For a 2-D error P(r > 3 sigma) = exp(-4.5) = 1.1 % per fix, so a false streak of 5 is
# 1.7e-10 (the former "< 1e-12" was the 1-D figure, 0.27 % per fix)

class EstimatorNode(Node):
    """Selects the winning position estimate and publishes the nav status."""

    def __init__(self) -> None:
        super().__init__("estimator_node")
        declare_float(self, "publish_rate_hz", 5.0)
        declare_float(self, "gps_timeout_s", 3.0)
        declare_float(self, "day_timeout_s", 5.0)    # = config/estimator_params.yaml (e1d0674)
        declare_float(self, "night_timeout_s", 5.0)
        declare_float(self, "cn_timeout_s", 45.0)
        declare_float(self, "imu_timeout_s", 1.0)
        declare_float(self, "future_tolerance_s", 0.5)
        declare_float(self, "switch_holdoff_s", 2.0)
        declare_float(self, "max_speed_mps", 100.0)
        declare_float(self, "gps_jump_margin_m", 50.0)
        # the jump gate also over this window: one margin per fix let a steady drag of
        # max_speed + margin/period through (150 m/s with the defaults, every 1 s fix passing)
        declare_float(self, "gps_jump_window_s", 20.0)
        # the attitude NAVERA uses (box, vehicle or ROS IMU): liveness only
        self.declare_parameter("imu_topic", "/navera/sensors/imu")
        declare_float(self, "gps_crosscheck_sigmas", 5.0)
        declare_float(self, "gps_crosscheck_persist_s", 3.0)
        # slow spoofing: the GROWTH of the GPS - vision offset (navera_common.GpsDriftTrend)
        self.declare_parameter("gps_trend_enabled", True)
        declare_float(self, "gps_trend_z", 6.0, "growth needed, in the noise the fixes show")
        declare_float(self, "gps_trend_min_growth_sigmas", 1.5,
                      "growth needed, in the combined stated sigma of the fix and the GPS")
        declare_float(self, "gps_trend_bias_rate_mps", 0.2, "vision bias change allowed (m/s)")
        declare_float(self, "gps_trend_min_jitter_m", 3.0, "floor of the measured fix jitter (m)")
        self.declare_parameter("gps_trend_min_fixes", 6)
        self.declare_parameter("gps_trend_confirm_n", 3)
        self.declare_parameter("gps_trend_windows_s", [8.0, 12.0, 16.0, 24.0, 32.0, 48.0, 64.0, 96.0, 128.0])
        # slow spoofing: GPS displacement vs visual-odometry displacement (navera_common.GpsMotionCheck)
        self.declare_parameter("gps_motion_enabled", True)
        self.declare_parameter("gps_motion_topic", "/navera/vision/odometry")
        declare_float(self, "gps_motion_h", 12.0, "CUSUM threshold (noise units)")
        declare_float(self, "gps_motion_k", 0.25, "CUSUM reference (noise units per step)")
        declare_float(self, "gps_motion_min_growth_m", 12.0, "drift accumulated needed to refuse (m)")
        declare_float(self, "gps_motion_bias_mps", 0.5, "GPS / odometry drift allowed (m/s)")
        declare_float(self, "gps_motion_eps_floor", 0.03, "odometry scale / heading error always allowed")
        # FIX also requires the stated horizontal sigma to be at most this.
        declare_float(self, "fix_max_sigma_m", 25.0)
        # mission-area guard (report only): how far the position is from the map's edge
        self.declare_parameter("map_images_dir", "")
        declare_float(self, "map_edge_warn_m", 500.0, "closer to the map's edge than this: NEAR_EDGE (m)")
        declare_float(self, "map_hold_s", 60.0, "the last position keeps the map flag this long (s)")
        rate = float(self.get_parameter("publish_rate_hz").value)
        if rate <= 0.0:
            raise ValueError(f"publish_rate_hz must be > 0 (got {rate})")
        self._future_tol = float(self.get_parameter("future_tolerance_s").value)
        self._holdoff = float(self.get_parameter("switch_holdoff_s").value)
        self._max_speed = float(self.get_parameter("max_speed_mps").value)
        self._jump_margin = float(self.get_parameter("gps_jump_margin_m").value)
        self._jump_window = float(self.get_parameter("gps_jump_window_s").value)
        self._trusted_hist = deque()                   # (lat, lon, Time) trusted GPS over the window
        self._crosscheck_sigmas = float(self.get_parameter("gps_crosscheck_sigmas").value)
        self._crosscheck_persist = float(self.get_parameter("gps_crosscheck_persist_s").value)
        # trusted GPS vs independent source: the refusal rule (shared with the bench)
        trend = None
        if bool(self.get_parameter("gps_trend_enabled").value):
            trend = GpsDriftTrend(
                windows_s=[float(w) for w in self.get_parameter("gps_trend_windows_s").value],
                z=float(self.get_parameter("gps_trend_z").value),
                min_growth_sigmas=float(self.get_parameter("gps_trend_min_growth_sigmas").value),
                bias_rate_mps=float(self.get_parameter("gps_trend_bias_rate_mps").value),
                min_jitter_m=float(self.get_parameter("gps_trend_min_jitter_m").value),
                min_fixes=int(self.get_parameter("gps_trend_min_fixes").value),
                confirm_n=int(self.get_parameter("gps_trend_confirm_n").value))
        self._xcheck = GpsCrossCheck(persist_s=self._crosscheck_persist, streak_n=STREAK_N, trend=trend)
        self._map_warn = float(self.get_parameter("map_edge_warn_m").value)
        self._map_hold = float(self.get_parameter("map_hold_s").value)
        self._map = self._load_map(str(self.get_parameter("map_images_dir").value))
        self._map_last = None                          # (lat, lon, monotonic s) last published position
        self._map_flag = None                          # last map_area reported (for the log)
        self._motion = None
        if bool(self.get_parameter("gps_motion_enabled").value):
            self._motion = GpsMotionCheck(
                h=float(self.get_parameter("gps_motion_h").value),
                k=float(self.get_parameter("gps_motion_k").value),
                min_growth_m=float(self.get_parameter("gps_motion_min_growth_m").value),
                bias_mps=float(self.get_parameter("gps_motion_bias_mps").value),
                eps_floor=float(self.get_parameter("gps_motion_eps_floor").value))
        self._vo_pending = deque(maxlen=50)          # odometry steps waiting for the GPS after them
        self._local_ref = None                       # (lat, lon) origin of the motion test's metres
        self._last_day_fix_ns = None
        self._confirm_needed_since: Optional[Time] = None  # refused by the cross-check
        self._last_ref_at = Time(seconds=0, clock_type=self.get_clock().clock_type)
        # (stamp ns, lat, lon) of received GPS fixes: 200 cover the odometry steps (up to ~5 s old when
        # they arrive) at 20 Hz GPS
        self._gps_hist = deque(maxlen=200)
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

        # id(message) -> (receive Time, arrived stamped in the future), for the latest message of
        # each source only (B6: a fix stamped ahead came back to life once the clock caught up)
        self._rx = {}
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
        self.sub_vo = self.create_subscription(
            String, str(self.get_parameter("gps_motion_topic").value), self._on_odometry, 10)

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
        self._note_rx(self._gps_last, msg)
        self._gps_last = msg
        if msg.valid and self._sane(msg):
            self._gps_hist.append((Time.from_msg(msg.header.stamp).nanoseconds, msg.latitude, msg.longitude))
        self._check_gps_plausibility(msg)
        self._motion_steps(msg)
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
                name, d, tol, ref_stamp, tol_strict, sample = ref
                # back only when it agrees within 3 sigma with two distinct independent
                # fixes: the 5-sigma window would "confirm" a GPS refused moments ago; after a
                # growth refusal (well inside 3 sigma) also only once the growth is undone
                agrees = d <= tol_strict and self._xcheck.back_to_baseline(sample)
                self._agree_refs = self._agree_refs | {ref_stamp} if agrees else set()
                if len(self._agree_refs) >= 2:
                    self.get_logger().warn(
                        f"GPS confirmed by {name} ({d:.0f} m apart, 3 sigma {tol_strict:.0f} m, "
                        f"2 fixes) — re-accepted")
                    self._agree_refs = set()
                    self._xcheck.baseline = None
                    self._confirm_needed_since = None
                    self._gps_suspect = None
                    self._set_trusted(msg.latitude, msg.longitude, stamp, restart=True)
                elif d > tol_strict:
                    if self._gps_suspect is None:
                        self.get_logger().error(
                            f"GPS refused: {d:.0f} m from {name} (3 sigma {tol_strict:.0f} m)")
                    self._gps_suspect = (f"GPS {d:.0f} m from {name} (3 sigma {tol_strict:.0f} m) "
                                         f"— possible spoofing")
                # within 3 sigma but the growth not undone: the growth refusal (and its reason) stands
                return
            if self._confirm_needed_since is not None:
                # caught drifting by an independent source: comparing GPS with its own last
                # (already spoofed) position proves nothing — only an independent fix clears
                # it, or 120 s without any (the source itself may have been the wrong one)
                if (stamp - max(self._confirm_needed_since, self._last_ref_at)).nanoseconds / 1e9 < 120.0:
                    return
                self.get_logger().warn("no independent source for 120 s: GPS judged on its own again")
                self._confirm_needed_since = None
                self._xcheck.baseline = None
        if self._gps_trusted is None:
            self._set_trusted(msg.latitude, msg.longitude, stamp, restart=True)
            return
        if continuous and self._drifting_away(msg, stamp):
            return
        lat0, lon0, t0 = self._gps_trusted
        dt = max(0.0, (stamp - t0).nanoseconds / 1e9)
        dist = _haversine_m(lat0, lon0, msg.latitude, msg.longitude)
        reachable = self._max_speed * dt + self._jump_margin
        drag = self._window_drag(msg, stamp) if dist <= reachable else None
        if dist <= reachable and drag is None:
            if self._gps_suspect:
                self.get_logger().warn("GPS plausible again — re-accepted")
            self._gps_suspect = None
            self._set_trusted(msg.latitude, msg.longitude, stamp)
        else:
            reason = drag or (f"implausible jump {dist:.0f} m in {dt:.1f} s "
                              f"(max {reachable:.0f} m at {self._max_speed:.0f} m/s) — possible spoofing")
            if self._gps_suspect is None:
                self.get_logger().error(f"GPS refused: {reason}")
            self._gps_suspect = reason

    def _set_trusted(self, lat: float, lon: float, stamp: Time, restart: bool = False) -> None:
        """The last plausible GPS fix; restart = a new trusted track (no window to compare with)."""
        self._gps_trusted = (lat, lon, stamp)
        if restart:
            self._trusted_hist.clear()
            self._xcheck.reset()              # offsets seen before belong to another GPS track
            if self._motion is not None:
                self._motion.reset()          # (its odometry calibration owes nothing to GPS: kept)
        self._trusted_hist.append((lat, lon, stamp))
        while self._trusted_hist and (stamp - self._trusted_hist[0][2]).nanoseconds / 1e9 > self._jump_window:
            self._trusted_hist.popleft()

    def _window_drag(self, msg: PositionEstimate, stamp: Time) -> Optional[str]:
        """The refusal reason when the fix is out of reach of a trusted fix of the window (one
        margin over the whole window, not one per fix), else None."""
        for lat0, lon0, t0 in self._trusted_hist:
            dt = (stamp - t0).nanoseconds / 1e9
            if dt <= 0.0 or dt > self._jump_window:
                continue
            dist = _haversine_m(lat0, lon0, msg.latitude, msg.longitude)
            reach = self._max_speed * dt + self._jump_margin
            if dist > reach:
                return (f"implausible drift {dist:.0f} m in {dt:.1f} s (max {reach:.0f} m at "
                        f"{self._max_speed:.0f} m/s) — possible spoofing")
        return None

    def _drifting_away(self, msg: PositionEstimate, stamp: Time) -> bool:
        """Trusted GPS vs an independent source of stated accuracy: True (and
        GPS refused) once they have disagreed for gps_crosscheck_persist_s."""
        ref = self._independent_reference(stamp, msg.latitude, msg.longitude)
        t = stamp.nanoseconds / 1e9
        if ref is None:
            self._xcheck.no_reference(t)
            return False
        name, d, tol, ref_stamp, tol_strict, sample = ref
        reason = self._xcheck.update(t, d, tol, tol_strict, ref_stamp, name, sample=sample)
        # two independent fixes in a row beyond 3 sigma: GPS is in doubt — still used, but
        # with an accuracy no better than the gap (the operator sees it, the autopilot
        # weighs it less, and a later switch to vision is no jump outside its accuracy).
        # A gap over DOUBT_MAX_M is more likely a wrong vision match: not applied.
        doubt = self._xcheck.in_doubt or (self._motion is not None and self._motion.in_doubt)
        self._gps_doubt = (d, name, self._trend_note()) if doubt and d <= DOUBT_MAX_M else None
        if reason is None:
            return False
        self._refuse(stamp, reason)
        return True

    def _trend_note(self) -> str:
        """', offset growing x m/s' while the growth test passes but is not confirmed, else ''."""
        tr, mo = self._xcheck.trend, self._motion
        if mo is not None and mo.in_doubt:
            return ", GPS moving off the visual odometry"
        if tr is None or not tr.in_doubt or not tr.last:
            return ""
        return f", offset growing {tr.last['rate_mps']:.1f} m/s"

    def _refuse(self, stamp: Time, reason: str) -> None:
        """GPS refused by the cross-check: only an independent fix can clear it."""
        self._gps_suspect = reason
        self._xcheck.reset()
        if self._motion is not None:
            self._motion.reset()
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

    def _gps_at(self, t_ns: int, max_gap_s: float = 2.5):
        """(lat, lon) of GPS at t_ns, interpolated between the two received fixes around it (at most
        max_gap_s apart), or the received fix within 0.1 s; None otherwise (no extrapolation)."""
        before = after = None
        for ts, lat, lon in self._gps_hist:
            if ts <= t_ns and (before is None or ts > before[0]):
                before = (ts, lat, lon)
            if ts >= t_ns and (after is None or ts < after[0]):
                after = (ts, lat, lon)
        for fix in (before, after):
            if fix is not None and abs(fix[0] - t_ns) <= 1e8:
                return fix[1], fix[2]
        if before is None or after is None or (after[0] - before[0]) / 1e9 > max_gap_s:
            return None
        w = (t_ns - before[0]) / (after[0] - before[0])
        return before[1] + w * (after[1] - before[1]), before[2] + w * (after[2] - before[2])

    def _gps_sigma(self) -> float:
        """The stated horizontal sigma of the latest GPS fix (0 when it states none)."""
        return (self._stated_sigma(self._gps_last) or 0.0) if self._gps_last is not None else 0.0

    def _independent_reference(self, gps_stamp: Time, gps_lat: float, gps_lon: float):
        """(name, distance_m, tolerance_m, ref_stamp_ns, tol_3sigma_m, sample) between the most
        accurate fresh non-GPS source with a STATED accuracy and GPS, or None. A source of unknown
        accuracy cannot vouch for or against GPS. A vision fix describes the instant
        its photo was taken (0.5-1.5 s ago): it is compared with the GPS fix of THAT
        instant when one was received, else with this one plus max_speed x the gap.
        sample: (t s, east m, north m, combined sigma m) of GPS interpolated at the fix's instant
        minus the fix, for the growth test; None when GPS around that instant is not known yet."""
        now = self.get_clock().now()
        best = None
        for last, timeout in ((self._day_last, self._day_timeout),
                              (self._night_last, self._night_timeout),
                              (self._cn_last, self._cn_timeout)):
            _, eligible, _ = self._eval_source(now, last, timeout)
            sigma = self._stated_sigma(last) if eligible else None
            if sigma is None or last.mode != PositionEstimate.MODE_MEASURED:
                continue                   # a propagated position partly comes from GPS itself
            if sigma > 1000.0:
                # a celestial fix (tens of km) "agrees" with a GPS spoofed by 100+ km: too
                # coarse to vouch for or against GPS
                continue
            t_ref = self._measured_at(last)
            self._last_ref_at = now
            same = self._gps_near(t_ref.nanoseconds)
            if same is not None:
                glat, glon, gap = same
            else:
                glat, glon, gap = gps_lat, gps_lon, abs((gps_stamp - t_ref).nanoseconds) / 1e9
            tol = self._crosscheck_sigmas * sigma + self._jump_margin + self._max_speed * gap
            if best is None or tol < best[2]:
                sample = None
                at = self._gps_at(t_ref.nanoseconds)
                if at is not None:
                    m_lat = 111195.0                       # metres per degree (R = 6371 km)
                    sample = (t_ref.nanoseconds / 1e9,
                              (at[1] - last.longitude) * m_lat * math.cos(math.radians(last.latitude)),
                              (at[0] - last.latitude) * m_lat, math.hypot(sigma, self._gps_sigma()))
                best = (_SOURCE_NAME.get(last.source, "source"),
                        _haversine_m(last.latitude, last.longitude, glat, glon), tol, t_ref.nanoseconds,
                        3.0 * sigma + self._max_speed * gap, sample)
        return best

    def _on_day(self, msg: PositionEstimate) -> None:
        self._note_rx(self._day_last, msg)
        self._day_last = msg
        self._motion_fix(msg)
        self._tick()

    # ---------- relative motion: GPS displacement vs visual odometry ----------

    def _local_en(self, lat: float, lon: float):
        """(east, north) metres of lat/lon from the motion test's origin (set on first use)."""
        if self._local_ref is None:
            self._local_ref = (lat, lon)
        m_lat = 111195.0
        return ((lon - self._local_ref[1]) * m_lat * math.cos(math.radians(self._local_ref[0])),
                (lat - self._local_ref[0]) * m_lat)

    def _motion_fix(self, msg: PositionEstimate) -> None:
        """A measured day-vision (map) fix of stated accuracy calibrates the odometry (scale, heading)."""
        if self._motion is None or msg.mode != PositionEstimate.MODE_MEASURED or not msg.valid \
                or not self._sane(msg) or self._stated_sigma(msg) is None:
            return
        t_ns = self._measured_at(msg).nanoseconds
        if self._last_day_fix_ns is not None and t_ns <= self._last_day_fix_ns:
            return
        self._last_day_fix_ns = t_ns
        e, n = self._local_en(msg.latitude, msg.longitude)
        at = self._gps_at(t_ns)
        off = None
        if at is not None:
            ge, gn = self._local_en(*at)
            off = (ge - e, gn - n)
        self._motion.add_fix(t_ns / 1e9, e, n, off)

    def _on_odometry(self, msg: String) -> None:
        """A visual-odometry step from the day node (JSON t0, t1 s, east_m, north_m): queued until GPS
        is known after its end."""
        if self._motion is None:
            return
        try:
            d = json.loads(msg.data)
            step = tuple(float(d[k]) for k in ("t0", "t1", "east_m", "north_m"))
        except (ValueError, TypeError, KeyError):
            return
        if all(math.isfinite(v) for v in step) and step[1] > step[0]:
            self._vo_pending.append(step)
            self._motion_steps(None)

    def _motion_steps(self, gps_msg: Optional[PositionEstimate]) -> None:
        """Odometry steps whose end the GPS now covers, against the GPS displacement over the same
        instants (GPS interpolated), while GPS is trusted. A refusal goes the cross-check's way."""
        if self._motion is None or not self._gps_hist:
            return
        newest = self._gps_hist[-1][0]
        while self._vo_pending and self._vo_pending[0][1] * 1e9 <= newest:
            t0, t1, de, dn = self._vo_pending.popleft()
            if self._gps_trusted is None or self._gps_suspect is not None:
                continue
            g0, g1 = self._gps_at(int(t0 * 1e9)), self._gps_at(int(t1 * 1e9))
            if g0 is None or g1 is None:
                continue
            e0, n0 = self._local_en(*g0)
            e1, n1 = self._local_en(*g1)
            why = self._motion.add_step(t0, t1, de, dn, e1 - e0, n1 - n0)
            if why is None:
                continue
            if self._motion.refused_baseline is not None:
                self._xcheck.baseline = self._motion.refused_baseline
            stamp = Time.from_msg(gps_msg.header.stamp) if gps_msg is not None else self.get_clock().now()
            self._refuse(stamp, f"GPS drifting away from day vision odometry: {why} — possible slow spoofing")
            self._vo_pending.clear()
            return

    def _on_night(self, msg: PositionEstimate) -> None:
        self._note_rx(self._night_last, msg)
        self._night_last = msg
        self._tick()

    def _on_cn(self, msg: PositionEstimate) -> None:
        self._note_rx(self._cn_last, msg)
        self._cn_last = msg
        self._tick()

    def _on_imu(self, msg: Imu) -> None:
        # Liveness only: we keep the stamp, never the sample. The IMU feeds no
        # position in v1.
        self._imu_last_stamp = Time.from_msg(msg.header.stamp)

    def _note_rx(self, old: Optional[PositionEstimate], msg: PositionEstimate) -> None:
        """Remember when msg arrived and whether it was stamped in the future then (it replaces old)."""
        if old is not None:
            self._rx.pop(id(old), None)
        now = self.get_clock().now()
        self._rx[id(msg)] = (now, self._age_s(now, self._measured_at(msg)) < -self._future_tol)

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
        return is_finite_latlon(msg.latitude, msg.longitude) and covariance_sane(msg.position_covariance)

    @staticmethod
    def _stated_sigma(msg: PositionEstimate) -> Optional[float]:
        """The horizontal 1-sigma the source STATES, or None when it states none: covariance
        type not one of the defined bounded types (a garbage byte must not promote a
        position), or a sigma under 1 cm (zero is no accuracy, it is a missing one)."""
        if msg.position_covariance_type not in (PositionEstimate.COVARIANCE_TYPE_APPROXIMATED,
                                                PositionEstimate.COVARIANCE_TYPE_DIAGONAL_KNOWN,
                                                PositionEstimate.COVARIANCE_TYPE_KNOWN):
            return None
        sigma = horizontal_sigma(msg.position_covariance)     # the ellipse's long axis
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
        rx = self._rx.get(id(last))
        if rx is not None:
            # a message that ARRIVED stamped in the future never becomes alive: once the clock
            # catches up it would look fresh although the source may have died meanwhile; and
            # a message is not fresh when it was received longer ago than the timeout
            alive = alive and not rx[1] and self._age_s(now, rx[0]) < timeout
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
        sigma = horizontal_sigma(winner.position_covariance)
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
            winner = self._in_doubt(winner, *self._gps_doubt[:2])
        if winner is not None:
            state, reason = self._classify(winner)
            if winner.source == PositionEstimate.SOURCE_GPS and self._gps_doubt:
                reason = (f"{reason} — GPS IN DOUBT: {self._gps_doubt[1]} disagrees by "
                          f"{self._gps_doubt[0]:.0f} m{self._gps_doubt[2]} (possible slow spoofing)")
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

    def _load_map(self, images_dir: str):
        """The mission's map coverage (navera_common.map_area), or None (guard off)."""
        if not images_dir:
            ds = os.environ.get("DAY_DATASET_DIR", "")
            images_dir = os.path.join(ds, "images") if ds else ""
        area = MapArea.from_images_dir(images_dir) if images_dir else None
        if area is None:
            self.get_logger().info(f"mission-area guard off: no map tiles in '{images_dir}'")
        else:
            self.get_logger().info(
                f"mission-area guard: {len(area.tiles)} map tiles ({area.area_km2:.1f} km2), "
                f"NEAR_EDGE within {self._map_warn:.0f} m of the edge")
        return area

    def _map_status(self, winner) -> tuple:
        """(NavStatus.map_area, map_edge_m) of the published position (or the last one, for
        map_hold_s), against the mission's map."""
        if self._map is None:
            return NavStatus.MAP_AREA_UNKNOWN, math.nan
        now = time.monotonic()
        if winner is not None and is_finite_latlon(winner.latitude, winner.longitude):
            self._map_last = (winner.latitude, winner.longitude, now)
        if self._map_last is None or now - self._map_last[2] > self._map_hold:
            return NavStatus.MAP_AREA_UNKNOWN, math.nan
        edge = self._map.edge_distance_m(self._map_last[0], self._map_last[1])
        flag = map_classify(edge, self._map_warn)
        if flag != self._map_flag:
            if flag in (NavStatus.MAP_AREA_NEAR_EDGE, NavStatus.MAP_AREA_OUTSIDE):
                self.get_logger().warn(
                    f"MISSION AREA: {'beyond' if flag == NavStatus.MAP_AREA_OUTSIDE else 'near'} the edge of "
                    f"the map ({edge:+.0f} m) — day vision has no map past it")
            elif self._map_flag is not None:
                self.get_logger().info(f"mission area: {edge:.0f} m inside the map")
            self._map_flag = flag
        return flag, edge

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
        status.map_area, status.map_edge_m = self._map_status(winner)
        status.gps_refused = self._gps_suspect is not None
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

#!/usr/bin/env python3
"""Closed loop in ArduPilot SITL: an AUTO mission flown GPS-denied on NAVERA's positions only.

Not part of run_tests.sh (needs an ArduPilot build; 4-7 min of simulation per run). Usage, from
the workspace root:

    nice -n 19 python3 navera_tools/tests/sitl_closed_loop.py --vehicle copter|plane
        [--scenarios nominal,outage10,outage30,outage60,spoof,burst,poor] [--set K=V,...]
        [--sigma 30] [--latency 0.3,1.0] [--instance 5] [--out DIR] [--tag NAME]

The SITL vehicle has no simulated GPS (SIM_GPS_DISABLE 1): its only position is the GPS_INPUT
this script sends, with NAVERA's recommended parameters (docs/ARDUPILOT_INTEGRATION.md §3).
The script plays NAVERA from the GPS and the day vision down to the wire, with NAVERA's own code
where it is pure Python:

  * GPS: the simulator's truth + 0.7 m noise at 5 Hz, stated 1.5 m, receiver velocity;
  * day vision: one frame per second (--frame-period), describing the truth of its photo instant
    and reaching the estimator --latency later (uniform, s). Its error is REPLAYED, fix by fix
    and in order, from the per-photo results of the 8 real UAV-VisLoc flights with the
    pose-attitude guard (~/.navera_sim/uavvisloc/more/f*_guard4.json, docs/VALIDATION_STATUS.md:
    pooled median 16 m, p90 34 m): an accepted photo gives its measured (east, north) error,
    a refused photo gives no fix. Pool "good" = flights 03, 04, 06, 11 (74-91 % accepted),
    "poor" = flights 01, 05, 08, 10 (5-27 % accepted: refusal runs up to 120 photos). Stated
    accuracy: the product's 30 m floor before self-calibration (max(30 m, the matcher's sigma));
  * the estimator: GPS > day, GPS refused by navera_common.gps_crosscheck (3-sigma streak, wide
    window, slow-drift trend) exactly as navera_estimator calls it, GPS in doubt widened to the
    gap; a source stale after 3 s;
  * the output: navera_output.policy.decide / hold / bridge / reacquire +
    navera_common.track.TrackVelocity and the vehicle_output_node send logic (carry to the
    present, bridge a gap up to 10 s, "no fix" after, velocity with every position, hold back
    after a gap until the new fixes' velocity is known), GPS_INPUT from
    mavlink_out.gps_input_fields(), forward_degraded with degraded_sigma_m = --sigma. Clock: the
    autopilot's (SITL) time.

Mission (relative to home): Copter 80 m, 10 m/s, 4 legs (300 / 400 / 400 / 400 m), RTL + land;
Plane 100 m, ~22 m/s, 5 legs of 0.6-1.2 km, RTL (loiter over home). GPS is lost when waypoint 1 is reached and never
returns. Scenarios (times after the loss):

  nominal    vision as replayed
  outageN    no vision frame for N s from +40 s (NAVERA bridges <= 10 s, then "no fix")
  burst      10 consecutive accepted fixes 150 m north (cross-track) of the truth from +40 s
  spoof      from waypoint 1 the GPS is pulled north at 2 m/s while still received (vision
             running); the GPS is jammed 120 s later
  poor       nominal with the "poor" pool

Measured from the simulator's truth: autopilot (EKF) position error, cross-track error on each
GPS-denied leg (away from the corners), closest approach to every GPS-denied waypoint,
completion, landing point (Copter) / RTL loiter centre (Plane) vs home, EKF_STATUS_REPORT
position variance, failsafes and EKF/GPS messages. Results: <out>/<vehicle>_<scenario>.json
and a summary table on stdout.
"""
import argparse
import bisect
import json
import math
import os
import random
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from pymavlink import mavutil

WS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for _pkg in ("navera_output", "navera_common"):
    sys.path.insert(0, os.path.join(WS, _pkg))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sitl_vehicles as sv                                                     # noqa: E402
from navera_common.gps_crosscheck import STREAK_N, GpsCrossCheck, GpsDriftTrend  # noqa: E402
from navera_common.track import TrackVelocity                                   # noqa: E402
from navera_output import mavlink_out                                           # noqa: E402
from navera_output.policy import (KIND_ESTIMATED, KIND_FIX, KIND_NONE, STATE_DEGRADED,  # noqa: E402
                                  STATE_FIX, STATE_NO_FIX, Config, bridge, decide, hold, reacquire)

HOME = sv.HOME
SOURCE_GPS, SOURCE_DAY = 1, 2
ERR_DIR = os.path.expanduser("~/.navera_sim/uavvisloc/more")
POOLS = {"good": ("03", "04", "06", "11"), "poor": ("01", "05", "08", "10")}
DAY_SIGMA_FLOOR_M = 30.0                     # day_pkg sigma_floor_no_cal_m
GPS_SIGMA_M, GPS_NOISE_M = 1.5, 0.7

# mission legs, metres north / east of home
MISSIONS = {
    "copter": dict(alt=80.0, wps=[(300, 0), (300, 400), (-100, 400), (-100, 0)],
                   params={"WPNAV_SPEED": 1000, "RTL_ALT": 8000, "WPNAV_RADIUS": 200}, corner_m=40.0),
    "plane": dict(alt=100.0, wps=[(600, 0), (600, 1200), (-600, 1200), (-600, 0), (600, 0)],
                  params={"TKOFF_ALT": 60, "RTL_RADIUS": 0, "ALT_HOLD_RTL": 10000}, corner_m=250.0),
}
# --endurance S (Copter): the Isaac endurance flight (navera_tools/isaac/run_closed_loop.sh --endurance):
# 250 m, 8 m/s, a 500 m diamond around home flown again and again (DO_JUMP forever) for S s after
# the GPS loss, then RTL
ENDURANCE = dict(alt=250.0, wps=[(500, 0), (0, 500), (-500, 0), (0, -500), (500, 0)],
                 params={"WPNAV_SPEED": 800, "WPNAV_SPEED_UP": 500, "WPNAV_SPEED_DN": 300, "LAND_SPEED_HIGH": 300,
                         "ANGLE_MAX": 3500, "RTL_ALT": 25000, "RTL_ALT_FINAL": 25000, "WPNAV_RADIUS": 200,
                         "SIM_BATT_CAP_AH": 0, "BATT_FS_LOW_ACT": 0, "BATT_FS_CRT_ACT": 0},
                 corner_m=60.0)
BLOCK_S = 300.0                              # endurance: statistics per 5 minutes after the loss
SCENARIOS = ("nominal", "outage10", "outage30", "outage60", "spoof", "burst", "poor")
EVENT_AT_S = 40.0                            # outage / burst start after the GPS loss
SPOOF_RATE_MPS, SPOOF_JAM_AFTER_S = 2.0, 120.0
BURST_N, BURST_OFFSET_M = 10, 150.0


# ----------------------------------------------------------------------------- error model
def load_frames(pool):
    """[(east err m, north err m, matcher sigma m) or None (refused)] in photo order."""
    out = []
    for fl in POOLS[pool]:
        with open(os.path.join(ERR_DIR, f"f{fl}_guard4.json")) as f:
            frames = json.load(f)["frames"]
        for fr in frames:
            if fl == "06" and 99 <= int(fr["file"][3:7]) <= 180:
                continue                     # excluded in VALIDATION_STATUS (bad ground truth)
            out.append((fr["east_m"], fr["north_m"], fr["stated_sigma_m"]) if fr["accepted"] else None)
    return out


class VisionErrors:
    """The real per-photo results replayed in order from a random start."""

    def __init__(self, pool, rng, max_refusals=0):
        self.frames = load_frames(pool)
        self.i = rng.randrange(len(self.frames))
        self.max_refusals = max_refusals     # > 0: a refusal run is cut to this many photos
        self.refused = 0

    def next(self):
        f = self.frames[self.i % len(self.frames)]
        self.i += 1
        if f is None and self.max_refusals > 0:
            self.refused += 1
            if self.refused > self.max_refusals:   # skip to the run's end: its next accepted photo
                while self.frames[self.i % len(self.frames)] is None:
                    self.i += 1
                f = self.frames[self.i % len(self.frames)]
                self.i += 1
        if f is not None:
            self.refused = 0
        return f


# ----------------------------------------------------------------------------- NAVERA emulation
def pos_msg(source, lat, lon, alt, sigma, t_meas, sats=None):
    """A PositionEstimate as the output node sees it (no ROS)."""
    s2 = sigma * sigma
    det = {"num_sats": sats, "geo_sep_m": 0.0} if source == SOURCE_GPS else {}
    return SimpleNamespace(source=source, latitude=lat, longitude=lon, altitude=alt,
                           position_covariance=[s2, 0, 0, 0, s2, 0, 0, 0, 4.0 if source == SOURCE_GPS else 0.0],
                           position_covariance_type=2, details_json=json.dumps(det), t_meas=t_meas)


class Estimator:
    """navera_estimator for GPS + day vision: election, staleness, GPS cross-check (shared code)."""

    def __init__(self):
        self.xcheck = GpsCrossCheck(persist_s=3.0, streak_n=STREAK_N, trend=GpsDriftTrend())
        self.gps = None                      # (t_rx, msg, vel)
        self.day = None                      # (t_rx, msg)
        self.gps_hist = []                   # (t_meas, lat, lon)
        self.refused = None                  # reason
        self.doubt = None                    # gap m
        self.published = None                # the last /navera/position
        self.events = []

    def on_gps(self, t, lat, lon, alt, vel):
        self.gps = (t, pos_msg(SOURCE_GPS, lat, lon, alt, GPS_SIGMA_M, t, sats=12), vel)
        self.gps_hist.append((t, lat, lon))
        if len(self.gps_hist) > 400:
            del self.gps_hist[:100]

    def gps_at(self, t):
        h = self.gps_hist
        if not h or t < h[0][0] or t > h[-1][0] + 0.5:
            return None
        i = bisect.bisect_left([x[0] for x in h], t)
        if i >= len(h):
            return h[-1][1:]
        if i == 0:
            return h[0][1:]
        a, b = h[i - 1], h[i]
        w = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
        return a[1] + w * (b[1] - a[1]), a[2] + w * (b[2] - a[2])

    def on_day(self, t, msg):
        self.day = (t, msg)
        if self.gps is None or self.refused or t - self.gps[0] > 3.0:
            return
        at = self.gps_at(msg.t_meas)
        if at is None:
            return
        sigma = math.sqrt(msg.position_covariance[0])
        n, e = sv.ne_from(msg.latitude, msg.longitude, at[0], at[1])
        d = math.hypot(n, e)
        tol, tol3 = 5.0 * sigma + 50.0, 3.0 * sigma
        reason = self.xcheck.update(t, d, tol, tol3, round(msg.t_meas, 3), "day vision",
                                    sample=(msg.t_meas, e, n, math.hypot(sigma, GPS_SIGMA_M)))
        if reason:
            self.refused = reason
            self.events.append((t, "GPS refused: " + reason))
            print(f"    navera {t:7.1f}: GPS refused: {reason}")
        self.doubt = d if self.xcheck.in_doubt and d <= 500.0 and not reason else None

    def elect(self, t):
        """(state, active source, current position message or None)."""
        if self.gps is not None and not self.refused and t - self.gps[0] <= 3.0:
            msg = self.gps[1]
            if self.doubt:
                g = max(GPS_SIGMA_M, self.doubt)
                msg = pos_msg(SOURCE_GPS, msg.latitude, msg.longitude, msg.altitude, g, msg.t_meas, 12)
                msg.key = ("gps", self.gps[0])
            state = STATE_FIX if math.sqrt(msg.position_covariance[0]) <= 25.0 else STATE_DEGRADED
            return state, SOURCE_GPS, msg, ("gps", self.gps[0])
        if self.day is not None and t - self.day[0] <= 3.0:
            return STATE_DEGRADED, SOURCE_DAY, self.day[1], ("day", self.day[0])
        return STATE_NO_FIX, None, None, None


class Output:
    """vehicle_output_node._tick / _bridged on the policy (pure) functions, in SITL time."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.track = TrackVelocity(window_s=20.0)
        self.status = None                   # (state, active, t)
        self.pos, self.pos_rx, self.sent_pos = None, None, None
        self.held, self.last_tx, self.bridging = None, None, False
        self.last_pos_tx = None
        self.gps_vel = None
        self.held_back = 0                   # positions held back by reacquire()
        self.counted_pos = None

    def ground_velocity(self, t):
        last = self.track.last_time()
        if last is None or t - last > 5.0:
            return None
        return self.track.velocity(t)

    def autopilot_velocity(self, t):
        last = self.track.last_time()
        if last is None or t - last > 5.0:
            return None
        return self.track.autopilot_velocity(t)

    def on_position(self, t, msg):
        self.pos, self.pos_rx = msg, t
        cov = msg.position_covariance
        self.track.add(msg.t_meas, msg.latitude, msg.longitude, math.sqrt(max(cov[0], cov[4])))
        return self.tick(t)

    def tick(self, t):
        st = self.status
        vel = self.gps_vel
        age = None if self.pos is None else t - self.pos.t_meas
        out = decide(self.cfg, st[0] if st else None, t - st[2] if st else None, self.pos,
                     t - self.pos_rx if self.pos else None, st[1] if st else None, vel, age,
                     self.ground_velocity(t), self.autopilot_velocity(t))
        out = self._bridged(out, t)
        if out is None:
            return None
        gated = reacquire(self.cfg, out, None if self.last_pos_tx is None else t - self.last_pos_tx)
        if gated is not out:                 # "no fix" at the tick rate, as the node
            if self.pos is not self.counted_pos:
                self.counted_pos = self.pos
                self.held_back += 1
            return gated
        if out.kind != KIND_NONE and not out.bridged:
            if self.pos is self.sent_pos:
                return None
            self.sent_pos = self.pos
            self.held = hold(out, t, self.ground_velocity(t))
            self.bridging = False
        if out.kind != KIND_NONE:
            self.last_tx = self.last_pos_tx = t
        return out

    def _bridged(self, out, t):
        if out.kind == KIND_FIX:
            self.held = self.last_tx = None
            self.bridging = False
            return out
        pending = (out.kind == KIND_ESTIMATED and self.pos is self.sent_pos) or (out.kind == KIND_NONE and out.soft)
        if not pending or self.held is None or self.cfg.bridge_max_s <= 0 or self.last_tx is None:
            if self.bridging and out.kind == KIND_NONE:
                self.bridging = False
            return out
        gap = t - self.last_tx
        if gap < (self.cfg.bridge_period_s if self.bridging else self.cfg.bridge_after_s):
            return None if out.kind == KIND_NONE else out
        b = bridge(self.cfg, self.held, t)
        if b.kind == KIND_NONE:
            self.bridging = False
            self.held = None
            return b
        self.bridging = True
        return b


# ----------------------------------------------------------------------------- the run
class Run:
    def __init__(self, vehicle, scenario, args, work):
        self.vehicle, self.scenario, self.a, self.work = vehicle, scenario, args, work
        self.rng = random.Random(args.seed)
        self.mission = MISSIONS[vehicle]
        if args.endurance > 0:
            if vehicle != "copter":
                raise SystemExit("--endurance: copter only")
            self.mission = ENDURANCE
        self.errors = VisionErrors("poor" if scenario == "poor" else "good", self.rng, args.max_refusals)
        self.est = Estimator()
        self.cfg = Config(forward_degraded=True, degraded_sigma_m=args.sigma, bridge_max_s=args.bridge_max_s,
                          reacquire_after_s=args.reacquire_after_s,
                          reacquire_vel_sigma_mps=args.reacquire_vel_sigma)
        self.cfg.validate()
        self.out = Output(self.cfg)
        self.truth_hist = []                 # (t, lat, lon, alt)
        self.samples = []
        self.sent = []                       # (t, kind, sigma, err to truth m or None)
        self.vision_log = []                 # (t_arr, err m) of the fixes delivered, after the loss
        self.t_loss = None                   # GPS lost (or spoof start)
        self.t_jam = None                    # GPS no longer received
        self.next_gps = self.next_frame = 0.0
        self.pending_frames = []             # (t_arrival, msg, err_m)
        self.burst_left = BURST_N
        self.utc0 = datetime.now(timezone.utc)
        self.live = None                     # live.jsonl for the plot (--viewer)
        self.last_status = 0.0
        self.last_sample = 0.0
        self.modes = []
        self.reached = []                    # (t, seq)
        self.seq = 0

    # --- truth
    def truth_at(self, t):
        h = self.truth_hist
        if not h:
            return None
        i = bisect.bisect_left([x[0] for x in h[-200:]], t) + max(0, len(h) - 200)
        if i <= 0:
            return h[0][1:]
        if i >= len(h):
            return h[-1][1:]
        a, b = h[i - 1], h[i]
        w = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
        return tuple(a[k] + w * (b[k] - a[k]) for k in (1, 2, 3))

    # --- NAVERA's inputs
    def gps_received(self, t):
        return self.t_jam is None or t < self.t_jam

    def gps_fix(self, t, truth):
        lat, lon = sv.offset_ll(truth[0], truth[1], self.rng.gauss(0, GPS_NOISE_M), self.rng.gauss(0, GPS_NOISE_M))
        if self.scenario == "spoof" and self.t_loss is not None:
            lat, lon = sv.offset_ll(lat, lon, SPOOF_RATE_MPS * (t - self.t_loss), 0.0)
        prev = self.truth_at(t - 1.0)
        vel = None
        if prev:
            n, e = sv.ne_from(prev[0], prev[1], truth[0], truth[1])
            vel = (n, e)
        return lat, lon, vel

    def vision_frame(self, t):
        """A photo taken now: queued for its arrival after the latency, or dropped (refused)."""
        rel = None if self.t_loss is None else t - self.t_loss
        if self.scenario.startswith("outage") and rel is not None:
            n = float(self.scenario[6:])
            if EVENT_AT_S <= rel < EVENT_AT_S + n:
                self.errors.next()
                return
        f = self.errors.next()
        if self.scenario == "burst" and rel is not None and rel >= EVENT_AT_S and self.burst_left > 0:
            self.burst_left -= 1
            f = (0.0, BURST_OFFSET_M, f[2] if f else 8.0)
        if f is None:
            return
        truth = self.truth_at(t)
        lat, lon = sv.offset_ll(truth[0], truth[1], f[1], f[0])
        sigma = max(DAY_SIGMA_FLOOR_M, f[2])
        lo, hi = self.a.latency
        msg = pos_msg(SOURCE_DAY, lat, lon, math.nan, sigma, t)
        self.pending_frames.append((t + self.rng.uniform(lo, hi), msg, math.hypot(f[0], f[1])))

    # --- one step
    def step(self, link):
        t = link.t
        if link.truth is None or t <= 0:
            return
        if not self.truth_hist or link.truth_ms / 1000.0 > self.truth_hist[-1][0]:
            self.truth_hist.append((link.truth_ms / 1000.0,) + tuple(link.truth))
            if len(self.truth_hist) > 3000:
                del self.truth_hist[:1000]
        truth = self.truth_at(t)
        new_pos = []
        if self.gps_received(t) and t >= self.next_gps:
            self.next_gps = t + 0.16          # 5+ Hz: ArduPilot wants < 245 ms between GPS messages
            lat, lon, vel = self.gps_fix(t, truth)
            self.est.on_gps(t, lat, lon, truth[2], vel)
            self.out.gps_vel = vel
            new_pos.append("gps")
        if t >= self.next_frame:
            self.next_frame = t + self.a.frame_period
            self.vision_frame(t)
        for item in [x for x in self.pending_frames if x[0] <= t]:
            self.pending_frames.remove(item)
            self.est.on_day(t, item[1])
            if self.t_jam is not None and t >= self.t_jam:
                self.vision_log.append((t, item[2]))
            new_pos.append("day")
        state, active, msg, key = self.est.elect(t)
        to_send = []
        if t - self.last_status >= 0.2 or new_pos:
            self.out.status = (state, active, t)
            self.last_status = t
        if msg is not None and (self.est.published is None or self.est.published[0] != key):
            self.est.published = (key, msg)
            r = self.out.on_position(t, msg)
            if r is not None:
                to_send.append(r)
        if not to_send and t - getattr(self, "_last_tick", 0.0) >= 0.2:
            self._last_tick = t
            r = self.out.tick(t)
            if r is not None:
                to_send.append(r)
        for o in to_send:
            self.send(link, o, t, truth)

    def send(self, link, o, t, truth):
        f = mavlink_out.gps_input_fields(o, self.utc0 + timedelta(seconds=t - o.age_s))
        link.mav.mav.gps_input_send(**f)
        err = verr = None
        if o.kind != KIND_NONE:
            tt = self.truth_at(t - o.age_s)
            n, e = sv.ne_from(tt[0], tt[1], o.lat, o.lon)
            err = math.hypot(n, e)
            prev = self.truth_at(t - 1.0)
            if o.has_velocity and prev is not None:
                tn, te = sv.ne_from(prev[0], prev[1], truth[0], truth[1])     # true velocity over the last 1 s
                verr = math.hypot(o.vel_n_mps - tn, o.vel_e_mps - te)
        sig_v = f["speed_accuracy"] if not f["ignore_flags"] & mavlink_out.IGNORE_SPEED_ACCURACY else None
        self.sent.append((round(t, 2), o.kind, round(o.sigma_h_m, 1) if o.kind != KIND_NONE else None,
                          round(err, 1) if err is not None else None, bool(o.bridged),
                          round(sig_v, 2) if sig_v is not None else None,
                          round(verr, 2) if verr is not None else None))

    def sample(self, link):
        t = link.t
        gp = link.last.get("GLOBAL_POSITION_INT")
        ek = link.last.get("EKF_STATUS_REPORT")
        mc = link.last.get("MISSION_CURRENT")
        if gp is None or link.truth is None:
            return
        self.samples.append(dict(
            t=round(t, 2), tlat=link.truth[0], tlon=link.truth[1], talt=round(link.truth[2] - HOME[2], 1),
            elat=gp.lat / 1e7, elon=gp.lon / 1e7, ealt=round(gp.relative_alt / 1000.0, 1),
            seq=mc.seq if mc else None, mode=link.mode_name(), armed=link.armed(),
            pv=round(ek.pos_horiz_variance, 3) if ek else None, vv=round(ek.velocity_variance, 3) if ek else None,
            ekf_flags=ek.flags if ek else None))
        lp, ss = link.last.get("LOCAL_POSITION_NED"), link.last.get("SIM_STATE")
        if lp is not None and ss is not None:      # the autopilot's velocity vs the simulator's (m/s)
            self.samples[-1].update(evn=round(lp.vx, 2), eve=round(lp.vy, 2), tvn=round(ss.vn, 2),
                                    tve=round(ss.ve, 2), lpx=round(lp.x, 2), lpy=round(lp.y, 2),
                                    lpt=lp.time_boot_ms)
        if self.live is not None:
            s = self.samples[-1]
            n, e = sv.ne_from(s["tlat"], s["tlon"], s["elat"], s["elon"])
            last = self.sent[-1] if self.sent else None
            self.live.write(json.dumps(dict(
                t=s["t"], ekf_err=round(math.hypot(n, e), 1), mode=s["mode"],
                navera_err=last[3] if last else None, navera_sigma=last[2] if last else None,
                gps=self.gps_received(t) and not self.est.refused, scenario=self.scenario)) + "\n")
            self.live.flush()

    def viewer(self, port):
        """MAVProxy map + console on the vehicle's SERIAL1 (TCP port + 2) and the live error plot (--viewer)."""
        procs = []
        mavproxy = [sys.executable, "-m", "MAVProxy.mavproxy"] if self.a.mavproxy == "module" else [self.a.mavproxy]
        for name, cmd in (("mavproxy", mavproxy + ["--master", f"tcp:127.0.0.1:{port + 2}", "--map", "--console",
                                                   "--non-interactive",              # no stdin in the background
                                                   f"--state-basedir={self.work}"]),
                          ("plot", [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                 "sitl_live_plot.py"), self.live.name])):
            try:
                procs.append(sv.run(cmd, self.work, open(os.path.join(self.work, name + ".log"), "w")))
            except OSError as e:                # no display tool: the run itself goes on
                print(f"  viewer: {name} not started ({e})")
        return procs

    def fly(self):
        a = self.a
        params = dict(sv.NAVERA_PARAMS, **self.mission["params"])
        params.update(a.set)
        os.makedirs(self.work, exist_ok=True)
        sitl, port = sv.start_sitl(self.vehicle, os.path.expanduser(a.ardupilot), self.work, params,
                                   instance=a.instance, speedup=a.speedup)
        self.live = open(os.path.join(self.work, "live.jsonl"), "w") if a.viewer else None
        views = []
        try:
            time.sleep(4)
            if a.viewer:
                views = self.viewer(port)
            link = sv.Link(port)
            link.speedup = a.speedup
            self.link = link
            link.request({mavutil.mavlink.MAVLINK_MSG_ID_SIM_STATE: 10,
                          mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT: 5,
                          mavutil.mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED: 5,
                          mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE: 25,
                          mavutil.mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT: 2,
                          mavutil.mavlink.MAVLINK_MSG_ID_MISSION_CURRENT: 2})
            self._loop(link)
            link.mav.close()
        finally:
            if views:
                time.sleep(self.a.viewer_hold_s)       # let the watcher see the end
            for p in views:
                sv.stop(p)
            sv.stop(sitl)

    def idle(self, link):
        link.pump(0.02)
        self.step(link)
        if link.t - self.last_sample >= 0.2:
            self.last_sample = link.t
            self.sample(link)
            mode = link.mode_name()
            if not self.modes or self.modes[-1][1] != mode:
                self.modes.append((round(link.t, 1), mode))
                print(f"    mode {link.t:7.1f}: {mode}")
        while link.inbox:
            m = link.take(("MISSION_ITEM_REACHED",))
            if m is None:
                break
            self.reached.append((round(link.t, 1), m.seq))
        mc = link.last.get("MISSION_CURRENT")
        if mc is not None:
            self.seq = mc.seq

    def until(self, link, cond, timeout_s, what):
        end = time.time() + timeout_s
        while time.time() < end:
            self.idle(link)
            if cond():
                return
        raise RuntimeError(f"timed out waiting for {what}")

    def _loop(self, link):
        v = self.vehicle
        self.until(link, lambda: any("origin set" in x for _, x in link.texts), 120, "EKF origin")
        m = self.mission
        items = [sv.mission_item(0, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, HOME[0], HOME[1], 0)]
        items.append(sv.mission_item(1, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, HOME[0], HOME[1],
                                     m["alt"] if v == "copter" else m["params"]["TKOFF_ALT"],
                                     p1=15.0 if v == "plane" else 0.0))
        self.wps = []
        for n, e in m["wps"]:
            lat, lon = sv.offset_ll(HOME[0], HOME[1], n, e)
            self.wps.append((lat, lon))
            items.append(sv.mission_item(len(items), mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, lat, lon, m["alt"]))
        if self.a.endurance > 0:              # the diamond again and again: back to its second corner
            items.append(sv.mission_item(len(items), mavutil.mavlink.MAV_CMD_DO_JUMP, p1=3, p2=-1))
        items.append(sv.mission_item(len(items), mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH))
        self.rtl_seq = len(items) - 1
        link.inbox.clear()
        sv.upload_mission(link, items, lambda: self.idle(link))
        arm_mode = "GUIDED" if v == "copter" else "AUTO"
        end = time.time() + 120
        while not link.armed():
            if time.time() > end:
                raise RuntimeError("could not arm")
            link.set_mode(v, arm_mode)
            link.arm()
            t_try = time.time() + 3
            while time.time() < t_try and not link.armed():
                self.idle(link)
        if v == "copter":
            link.set_mode(v, "AUTO")
            self.until(link, lambda: link.mode_name() == "AUTO", 20, "AUTO")
            link.command(mavutil.mavlink.MAV_CMD_MISSION_START, 0, 0)
        print(f"  armed at {link.t:.1f} s; flying to waypoint 1")
        # first waypoint (seq 2) reached: the mission is on the leg to seq 3
        self.until(link, lambda: self.seq >= 3, 600, "waypoint 1")
        self.t_loss = link.t
        self.t_jam = link.t + (SPOOF_JAM_AFTER_S if self.scenario == "spoof" else 0.0)
        print(f"  {'GPS spoof starts' if self.scenario == 'spoof' else 'GPS lost'} at {self.t_loss:.1f} s")
        t_rtl = None
        limit = time.time() + self.a.max_s
        last_rtl_try = 0.0
        while time.time() < limit:
            self.idle(link)
            if self.a.endurance > 0 and t_rtl is None and link.t > self.t_loss + self.a.endurance \
                    and time.time() - last_rtl_try > 3.0 and link.armed() and link.mode_name() == "AUTO":
                last_rtl_try = time.time()           # endurance over: home on vision
                link.set_mode(v, "RTL")
            if self.seq >= self.rtl_seq or link.mode_name() == "RTL":
                t_rtl = t_rtl or link.t
            if v == "copter" and not link.armed() and link.t > self.t_loss + 5:
                break                        # landed (mission RTL, or a failsafe LAND)
            if v == "plane":
                if t_rtl is not None and link.t - t_rtl > self.a.rtl_watch_s:
                    break
                if link.truth and link.truth[2] - HOME[2] < 3.0 and link.t > self.t_loss + 5:
                    print("  plane on the ground")
                    break
        end = time.time() + 2.0                # the last state (disarmed, landed)
        while time.time() < end:
            self.idle(link)
        self.sample(link)
        self.t_end = link.t
        self.t_rtl = t_rtl

    # ------------------------------------------------------------------------- analysis
    def blocks(self, after_loss):
        """Endurance: per BLOCK_S after the loss, the autopilot's position / velocity error, its
        position resets and the vision positions / velocities sent."""
        out = []
        t0 = self.t_loss
        n = int(max((s["t"] for s in after_loss), default=t0) - t0) // int(BLOCK_S) + 1
        for k in range(n):
            lo, hi = t0 + k * BLOCK_S, t0 + (k + 1) * BLOCK_S
            ss = [s for s in after_loss if lo <= s["t"] < hi and s["armed"]]
            ev = [s for s in ss if "evn" in s]
            pe = [_dist(sv.ne_from(HOME[0], HOME[1], s["elat"], s["elon"]),
                        sv.ne_from(HOME[0], HOME[1], s["tlat"], s["tlon"])) for s in ss]
            ve = [_vel_err(s) for s in ev]
            sent = [x for x in self.sent if lo <= x[0] < hi and x[1] == KIND_ESTIMATED]
            out.append(dict(block_min=f"{k * BLOCK_S / 60:.0f}-{(k + 1) * BLOCK_S / 60:.0f}",
                            ekf_err=[_q(pe, 0.5), _q(pe, 0.9), _q(pe, 1.0)],
                            ekf_vel_err=[_q(ve, 0.5), _q(ve, 0.9), _q(ve, 1.0)],
                            resets=len(_resets(ev)), modes=sorted({s["mode"] for s in ss}),
                            sent_err=[_q([x[3] for x in sent], 0.5), _q([x[3] for x in sent], 0.9)],
                            sent_vel_err=[_q([x[6] for x in sent], 0.5), _q([x[6] for x in sent], 0.9)],
                            sent_vel_sigma=_q([x[5] for x in sent], 0.5)))
        return out

    def analyse(self):
        S = self.samples
        lat0, lon0 = HOME[0], HOME[1]

        def ne(lat, lon):
            return sv.ne_from(lat0, lon0, lat, lon)
        denied = [s for s in S if self.t_jam is not None and s["t"] >= self.t_jam]
        after_loss = [s for s in S if self.t_loss is not None and s["t"] >= self.t_loss]
        ekf_err = [math.hypot(*[x - y for x, y in zip(ne(s["elat"], s["elon"]), ne(s["tlat"], s["tlon"]))])
                   for s in after_loss if s["armed"]]
        wps = [ne(*w) for w in self.wps]
        # cross-track per GPS-denied leg (seq k: leg from wp k-3 to wp k-2 in self.wps)
        legs = {}
        for s in denied:
            k = s["seq"]
            if s["mode"] != "AUTO" or k is None or k < 3 or k - 2 >= len(wps):
                continue
            a, b = wps[k - 3], wps[k - 2]
            p = ne(s["tlat"], s["tlon"])
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            along = (p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1]
            if along < self.mission["corner_m"] or along > L - self.mission["corner_m"]:
                continue
            xt = abs((p[0] - a[0]) * u[1] - (p[1] - a[1]) * u[0])
            legs.setdefault(k, []).append(xt)
        xt_all = [x for v in legs.values() for x in v]
        # closest approach of the truth to each waypoint targeted after the GPS loss
        approach = {}
        for k in range(3, 2 + len(wps)):
            pts = [ne(s["tlat"], s["tlon"]) for s in after_loss if s["seq"] in (k, k + 1)]
            if pts:
                w = wps[k - 2]
                approach[k - 1] = round(min(math.hypot(p[0] - w[0], p[1] - w[1]) for p in pts), 1)
        reached = sorted({q for _, q in self.reached if self.t_loss and _ >= self.t_loss})
        completed = self.rtl_seq - 1 in reached or (self.t_rtl is not None and any(
            m == "RTL" for _, m in self.modes) and self.seq >= self.rtl_seq)
        texts = [(round(t / 1000.0, 1), x) for t, x in self.link.texts]
        keys = ("EKF", "GPS", "ailsafe", "Glitch", "glitch", "variance", "aiding", "Lost", "lane", "Land",
                "yaw", "Crash", "crash", "AHRS", "DCM")
        notable = [(t, x) for t, x in texts if self.t_loss and t >= self.t_loss - 1 and any(k in x for k in keys)]
        res = dict(vehicle=self.vehicle, scenario=self.scenario, params=self.a.set, sigma=self.a.sigma,
                   bridge_max_s=self.a.bridge_max_s, reacquire=[self.a.reacquire_after_s, self.a.reacquire_vel_sigma],
                   all_texts=texts,
                   latency=self.a.latency, t_loss=self.t_loss, t_jam=self.t_jam, t_end=self.t_end,
                   modes=self.modes, reached=self.reached, notable_texts=notable,
                   ekf_err_median=_q(ekf_err, 0.5), ekf_err_p90=_q(ekf_err, 0.9), ekf_err_max=_q(ekf_err, 1.0),
                   xtrack_median=_q(xt_all, 0.5), xtrack_p90=_q(xt_all, 0.9), xtrack_max=_q(xt_all, 1.0),
                   xtrack_per_leg={k: [_q(v, 0.5), _q(v, 1.0)] for k, v in legs.items()},
                   wp_closest=approach, completed=bool(completed),
                   pos_var_max=max((s["pv"] for s in after_loss if s["pv"] is not None), default=None),
                   vel_var_max=max((s["vv"] for s in after_loss if s["vv"] is not None), default=None))
        vis = [e for _, e in self.vision_log]
        res["vision_fixes_after_jam"] = len(vis)
        res["vision_err_median"], res["vision_err_p90"] = _q(vis, 0.5), _q(vis, 0.9)
        sent_est = [x for x in self.sent if x[1] == KIND_ESTIMATED and self.t_jam and x[0] >= self.t_jam]
        res["sent_err_median"] = _q([x[3] for x in sent_est], 0.5)
        res["sent_err_p90"] = _q([x[3] for x in sent_est], 0.9)
        res["sent_sigma_median"] = _q([x[2] for x in sent_est], 0.5)
        res["no_fix_sent"] = sum(1 for x in self.sent if x[1] == KIND_NONE and self.t_jam and x[0] >= self.t_jam)
        res["bridged_sent"] = sum(1 for x in sent_est if x[4])
        res["held_back"] = self.out.held_back
        # the velocity given with the vision positions: error vs the truth, and vs its stated accuracy
        vel = [(x[5], x[6]) for x in sent_est if x[6] is not None]
        res["vel_sent"] = len(vel)
        res["vel_unknown_sent"] = sum(1 for x in sent_est if x[6] is None)
        res["vel_err_median"], res["vel_err_p90"] = _q([v[1] for v in vel], 0.5), _q([v[1] for v in vel], 0.9)
        res["vel_err_max"] = _q([v[1] for v in vel], 1.0)
        res["vel_sigma_median"] = _q([v[0] for v in vel], 0.5)
        # per axis 1-sigma stated: the 2D error is within 2.45 sigma 95 % of the time if honest
        res["vel_within_2_45_sigma"] = round(sum(1 for s_, e in vel if e <= 2.45 * s_) / len(vel), 3) if vel else None
        res["navera_events"] = self.est.events
        spd = []
        for s0, s1 in zip(denied, denied[5:]):
            if s0["mode"] == "AUTO" and s0["seq"] is not None and 3 <= s0["seq"] < self.rtl_seq and s1["t"] > s0["t"]:
                spd.append(_dist(ne(s1["tlat"], s1["tlon"]), ne(s0["tlat"], s0["tlon"])) / (s1["t"] - s0["t"]))
        res["leg_speed_median"] = _q(spd, 0.5)
        ev = [s for s in after_loss if "evn" in s and s["armed"]]
        res["ekf_vel_err_median"] = _q([_vel_err(s) for s in ev], 0.5)
        res["ekf_vel_err_p90"] = _q([_vel_err(s) for s in ev], 0.9)
        res["ekf_vel_err_max"] = _q([_vel_err(s) for s in ev], 1.0)
        res["ekf_pos_resets"] = len(_resets(ev))
        if self.a.endurance > 0:
            res["blocks"] = self.blocks(after_loss)
        if self.vehicle == "copter":
            air = False
            for s in after_loss:
                air = air or s["talt"] > 5.0
                if air and s["talt"] < 1.0:
                    res["touchdown_t"] = s["t"]
                    res["touchdown_mode"] = s["mode"]
                    res["landing_from_home_m"] = round(math.hypot(*ne(s["tlat"], s["tlon"])), 1)
                    break
            res["landed"] = "touchdown_t" in res
        else:
            rtl = [s for s in S if self.t_rtl and s["t"] >= self.t_rtl + 20]
            if rtl:
                pts = [ne(s["tlat"], s["tlon"]) for s in rtl]
                c = (statistics.mean(p[0] for p in pts), statistics.mean(p[1] for p in pts))
                res["rtl_centre_from_home_m"] = round(math.hypot(*c), 1)
            res["final_alt_m"] = S[-1]["talt"] if S else None
        if self.scenario == "spoof":
            ref = [x for x in self.est.events if "refused" in x[1]]
            res["spoof_refused_after_s"] = round(ref[0][0] - self.t_loss, 1) if ref else None
            res["spoof_offset_at_refusal_m"] = round(SPOOF_RATE_MPS * (ref[0][0] - self.t_loss), 1) if ref else None
            pre = [s for s in S if self.t_loss <= s["t"] < (self.t_jam or 1e9)]
            res["spoof_max_ekf_err"] = _q([_dist(ne(s["elat"], s["elon"]), ne(s["tlat"], s["tlon"])) for s in pre], 1.0)
        return res


def _vel_err(s):
    """The autopilot's horizontal velocity error (m/s) in one sample."""
    return math.hypot(s["evn"] - s["tvn"], s["eve"] - s["tve"])


def _resets(samples, jump_m=3.0):
    """EKF position resets: a step of the autopilot's local position that its own velocity does not
    explain (> jump_m between two samples); [(t, step m)]."""
    out = []
    for a, b in zip(samples, samples[1:]):
        dt = (b["lpt"] - a["lpt"]) / 1000.0
        if dt <= 0 or dt > 1.0:
            continue
        d = math.hypot(b["lpx"] - a["lpx"] - 0.5 * (a["evn"] + b["evn"]) * dt,
                       b["lpy"] - a["lpy"] - 0.5 * (a["eve"] + b["eve"]) * dt)
        if d > jump_m:
            out.append((b["t"], round(d, 1)))
    return out


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _q(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 1)


def parse_set(s):
    out = {}
    for kv in filter(None, (s or "").split(",")):
        k, v = kv.split("=")
        out[k.strip()] = float(v) if "." in v else int(v)
    return out


def summarise(out_dir):
    """A markdown table of every <vehicle>_<scenario>*.json result in out_dir."""
    print("| Run | Params | EKF err med / p90 / max (m) | Cross-track med / p90 / max (m) | Leg speed (m/s) | "
          "WP closest (m) | Mission done | End | Failsafes / EKF messages | Velocity sent: err med / p90 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name in sorted(os.listdir(out_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(out_dir, name)) as f:
            r = json.load(f)["result"]
        if "error" in r:
            print(f"| {name[:-5]} | | ERROR {r['error']} | | | | | | | |")
            continue
        if r["vehicle"] == "copter":
            end = (f"landed {r.get('landing_from_home_m')} m from home in {r.get('touchdown_mode')}"
                   if r.get("landed") else "not landed")
        else:
            end = f"RTL loiter centre {r.get('rtl_centre_from_home_m')} m from home, alt {r.get('final_alt_m')} m"
        keys = ("ailsafe", "aiding", "Glitch", "variance", "Crash", "DCM")
        msgs = sorted({x for _, x in r["notable_texts"] if any(k in x for k in keys)})
        wp = ", ".join(f"{v:.0f}" for v in r["wp_closest"].values())
        spoof = ""
        if r["scenario"] == "spoof":
            spoof = (f"; GPS refused after {r.get('spoof_refused_after_s')} s at {r.get('spoof_offset_at_refusal_m')} m"
                     f" offset, EKF err max {r.get('spoof_max_ekf_err')} m before the jam")
        setting = r["params"] or ""
        if r.get("bridge_max_s", 10.0) != 10.0:
            setting = f"{setting} bridge {r['bridge_max_s']:g} s"
        if r.get("vision_velocity"):
            setting = f"{setting} + track velocity sent"
        if r.get("reacquire") and r["reacquire"] != [Config.reacquire_after_s, Config.reacquire_vel_sigma_mps]:
            setting = f"{setting} reacquire {r['reacquire'][0]:g} s / {r['reacquire'][1]:g} m/s"
        vel = ""
        if r.get("vel_sent") is not None:
            vel = (f"{r['vel_err_median']} / {r['vel_err_p90']} m/s (σ {r['vel_sigma_median']}, "
                   f"{r['vel_within_2_45_sigma']} within 2.45σ; {r['vel_unknown_sent']} unknown, "
                   f"{r['held_back']} held back)")
        print(f"| {name[:-5]} | {setting} | {r['ekf_err_median']} / {r['ekf_err_p90']} / {r['ekf_err_max']} | "
              f"{r['xtrack_median']} / {r['xtrack_p90']} / {r['xtrack_max']} | {r.get('leg_speed_median')} | {wp} | "
              f"{'yes' if r['completed'] else 'no'} | {end} | {'; '.join(msgs) or 'none'}{spoof} | {vel} |")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--summarise":
        summarise(sys.argv[2])
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vehicle", choices=sorted(MISSIONS), default="copter")
    ap.add_argument("--scenarios", default="nominal")
    ap.add_argument("--set", type=parse_set, default={}, help="extra autopilot parameters K=V,...")
    ap.add_argument("--sigma", type=float, default=30.0, help="NAVERA_DEGRADED_SIGMA_M (m)")
    ap.add_argument("--latency", type=lambda s: tuple(float(x) for x in s.split(",")), default=(0.3, 1.0))
    ap.add_argument("--frame-period", type=float, default=1.0)
    ap.add_argument("--bridge-max-s", type=float, default=10.0, help="NAVERA_BRIDGE_MAX_S (0 = no bridge)")
    ap.add_argument("--reacquire-after-s", type=float, default=Config.reacquire_after_s,
                    help="policy.Config.reacquire_after_s (0 = never hold back after a gap)")
    ap.add_argument("--reacquire-vel-sigma", type=float, default=Config.reacquire_vel_sigma_mps)
    ap.add_argument("--endurance", type=float, default=0.0,
                    help="Copter: fly the Isaac endurance diamond (250 m, 8 m/s, 500 m) for S s after the loss, then RTL")
    ap.add_argument("--max-refusals", type=int, default=0,
                    help="cut the replayed refusal runs to this many photos (0 = as measured); the Isaac "
                         "endurance flight had no vision gap above 7 s: --frame-period 0.6 --max-refusals 5")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--instance", type=int, default=5)
    ap.add_argument("--speedup", type=float, default=1.0)
    ap.add_argument("--max-s", type=float, default=900.0, help="wall-clock limit after the GPS loss")
    ap.add_argument("--rtl-watch-s", type=float, default=90.0, help="Plane: RTL time watched")
    ap.add_argument("--ardupilot", default="~/ardupilot")
    ap.add_argument("--out", default=os.path.expanduser("~/.navera_sim/sitl_closed_loop"))
    ap.add_argument("--tag", default="")
    ap.add_argument("--viewer", action="store_true",
                    help="to watch it: MAVProxy --map --console on SERIAL1 + a live error plot (needs a display)")
    ap.add_argument("--mavproxy", default="mavproxy.py", help="MAVProxy executable, or 'module'")
    ap.add_argument("--viewer-hold-s", type=float, default=20.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for sc in a.scenarios.split(","):
        if sc not in SCENARIOS:
            raise SystemExit(f"unknown scenario {sc} ({', '.join(SCENARIOS)})")
        name = f"{a.vehicle}_{sc}{'_' + a.tag if a.tag else ''}"
        print(f"[{name}]")
        run = Run(a.vehicle, sc, a, os.path.join(a.out, name))
        try:
            run.fly()
            res = run.analyse()
        except Exception as e:                # a run that fails to start is reported, not hidden
            print(f"  ERROR {e}")
            res = dict(vehicle=a.vehicle, scenario=sc, error=str(e))
        with open(os.path.join(a.out, name + ".json"), "w") as f:
            json.dump(dict(result=res, samples=run.samples, sent=run.sent), f)
        print(json.dumps({k: v for k, v in res.items() if k not in ("modes", "reached")}, indent=None)[:3000])
        rows.append(res)
    print("\nvehicle  scenario   EKF err med/p90/max   xtrack med/p90/max   done  end  notes")
    for r in rows:
        if "error" in r:
            print(f"{r['vehicle']:8} {r['scenario']:10} ERROR {r['error']}")
            continue
        end = (f"land {r.get('landing_from_home_m')} m in {r.get('touchdown_mode')}" if r["vehicle"] == "copter"
               else f"RTL ctr {r.get('rtl_centre_from_home_m')} m")
        print(f"{r['vehicle']:8} {r['scenario']:10} {r['ekf_err_median']}/{r['ekf_err_p90']}/{r['ekf_err_max']}"
              f"   {r['xtrack_median']}/{r['xtrack_p90']}/{r['xtrack_max']}   {r['completed']}  {end}  "
              f"modes={[m for _, m in r['modes']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

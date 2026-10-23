#!/usr/bin/env python3
"""Replay the day node (day_subscriber's own code, no ROS graph) on REAL camera frames recorded by
screen_flight.py --record, with and without the gyro heading carry (day_pkg.gyro_heading).

    python3 navera_tools/bench/replay_gyro_heading.py REC_DIR [REC_DIR ...] --area AREA \
        [--gps-denied-at 30] [--bias 0.05] [--json out.json]

Each frame goes through DaySubscriber._process_frame as in flight: search around the node's own
carried position, the SIFT matcher (retry 4000, as shipped for "local"), the gates, the carry. GPS
(the recorded truth) is the prior until --gps-denied-at, then nothing from the truth is used.
The frames carry no attitude (attitude_source "none", as on the bench: the screen does not turn).

What is simulated: the bench flies a 900 m circle with the map north-up on the screen, so the
recorded frames do not turn with the route. The vehicle's heading is the route's; the gyro gives its
rate (+ --bias deg/s, + white noise --noise deg/s at 50 Hz); the heading vision measures on a fix is
the route's plus that frame's measured rotation error (fitted rotation - the bench's calibrated
rotation): the vision rotation noise is the real one.

Per run and arm: frames after GPS loss with an output, output error median / p90 / max, published
measured fixes, wrong ones (> 50 m), outputs outside 3 sigma.
"""
import argparse
import collections
import json
import math
import os
import sys
import threading
import time as _time
from types import SimpleNamespace

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common")):
    sys.path.insert(0, p)

from builtin_interfaces.msg import Time  # noqa: E402
from navera_msgs.msg import PositionEstimate  # noqa: E402

import day_pkg.nodes.day_subscriber as ds  # noqa: E402
from day_pkg.fix_sigma import SigmaCalibration  # noqa: E402
from day_pkg.frame_odometry import FrameOdometry  # noqa: E402
from day_pkg.gyro_heading import CourseReset, GyroHeading  # noqa: E402
from day_pkg.local_matcher import LocalMatcher  # noqa: E402
from day_pkg.vision_nav import VisionNavigator  # noqa: E402
from navera_common.sensor_history import History  # noqa: E402
from navera_common.track import TrackVelocity  # noqa: E402

EPOCH = 1.8e9                  # frame times are bench seconds: shifted to a plausible clock


class Clock:
    now = EPOCH

    @classmethod
    def time(cls):
        return cls.now

    def strftime(self, *a):
        return _time.strftime(*a)


class Log:
    def info(self, *a, **k): pass
    warn = warning = error = debug = info


class Pub:
    def __init__(self, sink=None, topic_name="x"):
        self.sink, self.topic_name = sink, topic_name

    def publish(self, m):
        if self.sink is not None:
            self.sink.append(m)


class Prior:
    """The arbiter's GPS: the recorded truth while the replay says GPS is trusted."""
    def __init__(self):
        self.pos = None

    def fresh(self, now=None):
        return self.pos

    def update(self, lat, lon, valid, measured=True, now=None):
        return bool(valid)

    def arbiter(self, *a, **k):
        pass


def make_node(matcher, gyro: bool, est_sink):
    """A DaySubscriber with the shipped parameter defaults and stubbed ROS I/O."""
    n = ds.DaySubscriber.__new__(ds.DaySubscriber)
    n.get_logger = Log
    n.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(
        to_msg=lambda: Time(sec=int(Clock.now), nanosec=int((Clock.now % 1) * 1e9))))
    for name in ("pub_fix", "pub_status", "pub_vision_alt", "pub_done"):
        setattr(n, name, Pub())
    n.pub_est = Pub(est_sink)
    n.conf_threshold, n.antijump_enabled, n.max_consecutive_rejects = 0.75, True, 3
    n.max_dead_reckon_s, n.dr_max_sigma_m = 120.0, 500.0
    n.track = TrackVelocity(accel_mps2=0.25)
    n._track_heading = n._dr_sigma = n._anchor_sigma = None
    n.gyro = GyroHeading(0.1, 0.02, 2.0, 10.0) if gyro else None
    # the GPS course reset as shipped; no mount yaw in the bench's meta: the offset is learned from vision
    n.course, n._mount_yaw = (CourseReset() if gyro else None), None
    n.gyro_min_inliers = 20
    n.local_min_radius_m, n.search_k, n.gate_k, n.strong_inliers = 80.0, 3.0, 3.0, 100
    n.strong_gate_k, n.min_spread, n.height_retry_after = 6.0, 0.25, 3
    n.map_bias, n.vo, n._vo_step, n._doubted = VisionNavigator(), FrameOdometry(), None, None
    n._carry = n._vel_epoch = None
    n._gps_hist = History(maxlen=600, max_gap_s=1.5)
    n.allow_global_search, n.max_speed_mps, n.gate_margin_m = False, 30.0, 250.0
    n._frame_count = n._success_count = n._skip_count = n._reject_count = 0
    n._anchor_lat = n._anchor_lon = n._anchor_time = n._last_measured_time = None
    n._rejects_in_row, n._anchor_saved_at = 0, 0.0
    n.matcher_mode, n.camera_hfov_deg = "local", float("nan")
    n.local_sigma_m, n.local_sigma_floor_m, n.frame_time_sigma_s, n.attitude_sigma_deg = 30.0, 5.0, 0.05, 0.5
    n.sigma_cal = SigmaCalibration(30.0, 15)
    n._last_fix_sigma, n.local_max_radius_m, n.local_scale_tol_max = 30.0, 600.0, 0.35
    n.local_heading_tol_deg, n.heading_search, n.alt_min_inliers = 20.0, False, 20
    n._alt_candidate = n._check_fix = None
    n._gps_was_trusted, n.calib_period_s, n.calib_radius_m, n._last_calib = False, 2.0, 600.0, 0.0
    n.local, n.shadow_mode = matcher, False
    n._gps_prior = Prior()
    # the camera-delay estimation is not what this replay measures: inert, nothing applied
    n.latency_cal = SimpleNamespace(add_gps=lambda *a: None, add_fix=lambda *a: None, freeze=lambda *a: None,
                                    correction=lambda: 0.0, nominal=0.0, state=lambda: {"applied_s": None})
    n.auto_latency, n._latency_applied, n.latency_rollback_s = False, None, 0.0
    n._dr_why = ""
    n._gps_pending, n._busy_lock = collections.deque(), threading.Lock()   # GPS read in its own thread
    return n


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(q[0]))
    return math.hypot(de, dn)


def run(rec, matcher, gyro, a, seed=11):
    meta_rows = [json.loads(line) for line in open(os.path.join(rec, "frames.jsonl"))]
    meta_rows = [m for m in meta_rows if m.get("mpp") and m.get("truth")]
    speed = float(meta_rows[0]["speed"])
    hdg = lambda t: (90.0 - math.degrees(speed / a.radius * t)) % 360.0     # noqa: E731  route heading
    rng = np.random.default_rng(seed)
    est = []
    n = make_node(matcher, gyro, est)
    cur = {}
    real_locate = matcher.locate

    def locate(img, *args, **kw):
        if kw.get("heading_deg") is not None:       # a heading in the route's frame -> the bench frame's
            kw = dict(kw, heading_deg=(kw["heading_deg"] - hdg(cur["t"]) + cur["rot"]) % 360.0)
        r = real_locate(img, *args, **kw)
        if r.get("rotation_deg") is not None:       # the vision heading: the route's + the real rotation error
            r = dict(r, rotation_deg=round((hdg(cur["t"]) + r["rotation_deg"] - cur["rot"]) % 360.0, 1))
        return r
    n.local = SimpleNamespace(locate=locate, tiles=matcher.tiles, scale_tol=matcher.scale_tol)
    n._frame_m_per_px = lambda img, meta: (cur["mpp"], None)
    gyro_t = [meta_rows[0]["t"] - 5.0]
    out = []
    for i, m in enumerate(meta_rows):
        img = cv2.imread(os.path.join(rec, m["file"]))
        if img is None:
            continue
        t = float(m["t"])
        if n.gyro is not None:                      # the gyro samples up to the frame (50 Hz)
            while gyro_t[0] < t + 0.3:
                gyro_t[0] += 0.02
                rate = -math.degrees(speed / a.radius) + a.bias + rng.normal(0.0, a.noise)
                n.gyro.add_rate(EPOCH + gyro_t[0], rate)
        cur.update(t=t, rot=float(m.get("rot_deg") or 0.0), mpp=float(m["mpp"]))
        truth = tuple(m["truth"])
        denied = t >= a.gps_denied_at
        Clock.now = EPOCH + t                       # the GPS at the frame's instant
        if not denied:
            n._gps_prior.pos = truth
            msg = PositionEstimate()
            msg.source, msg.valid, msg.mode = PositionEstimate.SOURCE_GPS, True, PositionEstimate.MODE_MEASURED
            msg.latitude, msg.longitude = truth
            msg.header.stamp = Time(sec=int(EPOCH + t), nanosec=int(((EPOCH + t) % 1) * 1e9))
            msg.position_covariance = [25.0, 0.0, 0.0, 0.0, 25.0, 0.0, 0.0, 0.0, 0.0]
            n.on_gps(msg)
        else:
            n._gps_prior.pos = None
        meta = dict(frame_id=i, image_stamp_ns=int((EPOCH + t) * 1e9), camera_type="day", lat=None, lon=None,
                    gps_valid=False, camera_hfov_deg=a.hfov or None, usable=True, straightened=False,
                    attitude_source="none", heading_deg=None, altitude_m=float(m["height_m"]))
        k = len(est)
        Clock.now = EPOCH + t + 0.3                 # processing after the exposure
        n._process_frame(i, img, meta)
        if not denied or m.get("truth_unc_m", 0.0) > 10.0:
            continue
        pub = [e for e in est[k:] if e.valid]
        if not pub:
            out.append(dict(t=t, err=None))
            continue
        e = pub[-1]
        err = metres((e.latitude, e.longitude), truth)
        sig = math.sqrt(e.position_covariance[0]) if e.position_covariance[0] > 0 else None
        out.append(dict(t=t, err=err, sigma=sig, measured=e.mode == PositionEstimate.MODE_MEASURED,
                        lost=m.get("phase") == "lost"))
        if a.verbose:
            print(f"  t {t:6.1f} {'fix' if out[-1]['measured'] else 'dr '} err {err:7.1f} sigma {sig}", flush=True)
    return out


def summary(rows):
    e = sorted(r["err"] for r in rows if r["err"] is not None)
    q = (lambda p: round(e[min(len(e) - 1, int(p * len(e)))], 1)) if e else (lambda p: None)
    meas = [r for r in rows if r["err"] is not None and r["measured"]]
    return {"frames": len(rows), "output": len(e), "median": q(0.5), "p90": q(0.9),
            "max": round(e[-1], 1) if e else None, "fixes": len(meas),
            "wrong": sum(r["err"] > 50.0 for r in meas),
            "wrong_t": [round(r["t"], 1) for r in meas if r["err"] > 50.0],
            "out3sigma": sum(1 for r in rows if r["err"] is not None and r["sigma"] and r["err"] > 3 * r["sigma"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--area", default=os.path.expanduser("~/.navera_sim/bench_2026-10-06/area"))
    ap.add_argument("--gps-denied-at", type=float, default=30.0, help="s: GPS no longer trusted")
    ap.add_argument("--radius", type=float, default=900.0, help="the bench circuit's radius, m")
    ap.add_argument("--hfov", type=float, default=0.0,
                    help="deg, given to the pose refinement; 0 = none (as on the bench: the screen is no ground)")
    ap.add_argument("--pose-tilt-guard", type=float, default=4.0,
                    help="deg, the matcher's pose_tilt_guard_deg (day_subscriber's default; 0 = off). Acts only with --hfov")
    ap.add_argument("--bias", type=float, default=0.05, help="simulated gyro bias, deg/s")
    ap.add_argument("--noise", type=float, default=0.1, help="simulated gyro noise per 50 Hz sample, deg/s")
    ap.add_argument("--arms", default="off,gyro")
    ap.add_argument("--json", default="")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    ds.time = Clock()                                # the node's clock is the replay's
    ds.state_store = SimpleNamespace(save=lambda *x, **k: None, load=lambda *x, **k: None)
    res = {}
    for d in a.dirs:
        name = os.path.basename(d.rstrip("/")).replace("rec_", "")
        for arm in a.arms.split(","):
            matcher = LocalMatcher(a.area, retry_features=4000, min_inliers=8, scale_tol=0.15,
                                   pose_tilt_guard_deg=a.pose_tilt_guard)
            rows = run(d, matcher, arm == "gyro", a)
            s = {"denied": summary(rows), "lost": summary([r for r in rows if r.get("lost")])}
            res.setdefault(name, {})[arm] = s
            print(f"{name:16s} {arm:5s} " + " | ".join(
                f"{ph}: " + " ".join(f"{k} {v}" for k, v in v_.items()) for ph, v_ in s.items()), flush=True)
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()

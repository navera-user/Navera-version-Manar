#!/usr/bin/env python3
"""Replay a REAL recorded flight (camera + IMU + GNSS + RTK truth) through NAVERA's day chain.

    python3 navera_tools/bench/replay_flight_dataset.py FLIGHT_DIR --area AREA_IMAGES_DIR \
        --site am|hk [--gps-denied-at 120] [--arm imu|gyro|dr] [--json out.json]

FLIGHT_DIR is made by mars_lvig_extract.py (frames/, frames.csv, sensors.npz). The chain is the
product's own code, wired in-process exactly as the ROS graph wires it, on a virtual clock:

  camera side   navera_common.frame_builder.FrameBuilder (undistort, IMU straightening, tilt and
                rate gates, heading) + navera_common.altitude.AltitudeEstimator (height above
                take-off = the vehicle's barometer, GPS altitude while GPS lasts, vision heights
                published back by the day node; with --terrain the map's DEM under the arbiter's
                position, the drone's home = its take-off point), as camera_pkg/live_camera.py does; frames are
                offered at most fps (1 Hz, live_camera's default) and only after the previous
                frame's ack (back-pressure): a frame that takes 1.4 s to process delays the next.
  day_pkg       DaySubscriber, built by its own __init__ (every shipped parameter default; the
                matcher is "auto": DISK + LightGlue on the GPU, SIFT fallback); frames enter
                through _dispatch (auto camera latency, GPS check frames while GPS is trusted:
                sigma calibration, map bias, latency samples, height calibration; then the
                tracking, gates, pose-tilt guard, carry, dead-reckoning after the GPS loss).
  estimator     navera_estimator EstimatorNode (GPS plausibility, vision cross-check, selection
                GPS > day, NavStatus back to the day node as the arbiter's decision).
  GNSS          the drone's GNSS (DJI gps_position, 5 Hz) is NAVERA's GPS until --gps-denied-at
                seconds after the first frame, then it stops (jamming: no messages, no GPS
                altitude). RTK (rtk_position) is only the truth.

The node's clock (time.time / monotonic in the modules that read it, ROS now() of both nodes)
is the virtual clock, advancing with the real processing time of each frame on this computer:
a slow frame costs what it costs in flight. ROS runs on its own domain (no message leaves).

Arms: imu  - frames straightened with the drone's attitude at exposure (FrameBuilder),
             heading from the attitude (an IMU with a trusted heading)
      gyro - frames not straightened, no attitude in the meta (attitude_source none: an IMU
             without a usable heading); the gyro (DJI IMU rate) feeds the day node's gyro heading
      dr   - as imu, but the matcher never matches after the GPS loss: NAVERA's dead-reckoning
             alone (the baseline vision has to beat)

Per run: frames offered/processed after the loss, accepted measured fixes, their error
(median/p90/max), fixes > 100 m, share within 3 stated sigma, dead-reckoned outputs and their
error vs time since the last fix, the estimator's output availability and error, the height
NAVERA used vs the true height above ground (RTK - DEM, if --dem), ms per frame.
"""
import argparse
import collections
import csv
import json
import math
import os
import sys
import tempfile
import time as _real_time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common"),
          os.path.join(ROOT, "navera_estimator")):
    sys.path.insert(0, p)
# a private ROS domain, no network: nothing this replay publishes reaches a running NAVERA
os.environ["ROS_DOMAIN_ID"] = os.environ.get("REPLAY_ROS_DOMAIN_ID", "87")
os.environ["ROS_LOCALHOST_ONLY"] = "1"
os.environ.setdefault("NAVERA_STATE_DIR", tempfile.mkdtemp(prefix="navera_replay_state_"))

# Camera intrinsics of the MARS-LVIG rigs (full 2448x2048 images), from the dataset authors'
# FAST-LIVO2 configuration (github.com/hku-mars/FAST-LIVO2, config/camera_MARS_LVIG.yaml):
# "am" = AMtown / AMvalley (Armenia), "hk" = HKairport / HKisland (Hong Kong). Pinhole k1 k2 p1 p2.
MARS_CAMERAS = {
    "am": dict(fx=1453.88, fy=1452.85, cx=1182.53, cy=1045.82, d=[-0.052, 0.1168, 0.0015, 0.00013]),
    "hk": dict(fx=1444.431662789634, fy=1444.343536688358, cx=1177.801079401826, cy=1043.601026568268,
               d=[-0.05729528706141188, 0.1210407244166642, 0.001274128378760289, 0.0004389741530109464]),
}
MARS_SIZE = (2448, 2048)


class VClock:
    """The virtual clock: a base time plus, while a frame is processed, the real time spent."""
    base = 0.0
    _run_from = None

    @classmethod
    def now(cls) -> float:
        if cls._run_from is None:
            return cls.base
        return cls.base + (_real_time.perf_counter() - cls._run_from)

    @classmethod
    def start_running(cls):
        cls._run_from = _real_time.perf_counter()

    @classmethod
    def stop_running(cls) -> float:
        el = _real_time.perf_counter() - cls._run_from
        cls.base += el
        cls._run_from = None
        return el


class FakeTimeModule:
    """Stands for the `time` module inside the product modules: the virtual clock."""
    def time(self):
        return VClock.now()

    def monotonic(self):
        return VClock.now()

    def strftime(self, *a):
        return _real_time.strftime(*a)

    def gmtime(self, *a):
        return _real_time.gmtime(*a)

    def sleep(self, s):
        pass

    perf_counter = staticmethod(_real_time.perf_counter)


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(q[0]))
    return math.hypot(de, dn)


class Interp:
    """Linear interpolation of the rows of a (t, ...) array at time t (None outside)."""
    def __init__(self, arr, cols):
        self.t = arr[:, 0]
        self.v = arr[:, cols]

    def at(self, t, max_gap=1.0):
        i = int(np.searchsorted(self.t, t))
        if i == 0 or i >= len(self.t):
            return None
        t0, t1 = self.t[i - 1], self.t[i]
        if t1 - t0 > max_gap:
            return None
        f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
        return self.v[i - 1] + f * (self.v[i] - self.v[i - 1])


def dem_height(dem_dir, lat, lon):
    """Ground height (m) from AWS Terrain Tiles (terrarium PNG, z14) cached in dem_dir, or None."""
    if not dem_dir:
        return None
    z = 14
    n = 2 ** z
    fx = (lon + 180.0) / 360.0 * n
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    x, y = int(fx), int(fy)
    path = os.path.join(dem_dir, f"{z}_{x}_{y}.png")
    if not os.path.exists(path):
        import urllib.request
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
        try:
            os.makedirs(dem_dir, exist_ok=True)
            urllib.request.urlretrieve(url, path)
        except Exception:                                   # noqa: BLE001 — no DEM: no height truth
            return None
    cache = dem_height.__dict__.setdefault("cache", {})
    im = cache.get(path)
    if im is None:
        im = cv2.imread(path, cv2.IMREAD_COLOR)
        if im is None:
            return None
        im = im[:, :, ::-1].astype(np.float64)              # RGB
        cache[path] = im
    px, py = (fx - x) * 256 - 0.5, (fy - y) * 256 - 0.5
    x0, y0 = int(max(0, min(254, math.floor(px)))), int(max(0, min(254, math.floor(py))))
    ax, ay = min(1.0, max(0.0, px - x0)), min(1.0, max(0.0, py - y0))
    h = im[:, :, 0] * 256 + im[:, :, 1] + im[:, :, 2] / 256 - 32768
    return float((1 - ax) * (1 - ay) * h[y0, x0] + ax * (1 - ay) * h[y0, x0 + 1]
                 + (1 - ax) * ay * h[y0 + 1, x0] + ax * ay * h[y0 + 1, x0 + 1])


def q_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def build_world(a):
    """rclpy, both nodes (product __init__), the patched clocks. Returns (day, est, sinks)."""
    import rclpy
    from rclpy.clock import ClockType
    from rclpy.time import Time
    import day_pkg.nodes.day_subscriber as ds
    import day_pkg.learned_matcher as lm
    import navera_common.prior as prior_mod
    import navera_estimator.nodes.estimator_node as en
    fake = FakeTimeModule()
    for mod in (ds, lm, prior_mod):
        mod.time = fake
    ds.state_store = type("NoState", (), {"save": staticmethod(lambda *x, **k: True),
                                          "load": staticmethod(lambda *x, **k: None)})

    class NoRetrieval:                    # the DINOv2 fallback is never used with local matching
        def load_models(self): pass
        def load_or_build_cache(self): pass
        def warm_up(self): pass
        def predict(self, *x, **k): return {"accepted": False, "error": "retrieval disabled in replay"}
    ds.DayLocalizer = NoRetrieval
    ds.IMAGES_DIR = a.area                 # the node reads the map's zoom(s) from <area>/../area.json
    args = ["--ros-args", "--log-level", a.log_level, "-p", "gyro_imu_topic:=/replay/imu"]
    for kv in a.param:
        args += ["-p", kv]
    rclpy.init(args=args)

    class FakeRosClock:
        clock_type = ClockType.ROS_TIME

        def now(self):
            return Time(nanoseconds=int(VClock.now() * 1e9), clock_type=ClockType.ROS_TIME)
    rc = FakeRosClock()
    day = ds.DaySubscriber()
    est = en.EstimatorNode()
    for n in (day, est):
        n.get_clock = lambda: rc
    sinks = {"day_est": [], "pos": [], "status": [], "vision_alt": []}

    class Pub:
        def __init__(self, fn, topic="x"):
            self.fn, self.topic_name = fn, topic

        def publish(self, m):
            self.fn(m)
    # the ROS graph, synchronous: day estimate -> estimator; estimator position (GPS) and nav
    # status -> day node; vision height -> camera side (AltitudeEstimator)
    day.pub_est = Pub(lambda m: (sinks["day_est"].append((VClock.now(), m)), est._on_day(m)))
    est.pub_pos = Pub(lambda m: (sinks["pos"].append((VClock.now(), m)), day.on_gps(m)))
    est.pub_status = Pub(lambda m: (sinks["status"].append((VClock.now(), m)), day.on_nav_status(m)))
    day.pub_vision_alt = Pub(lambda m: sinks["vision_alt"].append((VClock.now(), m)))
    for name in ("pub_fix", "pub_status", "pub_done", "pub_ready"):
        setattr(day, name, Pub(lambda m: None))
    return day, est, sinks


def run(a):
    from builtin_interfaces.msg import Time as TimeMsg
    from navera_msgs.msg import PositionEstimate
    from sensor_msgs.msg import Imu
    from navera_common.altitude import AltitudeEstimator
    from navera_common.camera_model import CameraModel
    from navera_common.frame_builder import FrameBuilder
    from navera_common.sensor_history import History, slerp

    rows = list(csv.DictReader(open(os.path.join(a.flight, "frames.csv"))))
    S = np.load(os.path.join(a.flight, "sensors.npz"))
    info = json.load(open(os.path.join(a.flight, "info.json")))
    ft = np.array([float(r["t"]) for r in rows])
    t_first = ft[0] + a.start_s
    t_deny = t_first + a.gps_denied_at
    t_end = min(ft[-1], t_deny + a.denied_s) if a.denied_s > 0 else ft[-1]
    rtk = Interp(S["rtk"], [1, 2, 3])
    att, gps, imu = S["att"], S["gps"], S["imu"]
    # the vehicle's height above take-off (its barometer, survives the GPS loss): MARS-LVIG's DJI
    # height_above_takeoff reads 0 in flight, so it is the RTK altitude minus its first sample (on
    # the ground) plus a barometer-like drift (--baro-drift-mps), at 10 Hz
    r = S["rtk"]
    tb = np.arange(r[0, 0], r[-1, 0], 0.1)
    rel = np.column_stack([tb, np.interp(tb, r[:, 0], r[:, 3]) - r[0, 3] + a.baro_drift_mps * (tb - tb[0])])

    # the camera: the dataset's calibration scaled to the extracted frames
    c = MARS_CAMERAS[a.site]
    w, h = info["image_size"]
    sc = w / MARS_SIZE[0]
    K = [[c["fx"] * sc, 0, c["cx"] * sc], [0, c["fy"] * sc, c["cy"] * sc], [0, 0, 1]]
    cam = CameraModel(K, c["d"], (w, h), "pinhole")
    mount = tuple(float(v) for v in a.mount.split(","))
    fb = FrameBuilder(cam, mount, max_tilt_deg=45.0, camera_type="day", gimbal=False,
                      require_attitude=(a.arm != "gyro"), max_rate_dps=30.0)
    att_hist = History(maxlen=4000, max_gap_s=0.2, interp=slerp)
    alt = AltitudeEstimator()
    if a.terrain:                                  # the map's DEM (live_camera terrain_dir)
        from navera_common.terrain import Terrain
        terrain = Terrain.load(a.terrain)
        if terrain is None:
            raise SystemExit(f"--terrain {a.terrain}: no DEM there (prepare_area --dem copernicus)")
        alt.set_terrain(terrain)
        # the vehicle's home (its take-off point, which the autopilot knows): the RTK's first sample
        alt.set_home(float(S["rtk"][0, 1]), float(S["rtk"][0, 2]))
    gps_hist = History(maxlen=600, max_gap_s=1.5)

    rangefinder = None
    if a.rangefinder:
        # a downward rangefinder / laser altimeter (live_camera altitude_topic, "measured"): here the
        # true height above ground, RTK altitude minus the DEM (--dem), at 10 Hz
        g0 = dem_height(a.dem, float(r[0, 1]), float(r[0, 2]))
        datum = float(r[0, 3]) - g0 - a.takeoff_agl_m

        def rangefinder(t):
            p = rtk.at(t)
            g = dem_height(a.dem, float(p[0]), float(p[1])) if p is not None else None
            return None if g is None else float(p[2]) - datum - g

    VClock.base = t_first - 5.0
    day, est, sinks = build_world(a)

    def on_vision_alt(m):                          # live_camera._on_vision_alt
        sinks["vision_alt"].append((VClock.now(), m))
        alt.add_vision(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m.range, m.field_of_view or 5.0)
    day.pub_vision_alt.fn = on_vision_alt

    def on_position(m):                            # live_camera._on_position (the arbiter's output)
        sinks["pos"].append((VClock.now(), m))
        day.on_gps(m)
        if m.valid:
            st = m.sensor_stamp.sec + m.sensor_stamp.nanosec * 1e-9 or VClock.now()
            alt.add_position(st, m.latitude, m.longitude, math.sqrt(max(m.position_covariance[0], 0.0)))
    est.pub_pos.fn = on_position
    calls = []                                     # this frame's matcher calls (instrumentation only)

    def wrap(matcher):
        real_locate = matcher.locate

        def locate(img, prior, search_m, *x, **k):
            if a.arm == "dr" and VClock.now() >= t_deny:
                r = {"accepted": False, "matcher": "local", "reason": "dr arm: no map matching after the GPS loss"}
            else:
                r = real_locate(img, prior, search_m, *x, **k)
            calls.append(dict(R=round(float(search_m)), acc=bool(r.get("accepted")), inl=r.get("inliers"),
                              why=str(r.get("reason") or "")[:70], frm=r.get("position_from"),
                              feat=r.get("features"), scale=r.get("scale_residual"), z=getattr(matcher, "z", None)))
            return r
        matcher.locate, matcher._replay_wrapped = locate, True
    wrap(day.local)
    real_select = day._select_map

    def select_map(img, meta):                     # a matcher built for another zoom is instrumented too
        real_select(img, meta)
        if not getattr(day.local, "_replay_wrapped", False):
            wrap(day.local)
    day._select_map = select_map
    statuses = []
    day.pub_status = type("P", (), {"publish": staticmethod(lambda m: statuses.append(m.data)),
                                    "topic_name": "status"})()
    # streams, merged in time order
    ia = ig = ir = iu = 0
    gps_period, last_gps = 1.0 / a.gps_hz, -1e9
    imu_period, last_imu = 1.0 / a.imu_hz, -1e9
    tick_period, next_tick = 1.0 / 5.0, VClock.base
    stamp = lambda t: TimeMsg(sec=int(t), nanosec=int(round((t % 1) * 1e9)) % 1_000_000_000)  # noqa: E731

    def feed_until(t_to):
        nonlocal ia, ig, ir, iu, last_gps, last_imu, next_tick
        while True:
            cands = []
            if ia < len(att):
                cands.append((att[ia, 0], "att"))
            if ig < len(gps):
                cands.append((gps[ig, 0], "gps"))
            if ir < len(rel):
                cands.append((rel[ir, 0], "rel"))
            if iu < len(imu):
                cands.append((imu[iu, 0], "imu"))
            cands.append((next_tick, "tick"))
            t, kind = min(cands)
            if t > t_to:
                break
            if t > VClock.base:
                VClock.base = t
            if kind == "att":
                q = tuple(att[ia, 1:5])
                if a.yaw_error_deg:
                    z = math.radians(a.yaw_error_deg) / 2
                    q = q_mul((0.0, 0.0, math.sin(z), math.cos(z)), q)
                att_hist.add(t, q)
                ia += 1
            elif kind == "rel":
                alt.add_relative(t, float(rel[ir, 1]))
                if rangefinder is not None:
                    rf = rangefinder(t)
                    if rf is not None:
                        alt.add_measured(t, rf, 1.0)
                ir += 1
            elif kind == "imu":
                if t - last_imu >= imu_period - 1e-6:
                    last_imu = t
                    m = Imu()
                    m.header.stamp = stamp(t)
                    m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z = (float(v) for v in imu[iu, 1:4])
                    o = m.orientation
                    o.x, o.y, o.z, o.w = (float(v) for v in imu[iu, 4:8])
                    if day.gyro is not None:
                        day.on_imu(m)
                    est._on_imu(m)
                iu += 1
            elif kind == "gps":
                if t < t_deny and t - last_gps >= gps_period - 1e-6 and gps[ig, 4] >= 0:
                    last_gps = t
                    lat, lon, galt = (float(v) for v in gps[ig, 1:4])
                    gps_hist.add(t, (lat, lon))
                    alt.add_gps(t, galt, lat, lon)
                    m = PositionEstimate()
                    m.header.stamp = stamp(t)
                    m.sensor_stamp = stamp(t)
                    m.source, m.mode, m.valid = PositionEstimate.SOURCE_GPS, PositionEstimate.MODE_MEASURED, True
                    m.latitude, m.longitude, m.altitude = lat, lon, galt
                    var = a.gps_sigma_m ** 2
                    m.position_covariance = [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, 0.0]
                    m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
                    m.producer = "gps_node"
                    est._on_gps(m)
                ig += 1
            else:
                est._tick()
                next_tick += tick_period
        VClock.base = max(VClock.base, t_to)

    # the camera loop: one frame offered when the previous one is acked, at most fps
    period = 1.0 / a.fps
    t_send = t_first
    log = []
    n = 0
    while t_send <= t_end:
        feed_until(t_send)
        i = int(np.searchsorted(ft, t_send - a.capture_delay_s, side="right")) - 1
        if i < 0:
            t_send += period
            continue
        t_exp = ft[i]
        img = cv2.imread(os.path.join(a.flight, "frames", rows[i]["file"]))
        q = att_hist.at(t_exp)
        if a.arm == "gyro":
            q = None
        rate = None
        qa, qb = att_hist.at(t_exp - 0.2), att_hist.at(t_exp)
        if qa is not None and qb is not None:
            dot = min(1.0, abs(sum(x * y for x, y in zip(qa, qb))))
            rate = math.degrees(2.0 * math.acos(dot)) / 0.2
        g = gps_hist.at(t_exp)
        t_stamp = t_exp + a.stamp_error_s            # the camera's stamp (its delay unknown to it)
        VClock.start_running()
        out, meta = fb.build(img, n, int(t_stamp * 1e9), q, "imu", alt.estimate(t_exp), g, None, rate)
        meta["image_stamp_ns"] = int(round(t_stamp * 1e9))
        k_est, k_alt = len(sinks["day_est"]), len(sinks["vision_alt"])
        calls.clear()
        statuses.clear()
        day._dispatch(out, meta)
        el = VClock.stop_running()
        truth = rtk.at(t_exp)
        ests = [m for _, m in sinks["day_est"][k_est:]]
        rec = dict(n=n, t=round(float(t_exp - t_first), 2), t_abs=float(t_exp), ms=round(el * 1000, 1),
                   denied=bool(t_exp >= t_deny),
                   usable=meta.get("usable"), tilt=meta.get("tilt_deg"), alt_used=meta.get("altitude_m"),
                   alt_sigma=meta.get("altitude_sigma_m"), alt_src=meta.get("altitude_source"),
                   truth=None if truth is None else [float(truth[0]), float(truth[1]), float(truth[2])],
                   calls=list(calls))
        if len(sinks["vision_alt"]) > k_alt:
            rec["vision_alt"] = round(float(sinks["vision_alt"][-1][1].range), 1)
        for st in statuses:
            try:
                d = json.loads(st)
            except ValueError:
                continue
            rec["status"] = {k: d.get(k) for k in ("source", "reason", "inliers", "position_from", "pose_guard",
                                                   "map_bias_m", "reacquired", "latency", "sigma_cal")
                             if d.get(k) is not None}
        for m in ests:
            if not m.valid:
                rec.setdefault("no_fix", m.reason[:120])
                continue
            d = json.loads(m.details_json or "{}")
            if d.get("gps_check"):
                rec["check"] = True
            st = m.sensor_stamp.sec + m.sensor_stamp.nanosec * 1e-9
            tr = truth                                 # a fix / carry describes this frame's exposure
            sig = math.sqrt(m.position_covariance[0]) if m.position_covariance[0] > 0 else None
            rec.setdefault("out", []).append(dict(
                mode="fix" if m.mode == PositionEstimate.MODE_MEASURED else "dr", gps_check=bool(d.get("gps_check")),
                err=None if tr is None else round(metres((m.latitude, m.longitude), tr), 1),
                sigma=None if sig is None else round(sig, 1), inliers=d.get("inliers"),
                pos_from=None, age=round(VClock.now() - st, 2)))
        log.append(rec)
        if a.verbose:
            o = rec.get("out") or [{}]
            st = rec.get("status", {})
            print(f"  t {rec['t']:6.1f} {o[-1].get('mode', '-'):3s} err {o[-1].get('err')} sig {o[-1].get('sigma')} "
                  f"ms {rec['ms']:.0f} {st.get('source', '')} {str(st.get('reason', ''))[:70]} "
                  f"{rec['calls'][-1] if rec['calls'] else ''}", flush=True)
        n += 1
        t_send = max(t_send + period, VClock.base + 0.02)   # ack, then the next frame (fps cap)
    feed_until(t_end + 1.0)
    return log, sinks, dict(t_first=t_first, t_deny=t_deny, t_end=t_end, rtk=rtk)


def summarise(log, sinks, ctx, a):
    from navera_msgs.msg import NavStatus, PositionEstimate
    rtk, t_deny = ctx["rtk"], ctx["t_deny"]
    den = [r for r in log if r["denied"]]
    fixes = [o for r in den for o in r.get("out", []) if o["mode"] == "fix" and o["err"] is not None]
    drs = [o for r in den for o in r.get("out", []) if o["mode"] == "dr" and o["err"] is not None]
    checks = [o for r in log if not r["denied"] for o in r.get("out", []) if o["gps_check"] and o["err"] is not None]

    def q(v, p):
        v = sorted(v)
        return round(v[min(len(v) - 1, int(p * len(v)))], 1) if v else None

    def stats(v):
        e = [o["err"] for o in v]
        in3 = [o for o in v if o["sigma"]]
        return {"n": len(v), "median": q(e, 0.5), "p90": q(e, 0.9), "max": round(max(e), 1) if e else None,
                "gt100": sum(x > 100 for x in e), "gt50": sum(x > 50 for x in e),
                "within3s": round(sum(o["err"] <= 3 * o["sigma"] for o in in3) / len(in3), 3) if in3 else None,
                "sigma_median": q([o["sigma"] for o in in3], 0.5)}
    # the estimator's output (what the autopilot gets) after the loss, at each publication
    pos = []
    by_frame = {r["n"]: r["t_abs"] for r in log}
    for tv, m in sinks["pos"]:
        if tv < t_deny or not m.valid:
            continue
        t_exp = by_frame.get(m.frame_index)       # the exposure the published position describes
        tr_meas, tr_now = (rtk.at(t_exp) if t_exp is not None else None), rtk.at(tv)
        if tr_meas is None or tr_now is None:
            continue
        sig = math.sqrt(m.position_covariance[0]) if m.position_covariance[0] > 0 else None
        pos.append(dict(t=tv, src=m.source, mode=m.mode, err=metres((m.latitude, m.longitude), tr_meas),
                        err_now=metres((m.latitude, m.longitude), tr_now), sigma=sig))
    states = [(tv, m.state) for tv, m in sinks["status"] if tv >= t_deny]
    # while GPS was good: did the cross-check ever refuse it or put it in doubt (a false alarm)?
    before = [m for tv, m in sinks["status"] if ctx["t_first"] <= tv < t_deny]
    gps_refused = sum(1 for m in before if m.active_source != NavStatus.SOURCE_GPS)
    gps_doubt = sum(1 for m in before if "IN DOUBT" in m.reason)
    ok_states = (NavStatus.STATE_FIX, NavStatus.STATE_DEGRADED)
    avail = sum(s in ok_states for _, s in states) / len(states) if states else None
    gps_after = sum(1 for p in pos if p["src"] == PositionEstimate.SOURCE_GPS)
    # dead-reckoning error vs time since the last fix
    dr_age = {}
    last_fix_t = t_deny - ctx["t_first"]           # the last GPS fix, until vision gives one
    for r in den:
        for o in r.get("out", []):
            if o["mode"] == "fix":
                last_fix_t = r["t"]
            elif o["err"] is not None and last_fix_t is not None:
                b = "0-10" if r["t"] - last_fix_t < 10 else "10-30" if r["t"] - last_fix_t < 30 else "30-60" \
                    if r["t"] - last_fix_t < 60 else ">60"
                dr_age.setdefault(b, []).append(o["err"])
    # height: what the camera side used (and the vision height) vs RTK - DEM
    hts, vh = [], []
    off = None
    if a.dem:
        g0 = dem_height(a.dem, *[float(v) for v in rtk.v[0][:2]])
        if g0 is not None:
            off = float(rtk.v[0][2]) - g0 - a.takeoff_agl_m       # RTK altitude datum - DEM datum
    if off is not None:
        for r in den:
            if r["truth"] and r["alt_used"] is not None:
                gh = dem_height(a.dem, r["truth"][0], r["truth"][1])
                if gh is not None:
                    agl = r["truth"][2] - off - gh
                    hts.append((r["alt_used"] - agl, r["alt_sigma"], agl))
                    if r.get("vision_alt") is not None:
                        vh.append(r["vision_alt"] - agl)
    ms = [r["ms"] for r in log if r["denied"]]
    span = (log[-1]["t"] - (t_deny - ctx["t_first"])) if den else 0.0
    return {
        "frames_after_loss": len(den), "span_s": round(span, 1),
        "frames_per_s": round(len(den) / span, 2) if span > 0 else None,
        "accepted": len(fixes), "accepted_share": round(len(fixes) / len(den), 3) if den else None,
        "fixes": stats(fixes), "dr": stats(drs), "no_output": sum(1 for r in den if not r.get("out")),
        "dr_err_by_age": {k: {"n": len(v), "median": q(v, 0.5), "max": round(max(v), 1)}
                          for k, v in sorted(dr_age.items())},
        "gps_checks": stats(checks),
        "estimator": {"available": None if avail is None else round(avail, 3), "published": len(pos),
                      "gps_after_loss": gps_after, "ticks_before_loss": len(before),
                      "gps_not_used_before_loss": gps_refused, "gps_in_doubt_before_loss": gps_doubt,
                      "err": stats([dict(err=p["err"], sigma=p["sigma"]) for p in pos]),
                      "err_vs_now": stats([dict(err=p["err_now"], sigma=p["sigma"]) for p in pos])},
        "height": None if not hts else {"n": len(hts), "err_median": q([e for e, _, _ in hts], 0.5),
                                        "abs_err_p90": q([abs(e) for e, _, _ in hts], 0.9),
                                        "abs_err_max": round(max(abs(e) for e, _, _ in hts), 1),
                                        "within_2sigma": round(sum(abs(e) <= 2 * s for e, s, _ in hts if s) /
                                                               max(1, sum(1 for _, s, _ in hts if s)), 3),
                                        "agl_median": q([g for _, _, g in hts], 0.5),
                                        "sources": dict(collections.Counter(r["alt_src"] for r in den)),
                                        "vision": {"n": len(vh), "err_median": q(vh, 0.5),
                                                   "abs_err_p90": q([abs(e) for e in vh], 0.9)}},
        "ms_per_frame": {"median": q(ms, 0.5), "p90": q(ms, 0.9), "max": round(max(ms), 0) if ms else None},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("flight")
    ap.add_argument("--area", required=True, help="map tiles dir (tile_17_x_y.jpg), prepare_area.py <out>/images")
    ap.add_argument("--site", required=True, choices=sorted(MARS_CAMERAS))
    ap.add_argument("--mount", default="0,0,0", help="camera mount roll,pitch,yaw deg (FrameBuilder)")
    ap.add_argument("--arm", default="imu", choices=["imu", "gyro", "dr"])
    ap.add_argument("--start-s", type=float, default=0.0, help="s after the first frame where the replay starts")
    ap.add_argument("--gps-denied-at", type=float, default=120.0, help="s after the start: GPS stops")
    ap.add_argument("--denied-s", type=float, default=0.0, help="replay this long after the loss (0: to the end)")
    ap.add_argument("--fps", type=float, default=1.0, help="live_camera fps (frames offered at most)")
    ap.add_argument("--gps-hz", type=float, default=5.0)
    ap.add_argument("--gps-sigma-m", type=float, default=2.5)
    ap.add_argument("--imu-hz", type=float, default=100.0)
    ap.add_argument("--capture-delay-s", type=float, default=0.0, help="frame grabbed this long after its exposure")
    ap.add_argument("--stamp-error-s", type=float, default=0.0,
                    help="the camera stamps frames this much later than their exposure (auto latency must find it)")
    ap.add_argument("--yaw-error-deg", type=float, default=0.0, help="error added to the IMU heading")
    ap.add_argument("--baro-drift-mps", type=float, default=0.0, help="drift of the simulated barometer, m/s")
    ap.add_argument("--dem", default="", help="dir for AWS terrarium z14 DEM tiles (height truth)")
    ap.add_argument("--terrain", default="",
                    help="the map's DEM (an area dir with terrain/, prepare_area --dem copernicus): the camera "
                         "side's height above ground over relief")
    ap.add_argument("--rangefinder", action="store_true",
                    help="feed the true height above ground (RTK - DEM) as a measured altitude (needs --dem)")
    ap.add_argument("--takeoff-agl-m", type=float, default=0.3, help="RTK antenna above the ground at the first sample")
    ap.add_argument("--param", action="append", default=[], help="extra day/estimator ROS parameter name:=value")
    ap.add_argument("--log-level", default="fatal")
    ap.add_argument("--json", default="")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    log, sinks, ctx = run(a)
    s = summarise(log, sinks, ctx, a)
    s["args"] = {k: v for k, v in vars(a).items()}
    print(json.dumps(s, indent=1), flush=True)
    if a.json:
        json.dump({"summary": s, "frames": log}, open(a.json, "w"), indent=0, default=str)
    os._exit(0)                            # rclpy/torch threads: do not wait for them


if __name__ == "__main__":
    main()

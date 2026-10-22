#!/usr/bin/env python3
"""Replay an Insta360 raw recording through the Insta360 kit AND NAVERA's day chain, in process, on
a virtual clock: do frames now get an attitude, and fixes?

    python3 navera_tools/bench/insta360_kit_replay.py REC_DIR --area AREA_IMAGES_DIR \
        [--gps-denied-at 40] [--arm kit|noatt] [--param matcher:=local] [--json out.json]

REC_DIR holds raw/ (a field raw recording, or one made by navera_tools/sim/insta360_raw_sim.py),
gps.csv (t, lat, lon, alt) and truth.csv (t, lat, lon, agl, qx, qy, qz, qw, heading) when known.

The product's own code, wired as the ROS graph wires it:
  kit side      camera_pkg.insta360_kit.Insta360Kit (packets -> ImuStream -> AttitudeFilter; key
                frames decoded one by one -> NadirView, stamped at exposure), GpsCourse fed by the
                GPS while it is trusted, vision headings from the day node's status (insta360_node)
  camera side   FrameBuilder with the kit's view (ideal lens, view hfov) and the kit's attitude at the
                exposure, the live camera's heading gate (yaw sigma > 5 deg: no heading in the meta),
                AltitudeEstimator (GPS altitude, then the heights vision measures), newest frame
                when the localizer is free, at most --fps
  day_pkg       DaySubscriber (its __init__ defaults + --param), the gyro heading fed by the kit's IMU
  estimator     navera_estimator EstimatorNode (from navera_tools/bench/replay_flight_dataset.py)
Arms: kit   = the kit's attitude in the frames (this change)
      noatt = the IMU without orientation (before: insta360_imu_node gave none): a fixed camera's
              frames are refused ("no attitude at the frame's exposure")
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "camera_pkg"), os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common"),
          os.path.join(ROOT, "navera_estimator")):
    if p not in sys.path:
        sys.path.insert(0, p)

from navera_tools.bench import replay_flight_dataset as rfd  # noqa: E402  (sets a private ROS domain)

CAL0 = (np.zeros(3), np.ones(3), np.zeros(3))


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(q[0]))
    return math.hypot(de, dn)


def load_csv(path):
    if not os.path.isfile(path):
        return None
    rows = list(csv.reader(open(path)))
    return np.array([[float(v) for v in r] for r in rows[1:]])


def run(a):
    from builtin_interfaces.msg import Time as TimeMsg
    from navera_msgs.msg import PositionEstimate
    from sensor_msgs.msg import Imu
    from navera_common.altitude import AltitudeEstimator
    from navera_common.camera_model import CameraModel
    from navera_common.frame_builder import FrameBuilder
    from navera_common.insta360_protocol import load_imu_calibration
    from navera_common.sensor_history import History, slerp
    from camera_pkg.insta360_attitude import AttitudeFilter, GpsCourse, heading_of
    from camera_pkg.insta360_imu import ImuStream, mount_rotation
    from camera_pkg.insta360_kit import Insta360Kit, replay_all
    from camera_pkg.insta360_view import NadirView, load_lenses
    from camera_pkg.nodes.insta360_node import frame_top_offset_deg, vision_heading
    from navera_common.camera_model import quat_to_matrix

    gps = load_csv(os.path.join(a.rec, "gps.csv"))
    truth = load_csv(os.path.join(a.rec, "truth.csv"))
    R_bc = mount_rotation(a.mount)
    cal = CAL0 if a.neutral_calibration else load_imu_calibration()
    stream = ImuStream(R_bc, 5, cal, bias_at_rest=True)
    flt = AttitudeFilter()
    course = GpsCourse()
    lenses, lens_src = load_lenses(a.lens)
    view = NadirView(lenses, R_bc, a.hfov, a.width, a.height)
    kit = Insta360Kit(stream, flt, view, speed_at=course.speed)
    fb = FrameBuilder(CameraModel.ideal(a.hfov, (a.width, a.height)), (0.0, 0.0, 0.0), max_tilt_deg=45.0,
                      camera_type="day", gimbal=False, require_attitude=True, max_rate_dps=30.0)
    att_hist = History(maxlen=20000, max_gap_s=0.2, interp=slerp)
    yaw_hist = History(maxlen=20000, max_gap_s=0.2)
    alt = AltitudeEstimator(ground_altitude_m=0.0)
    packets = list(replay_all(os.path.join(a.rec, "raw"), rate=0, clock="recorded"))
    t_first = packets[0][0]
    t_deny = t_first + a.gps_denied_at
    rfd.VClock.base = t_first - 1.0
    day, est, sinks = rfd.build_world(a)
    statuses = []
    day.pub_status = type("P", (), {"publish": staticmethod(lambda m: statuses.append(m.data)),
                                    "topic_name": "status"})()

    def on_vision_alt(m):
        alt.add_vision(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m.range, m.field_of_view or 5.0)
    day.pub_vision_alt.fn = on_vision_alt

    def on_position(m):
        sinks["pos"].append((rfd.VClock.now(), m))
        day.on_gps(m)
        if m.valid:
            st = m.sensor_stamp.sec + m.sensor_stamp.nanosec * 1e-9 or rfd.VClock.now()
            alt.add_position(st, m.latitude, m.longitude, math.sqrt(max(m.position_covariance[0], 0.0)))
    est.pub_pos.fn = on_position
    stamp = lambda t: TimeMsg(sec=int(t), nanosec=int(round((t % 1) * 1e9)) % 1_000_000_000)  # noqa: E731
    ig, next_tick, last_imu = 0, rfd.VClock.base, -1e9
    latest = None
    log, n, last_sent = [], 0, -1e9
    ip = 0

    def truth_at(t):
        if truth is None:
            return None
        i = int(np.searchsorted(truth[:, 0], t))
        if i <= 0 or i >= len(truth):
            return None
        r0, r1 = truth[i - 1], truth[i]
        f = (t - r0[0]) / (r1[0] - r0[0])
        return r0 + f * (r1 - r0)

    def feed_until(t_to):
        nonlocal ip, ig, next_tick, last_imu, latest
        while ip < len(packets) and packets[ip][0] <= t_to:
            t, p = packets[ip]
            ip += 1
            while gps is not None and ig < len(gps) and gps[ig, 0] <= t:
                tg, lat, lon, galt = gps[ig]
                ig += 1
                if tg >= t_deny:
                    continue
                course.add_fix(tg, lat, lon)
                course.maybe_set(flt)
                alt.add_gps(tg, galt, lat, lon)
                m = PositionEstimate()
                m.header.stamp = m.sensor_stamp = stamp(tg)
                m.source, m.mode, m.valid = PositionEstimate.SOURCE_GPS, PositionEstimate.MODE_MEASURED, True
                m.latitude, m.longitude, m.altitude = lat, lon, galt
                m.position_covariance = [4.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0]
                m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
                m.producer = "gps_node"
                est._on_gps(m)
            if gps is not None and t >= t_deny:
                course.clear()
            while next_tick <= t:
                est._tick()
                next_tick += 0.2
            for s, st in kit.feed(t, p):
                if a.arm == "kit":
                    att_hist.add(s.t, st.q)
                    yaw_hist.add(s.t, st.heading_sigma_deg)
                if s.t - last_imu >= 0.01 - 1e-6:
                    last_imu = s.t
                    m = Imu()
                    m.header.stamp = stamp(s.t)
                    m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z = (float(v) for v in s.gyro)
                    if a.arm == "kit":
                        o = m.orientation
                        o.x, o.y, o.z, o.w = (float(v) for v in st.q)
                    else:
                        m.orientation_covariance[0] = -1.0
                    if day.gyro is not None:
                        day.on_imu(m)
                    est._on_imu(m)
            for fr in kit.decode_pending():
                latest = (t, fr)
            rfd.VClock.base = max(rfd.VClock.base, t)
        rfd.VClock.base = max(rfd.VClock.base, t_to)

    while ip < len(packets):
        feed_until(rfd.VClock.base + 0.05)
        if latest is None or latest[1].t <= last_sent + 1e-6 or rfd.VClock.base - last_sent < 1.0 / a.fps:
            continue
        _, fr = latest
        t_exp = fr.t
        q = att_hist.at(t_exp)
        qa = att_hist.at(t_exp - 0.2)
        rate = None
        if q is not None and qa is not None:
            dot = min(1.0, abs(sum(x * y for x, y in zip(qa, q))))
            rate = math.degrees(2.0 * math.acos(dot)) / 0.2
        tr = truth_at(t_exp)
        rfd.VClock.start_running()
        out, meta = fb.build(fr.image, n, int(round(t_exp * 1e9)), q, "insta360", alt.estimate(t_exp), None, None, rate)
        meta["image_stamp_ns"] = int(round(t_exp * 1e9))
        ys = yaw_hist.at(t_exp)
        if meta.get("heading_deg") is not None and ys is not None and ys > 5.0:      # live_camera._check_heading
            meta.update(heading_deg=None, heading_sigma_deg=round(min(ys, 180.0), 1))
        k_est = len(sinks["day_est"])
        statuses.clear()
        day._dispatch(out, meta)
        el = rfd.VClock.stop_running()
        rec = dict(n=n, t=round(t_exp - t_first, 2), denied=t_exp >= t_deny, usable=meta.get("usable"),
                   reason=meta.get("reason"), tilt=meta.get("tilt_deg"), heading=meta.get("heading_deg"),
                   ms=round(el * 1000))
        if tr is not None and q is not None:
            Rt, Re = quat_to_matrix(tr[4:8]), quat_to_matrix(q)
            rec["tilt_err"] = round(math.degrees(math.acos(max(-1.0, min(1.0, float(Rt[2, :] @ Re[2, :]))))), 3)
            if ys is not None and math.isfinite(ys):
                rec["heading_err"] = round(abs((heading_of(Re) - tr[8] + 180.0) % 360.0 - 180.0), 2)
                rec["heading_sigma"] = round(ys, 2)
        for st_txt in statuses:
            try:
                d = json.loads(st_txt)
            except ValueError:
                continue
            rec["status"] = {k: d.get(k) for k in ("source", "reason", "inliers", "rotation_deg")
                             if d.get(k) is not None}
            v = vision_heading(meta, d, 20)
            if v is not None and a.arm == "kit":
                Rv = flt.matrix_at(v[0])
                if Rv is not None:
                    rec["vision_heading_taken"] = flt.set_heading(v[0], (v[1] - frame_top_offset_deg(Rv)) % 360.0,
                                                                  2.0, "vision")
        for _, m in sinks["day_est"][k_est:]:
            if not m.valid:
                rec.setdefault("no_fix", m.reason[:100])
                continue
            dj = json.loads(m.details_json or "{}")
            o = dict(mode="fix" if m.mode == PositionEstimate.MODE_MEASURED else "dr",
                     gps_check=bool(dj.get("gps_check")),
                     sigma=round(math.sqrt(m.position_covariance[0]), 1) if m.position_covariance[0] > 0 else None)
            if tr is not None:
                o["err"] = round(metres((m.latitude, m.longitude), (tr[1], tr[2])), 1)
            rec.setdefault("out", []).append(o)
        log.append(rec)
        if a.verbose:
            o = (rec.get("out") or [{}])[-1]
            print(f"  t {rec['t']:6.1f} {'DENIED' if rec['denied'] else 'gps   '} usable {rec['usable']} tilt_err "
                  f"{rec.get('tilt_err')} hdg_err {rec.get('heading_err')} {o.get('mode', '-')} err {o.get('err')} "
                  f"{(rec.get('reason') or rec.get('no_fix') or '')[:60]}", flush=True)
        last_sent = t_exp
        n += 1
    return log, dict(lens=lens_src, frames_decoded=kit.decoded, keyframes=kit.keyframes,
                     decode_errors=kit.decode_errors,
                     course_sets=course.sets, view_coverage=view.coverage)


def summarise(log):
    def q(v, p):
        v = sorted(v)
        return round(v[min(len(v) - 1, int(p * len(v)))], 2) if v else None
    den = [r for r in log if r["denied"]]
    fixes = [o for r in den for o in r.get("out", []) if o["mode"] == "fix" and o.get("err") is not None]
    outs = [o for r in den for o in r.get("out", []) if o.get("err") is not None]
    te = [r["tilt_err"] for r in log if r.get("tilt_err") is not None]
    he = [r["heading_err"] for r in log if r.get("heading_err") is not None]
    reasons = {}
    for r in log:
        if r["usable"] is False:
            reasons[(r.get("reason") or "")[:50]] = reasons.get((r.get("reason") or "")[:50], 0) + 1
    return {"frames": len(log), "frames_with_attitude": sum(r.get("tilt") is not None for r in log),
            "unusable": sum(r["usable"] is False for r in log), "unusable_reasons": reasons,
            "frames_after_loss": len(den), "fixes_after_loss": len(fixes),
            "fix_err_median": q([o["err"] for o in fixes], 0.5), "fix_err_p90": q([o["err"] for o in fixes], 0.9),
            "fix_err_max": max([o["err"] for o in fixes]) if fixes else None,
            "outputs_after_loss": len(outs), "output_err_median": q([o["err"] for o in outs], 0.5),
            "output_err_max": max([o["err"] for o in outs]) if outs else None,
            "tilt_err_median_deg": q(te, 0.5), "tilt_err_p95_deg": q(te, 0.95),
            "tilt_err_max_deg": max(te) if te else None,
            "heading_err_median_deg": q(he, 0.5), "heading_err_max_deg": max(he) if he else None,
            "frames_with_heading_in_meta": sum(r.get("heading") is not None for r in log)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rec")
    ap.add_argument("--area", required=True)
    ap.add_argument("--arm", default="kit", choices=["kit", "noatt"])
    ap.add_argument("--mount", default="+x,+z,-y")
    ap.add_argument("--lens", default="")
    ap.add_argument("--hfov", type=float, default=100.0)
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--fps", type=float, default=1.0)
    ap.add_argument("--gps-denied-at", type=float, default=40.0)
    ap.add_argument("--neutral-calibration", action="store_true", help="IMU calibration neutral (synthetic data)")
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--log-level", default="fatal")
    ap.add_argument("--json", default="")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    log, info = run(a)
    s = dict(summarise(log), arm=a.arm, **info)
    print(json.dumps(s, indent=1))
    if a.json:
        json.dump(dict(summary=s, log=log), open(a.json, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

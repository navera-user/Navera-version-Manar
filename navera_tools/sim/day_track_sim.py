#!/usr/bin/env python3
"""Day-vision flight over rendered frames: GPS lost for long, GPS spoofed (drifting), offline.

A vehicle flies circles over the screen-bench map (Sousse) at --height; each --dt a frame is
rendered from the imagery (dayvision_conditions renderer, same-source z18 + camera appearance
change), straightened with an attitude carrying --tilt-err, given a heading carrying a slowly
drifting yaw error (--yaw-drift deg over the flight, an IMU without magnetometer), and located
by the production matcher (LearnedMatcher) in the window VisionNavigator asks for. Between
frames VisionNavigator (day_pkg.vision_nav, the day node's rules) carries the position.

Scenarios (--scenario):
  lost       GPS good for --gps-s, then lost for --seconds: drift of the output, fix rate,
             and whether the stated sigma is honest (share of errors within 3 sigma)
  spoof:R    from --gps-s the GPS drifts at R m/s (east). The arbiter's two GPS rules are
             modelled (navera_estimator): a GPS fix further from the last accepted one than
             max_speed x dt + 50 m is refused; two vision fixes in a row (a GPS-check match
             every frame here) beyond 3 sigma of GPS refuse it. Then vision takes over from
             its last fix. Reported: drift when refused, output error after.

    python3 navera_tools/sim/day_track_sim.py --scenario lost --seconds 600
    python3 navera_tools/sim/day_track_sim.py --scenario spoof:10 --seconds 120
"""
import argparse
import json
import math
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common")):
    if p not in sys.path:
        sys.path.insert(0, p)

from navera_common.camera_model import heading_of_image_up_deg, nadir_homography  # noqa: E402
from navera_tools.sim import dayvision_conditions as dv  # noqa: E402
from navera_tools.sim.day_robustness import SCENES  # noqa: E402
from day_pkg.vision_nav import VisionNavigator, _en, _move  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="lost")
    ap.add_argument("--seconds", type=float, default=600.0, help="after the GPS phase")
    ap.add_argument("--gps-s", type=float, default=30.0)
    ap.add_argument("--dt", type=float, default=1.0, help="s between frames")
    ap.add_argument("--speed", type=float, default=20.0)
    ap.add_argument("--radius", type=float, default=800.0, help="circle radius, m")
    ap.add_argument("--height", type=float, default=300.0)
    ap.add_argument("--tilt-err", type=float, default=0.5, help="deg, attitude error of the straightening")
    ap.add_argument("--yaw-drift", type=float, default=2.0, help="deg, heading error reached at the end")
    ap.add_argument("--max-speed", type=float, default=30.0, help="the vehicle's top speed (gates)")
    ap.add_argument("--hfov", type=float, default=100.0)
    ap.add_argument("--size", default="1200x900")
    ap.add_argument("--matcher", choices=["learned", "sift"], default="learned")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scene", default="bench", help="bench (same source, optimistic) or xdate2022 (2022 vs ~2025)")
    ap.add_argument("--gaps", default="", help="P:L — every P s after the GPS loss, L s of 95 %% cloud (no match)")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    size = tuple(int(v) for v in a.size.split("x"))
    sc = SCENES[a.scene]
    gap_p, gap_l = (float(v) for v in a.gaps.split(":")) if a.gaps else (0.0, 0.0)
    imagery = dv.Imagery(sc["query"])
    if a.matcher == "sift":
        from day_pkg.local_matcher import LocalMatcher
        M = LocalMatcher(sc["map"], device="cpu")          # CPU: runs beside a GPU job
    else:
        from day_pkg.learned_matcher import LearnedMatcher
        M = LearnedMatcher(sc["map"])
    K = dv.K_of(size[0], size[1], a.hfov)
    rng = np.random.default_rng(a.seed)
    nav = VisionNavigator(max_speed_mps=a.max_speed)
    spoof = float(a.scenario.split(":")[1]) if a.scenario.startswith("spoof") else None
    centre = sc["centre"]
    w = a.speed / a.radius
    T = a.gps_s + a.seconds
    rows = []
    refused_at, doubts, last_gps = None, 0, None
    t = 0.0
    while t <= T:
        ang = w * t
        truth = _move(centre, a.radius * math.sin(ang), a.radius * (1 - math.cos(ang)) - a.radius / 2)
        heading = math.degrees(math.atan2(math.cos(ang), math.sin(ang))) % 360       # velocity (cos, sin)
        R = dv.camera_R(heading, 0.0, 0.0)
        frame, _ = dv.render(imagery, sc["qz"], truth, a.height, R, K, size)
        if sc["app"]:
            frame = dv.appearance(frame, rng)
        in_gap = gap_p > 0 and t > a.gps_s and (t - a.gps_s) % gap_p > gap_p - gap_l
        if in_gap:
            frame = dv.d_clouds(frame, rng, cover=0.95)
        R_est = dv.small_rotation(a.tilt_err, rng) @ R
        frame = cv2.warpPerspective(frame, nadir_homography(K, R_est), size, flags=cv2.INTER_LINEAR)
        yaw_err = a.yaw_drift * t / T + rng.normal(0, 0.3)
        imu = (heading_of_image_up_deg(R_est) + yaw_err) % 360
        mpp = 2.0 * a.height * math.tan(math.radians(a.hfov) / 2.0) / size[0]
        # GPS this frame (None: lost / refused)
        gps = None
        if t < a.gps_s:
            gps = truth
        elif spoof is not None and refused_at is None:
            gps = _move(truth, spoof * (t - a.gps_s), 0.0)
            if last_gps is not None:           # the arbiter's kinematic gate on GPS
                jump = math.hypot(*_en(gps, last_gps[0]))
                if jump > a.max_speed * (t - last_gps[1]) + 50.0:
                    refused_at = (t, spoof * (t - a.gps_s), "kinematic")
                    gps = None
        if gps is not None:
            last_gps = (gps, t)
            nav.gps(t, *gps, heading_deg=imu)
            centre_s, R_s = gps, 600.0 if spoof is not None else 150.0     # the GPS check window
        else:
            centre_s, R_s = nav.search(t, imu)
        t0 = time.time()
        if hasattr(M, "_heading"):
            M._heading = None
        r = M.locate(frame, centre_s, R_s, mpp, heading_deg=imu, heading_tol_deg=20.0, hfov_deg=a.hfov) \
            if centre_s is not None else dict(accepted=False, reason="no prior")
        ms = (time.time() - t0) * 1000.0
        verr = math.hypot(*_en((r["predicted_lat"], r["predicted_lon"]), truth)) if r.get("accepted") else None
        if gps is not None and t >= a.gps_s and r.get("accepted"):
            # the arbiter's cross-check: an independent fix beyond 3 sigma of GPS, twice in a row
            gap = math.hypot(*_en((r["predicted_lat"], r["predicted_lon"]), gps))
            doubts = doubts + 1 if gap > 3.0 * math.hypot(5.0, max(30.0, float(r.get("sigma_m") or 0))) else 0
            if doubts >= 2:
                refused_at = (t, spoof * (t - a.gps_s), "cross-check")
                nav.gps(t, r["predicted_lat"], r["predicted_lon"], sigma_m=float(r.get("sigma_m") or 10.0),
                        heading_deg=imu)                          # vision takes over
                gps = None
        used = False
        if gps is None and r.get("accepted") and not (refused_at and refused_at[0] == t):
            used = nav.update(t, r, a.height, imu, gps_valid=False, search_m=R_s)
        lat, lon, sig, mode = nav.output(t, imu)
        err = math.hypot(*_en((lat, lon), truth)) if lat is not None else None
        rows.append(dict(t=t, gps=gps is not None, gap=bool(in_gap), matched=bool(r.get("accepted")), vis_err=verr, used=used,
                         err=err, sigma=sig, mode=mode, inliers=int(r.get("inliers") or 0), ms=ms,
                         search_m=R_s, reason=None if used else (nav.last_reason or r.get("reason") or "")[:80]))
        print(f"{t:6.0f}s gps={'Y' if gps is not None else '-'} match={'Y' if r.get('accepted') else '-'} "
              f"vis {('%6.1f' % verr) if verr is not None else '   -  '} used={'Y' if used else '-'} out "
              f"{('%6.1f' % err) if err is not None else '   -  '} ±{(sig or 0):5.0f} {mode:11s} R {R_s or 0:4.0f} "
              f"{ms:5.0f} ms", flush=True)
        t += a.dt
    lost = [x for x in rows if not x["gps"] and x["t"] >= a.gps_s]
    out = [x for x in lost if x["err"] is not None]
    e = np.array([x["err"] for x in out]) if out else np.array([np.nan])
    cov = sum(1 for x in out if x["err"] <= 3 * x["sigma"])
    prop = [x for x in out if x["mode"] == "propagated"]
    ep = np.array([x["err"] for x in prop]) if prop else np.array([np.nan])
    summ = dict(scenario=a.scenario, frames=len(lost), matched=sum(x["matched"] for x in lost),
                used=sum(x["used"] for x in lost), with_output=len(out),
                wrong_used=sum(1 for x in lost if x["used"] and x["vis_err"] is not None and x["vis_err"] > 50),
                out_med=float(np.median(e)), out_p90=float(np.percentile(e, 90)), out_max=float(np.max(e)),
                within_3sigma=f"{cov}/{len(out)}", refused_at=refused_at,
                propagated=len(prop), prop_med=float(np.median(ep)), prop_max=float(np.max(ep)),
                prop_within_3sigma=f"{sum(1 for x in prop if x['err'] <= 3 * x['sigma'])}/{len(prop)}",
                unavailable=sum(1 for x in lost if x["mode"] == "unavailable"),
                ms_med=float(np.median([x["ms"] for x in lost])) if lost else None)
    print(json.dumps(summ))
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(dict(args=vars(a), summary=summ, rows=rows), fh, indent=0, default=str)


if __name__ == "__main__":
    main()

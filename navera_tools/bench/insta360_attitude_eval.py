#!/usr/bin/env python3
"""How good is the Insta360 kit's attitude (camera_pkg.insta360_attitude)? Two measurements:

    python3 navera_tools/bench/insta360_attitude_eval.py [--json out.json] [RAW_DIR ...]

1. Synthetic motion with truth (navera_tools/sim/insta360_motion.py: fixed wing survey and steep
   turns, multirotor, car; SIMULATION of the motion) carrying the camera's REAL noise: the residuals
   of the recordings at rest (default: the user's One R, 2026-10-20 / 21, three recordings) replayed
   on top, plus a gyro bias left after the bias at rest (0.02-0.04 deg/s + a random walk). Tilt
   (roll / pitch) error vs truth, with the speed known (GPS trusted) and without (GPS lost), and the
   share inside 3 stated sigma.
2. The REAL recordings at rest through the kit (ImuStream + AttitudeFilter): the attitude's
   steadiness and the yaw drift (the gyro bias at rest is tracked; it creeps with temperature).

No camera is opened. Truth for real MOTION needs the dot-grid bench (bench/attitude_check.py with
the camera turned by hand) — not available in a recording: see docs/USER_MANUAL.md for the run.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "camera_pkg"), os.path.join(ROOT, "navera_common")):
    if p not in sys.path:
        sys.path.insert(0, p)

from camera_pkg.insta360_attitude import AttitudeFilter  # noqa: E402
from camera_pkg.insta360_imu import ImuStream, mount_rotation, raw_imu_rows  # noqa: E402
from camera_pkg.insta360_kit import replay_all  # noqa: E402
from navera_common.insta360_protocol import load_imu_calibration  # noqa: E402
from navera_tools.sim import insta360_motion as sim  # noqa: E402

DEFAULT_RAW = sorted(glob.glob(os.path.expanduser("~/navera-field/2026-10-2*_*/raw"))) + \
    [os.path.expanduser("~/navera-field/day_image_2026-10-20/raw40")]
CASES = (("uav_survey", 240), ("uav_steep", 150), ("copter", 110), ("car", 120))


def synthetic(noise, seeds=(1, 2, 3)):
    out = []
    for prof, secs in CASES:
        for speed in (True, False):
            e_all, in3 = [], []
            for seed in seeds:
                m = sim.simulate(prof, secs, seed=seed, noise=np.roll(noise, 7919 * seed, axis=0))
                t, w, f = sim.decimate(m)
                flt = AttitudeFilter()
                for i in range(len(t)):
                    j = i * 5 + 2
                    sp = (m.speed[j], m.accel_fwd[j]) if speed else (None, None)
                    s = flt.update(t[i], w[i], f[i], *sp)
                    if s is None or t[i] < 2.0:
                        continue
                    e = sim.tilt_error_deg(m.R[j], flt.R)
                    e_all.append(e)
                    in3.append(e <= 3.0 * s.tilt_sigma_deg)
            e = np.array(e_all)
            out.append(dict(profile=prof, speed_known=speed, samples=len(e), median_deg=round(float(np.median(e)), 2),
                            p95_deg=round(float(np.percentile(e, 95)), 2), max_deg=round(float(e.max()), 2),
                            within_3sigma=round(float(np.mean(in3)), 3)))
            r = out[-1]
            print(f"  {prof:11s} speed {'known  ' if speed else 'unknown'}: tilt error median {r['median_deg']:.2f} "
                  f"p95 {r['p95_deg']:.2f} max {r['max_deg']:.2f} deg, {100 * r['within_3sigma']:.1f} % "
                  f"within 3 sigma", flush=True)
    return out


def real_at_rest(path):
    R = mount_rotation("+y,+z,+x")                                    # standing on the table, as recorded
    stream = ImuStream(R, 5, load_imu_calibration(), bias_at_rest=True)
    flt = AttitudeFilter()
    st = []
    for t, p in replay_all(path, rate=0, clock="recorded"):
        for s in stream.feed(t, p):
            x = flt.update(s.t, s.gyro, s.accel)
            if x is not None:
                st.append(x)
    st = st[200:]                                                     # after the first 2 s
    span = st[-1].t - st[0].t
    roll, pitch = np.array([s.roll_deg for s in st]), np.array([s.pitch_deg for s in st])
    yaw = np.unwrap(np.radians([s.heading_deg for s in st]))
    return dict(recording=path, span_s=round(span, 1), roll_deg=round(float(roll.mean()), 2),
                pitch_deg=round(float(pitch.mean()), 2), roll_std_deg=round(float(roll.std()), 4),
                pitch_std_deg=round(float(pitch.std()), 4),
                yaw_drift_deg_per_min=round(float(np.degrees(yaw[-1] - yaw[0])) / span * 60.0, 3),
                still_share=round(float(np.mean([s.still for s in st])), 3),
                tilt_sigma_deg=round(float(st[-1].tilt_sigma_deg), 2))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", nargs="*", default=DEFAULT_RAW)
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    raws = [p for p in a.raw if os.path.isdir(p) or os.path.isfile(p)]
    R_lying = mount_rotation("+x,+z,-y")
    noise = np.vstack([sim.real_noise(raw_imu_rows(p), R_lying) for p in raws]) if raws else None
    print("noise: " + (f"REAL residuals of {len(raws)} recordings at rest" if raws else "Gaussian (no recording)"))
    res = {"noise": raws or "gaussian", "synthetic": synthetic(noise)}
    res["real_at_rest"] = []
    for p in raws:
        r = real_at_rest(p)
        res["real_at_rest"].append(r)
        print(f"  {p}: {r['span_s']} s, roll {r['roll_deg']} pitch {r['pitch_deg']} deg (std {r['roll_std_deg']} / "
              f"{r['pitch_std_deg']}), yaw drift {r['yaw_drift_deg_per_min']} deg/min", flush=True)
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()

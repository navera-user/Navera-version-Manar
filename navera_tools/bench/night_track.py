#!/usr/bin/env python3
"""Night vision over a long GPS loss: the track (anchor, motion gate, dead reckoning).

OFFLINE and SYNTHETIC. A vehicle flies a square circuit (1.5 km legs, 25 m/s, 400 m
above ground, 20 deg banked turns) over Sousse; GPS is lost after GPS_S seconds. Each
second a thermal-like frame is rendered at the true pose (navera_tools/bench/
night_conditions.py rendering), straightened with an IMU attitude error, and handled
exactly as night_subscriber does: search centre = the tracker's anchor carried to the
exposure, NightLocalizer.localize, NightTracker.offer on a fix, NightTracker.coast
otherwise. The measured heading carries a 2 deg bias + 1 deg noise and the measured
speed a +5 % bias (dead reckoning drifts).

Scripted events (frame = second):
  * CLOUD (100 % cover) frames: no fix, dead reckoning;
  * WRONG frames: the localizer's answer is replaced by a fix WRONG_M metres from the
    truth (a confident wrong STHN match that passed every check) — fault injection to
    see whether the track locks onto it (problem B16) and how it re-acquires.

Per run: published-position error over time (fix or dead reckoning), frames with no
position, frames > 100 m off, frames from the wrong fix until the error is < 50 m again.

    python3 navera_tools/bench/night_track.py [--seconds 300] [--localizer sthn|mock]
        [--wrong-at 120] [--wrong-m 300] [--csv out.csv]

--localizer mock replaces STHN by a model of it (fix within N(0, 10 m), no fix under
cloud) to test the track logic quickly; sthn runs the real network (~0.5 s per frame).
"""
import argparse
import csv
import math
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT / "night_pkg", ROOT / "navera_common", ROOT / "navera_tools" / "sim", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import night_conditions as nc  # noqa: E402
from navera_common.geo import dead_reckon, haversine_m  # noqa: E402

SPEED = 25.0
AGL = 400.0
LEG_M = 1500.0
TURN_RATE = math.degrees(9.81 * math.tan(math.radians(20.0)) / SPEED)   # deg/s at 20 deg bank
START = (35.8280, 10.6200)
GPS_S = 5


def truth(seconds: int):
    """[(t, lat, lon, heading, roll)] at 1 Hz along the square circuit (west, south, east, north)."""
    out, lat, lon, hdg, t = [], START[0], START[1], 270.0, 0
    leg_t, target = 0.0, 270.0
    while t <= seconds:
        roll = 0.0
        if abs(((target - hdg + 180) % 360) - 180) > 0.5:      # turning towards target
            step = min(TURN_RATE, abs(((target - hdg + 180) % 360) - 180))
            hdg = (hdg - step) % 360.0
            roll = -20.0
        out.append((float(t), lat, lon, hdg, roll))
        lat, lon = dead_reckon(lat, lon, hdg, SPEED, 1.0)
        leg_t += SPEED
        if leg_t >= LEG_M:
            leg_t, target = 0.0, (target - 90.0) % 360.0
        t += 1
    return out


class MockLocalizer:
    """STHN stand-in: a fix N(0, 10 m) around the truth when the frame shows ground."""

    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)
        self.truth = None
        self.cloud = False

    def localize(self, img, lat, lon, **kw):
        if self.cloud or haversine_m(lat, lon, *self.truth) > 745.0:
            return {"success": False, "conf": 0.0, "reason": "mock: no match", "lat": lat, "lon": lon}
        e = self.rng.normal(0, 10.0, 2)
        p = nc.offset(self.truth[0], self.truth[1], e[0], e[1])
        return {"success": True, "conf": 1.0, "lat": p[0], "lon": p[1]}


def run(args, tracker_cls, loc, cam, fb):
    rng = np.random.default_rng(7)
    track = tracker_cls(max_speed_mps=30.0, gate_margin_m=30.0, max_dead_reckon_s=30.0)
    clouds = set()
    for a, b in args.cloud:
        clouds.update(range(a, b))
    rows = []
    for t, lat, lon, hdg, roll in truth(args.seconds):
        k = int(t)
        h_meas = (hdg + 2.0 + rng.normal(0, 1.0)) % 360.0
        v_meas = SPEED * 1.05
        if k < GPS_S:
            track.set_known(lat, lon, t)
            rows.append(dict(t=t, src="gps", err=0.0))
            continue
        track.note_gps_lost(t)
        c = track.search_centre(t, h_meas, v_meas)
        if isinstance(loc, MockLocalizer):
            loc.truth, loc.cloud = (lat, lon), k in clouds
            r = loc.localize(None, *c)
        else:
            pose = nc.Pose("track", lat, lon, AGL, hdg, roll, 0.0, SPEED, AGL * 1.02, 0.03 * AGL,
                           (float(rng.normal(0, 0.5)), float(rng.normal(0, 0.5)), h_meas - hdg), c)
            bgr, _ = cam.render(lat, lon, AGL, nc.quat_rpy(roll, 0.0, hdg))
            gsd = 2 * AGL * math.tan(math.radians(nc.HFOV_DEG / 2)) / nc.SIZE[0]
            ctx = nc.Ctx(pose, gsd, np.random.default_rng(90_000 + k))
            look = nc._clouds(1.0) if k in clouds else nc.c_nominal
            g = look(nc.to_thermal(bgr), ctx, bgr)
            frame = nc.cv2.cvtColor((np.clip(g, 0, 1) * 255).astype(np.uint8), nc.cv2.COLOR_GRAY2BGR)
            e = pose.att_err
            img, meta = fb.build(frame, k, int(t * 1e9), nc.quat_rpy(roll + e[0], e[1], h_meas), "imu",
                                 altitude=(pose.alt_meas, pose.alt_sigma, "baro"))
            r = loc.localize(img, c[0], c[1], altitude_m=meta["altitude_m"],
                             hfov_deg=meta["camera_hfov_deg"], heading_deg=meta["heading_deg"])
        injected = k in args.wrong_at
        if injected:
            w = nc.offset(lat, lon, args.wrong_m * 0.6, args.wrong_m * 0.8)
            r = {"success": True, "conf": 1.0, "lat": w[0], "lon": w[1]}
        pub, src, why = None, "none", r.get("reason", "")
        if r.get("success"):
            why = track.offer(r["lat"], r["lon"], t, h_meas, v_meas)
            if why is None:
                pub, src = (r["lat"], r["lon"]), "night"
        if pub is None:
            p = track.coast(t, h_meas, v_meas)
            if p is not None:
                pub, src = p, "dr"
        err = haversine_m(pub[0], pub[1], lat, lon) if pub else None
        fix_err = haversine_m(r["lat"], r["lon"], lat, lon) if r.get("success") else None
        rows.append(dict(t=t, src=src, err=err, fix_err=fix_err, injected=injected,
                         cloud=k in clouds, reason=(why or "")[:60]))
    return rows


def report(rows, wrong_at, label):
    lost = [r for r in rows if r["src"] != "gps"]
    errs = [r["err"] for r in lost if r["err"] is not None]
    none = sum(r["err"] is None for r in lost)
    big = sum(1 for e in errs if e > 100.0)
    night = sum(r["src"] == "night" for r in lost)
    refused_good = sum(1 for r in lost if r["src"] != "night" and r.get("fix_err") is not None
                       and r["fix_err"] < 50.0 and not r["injected"])
    reacq = []
    for w in sorted(wrong_at):
        after = [r for r in rows if r["t"] > w]
        n = next((i + 1 for i, r in enumerate(after) if r["err"] is not None and r["err"] < 50.0), None)
        reacq.append(n)
    print(f"\n[{label}] {len(lost)} frames without GPS: night fixes {night}, refused correct fixes "
          f"{refused_good}, no position {none}, published error median "
          f"{statistics.median(errs) if errs else float('nan'):.0f} m, p90 "
          f"{np.percentile(errs, 90) if errs else float('nan'):.0f} m, max {max(errs) if errs else float('nan'):.0f} m, "
          f"> 100 m: {big} frames; frames to re-acquire (< 50 m) after each wrong fix: {reacq}")
    return dict(frames=len(lost), night=night, refused_good=refused_good, none=none,
                median=statistics.median(errs) if errs else None,
                p90=float(np.percentile(errs, 90)) if errs else None,
                max=max(errs) if errs else None, over100=big, reacquire=reacq)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=int, default=300)
    ap.add_argument("--localizer", choices=("sthn", "mock"), default="mock")
    ap.add_argument("--wrong-at", default="120", help="frames (s) with an injected wrong fix, comma-separated")
    ap.add_argument("--wrong-m", type=float, default=300.0)
    ap.add_argument("--cloud", default="60-80,200-215", help="cloud intervals a-b (s), comma-separated")
    ap.add_argument("--csv", default="")
    ap.add_argument("--night-pkg", default="",
                    help="another night_pkg source tree to test (e.g. an older commit, for before/after)")
    a = ap.parse_args()
    if a.night_pkg:
        sys.path.insert(0, str(Path(a.night_pkg).resolve()))
    a.wrong_at = {int(x) for x in a.wrong_at.split(",") if x.strip()}
    a.cloud = [tuple(int(v) for v in s.split("-")) for s in a.cloud.split(",") if s.strip()]
    from night_pkg.nodes.night_tracker import NightTracker
    cam = fb = None
    if a.localizer == "mock":
        loc = MockLocalizer()
    else:
        import torch
        from navera_common.camera_model import CameraModel
        from navera_common.frame_builder import FrameBuilder
        from night_pkg.nodes.night_localizer import NightLocalizer
        mbtiles = os.environ.get("NAVERA_MBTILES", os.path.expanduser("~/navera_data_map.mbtiles"))
        sthn = os.environ.get("NAVERA_STHN_DIR", os.path.expanduser("~/navera_data/night_pkg/STHN"))
        weights = os.environ.get("NAVERA_STHN_WEIGHTS", os.path.join(sthn, "weights/one_stage/model.safetensors"))
        lens = dict(model="pinhole", image_width=nc.SIZE[0], image_height=nc.SIZE[1], distortion=[],
                    camera_matrix=CameraModel.ideal(nc.HFOV_DEG, nc.SIZE).K.ravel().tolist())
        cam = nc._GeomCamera(lens, nc.Tiles(mbtiles).get)
        fb = FrameBuilder(CameraModel.ideal(nc.HFOV_DEG, nc.SIZE), camera_type="thermal")
        loc = NightLocalizer(sthn, weights, mbtiles)
    t0 = time.time()
    try:
        rows = run(a, NightTracker, loc, cam, fb)
    finally:
        if a.localizer == "sthn":
            del loc
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    report(rows, a.wrong_at, f"{a.localizer}, {time.time() - t0:.0f} s")
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[-1].keys()), extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()

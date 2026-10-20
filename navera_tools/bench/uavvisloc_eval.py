#!/usr/bin/env python3
"""NAVERA's day matcher on REAL drone images with GPS truth (UAV-VisLoc), no screen, no camera.

Each drone image is located against satellite tiles (uavvisloc_tiles.py) from a wrong prior:
the truth shifted by --prior-m in a random direction (a vehicle that drifted), search window
--search-m, heading from the flight track's Phi2, height from the dataset. The camera's
field of view is not given by the dataset: it is fitted on --calib-n images first (the value
that gives the most accepted matches), and reported.

    python3 navera_tools/bench/uavvisloc_eval.py <flight dir> <area dir> [--prior-m 250] [--stride 8]

Error = distance of the matcher's position from the truth. "accepted" is NAVERA's own gate.
"""
import argparse
import csv
import json
import math
import os
import random
import statistics as st
import time

import cv2
import numpy as np

import day_pkg.learned_matcher as _lm
from day_pkg.learned_matcher import LearnedMatcher
from day_pkg.local_matcher import map_m_per_px
from day_pkg.fix_sigma import day_fix_sigma_m

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("flight")
ap.add_argument("area")
ap.add_argument("--prior-m", type=float, default=250.0, help="how far the prior is from the truth")
ap.add_argument("--search-m", type=float, default=0.0, help="default: prior-m + 100")
ap.add_argument("--stride", type=int, default=8)
ap.add_argument("--width", type=int, default=1280, help="the drone image is reduced to this width")
ap.add_argument("--calib-n", type=int, default=12)
ap.add_argument("--hfov", type=float, default=0.0, help="skip the fit")
ap.add_argument("--max-tilt", type=float, default=99.0, help="only images with |roll|,|pitch| below this (deg)")
ap.add_argument("--heading-err", type=float, default=0.0, help="heading error given to the matcher (deg, random sign)")
ap.add_argument("--height-err", type=float, default=0.0, help="height error given to the matcher (fraction, random sign)")
ap.add_argument("--ground-csv", default="", help="filename,ground_m (uavvisloc_dem.py): use the height above ground "
                "(the dataset's height is above sea level; ignored ground = flat at sea level, as flight 03)")
ap.add_argument("--position", choices=("pose", "centre"), default="pose",
                help="pose (as day_subscriber: hfov_deg given, the point under the camera from the fitted pose) or "
                     "centre (the frame centre; the drone's tilt then adds height x tan(tilt): 2026-10-20 runs before this option)")
ap.add_argument("--pose-tilt-guard", type=float, default=4.0,
                help="deg, the matcher's pose_tilt_guard_deg (day_subscriber's default 4; 0 = off, the runs before "
                     "VL-1). The photos are not straightened: the expected tilt is the recorded attitude's")
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--out", default="uavvisloc_eval.json")
a = ap.parse_args()
search_m = a.search_m or a.prior_m + 100.0
rows = list(csv.DictReader(open(os.path.join(a.flight, os.path.basename(a.flight) + ".csv"))))
ground = {r["filename"]: float(r["ground_m"]) for r in csv.DictReader(open(a.ground_csv))} if a.ground_csv else {}
for r in rows:
    r["height"] = str(float(r["height"]) - ground.get(r["filename"], 0.0))     # above ground from here on
rng = random.Random(a.seed)
_refine = _lm.refine_with_pose


def _refine_keep_centre(res, *args, **kw):
    """refine_with_pose, keeping the frame-centre position too (centre_lat/lon): both are scored from one run."""
    res["centre_lat"], res["centre_lon"] = res.get("predicted_lat"), res.get("predicted_lon")
    return _refine(res, *args, **kw)


_lm.refine_with_pose = _refine_keep_centre
M = LearnedMatcher(os.path.join(a.area, "images"), zoom=17, cache_dir=os.path.join(a.area, "learned_features"),
                   pose_tilt_guard_deg=a.pose_tilt_guard)


def attitude_tilt_deg(r):
    """The photo's optical axis from straight down by its recorded attitude (Omega, Kappa)."""
    return math.degrees(math.atan(math.hypot(math.tan(math.radians(float(r["Omega"]))),
                                             math.tan(math.radians(float(r["Kappa"]))))))


def load(r):
    im = cv2.imread(os.path.join(a.flight, "drone", r["filename"]))
    s = a.width / im.shape[1]
    return cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)


def shifted(r, dist):
    th = rng.uniform(0, 2 * math.pi)
    lat, lon = float(r["lat"]), float(r["lon"])
    return (lat + dist * math.cos(th) / 111320.0, lon + dist * math.sin(th) / (111320.0 * math.cos(math.radians(lat))))


def en_m(res, r):
    """(east, north) metres of the matcher's position from the truth."""
    return ((res["predicted_lon"] - float(r["lon"])) * 111320.0 * math.cos(math.radians(float(r["lat"]))),
            (res["predicted_lat"] - float(r["lat"])) * 111320.0)


def err_m(res, r):
    return math.hypot(*en_m(res, r))


def locate(r, im, hfov, prior_m, smeters):
    h = float(r["height"]) * (1.0 + a.height_err * rng.choice((-1, 1)) * (prior_m > 40))
    mpp = 2 * h * math.tan(math.radians(hfov) / 2) / im.shape[1]
    prior = shifted(r, prior_m)
    t0 = time.time()
    res = M.locate(im, prior, smeters, mpp, heading_deg=(float(r["Phi2"]) + a.heading_err * rng.choice((-1, 1)) * (prior_m > 40)) % 360,
                   hfov_deg=hfov if a.position == "pose" else None, expected_tilt_deg=attitude_tilt_deg(r))
    res["ms"] = (time.time() - t0) * 1000
    return res


def speed_mps(i):
    """Ground speed from the neighbouring images' GPS and times (the dataset has no speed)."""
    from datetime import datetime
    j, k = max(i - 1, 0), min(i + 1, len(rows) - 1)
    if j == k:
        return None
    dt = (datetime.fromisoformat(rows[k]["date"]) - datetime.fromisoformat(rows[j]["date"])).total_seconds()
    if dt <= 0:
        return None
    de = (float(rows[k]["lon"]) - float(rows[j]["lon"])) * 111320.0 * math.cos(math.radians(float(rows[j]["lat"])))
    dn = (float(rows[k]["lat"]) - float(rows[j]["lat"])) * 111320.0
    return math.hypot(de, dn) / dt


def fit_hfov():
    idx = [int(i * (len(rows) - 1) / (a.calib_n - 1)) for i in range(a.calib_n)]
    best = (-1, None)
    for hfov in (40, 46, 52, 58, 64, 70, 76, 82, 88):
        ok = sum(1 for i in idx if locate(rows[i], load(rows[i]), hfov, 40.0, 200.0)["accepted"])
        print(f"  hfov {hfov}: {ok}/{len(idx)} accepted", flush=True)
        if ok > best[0]:
            best = (ok, hfov)
    # refine around the best
    for hfov in (best[1] - 3, best[1] - 1.5, best[1] + 1.5, best[1] + 3):
        ok = sum(1 for i in idx if locate(rows[i], load(rows[i]), hfov, 40.0, 200.0)["accepted"])
        print(f"  hfov {hfov}: {ok}/{len(idx)} accepted", flush=True)
        if ok > best[0]:
            best = (ok, hfov)
    return best[1]


hfov = a.hfov or fit_hfov()
print("hfov used:", hfov, flush=True)
out = []
for i in range(0, len(rows), a.stride):
    r = rows[i]
    tilt = max(abs(float(r["Omega"])), abs(float(r["Kappa"])))
    if tilt > a.max_tilt:
        continue
    res = locate(r, load(r), hfov, a.prior_m, search_m)
    e = err_m(res, r) if res.get("predicted_lat") is not None else None
    de, dn = en_m(res, r) if e is not None else (None, None)
    spd = speed_mps(i)
    stated = day_fix_sigma_m(res.get("sigma_m"), speed_mps=spd, height_m=float(r["height"])) if res.get("sigma_m") else None
    out.append(dict(file=r["filename"], east_m=None if de is None else round(de, 1), north_m=None if dn is None else round(dn, 1), tilt=round(tilt, 1), accepted=bool(res["accepted"]), err_m=None if e is None else round(e, 1),
                    inliers=res.get("inliers"), ms=round(res["ms"]), reason=res.get("reason"),
                    # the stated accuracy (day_fix_sigma_m, as day_subscriber publishes it) and what it is built from
                    match_sigma_m=res.get("sigma_m"), stated_sigma_m=None if stated is None else round(stated, 2),
                    spread=res.get("spread"), position_from=res.get("position_from"),
                    centre_east_m=None if res.get("centre_lat") is None else round(en_m(dict(predicted_lat=res["centre_lat"], predicted_lon=res["centre_lon"]), r)[0], 1),
                    centre_north_m=None if res.get("centre_lat") is None else round(en_m(dict(predicted_lat=res["centre_lat"], predicted_lon=res["centre_lon"]), r)[1], 1), pose_tilt_deg=res.get("pose_tilt_deg"), pose_guard=res.get("pose_guard"),
                    omega=float(r["Omega"]), kappa=float(r["Kappa"]), phi2=float(r["Phi2"]), height_m=float(r["height"]), speed_mps=None if spd is None else round(spd, 1),
                    t=r["date"], lat=float(r["lat"]), lon=float(r["lon"])))
    print(f"{r['filename']} tilt {tilt:4.1f}  {'ACC' if res['accepted'] else 'rej'}  err {'-' if e is None else round(e, 1)} m  "
          f"inl {res.get('inliers')}  {res['ms']:.0f} ms", flush=True)

acc = [o for o in out if o["accepted"]]
pose_share = sum(o["position_from"] not in (None, "frame centre") for o in acc) / len(acc) if acc else None
ok = [o["err_m"] for o in acc]
bad = [o for o in acc if o["err_m"] > 30]
good = [o for o in acc if o["err_m"] <= 100]       # a fix within 100 m: the offset below is theirs
be = st.median([o["east_m"] for o in good]) if good else 0.0
bn = st.median([o["north_m"] for o in good]) if good else 0.0
deb = [math.hypot(o["east_m"] - be, o["north_m"] - bn) for o in good]
summ = dict(images=len(out), bias_east_m=round(be, 1), bias_north_m=round(bn, 1),
            err_after_bias_median=round(st.median(deb), 1) if deb else None,
            err_after_bias_p95=round(sorted(deb)[int(0.95 * (len(deb) - 1))], 1) if deb else None,
            accepted_over_100m=len(acc) - len(good), prior_m=a.prior_m, search_m=search_m, hfov=hfov, accepted=len(acc),
            accepted_wrong_over_30m=len(bad),
            err_median=round(st.median(ok), 1) if ok else None,
            err_p95=round(sorted(ok)[int(0.95 * (len(ok) - 1))], 1) if ok else None,
            err_max=round(max(ok), 1) if ok else None,
            position=a.position, pose_tilt_guard=a.pose_tilt_guard,
            accepted_pose_guard=sum(bool(o["pose_guard"]) for o in acc), accepted_from_pose=None if pose_share is None else round(pose_share, 3),
            ms_median=round(st.median([o["ms"] for o in out])) if out else None)
print(json.dumps(summ))
json.dump(dict(summary=summ, frames=out), open(a.out, "w"), indent=1)

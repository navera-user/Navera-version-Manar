#!/usr/bin/env python3
"""NAVERA's day matcher on REAL drone frames with GNSS truth (AerialVL, Qingdao, March 2023).

AerialVL (github.com/hmf21/AerialVL, Hugging Face hmf21/AerialVL, CC BY 4.0): a multirotor with a
gimballed downward RGB camera (FLIR BFS-U3-31S4C, 2048 x 1536), NovAtel GNSS (1.5 m RMS), frames
named @<UTC ms>@<lon>@<lat>@.png, turned by the authors so that the image top points EAST. The
dataset gives no height and no lens: the frame scale (metres per pixel) is fitted per sequence on
--calib-n frames (the height that gives the most accepted matches, refined by the median fitted
scale of the matches, as `locate_any_height` measures a height) and then held fixed for the whole
sequence, as a barometer height would be. The gimbal keeps the camera nadir: the position is the
frame centre (no hfov given to the matcher, so no pose; see --hfov).

Each frame is located as uavvisloc_eval.py does it: prior --prior-m off the truth in a random
direction, search prior + 100 m, heading 90 (east-up), no tracking between frames, against z17
map tiles (prepare_area.py, Esri World Imagery as for a mission, or the dataset's own map).

    python3 navera_tools/bench/aerialvl_eval.py <sequence dir> <area dir> --out f.json [--stride 1]

The output JSON has the same frames/summary layout as uavvisloc_eval.py, so replay_sigma_cal.py
--table scores it (stated sigma, self-calibration).
"""
import argparse
import glob
import json
import math
import os
import random
import statistics as st
import time

import cv2

from day_pkg.learned_matcher import LearnedMatcher
from day_pkg.fix_sigma import day_fix_sigma_m

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("seq")
ap.add_argument("area")
ap.add_argument("--prior-m", type=float, default=250.0)
ap.add_argument("--search-m", type=float, default=0.0, help="default: prior-m + 100")
ap.add_argument("--stride", type=int, default=1)
ap.add_argument("--width", type=int, default=1280, help="the frame is reduced to this width")
ap.add_argument("--calib-n", type=int, default=12)
ap.add_argument("--nominal-hfov", type=float, default=60.0,
                help="deg; only turns the fitted height into a frame scale (with the centre position, "
                     "height and hfov enter only through their product)")
ap.add_argument("--height", type=float, default=0.0, help="skip the fit (m, with --nominal-hfov)")
ap.add_argument("--hfov", type=float, default=0.0, help="give the matcher an hfov (pose position); default none")
ap.add_argument("--heading", type=float, default=90.0, help="image-top direction of the dataset's frames")
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--out", required=True)
a = ap.parse_args()
search_m = a.search_m or a.prior_m + 100.0
rng = random.Random(a.seed)


def parse(p):
    _, t, lon, lat, _ = os.path.basename(p).split("@")
    return dict(file=os.path.basename(p), path=p, t=int(t) / 1000.0, lat=float(lat), lon=float(lon))


rows = sorted((parse(p) for p in glob.glob(os.path.join(a.seq, "*.png"))), key=lambda r: r["t"])
M = LearnedMatcher(os.path.join(a.area, "images"), zoom=17, cache_dir=os.path.join(a.area, "learned_features"))


def load(r):
    im = cv2.imread(r["path"])
    s = a.width / im.shape[1]
    return cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)


def shifted(r, dist):
    th = rng.uniform(0, 2 * math.pi)
    return (r["lat"] + dist * math.cos(th) / 111320.0,
            r["lon"] + dist * math.sin(th) / (111320.0 * math.cos(math.radians(r["lat"]))))


def en_m(lat, lon, r):
    return ((lon - r["lon"]) * 111320.0 * math.cos(math.radians(r["lat"])), (lat - r["lat"]) * 111320.0)


def locate(r, im, h, prior_m, smeters):
    mpp = 2 * h * math.tan(math.radians(a.nominal_hfov) / 2) / im.shape[1]
    t0 = time.time()
    res = M.locate(im, shifted(r, prior_m), smeters, mpp, heading_deg=a.heading % 360,
                   hfov_deg=a.hfov or None, expected_tilt_deg=0.0)
    res["ms"] = (time.time() - t0) * 1000
    return res


def speed_mps(i):
    j, k = max(i - 1, 0), min(i + 1, len(rows) - 1)
    dt = rows[k]["t"] - rows[j]["t"]
    if j == k or dt <= 0:
        return None
    return math.hypot(*en_m(rows[k]["lat"], rows[k]["lon"], rows[j])) / dt


def fit_height():
    idx = [int(i * (len(rows) - 1) / (a.calib_n - 1)) for i in range(a.calib_n)]
    ims = {i: load(rows[i]) for i in idx}
    best = (-1, None, [])
    for h in (60, 80, 100, 120, 150, 180, 220, 260, 320):
        res = [locate(rows[i], ims[i], h, 40.0, 200.0) for i in idx]
        ok = [x for x in res if x["accepted"]]
        print(f"  height {h}: {len(ok)}/{len(idx)} accepted", flush=True)
        if len(ok) > best[0]:
            best = (len(ok), h, [float(x.get("scale_residual") or 1.0) for x in ok])
    h = best[1] * (st.median(best[2]) if best[2] else 1.0)
    print(f"  fitted height {h:.0f} m (nominal hfov {a.nominal_hfov} deg; best grid {best[1]}, "
          f"median scale {st.median(best[2]) if best[2] else 1:.3f})", flush=True)
    return h


h = a.height or fit_height()
out = []
for i in range(0, len(rows), a.stride):
    r = rows[i]
    res = locate(r, load(r), h, a.prior_m, search_m)
    e = de = dn = None
    if res.get("predicted_lat") is not None:
        de, dn = en_m(res["predicted_lat"], res["predicted_lon"], r)
        e = math.hypot(de, dn)
    spd = speed_mps(i)
    stated = day_fix_sigma_m(res.get("sigma_m"), speed_mps=spd, height_m=h) if res.get("sigma_m") else None
    out.append(dict(file=r["file"], east_m=None if de is None else round(de, 1), north_m=None if dn is None else round(dn, 1),
                    accepted=bool(res["accepted"]), err_m=None if e is None else round(e, 1),
                    inliers=res.get("inliers"), ms=round(res["ms"]), reason=res.get("reason"),
                    match_sigma_m=res.get("sigma_m"), stated_sigma_m=None if stated is None else round(stated, 2),
                    scale_residual=res.get("scale_residual"), rescaled_by=res.get("rescaled_by"),
                    rotation_deg=res.get("rotation_deg"), features=res.get("features"),
                    position_from=res.get("position_from"), height_m=round(h, 1),
                    speed_mps=None if spd is None else round(spd, 1), t=r["t"], lat=r["lat"], lon=r["lon"]))
    print(f"{r['file']}  {'ACC' if res['accepted'] else 'rej'}  err {'-' if e is None else round(e, 1)} m  "
          f"inl {res.get('inliers')}  {res['ms']:.0f} ms  {'' if res['accepted'] else res.get('reason')}", flush=True)

acc = [o for o in out if o["accepted"]]
errs = sorted(o["err_m"] for o in acc)
summ = dict(images=len(out), accepted=len(acc), height_fit_m=round(h, 1), nominal_hfov=a.nominal_hfov,
            hfov=a.hfov or None, prior_m=a.prior_m, search_m=search_m,
            err_median=round(st.median(errs), 1) if errs else None,
            err_p90=errs[int(0.9 * (len(errs) - 1))] if errs else None,
            err_max=errs[-1] if errs else None,
            accepted_over_50m=sum(e > 50 for e in errs), accepted_over_100m=sum(e > 100 for e in errs),
            ms_median=round(st.median(o["ms"] for o in out)) if out else None)
print(json.dumps(summ))
json.dump(dict(summary=summ, frames=out), open(a.out, "w"), indent=1)

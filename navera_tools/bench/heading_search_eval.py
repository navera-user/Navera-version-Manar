#!/usr/bin/env python3
"""Cost and benefit of the day heading search (D18: local_heading_search) on real drone photos.

The IRIS kit has no magnetometer (Insta360 IMU): the heading comes from the GPS course and vision fixes,
carried by the gyro (day_pkg.gyro_heading), and can be unknown (GPS denied from take-off) or drift. The
learned matcher then either trusts a wrong heading (no match beyond ~20 deg) or searches every 30 deg
(LearnedMatcher.locate(heading_search=True)). Here UAV-VisLoc photos (Esri map, the product matcher,
uavvisloc_eval.py's record of each photo: height above ground, fitted hfov, heading Phi2) are located
from a prior --prior-m off with the heading given wrong by each of --errors, search off and on:
accepted, wrong (> 50 m), time per frame (all / failed only).

    flock /tmp/claude-1000/navera_gpu.lock python3 navera_tools/bench/heading_search_eval.py [--flight 04] [--n 30]
"""
import argparse
import json
import math
import os
import random
import statistics as st
import time

import cv2

from day_pkg.learned_matcher import LearnedMatcher

DATA = "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/uavvisloc/full"
RES = os.path.expanduser("~/.navera_sim/pubdata/uavvisloc")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flight", default="04")
    ap.add_argument("--n", type=int, default=30, help="photos: those the Esri run accepted within 30 m, evenly spread, "
                                                      "plus as many it refused (the cost on frames that fail)")
    ap.add_argument("--errors", default="0,15,30,60,120,180,none", help="deg; none: no heading given")
    ap.add_argument("--prior-m", type=float, default=100.0)
    ap.add_argument("--search-m", type=float, default=250.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    d = json.load(open(os.path.join(RES, f"f{a.flight}_esri.json")))
    hfov = float(d["summary"]["hfov"])
    good = [r for r in d["frames"] if r["accepted"] and r["err_m"] < 30]
    bad = [r for r in d["frames"] if not r["accepted"]]
    pick = lambda lst, n: [lst[int(i * (len(lst) - 1) / max(n - 1, 1))] for i in range(min(n, len(lst)))]  # noqa: E731
    frames = [(r, True) for r in pick(good, a.n)] + [(r, False) for r in pick(bad, a.n)]
    area = os.path.join(DATA, f"area{a.flight}_esri")
    M = LearnedMatcher(os.path.join(area, "images"), zoom=17, cache_dir=os.path.join(area, "learned_features"),
                       pose_tilt_guard_deg=4.0)
    rng = random.Random(a.seed)
    ims = {}

    def load(r):
        if r["file"] not in ims:
            im = cv2.imread(os.path.join(DATA, a.flight, "drone", r["file"]))
            s = a.width / im.shape[1]
            ims[r["file"]] = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        return ims[r["file"]]

    def tilt(r):
        return math.degrees(math.atan(math.hypot(math.tan(math.radians(r["omega"])),
                                                 math.tan(math.radians(r["kappa"])))))
    print(f"flight {a.flight}: {len(frames)} photos ({sum(g for _, g in frames)} located by the Esri run), hfov {hfov}")
    print("| heading error | search | located (of the good) | wrong > 50 m | ms median, all "
          "| ms median / max, failed |")
    print("|---|---|---|---|---|---|")
    for err in (None if x == "none" else float(x) for x in a.errors.split(",")):
        for search in (False, True):
            acc = wrong = 0
            ms_all, ms_fail = [], []
            for r, was_good in frames:
                M._heading = None                       # no memory of a previous frame's rotation
                th = rng.uniform(0, 2 * math.pi)
                prior = (r["lat"] + a.prior_m * math.cos(th) / 111320.0,
                         r["lon"] + a.prior_m * math.sin(th) / (111320.0 * math.cos(math.radians(r["lat"]))))
                im = load(r)
                mpp = 2 * r["height_m"] * math.tan(math.radians(hfov) / 2) / im.shape[1]
                hdg = None if err is None else (r["phi2"] + err * rng.choice((-1, 1))) % 360
                t0 = time.time()
                res = M.locate(im, prior, a.search_m, mpp, heading_deg=hdg, hfov_deg=hfov, heading_search=search,
                               expected_tilt_deg=tilt(r))
                ms = (time.time() - t0) * 1000
                ms_all.append(ms)
                if res.get("accepted"):
                    e = math.hypot((res["predicted_lon"] - r["lon"]) * 111320.0 * math.cos(math.radians(r["lat"])),
                                   (res["predicted_lat"] - r["lat"]) * 111320.0)
                    acc += was_good and e <= 50
                    wrong += e > 50
                else:
                    ms_fail.append(ms)
            label = "unknown" if err is None else "%.0f deg" % err
            print(f"| {label} | {'on' if search else 'off'} | {acc}/{sum(g for _, g in frames)} | {wrong} | "
                  f"{st.median(ms_all):.0f} | " + (f"{st.median(ms_fail):.0f} / {max(ms_fail):.0f}" if ms_fail else "-")
                  + " |", flush=True)


if __name__ == "__main__":
    main()

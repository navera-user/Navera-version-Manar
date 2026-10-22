#!/usr/bin/env python3
"""UAV-VisLoc frames replayed as the product sees them: straightened by the attitude first (VL-1 check).

The Esri re-run (2026-10-22, uavvisloc_eval.py) accepted 3 fixes > 100 m (04_0439, 04_0663, 05_0149):
camera poses from 12-58 inliers on photos tilted 3-10 deg, which the VL-1 pose guard let through because
the bench photos are NOT straightened (the expected tilt is then the photo's own, and the poses agreed
with it within 4 deg). In the product the camera frame is straightened with the IMU attitude before
matching (camera_pkg / navera_common.camera_model.nadir_homography) and the expected tilt is 0.

Here each listed photo is warped to the straight-down view by its recorded attitude (Omega, Kappa: the
rotation K R K^-1 about the lens centre) and located with expected_tilt_deg = 0, from --priors priors
--prior-m off in evenly spread directions (search --search-m), as uavvisloc_eval.py otherwise (same
matcher, gates, height, heading Phi2, fitted hfov). The dataset does not say how Omega / Kappa map to
the image axes: the convention is chosen on --calib frames (accepted, < 20 m, >= 30 inliers, tilt > 4
deg in the Esri runs) as the one that locates most of them, then brings their pose tilt closest to 0; reported with its
evidence. Each frame is also run unstraightened (expected tilt = the photo's), as the bench did.

    flock /tmp/claude-1000/navera_gpu.lock python3 navera_tools/bench/uavvisloc_straightened.py
"""
import argparse
import itertools
import json
import math
import os
import statistics as st

import cv2
import numpy as np

from day_pkg.learned_matcher import LearnedMatcher

DATA = "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/uavvisloc/full"
RES = os.path.expanduser("~/.navera_sim/pubdata/uavvisloc")


def record(name):
    """The Esri run's record of a photo (truth, attitude, height above ground, fitted hfov)."""
    fl = name[:2]
    d = json.load(open(os.path.join(RES, f"f{fl}_esri.json")))
    r = next(x for x in d["frames"] if x["file"] == name)
    return dict(r, hfov=float(d["summary"]["hfov"]), flight=fl)


def rot(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def straighten(im, hfov, omega, kappa, conv):
    """The photo warped as a camera turned by -attitude would see it (convention conv = (swap, s1, s2)):
    omega about the image x axis and kappa about y (swap: the other way round), signs s1, s2."""
    swap, s1, s2 = conv
    h, w = im.shape[:2]
    f = 0.5 * w / math.tan(math.radians(hfov) / 2)
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1.0]])
    a, b = ("y", "x") if swap else ("x", "y")
    R = rot(a, s1 * omega) @ rot(b, s2 * kappa)
    H = K @ R @ np.linalg.inv(K)
    return cv2.warpPerspective(im, H, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def tilt_of(r):
    return math.degrees(math.atan(math.hypot(math.tan(math.radians(r["omega"])), math.tan(math.radians(r["kappa"])))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", default="04_0439.JPG,04_0663.JPG,05_0149.JPG")
    ap.add_argument("--calib", default="04_0227.JPG,04_0309.JPG,04_0659.JPG,04_0675.JPG,06_0231.JPG,"
                                       "06_0287.JPG,11_0171.JPG,11_0335.JPG,11_0375.JPG,01_0489.JPG")
    ap.add_argument("--priors", type=int, default=8)
    ap.add_argument("--prior-m", type=float, default=250.0)
    ap.add_argument("--search-m", type=float, default=350.0)
    ap.add_argument("--width", type=int, default=1280)
    a = ap.parse_args()
    matchers = {}

    def matcher(fl):
        if fl not in matchers:
            area = os.path.join(DATA, f"area{fl}_esri")
            first = next(iter(matchers.values()), None)
            matchers[fl] = LearnedMatcher(os.path.join(area, "images"), zoom=17,
                                          cache_dir=os.path.join(area, "learned_features"),
                                          pose_tilt_guard_deg=4.0, models_from=first)
        return matchers[fl]

    def load(r):
        im = cv2.imread(os.path.join(DATA, r["flight"], "drone", r["file"]))
        s = a.width / im.shape[1]
        return cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)

    def locate(r, im, expected, prior_dir=None):
        lat, lon = r["lat"], r["lon"]
        if prior_dir is not None:
            d = a.prior_m
            lat += d * math.cos(prior_dir) / 111320.0
            lon += d * math.sin(prior_dir) / (111320.0 * math.cos(math.radians(r["lat"])))
        mpp = 2 * r["height_m"] * math.tan(math.radians(r["hfov"]) / 2) / im.shape[1]
        res = matcher(r["flight"]).locate(im, (lat, lon), a.search_m if prior_dir is not None else 150.0, mpp,
                                          heading_deg=r["phi2"] % 360, hfov_deg=r["hfov"], expected_tilt_deg=expected)
        err = None
        if res.get("accepted"):
            de = (res["predicted_lon"] - r["lon"]) * 111320.0 * math.cos(math.radians(r["lat"]))
            dn = (res["predicted_lat"] - r["lat"]) * 111320.0
            err = math.hypot(de, dn)
        return res, err

    # 1. the attitude convention, from frames the matcher placed right
    calib = [record(n) for n in a.calib.split(",")]
    print("convention (swap, sign omega, sign kappa): median |pose tilt| of the straightened calibration frames")
    scores = []
    for conv in itertools.product((False, True), (1, -1), (1, -1)):
        tilts = []
        for r in calib:
            res, err = locate(r, straighten(load(r), r["hfov"], r["omega"], r["kappa"], conv), 0.0)
            if res.get("pose_tilt_deg") is not None and err is not None and err < 30:
                tilts.append(res["pose_tilt_deg"])
        med = st.median(tilts) if tilts else 99.0
        scores.append((med, conv, tilts))
        print(f"  {conv}: {len(tilts)}/{len(calib)} located, pose tilt median {med:.2f} deg "
              f"{[round(t, 1) for t in tilts]}")
    raw = []
    for r in calib:
        res, err = locate(r, load(r), tilt_of(r))
        if res.get("pose_tilt_deg") is not None and err is not None and err < 30:
            raw.append(res["pose_tilt_deg"])
    print(f"  unstraightened: pose tilt median {st.median(raw) if raw else float('nan'):.2f} deg "
          f"(photo tilts {[round(tilt_of(r), 1) for r in calib]})")
    conv = min(scores, key=lambda x: (-len(x[2]), x[0]))[1]      # most located, then the smallest tilt
    print(f"chosen: {conv}\n")

    # 2. the three frames
    print("| frame (photo tilt) | as the bench (unstraightened, expected = photo tilt) "
          "| straightened, expected 0 (product) |")
    print("|---|---|---|")
    for n in a.frames.split(","):
        r = record(n)
        im0 = load(r)
        im1 = straighten(im0, r["hfov"], r["omega"], r["kappa"], conv)
        cols = []
        for im, exp in ((im0, tilt_of(r)), (im1, 0.0)):
            acc, errs, guarded, poses, far = 0, [], 0, [], 0
            for k in range(a.priors):
                res, err = locate(r, im, exp, 2 * math.pi * k / a.priors)
                if res.get("accepted"):
                    acc += 1
                    errs.append(err)
                    far += err > 100
                    guarded += bool(res.get("pose_guard"))
                if res.get("pose_tilt_deg") is not None:
                    poses.append(res["pose_tilt_deg"])
            cols.append(f"{acc}/{a.priors} accepted, {far} > 100 m, pose guard {guarded}, errors "
                        f"{[round(e) for e in errs]} m, pose tilts {[round(p, 1) for p in poses]}")
        print(f"| {n} ({tilt_of(r):.1f} deg) | {cols[0]} | {cols[1]} |")


if __name__ == "__main__":
    main()

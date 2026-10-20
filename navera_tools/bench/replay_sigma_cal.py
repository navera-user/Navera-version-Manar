#!/usr/bin/env python3
"""Replay day-vision fixes with known errors as flights: the first part with GPS (the stated sigma is calibrated
against it, day_pkg.fix_sigma.SigmaCalibration), the rest GPS lost. Coverage of the published sigma after the
loss (within 1/2/3 sigma): self-calibration vs the model alone vs fixed floors.

    python3 navera_tools/bench/replay_sigma_cal.py --uavvisloc F.json [--gps-frac 0.3] --campaign DIR
"""
import argparse
import csv
import glob
import json
import math
import os
import re
import statistics as st
import sys

sys.path[:0] = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "day_pkg")]
from day_pkg.fix_sigma import SigmaCalibration, day_fix_sigma_m  # noqa: E402
from day_pkg.local_matcher import fix_sigma_m  # noqa: E402

MPP_Z17_SOUSSE = 156543.03392 * math.cos(math.radians(35.82227)) / 2 ** 17


def coverage(pairs):
    """pairs: (err, sigma) -> (within 1, 2, 3 sigma), median sigma."""
    if not pairs:
        return None
    z = [e / s for e, s in pairs]
    return tuple(round(sum(x <= k for x in z) / len(z), 3) for k in (1, 2, 3)), round(st.median(s for _, s in pairs), 1)


def run(flights, floors, min_samples):
    """flights: list of (calibration [(err, model sigma)], lost [(err, model sigma)])."""
    out = {}
    lost_all = [p for _, lost in flights for p in lost]
    out["model alone"] = coverage(lost_all)
    for f in floors:
        out[f"fixed floor {f:.0f} m"] = coverage([(e, max(s, f)) for e, s in lost_all])
    for f in floors[:1] + floors[-1:]:
        pub = []
        for cal_part, lost in flights:
            cal = SigmaCalibration(floor_no_cal_m=f, min_samples=min_samples)
            for e, s in cal_part:
                cal.add(e, s)
            pub += [(e, cal.apply(s)) for e, s in lost]
        out[f"self-calibrated (no-cal floor {f:.0f} m)"] = coverage(pub)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--uavvisloc", action="append", default=[])
    ap.add_argument("--campaign", default="")
    ap.add_argument("--gps-frac", type=float, default=0.3)
    ap.add_argument("--min-samples", type=int, default=15)
    a = ap.parse_args()
    floors = [15.0, 20.0, 30.0]
    if a.uavvisloc:
        flights = []
        for path in a.uavvisloc:
            fr = [f for f in json.load(open(path))["frames"] if f["accepted"] and f.get("stated_sigma_m")]
            k = int(a.gps_frac * len(fr))
            # the GPS check frames come every gps_check_period_s (2 s): every 2nd image while GPS is trusted
            cal = [(f["err_m"], f["stated_sigma_m"]) for f in fr[:k:2]]
            flights.append((cal, [(f["err_m"], f["stated_sigma_m"]) for f in fr[k:]]))
        print("UAV-VisLoc (real drone flight imagery):", json.dumps(run(flights, floors, a.min_samples), indent=1))
    if a.campaign:
        flights = []
        for p in sorted(glob.glob(os.path.join(a.campaign, "*_v*.csv"))):
            v = float(re.search(r"_v(\d+)\.csv", p).group(1))
            rows = [r for r in csv.DictReader(open(p)) if r["vision_err_m"] not in ("", "None") and r["inliers"] not in ("", "None")]
            model = lambda r: day_fix_sigma_m(fix_sigma_m(int(float(r["inliers"])), MPP_Z17_SOUSSE), speed_mps=v,  # noqa: E731
                                              height_m=float(r["height_m"] or 1500))
            cal = [(float(r["vision_err_m"]), model(r)) for r in rows if r["phase"] == "gps"][::2]   # the 55 s GPS phase: every 2nd frame (product: every 2 s for minutes)
            lost = [(float(r["vision_err_m"]), model(r)) for r in rows if r["phase"] == "lost"]
            if lost:
                flights.append((cal, lost))
        print("real camera screen campaign (each run = a flight):", json.dumps(run(flights, floors, a.min_samples), indent=1))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Replay day-vision fixes with known errors as flights: the first part with GPS (the stated sigma is calibrated
against it, day_pkg.fix_sigma.SigmaCalibration), the rest GPS lost. Coverage of the published sigma after the
loss (within 1/2/3 sigma): self-calibration vs the model alone vs fixed floors.

    python3 navera_tools/bench/replay_sigma_cal.py --uavvisloc F.json [--gps-frac 0.3] --campaign DIR
    python3 navera_tools/bench/replay_sigma_cal.py --table --uavvisloc f03.json --uavvisloc f05.json ...

--table: one row per UAV-VisLoc flight and a pooled row: accepted fixes, error median/p90/max, wrong
fixes (> --wrong-m), share within 3 sigma of the model alone, of the uncalibrated publication
max(model, floor_no_cal) over the whole flight (GPS denied from take-off), and of the self-calibrated
sigma after the loss, with the calibration terms (f, b) and the fixes outside 3 published sigma.
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


def _q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))] if v else float("nan")


def flight_row(name, frames, summary, gps_frac, min_samples, floor_no_cal, wrong_m):
    """One flight's numbers (dict) and its (err, published sigma) pairs per scheme."""
    fr = [f for f in frames if f["accepted"] and f.get("stated_sigma_m")]
    k = int(gps_frac * len(fr))
    cal = SigmaCalibration(floor_no_cal_m=floor_no_cal, min_samples=min_samples)
    for f in fr[:k:2]:
        cal.add(f["err_m"], f["stated_sigma_m"])
    lost = fr[k:]
    err = [f["err_m"] for f in fr]
    pairs = {"model": [(f["err_m"], f["stated_sigma_m"]) for f in lost],
             "nocal": [(f["err_m"], max(f["stated_sigma_m"], floor_no_cal)) for f in fr],
             "cal": [(f["err_m"], cal.apply(f["stated_sigma_m"])) for f in lost]}
    within3 = lambda ps: sum(e <= 3 * s for e, s in ps) / len(ps) if ps else float("nan")  # noqa: E731
    t = cal.terms()
    row = dict(flight=name, height_m=round(st.median(f["height_m"] for f in frames)), hfov=summary.get("hfov"),
               images=len(frames), accepted=len(fr), err_med=_q(err, 0.5), err_p90=_q(err, 0.9), err_max=max(err, default=float("nan")),
               wrong=sum(e > wrong_m for e in err), cal_samples=cal.samples, f=None if t is None else round(t[0], 2),
               b=None if t is None else round(t[1], 1),
               w3_model=within3(pairs["model"]), w3_nocal=within3(pairs["nocal"]), w3_cal=within3(pairs["cal"]),
               sig_cal_med=_q([s for _, s in pairs["cal"]], 0.5),
               out3_cal=sum(e > 3 * s for e, s in pairs["cal"]), out3_cal_wrong=sum(e > 3 * s and e > wrong_m for e, s in pairs["cal"]),
               out3_nocal_wrong=sum(e > 3 * s and e > wrong_m for e, s in pairs["nocal"]))
    return row, pairs


def _excluded(fname, ranges):
    """ranges: ["06_0099-06_0180", ...] (inclusive, by image name)."""
    stem = fname.rsplit(".", 1)[0]
    return any(lo <= stem <= hi for lo, hi in (r.split("-") for r in ranges))


def _with_position(f, mode):
    """The frame scored with another position (uavvisloc_eval.py --position pose keeps both):
    'centre' = the frame centre; 'guard:T' = the pose position unless its tilt differs from the
    recorded attitude's tilt by more than T deg (then the frame centre: a pose that disagrees with
    the attitude is a poorly conditioned solution); 'refuse:T' = such a match refused."""
    if mode == "as-run" or not f.get("accepted") or f.get("centre_east_m") is None:
        return f
    use_centre = mode == "centre"
    if mode.startswith(("guard:", "refuse:")) and f.get("position_from") == "camera pose":
        rec = math.degrees(math.atan(math.hypot(math.tan(math.radians(f["omega"])), math.tan(math.radians(f["kappa"])))))
        use_centre = abs(f["pose_tilt_deg"] - rec) > float(mode.split(":")[1])
        if use_centre and mode.startswith("refuse:"):          # the match refused instead
            return dict(f, accepted=False)
    if not use_centre:
        return f
    g = dict(f)
    g["east_m"], g["north_m"] = f["centre_east_m"], f["centre_north_m"]
    g["err_m"] = round(math.hypot(g["east_m"], g["north_m"]), 1)
    return g


def table(paths, gps_frac, min_samples, floor_no_cal, wrong_m, exclude=(), position="as-run"):
    rows, pooled = [], {"model": [], "nocal": [], "cal": []}
    allerr = []
    for p in paths:
        d = json.load(open(p))
        name = os.path.basename(p).split("_")[0]
        d["frames"] = [_with_position(f, position) for f in d["frames"] if not _excluded(f["file"], exclude)]
        r, pairs = flight_row(name, d["frames"], d["summary"], gps_frac, min_samples, floor_no_cal, wrong_m)
        rows.append(r)
        for k in pooled:
            pooled[k] += pairs[k]
        allerr += [f["err_m"] for f in d["frames"] if f["accepted"] and f.get("stated_sigma_m")]
    w3 = lambda ps: sum(e <= 3 * s for e, s in ps) / len(ps) if ps else float("nan")  # noqa: E731
    rows.append(dict(flight="pooled", height_m=None, hfov=None, images=sum(r["images"] for r in rows),
                     accepted=sum(r["accepted"] for r in rows), err_med=_q(allerr, 0.5), err_p90=_q(allerr, 0.9),
                     err_max=max(allerr, default=float("nan")), wrong=sum(r["wrong"] for r in rows),
                     cal_samples=sum(r["cal_samples"] for r in rows), f=None, b=None,
                     w3_model=w3(pooled["model"]), w3_nocal=w3(pooled["nocal"]), w3_cal=w3(pooled["cal"]),
                     sig_cal_med=_q([s for _, s in pooled["cal"]], 0.5),
                     out3_cal=sum(r["out3_cal"] for r in rows), out3_cal_wrong=sum(r["out3_cal_wrong"] for r in rows),
                     out3_nocal_wrong=sum(r["out3_nocal_wrong"] for r in rows)))
    hdr = ("flight", "h m", "hfov", "img", "acc", "med", "p90", "max", f">{wrong_m:.0f}m", "cal n", "f", "b m",
           "3s model", f"3s floor{floor_no_cal:.0f}", "3s cal", "sig cal", "out cal", "out>wrong cal", "out>wrong floor")
    print(" | ".join(hdr))
    fmt = lambda v: "-" if v is None else (f"{v:.3f}" if isinstance(v, float) and v <= 1.0 else (f"{v:.1f}" if isinstance(v, float) else str(v)))  # noqa: E731
    for r in rows:
        print(" | ".join(fmt(r[k]) for k in ("flight", "height_m", "hfov", "images", "accepted", "err_med", "err_p90", "err_max", "wrong",
                                              "cal_samples", "f", "b", "w3_model", "w3_nocal", "w3_cal", "sig_cal_med", "out3_cal",
                                              "out3_cal_wrong", "out3_nocal_wrong")))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--uavvisloc", action="append", default=[])
    ap.add_argument("--campaign", default="")
    ap.add_argument("--gps-frac", type=float, default=0.3)
    ap.add_argument("--min-samples", type=int, default=15)
    ap.add_argument("--floor-no-cal", type=float, default=30.0)
    ap.add_argument("--wrong-m", type=float, default=100.0)
    ap.add_argument("--table", action="store_true", help="per-flight table + pooled row (UAV-VisLoc files)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="image range left out, e.g. 06_0099-06_0180 (flight 06: GPS labels ~360 m along-track off)")
    ap.add_argument("--position", default="as-run", help="as-run | centre | guard:T | refuse:T (see _with_position)")
    a = ap.parse_args()
    if a.table:
        table(a.uavvisloc, a.gps_frac, a.min_samples, a.floor_no_cal, a.wrong_m, a.exclude, a.position)
        return
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

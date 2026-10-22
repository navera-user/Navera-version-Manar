#!/usr/bin/env python3
"""Night vision (STHN, NightLocalizer product path) on REAL recorded night thermal FRAMES with GNSS truth.

Unlike night_real_thermal.py (frames cut from an orthomosaic), these are the drone camera's own
frames: real geometry (relief, building lean, lights, cars, motion), real radiometry, real AGC.
First data: Thermal-UAV (Hugging Face FloralHercules/Thermal-UAV, Apache-2.0, "intended for academic
research"): DJI Matrice 4T, gimballed nadir thermal (640 x 512 sensor delivered as 1280 x 1024,
12 mm on a 7.68 mm-wide sensor: 35.5 deg), ~300 m above take-off, night, Changsha (China),
Dec 2025 and Mar 2026; per frame: lat, lon, height above take-off, gimbal pitch / yaw.

Each frame goes NightLocalizer.localize as night_subscriber calls it (map check, re-check, heading
and height retries), height = the recorded height above take-off (the barometer's), heading = the
recorded yaw (+ N(0, 2 deg) unless --heading-sd 0), prior 100-250 m off in a random direction,
against an Esri World Imagery z17 MBTiles fetched for the frames (NAVERA's evaluation map).

    python3 navera_tools/bench/night_real_frames.py <sequence dir with Thermal_info.csv> --map m.mbtiles \
        [--hfov 35.5] [--stride 1] [--min-coverage X] --csv out.csv

--min-coverage overrides night_localizer.MIN_QUERY_COVERAGE (0.85) and MIN_GROUND_COVERAGE (0.55): a DIAGNOSTIC, not the product
(a narrow camera at 300 m covers ~20 % of the reference the product requires).
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
for p in (ROOT / "night_pkg", ROOT / "navera_common", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import thermal_ortho as to  # noqa: E402
from night_real_thermal import HEADING_RETRY, HEIGHT_RETRY, WRONG_M, summarize, _f  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seq")
    ap.add_argument("--map", required=True)
    ap.add_argument("--hfov", type=float, default=35.5)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--heading-sd", type=float, default=2.0)
    ap.add_argument("--yaw-offset", type=float, default=0.0, help="added to the recorded yaw (image-top direction)")
    ap.add_argument("--min-coverage", type=float, default=None)
    ap.add_argument("--no-retry", action="store_true")
    ap.add_argument("--min-ncc", type=float, default=None, help="map-check gate override (<= -1: off; diagnostic)")
    ap.add_argument("--recheck-max", type=float, default=None, help="re-check gate override, m (<= -1: off; diagnostic)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--device", default=None)
    ap.add_argument("--csv", default="")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(os.path.join(a.seq, "Thermal_info.csv"))))
    have = set(os.listdir(os.path.join(a.seq, "Thermal")))
    rows = [r for r in rows if os.path.basename(r["filename"]) in have][::a.stride]
    rng = np.random.default_rng(a.seed)
    poses = []
    for r in rows:
        pm, pa = float(rng.uniform(100, 250)), float(rng.uniform(0, 2 * math.pi))
        lat, lon = float(r["lat"]), float(r["lon"])
        plat, plon = to.enu_to_latlon(lat, lon, pm * math.sin(pa), pm * math.cos(pa))
        poses.append(dict(r=r, lat=lat, lon=lon, prior=(float(plat), float(plon)), prior_m=pm,
                          head_err=float(rng.normal(0, a.heading_sd)) if a.heading_sd > 0 else 0.0))
    maps = to.MapTiles(a.map)
    keys = set()
    for p in poses:
        keys |= to.tiles_around(p["prior"][0], p["prior"][1], 1150.0)
    got, failed = maps.fetch(sorted(keys))
    print(f"{len(poses)} frames; map: {len(keys)} z17 tiles, {got} fetched, {failed} failed", flush=True)
    if a.fetch_only:
        return

    import cv2
    import torch
    import night_pkg.nodes.night_localizer as nl
    if a.min_coverage is not None:
        nl.MIN_QUERY_COVERAGE = a.min_coverage
        nl.MIN_GROUND_COVERAGE = min(nl.MIN_GROUND_COVERAGE, a.min_coverage)
    sthn = os.environ.get("NAVERA_STHN_DIR", os.path.expanduser("~/navera_data/night_pkg/STHN"))
    weights = os.environ.get("NAVERA_STHN_WEIGHTS", os.path.join(sthn, "weights/one_stage/model.safetensors"))
    gates = {k: (v if v > -1 else None) for k, v in (("min_match_ncc", a.min_ncc), ("recheck_max_m", a.recheck_max))
             if v is not None}
    loc = nl.NightLocalizer(sthn, weights, a.map, device=a.device, **gates)
    out = []
    try:
        for i, p in enumerate(poses):
            r = p["r"]
            img = cv2.imread(os.path.join(a.seq, "Thermal", os.path.basename(r["filename"])))
            heading = (float(r["yaw"]) + a.yaw_offset + p["head_err"]) % 360.0
            t1 = time.perf_counter()
            res = loc.localize(img, p["prior"][0], p["prior"][1], altitude_m=float(r["rel_height"]),
                               hfov_deg=a.hfov, heading_deg=heading,
                               heading_retry_deg=() if a.no_retry else HEADING_RETRY,
                               height_retry=() if a.no_retry else HEIGHT_RETRY)
            dt = (time.perf_counter() - t1) * 1000
            acc = bool(res.get("success"))
            err = to.dist_m((p["lat"], p["lon"]), (res["lat"], res["lon"])) if acc else None
            row = dict(file=os.path.basename(r["filename"]), t=r["date"], lat=p["lat"], lon=p["lon"],
                       agl=float(r["rel_height"]), yaw=float(r["yaw"]), prior_m=p["prior_m"], accepted=acc,
                       err_m=err, sigma_m=res.get("sigma_m"), wrong=acc and err > WRONG_M,
                       reason=res.get("reason", ""), dt_ms=dt, recheck_m=res.get("recheck_m"),
                       ncc=(res.get("verify") or {}).get("ncc"), heading_fix=res.get("heading_correction_deg"),
                       height_fix=res.get("height_correction"), coverage=(res.get("query") or {}).get("coverage"))
            out.append(row)
            print(f"{i:4d} {row['file'][-30:]} {'ACC' if acc else 'rej'} err {_f(err)} m  "
                  f"{'' if acc else str(row['reason'])[:90]}", flush=True)
    finally:
        del loc
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    s = summarize(out)
    print(f"\n{os.path.basename(a.seq.rstrip('/'))}: {s['accepted']}/{s['n']} accepted, median {_f(s['median_m'])} "
          f"p90 {_f(s['p90_m'])} max {_f(s['max_m'])} m, wrong (> {WRONG_M:.0f} m) {s['wrong']}, "
          f"within 3 sigma {_f(s['in3s'], '{:.0%}')}, {_f(s['ms_median'])} ms; refused {s['refused']}")
    if a.csv and out:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)


if __name__ == "__main__":
    main()

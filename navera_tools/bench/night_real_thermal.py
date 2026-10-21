#!/usr/bin/env python3
"""Night vision (STHN, NightLocalizer product path) on REAL aerial thermal imagery.

Frames are cut from real airborne thermography orthomosaics (thermal_ortho.py: Bordeaux
2017-18 winter NIGHT scanner, 0.5 m; Clermont-Ferrand 2024 summer DAY MWIR, 1 m; both
Licence Ouverte) as a nadir camera at a true position / height / heading would see them,
at a chosen sensor (FLIR Boson 640 50 deg, Hikvision DS-2TD2617B 160 x 120 50 deg...).
The radiometry is real thermal; the geometry is an orthophoto (no relief, no lean, no
motion blur, nadir). Neither area is in STHN's training data (Boson-nighttime, US).

Each frame goes NightLocalizer.localize exactly as night_subscriber calls it: map check,
second-centre re-check, heading retries (-10, 10, -20, 20) and height retries (0.1, -0.1,
0.2), against an Esri World Imagery z17 MBTiles (NAVERA's map provider) fetched for the
poses. Measured height has a 3 % 1-sigma error, measured heading 2 deg, prior 100-250 m
off in a random direction (night_conditions.py defaults). The same poses (seeded) are used
for every sensor and height.

    python3 navera_tools/bench/night_real_thermal.py --site bordeaux \
        --sensors boson640_50,hik160_50 --agl 500,700,1000 --n 40 --csv out.csv

Data (env or flags): NAVERA_THERMAL_DIR (default /media/shadow-team/ADATA SD620/
NAVERA_TESTDATA/thermal), NAVERA_STHN_DIR, NAVERA_STHN_WEIGHTS.
"""
import argparse
import csv
import json
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

WRONG_M = 50.0
HEADING_RETRY = (-10.0, 10.0, -20.0, 20.0)      # night_subscriber defaults
HEIGHT_RETRY = (0.1, -0.1, 0.2)
SENSORS = {
    "boson640_50": to.Sensor("FLIR Boson 640, 50 deg", 640, 512, 50.0, noise=0.01),
    "boson640_95": to.Sensor("FLIR Boson 640, 95 deg", 640, 512, 95.0, noise=0.01),
    "hik160_50": to.Sensor("Hikvision DS-2TD2617B-3/PA 160x120, 50 deg", 160, 120, 50.0, noise=0.02),
    "lepton160_57": to.Sensor("FLIR Lepton 3.5 160x120, 57 deg", 160, 120, 57.0, noise=0.02),
    "infiray640_63": to.Sensor("InfiRay Micro III 640, 62.9 deg", 640, 512, 62.9, noise=0.015),
}


def load_site(site: str, root: str) -> "to.ThermalOrtho":
    if site == "bordeaux":
        return to.ThermalOrtho.bordeaux(os.path.join(root, "bordeaux_2018_night", "raw"))
    if site == "clermont":
        return to.ThermalOrtho.geotiff_float(os.path.join(root, "clermont_2024_day", "dalles"),
                                             "clermont_day", to.LAMBERT93, 1.0,
                                             # masked by the producer (streaky fill) at the airport
                                             exclude=[(711900, 6519700, 713500, 6520700)])
    raise SystemExit(f"unknown site {site}")


def make_poses(ortho, n: int, max_half_diag_m: float, seed: int = 0):
    """n poses fully inside the data: truth, heading, measured errors, prior."""
    rng = np.random.default_rng(seed)
    poses = []
    tries = 0
    while len(poses) < n and tries < 50 * n:
        tries += 1
        lat, lon = ortho.random_point(rng)
        if not ortho.covers(lat, lon, max_half_diag_m):
            continue
        heading = float(rng.uniform(0, 360))
        pm, pa = float(rng.uniform(100, 250)), float(rng.uniform(0, 2 * math.pi))
        plat, plon = to.enu_to_latlon(lat, lon, pm * math.sin(pa), pm * math.cos(pa))
        poses.append(dict(i=len(poses), lat=lat, lon=lon, heading=heading,
                          head_err=float(rng.normal(0, 2.0)), alt_rel_err=float(rng.normal(0, 0.03)),
                          prior=(float(plat), float(plon)), prior_m=pm, seed=int(rng.integers(1 << 30))))
    return poses


def summarize(rows):
    n = len(rows)
    acc = [r for r in rows if r["accepted"]]
    errs = sorted(r["err_m"] for r in acc)
    refused = {}
    for r in rows:
        if not r["accepted"]:
            k = (r["reason"] or "rejected").split("(")[0].split(" — ")[0].split(":")[0].strip()[:38]
            refused[k] = refused.get(k, 0) + 1
    in3 = [r for r in acc if r["sigma_m"] and r["err_m"] <= 3 * r["sigma_m"]]
    return dict(n=n, accepted=len(acc),
                median_m=statistics.median(errs) if errs else None,
                p90_m=float(np.percentile(errs, 90)) if errs else None,
                max_m=max(errs) if errs else None,
                wrong=sum(r["wrong"] for r in rows),
                in3s=len(in3) / len(acc) if acc else None,
                ms_median=statistics.median(r["dt_ms"] for r in rows) if rows else None,
                ms_acc=statistics.median(r["dt_ms"] for r in acc) if acc else None,
                refused=refused)


def _f(v, fmt="{:.0f}"):
    return "-" if v is None else fmt.format(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="bordeaux", help="bordeaux | clermont")
    ap.add_argument("--sensors", default="boson640_50,hik160_50")
    ap.add_argument("--agl", default="500,700,1000", help="heights above ground (m)")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--source", default="thermal",
                    help="thermal (the orthomosaic) | map (grey render of the satellite map itself: control)")
    ap.add_argument("--polarity", type=int, default=1, help="1 white-hot, -1 black-hot")
    ap.add_argument("--heading-err", type=float, default=None,
                    help="measured heading off by this many degrees (random sign) instead of N(0, 2)")
    ap.add_argument("--no-retry", action="store_true", help="no heading / height retries")
    ap.add_argument("--map", default="", help="MBTiles to use / fill (default: <thermal dir>/<site>_esri_z17.mbtiles)")
    ap.add_argument("--fetch-only", action="store_true", help="fetch the map tiles for the poses, then stop")
    ap.add_argument("--device", default=None)
    ap.add_argument("--csv", default="")
    ap.add_argument("--only-runs", default="",
                    help="run only these sensor:height pairs (e.g. boson640_50:700); the poses stay "
                         "those of the full --sensors / --agl set")
    ap.add_argument("--min-ncc", type=float, default=None, help="map-check gate override (<= -1: off)")
    ap.add_argument("--recheck-max", type=float, default=None, help="re-check gate override, m (<= -1: off)")
    ap.add_argument("--save-frames", default="", help="save the first frames of each run here")
    ap.add_argument("--probe-jsonl", default="",
                    help="run every retry of each frame and write its evidence here (night_retry_probe); "
                         "the table is then localize's choice without a retry gate")
    a = ap.parse_args()

    root = os.environ.get("NAVERA_THERMAL_DIR", "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/thermal")
    ortho = load_site(a.site, root)
    sensors = [SENSORS[s] for s in a.sensors.split(",")]
    agls = [float(x) for x in a.agl.split(",")]
    half_diag = max(math.hypot(1, s.height / s.width) * s.width * s.gsd(h) / 2 for s in sensors for h in agls)
    radius = min(half_diag * 1.25, 1500.0)
    cache = os.path.join(root, f"{a.site}_poses_n{a.n}_s{a.seed}_r{radius:.0f}.json")
    if os.path.exists(cache):
        poses = json.load(open(cache))
    else:
        poses = make_poses(ortho, a.n, radius, a.seed)
        json.dump(poses, open(cache, "w"))
    print(f"{a.site}: {len(ortho.tiles)} thermal tiles, {len(poses)} poses", flush=True)

    mb = a.map or os.path.join(root, f"{a.site}_esri_z17.mbtiles")
    maps = to.MapTiles(mb)
    keys = set()
    for p in poses:
        keys |= to.tiles_around(p["prior"][0], p["prior"][1], 1150.0)
    t0 = time.time()
    got, failed = maps.fetch(sorted(keys))
    print(f"map: {len(keys)} z17 tiles needed, {got} fetched, {failed} failed in {time.time() - t0:.0f} s "
          f"-> {mb}", flush=True)
    if a.fetch_only:
        return
    if a.source == "map":
        ortho = to.MapOrtho(maps)

    import torch
    from night_pkg.nodes.night_localizer import NightLocalizer
    sthn = os.environ.get("NAVERA_STHN_DIR", os.path.expanduser("~/navera_data/night_pkg/STHN"))
    weights = os.environ.get("NAVERA_STHN_WEIGHTS", os.path.join(sthn, "weights/one_stage/model.safetensors"))
    overrides = (("min_match_ncc", a.min_ncc), ("recheck_max_m", a.recheck_max))
    gates = {k: (v if v > -1 else None) for k, v in overrides if v is not None}
    loc = NightLocalizer(sthn, weights, mb, device=a.device, **gates)
    only = {(x.split(":")[0], float(x.split(":")[1])) for x in a.only_runs.split(",") if x.strip()}
    save = Path(a.save_frames) if a.save_frames else None
    if save:
        save.mkdir(parents=True, exist_ok=True)
    import cv2

    def head_err(p):
        if a.heading_err is None:
            return p["head_err"]
        return a.heading_err * (1.0 if p["seed"] % 2 else -1.0)
    probe_f = None
    if a.probe_jsonl:
        import night_retry_probe as nrp
        loc.map_check_shifts_px = nrp.PROBE_SHIFTS_PX
        probe_f = open(a.probe_jsonl, "a")
    rows, table = [], []
    try:
        for s_key, s in zip(a.sensors.split(","), sensors):
            for agl in agls:
                if only and (s_key, agl) not in only:
                    continue
                run = []
                for p in poses:
                    rng = np.random.default_rng(p["seed"])
                    img = to.render(ortho, s, p["lat"], p["lon"], agl, p["heading"], rng, a.polarity)
                    if img is None:
                        continue
                    if save is not None and p["i"] < 4:
                        cv2.imwrite(str(save / f"{a.site}_{a.source}_{s_key}_{agl:.0f}_{p['i']}.png"), img)
                    t1 = time.perf_counter()
                    kw = dict(altitude_m=agl * (1 + p["alt_rel_err"]), hfov_deg=s.hfov_deg,
                              heading_deg=(p["heading"] + head_err(p)) % 360.0,
                              heading_retry_deg=() if a.no_retry else HEADING_RETRY,
                              height_retry=() if a.no_retry else HEIGHT_RETRY)
                    if probe_f is None:
                        r = loc.localize(img, p["prior"][0], p["prior"][1], **kw)
                    else:
                        att = nrp.probe(loc, img, p["prior"][0], p["prior"][1], **kw)
                        probe_f.write(json.dumps(dict(
                            site=a.site, source=a.source, polarity=a.polarity, heading_err=a.heading_err,
                            sensor=s_key, px=s.width, agl=agl, i=p["i"], lat=p["lat"], lon=p["lon"],
                            prior=p["prior"], attempts=att)) + "\n")
                        probe_f.flush()
                        k = nrp.decide(att)
                        c = att[k if k is not None else 0]
                        r = dict(success=k is not None, lat=c["lat"], lon=c["lon"], sigma_m=c["sigma_m"],
                                 reason="" if k is not None else c["reason"], recheck_m=c["recheck_m"],
                                 verify=dict(ncc=c["ncc"]), heading_correction_deg=c["d"] or None,
                                 height_correction=c["f"] or None)
                    dt = (time.perf_counter() - t1) * 1000
                    acc = bool(r.get("success"))
                    err = to.dist_m((p["lat"], p["lon"]), (r["lat"], r["lon"])) if acc else None
                    dn = de = None
                    if acc:
                        dn = (r["lat"] - p["lat"]) * 111_132.0
                        de = (r["lon"] - p["lon"]) * 111_320.0 * math.cos(math.radians(p["lat"]))
                    row = dict(site=a.site, sensor=s_key, agl=agl, i=p["i"], lat=p["lat"], lon=p["lon"],
                               heading=p["heading"], prior_m=p["prior_m"], accepted=acc, err_m=err,
                               err_n=dn, err_e=de, sigma_m=r.get("sigma_m"), wrong=acc and err > WRONG_M,
                               reason=r.get("reason", ""), dt_ms=dt, recheck_m=r.get("recheck_m"),
                               ncc=(r.get("verify") or {}).get("ncc"),
                               heading_fix=r.get("heading_correction_deg"),
                               height_fix=r.get("height_correction"),
                               coverage=(r.get("query") or {}).get("coverage"))
                    run.append(row)
                s_ = summarize(run)
                table.append((s_key, agl, s.gsd(agl), s_))
                rows += run
                print(f"{s_key} {agl:.0f} m (gsd {s.gsd(agl):.2f} m): {s_['accepted']}/{s_['n']} accepted, "
                      f"median {_f(s_['median_m'])} p90 {_f(s_['p90_m'])} max {_f(s_['max_m'])} m, "
                      f"wrong {s_['wrong']}, {_f(s_['ms_median'])} ms; {s_['refused']}", flush=True)
    finally:
        del loc
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    print(f"\n{'sensor':14s} {'agl':>5s} {'gsd':>5s} {'acc':>7s} {'med':>5s} {'p90':>5s} {'max':>5s} "
          f"{'wrong':>5s} {'in3σ':>5s} {'ms':>5s}  refused")
    for k, agl, g, s_ in table:
        print(f"{k:14s} {agl:5.0f} {g:5.2f} {s_['accepted']:3d}/{s_['n']:<3d} {_f(s_['median_m']):>5s} "
              f"{_f(s_['p90_m']):>5s} {_f(s_['max_m']):>5s} {s_['wrong']:5d} {_f(s_['in3s'], '{:.0%}'):>5s} "
              f"{_f(s_['ms_median']):>5s}  {'; '.join(f'{x}:{y}' for x, y in s_['refused'].items())}")
    if a.csv and rows:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()

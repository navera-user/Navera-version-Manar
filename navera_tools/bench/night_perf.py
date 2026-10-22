#!/usr/bin/env python3
"""Night vision accuracy benchmark, offline (NAV-PERF-03 regression): data already on disk.

Both parts call ``NightLocalizer.localize`` as ``night_subscriber`` does: the localizer's
default gates (map check, second-centre re-check, retry gate) and the node's default retries
(heading -10, 10, -20, 20 deg; height +10, -10, +20 %).

``synthetic``  bench/night_conditions.py frames (grey renders of the Sousse map through the
               simulator's 75 x 63 deg, 640 x 512 thermal camera, straightened with a 0.5 / 2 deg
               IMU error, 3 % height error, prior 100-250 m off), the same seeded poses, for the
               conditions ``nominal`` (400 m), ``agl_600m``, ``terrain_farmland`` and the
               no-information frames ``terrain_sea`` / ``uniform_frame`` (every accept is wrong).
``thermal``    bench/night_real_thermal.py frames: REAL aerial night LWIR (Bordeaux winter
               2017-18 scanner, Licence Ouverte) rendered as a nadir camera at the cached 60 poses,
               FLIR Boson 640 50 deg and Hikvision 160 x 120 50 deg at 1000 m, against the Esri z17
               map fetched for those poses (no network needed when it is on disk).

    python3 navera_tools/bench/night_perf.py synthetic [--n 24]
    python3 navera_tools/bench/night_perf.py thermal [--n 60]

Data: NAVERA_MBTILES (synthetic), NAVERA_THERMAL_DIR (default the ADATA disk's
NAVERA_TESTDATA/thermal), NAVERA_STHN_DIR, NAVERA_STHN_WEIGHTS (see ~/navera_env.sh).
"""
import argparse
import json
import os
import statistics
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "night_pkg"), os.path.join(ROOT, "navera_common"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

STHN_DIR = os.environ.get("NAVERA_STHN_DIR", os.path.expanduser("~/navera_data/night_pkg/STHN"))
STHN_WEIGHTS = os.environ.get("NAVERA_STHN_WEIGHTS", os.path.join(STHN_DIR, "weights/one_stage/model.safetensors"))
MBTILES = os.environ.get("NAVERA_MBTILES", os.path.expanduser("~/navera_data_map.mbtiles"))
THERMAL_DIR = os.environ.get("NAVERA_THERMAL_DIR", "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/thermal")
# rendered thermal frames (deterministic: pose seed, sensor, height) are kept here: a Boson 640
# frame takes ~2.5 s to render from the orthomosaic, the localizer is what is measured
CACHE_DIR = os.environ.get("NAVERA_PERF_CACHE", os.path.expanduser("~/.cache/navera_perf"))
HEADING_RETRY = (-10.0, 10.0, -20.0, 20.0)       # night_subscriber defaults
HEIGHT_RETRY = (0.1, -0.1, 0.2)
SYNTH_CONDITIONS = ("nominal", "agl_600m", "terrain_farmland", "terrain_sea", "uniform_frame")
THERMAL_RUNS = (("boson640_50", 1000.0), ("hik160_50", 1000.0))
THERMAL_POSES = "bordeaux_poses_n60_s0_r746.json"   # the 2026-10-21 runs' poses (500/700/1000 m set)
WRONG_M = 50.0


def summary(rows) -> dict:
    acc = [r for r in rows if r["accepted"]]
    e = sorted(r["err_m"] for r in acc)
    return dict(n=len(rows), accepted=len(acc), availability=len(acc) / len(rows) if rows else 0.0,
                median=statistics.median(e) if e else None, p90=float(np.percentile(e, 90)) if e else None,
                max=e[-1] if e else None, wrong=sum(bool(r["wrong"]) for r in rows),
                within_3sigma=(sum(r["err_m"] <= 3 * r["sigma_m"] for r in acc if r["sigma_m"]) / len(acc)
                               if acc else None),
                ms=statistics.median(r["dt_ms"] for r in rows) if rows else None)


def _release(loc) -> None:
    import torch
    del loc
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_synthetic(n: int = 24, conditions=SYNTH_CONDITIONS) -> dict:
    """{condition: summary} on night_conditions.py's frames, with the product retries."""
    import night_conditions as nc
    from navera_common.camera_model import CameraModel
    from navera_common.frame_builder import FrameBuilder
    from night_pkg.nodes.night_localizer import NightLocalizer
    nc.HEADING_RETRY, nc.HEIGHT_RETRY = HEADING_RETRY, HEIGHT_RETRY
    by_name = {c.name: c for c in nc.CONDITIONS}
    lens = dict(model="pinhole", image_width=nc.SIZE[0], image_height=nc.SIZE[1], distortion=[],
                camera_matrix=CameraModel.ideal(nc.HFOV_DEG, nc.SIZE).K.ravel().tolist())
    cam = nc._GeomCamera(lens, nc.Tiles(MBTILES).get)
    fb = FrameBuilder(CameraModel.ideal(nc.HFOV_DEG, nc.SIZE), camera_type="thermal")
    loc = NightLocalizer(STHN_DIR, STHN_WEIGHTS, MBTILES)
    out = {}
    try:
        for name in conditions:
            _, rows = nc.run_condition(by_name[name], loc, cam, fb, n)
            out[name] = summary(rows)
    finally:
        _release(loc)
    return out


def _thermal_frame(ortho, to, s_key, sensor, agl, p):
    """night_real_thermal's frame for pose p (white-hot), from the cache when rendered before."""
    import cv2
    d = os.path.join(CACHE_DIR, "thermal_frames", os.path.splitext(THERMAL_POSES)[0])
    f = os.path.join(d, f"{s_key}_{agl:.0f}_{p['i']}_{p['seed']}.png")
    if os.path.exists(f):
        return cv2.imread(f, cv2.IMREAD_UNCHANGED)
    img = to.render(ortho, sensor, p["lat"], p["lon"], agl, p["heading"], np.random.default_rng(p["seed"]), 1)
    if img is not None:
        os.makedirs(d, exist_ok=True)
        cv2.imwrite(f, img)
    return img


def run_thermal(n: int = 60, runs=THERMAL_RUNS, site: str = "bordeaux") -> dict:
    """{"sensor:agl": summary} on real night thermal, the 2026-10-21 poses (first n)."""
    import night_real_thermal as nrt
    import thermal_ortho as to
    from night_pkg.nodes.night_localizer import NightLocalizer
    poses = json.load(open(os.path.join(THERMAL_DIR, THERMAL_POSES)))[:n]
    ortho = nrt.load_site(site, THERMAL_DIR)
    mb = os.path.join(THERMAL_DIR, f"{site}_esri_z17.mbtiles")
    loc = NightLocalizer(STHN_DIR, STHN_WEIGHTS, mb)
    out = {}
    try:
        for s_key, agl in runs:
            s = nrt.SENSORS[s_key]
            rows = []
            for p in poses:
                img = _thermal_frame(ortho, to, s_key, s, agl, p)
                if img is None:
                    continue
                t0 = time.perf_counter()
                r = loc.localize(img, p["prior"][0], p["prior"][1], altitude_m=agl * (1 + p["alt_rel_err"]),
                                 hfov_deg=s.hfov_deg, heading_deg=(p["heading"] + p["head_err"]) % 360.0,
                                 heading_retry_deg=HEADING_RETRY, height_retry=HEIGHT_RETRY)
                dt = (time.perf_counter() - t0) * 1000
                acc = bool(r.get("success"))
                err = to.dist_m((p["lat"], p["lon"]), (r["lat"], r["lon"])) if acc else None
                rows.append(dict(accepted=acc, err_m=err, sigma_m=r.get("sigma_m"), dt_ms=dt,
                                 wrong=acc and err > WRONG_M))
            out[f"{s_key}:{agl:.0f}"] = summary(rows)
    finally:
        _release(loc)
    return out


def _fmt(s):
    return " ".join(f"{k} {round(v, 2) if isinstance(v, float) else v}" for k, v in s.items())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part", choices=["synthetic", "thermal"])
    ap.add_argument("--n", type=int, default=0, help="frames per condition / poses (default 24 / 60)")
    a = ap.parse_args()
    t0 = time.time()
    res = run_synthetic(a.n or 24) if a.part == "synthetic" else run_thermal(a.n or 60)
    for k, s in res.items():
        print(f"{k:18s} {_fmt(s)}", flush=True)
    print(f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Make courses/26-stars/hidden/expected.json for mission 26's check (teacher only).

    python3 solutions/26-stars/make_expected.py        (on the host, from anywhere; after make_dataset.py)

1. Unseen inputs and the course reference's outputs for TODOs 1–4 and 6–9 (the check never imports the reference).
2. The lab's numbers: the runner run_stars.py is run on the reference solution (a temporary copy of the starter
   files + solutions/26-stars/navera_lite, data from datasets/26-stars) and its printed numbers are read back,
   so the constants are exactly what a correct student sees. TEACHER.md quotes them.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "solutions", "_navera_lite"))
from navera_lite import stars as S                      # noqa: E402
from navera_lite.rotations import q_from_euler_zyx      # noqa: E402

OUT = os.path.join(ROOT, "courses", "26-stars", "hidden", "expected.json")


def unseen():
    rng = np.random.default_rng(2627)
    e = {}
    dates = [(1987, 4, 10, 19, 21, 0.0), (2024, 2, 29, 18, 0, 0.0), (2031, 1, 5, 3, 7, 30.0),
             (2100, 6, 15, 12, 0, 0.0), (2026, 12, 31, 23, 59, 59.5), (2027, 3, 1, 0, 0, 0.0)]
    e["jd"] = [[list(d), S.julian_date(*d)] for d in dates]
    jds = [2447000.25, 2455197.5, 2461400.87654, 2469807.5]
    e["gmst"] = [[j, S.gmst_deg(j)] for j in jds]
    alt_cases = []
    for lat, lon, gst in ((-41.29, 174.78, 12.5), (51.50, -0.12, 200.0), (64.15, -21.94, 333.3), (-0.18, -78.47, 95.0)):
        ra = rng.uniform(0, 360, 7)
        dec = rng.uniform(-80, 80, 7)
        a, z = S.altaz(ra, dec, lat, lon, gst)
        alt_cases.append({"ra": ra.tolist(), "dec": dec.tolist(), "lat": lat, "lon": lon, "gst": gst,
                          "alt": np.asarray(a).tolist(), "az": np.asarray(z).tolist()})
    e["altaz"] = alt_cases
    e["altaz_one"] = [[[101.5865, -16.7457, -33.87, 151.21, 52.3], list(S.altaz(101.5865, -16.7457, -33.87, 151.21, 52.3))]]
    e["polaris"] = [[[a, h, p], S.lat_from_polaris(a, h, p)] for a, h, p in ((41.3, 130.0, 0.6253), (63.9, 355.0, 0.6253),
                                                                             (12.0, 250.0, 0.70))]
    e["polaris_none"] = [[33.3, S.lat_from_polaris(33.3)]]
    bores = []
    for hdg, pu, roll, axis in ((137.0, -6.0, 4.0, S.CAM_AXIS_BODY), (290.0, 3.0, -10.0, S.CAM_AXIS_BODY),
                                (15.0, 0.0, 0.0, (0.0, 0.0, 1.0)), (200.0, -30.0, 0.0, (0.5, 0.0, 0.8660254))):
        q = q_from_euler_zyx(math.radians(roll), -math.radians(pu), math.radians(90.0 - hdg))
        bores.append({"q": [float(x) for x in q], "axis": [float(x) for x in axis],
                      "want": list(S.boresight_altaz(q, axis))})
    e["boresight"] = bores
    roots = []
    for lat, lon, a, A, gst in ((69.65, 18.96, 55.0, 0.0, 300.0), (-20.0, 57.5, 62.0, 200.0, 33.0),
                                (64.15, -21.94, 55.0, 45.0, 140.0), (10.0, 179.5, 70.0, 95.0, 250.0),
                                (-70.0, -60.0, 55.0, 180.0, 10.0)):
        al, Az, phi = map(math.radians, (a, A, lat))
        dec = math.degrees(math.asin(math.sin(al) * math.sin(phi) + math.cos(al) * math.cos(phi) * math.cos(Az)))
        H = math.degrees(math.atan2(-math.cos(al) * math.sin(Az),
                                    math.sin(al) * math.cos(phi) - math.cos(al) * math.sin(phi) * math.cos(Az)))
        ra = (gst + lon - H) % 360.0
        roots.append({"args": [a, A, ra, dec, gst], "truth": [lat, lon], "want": S.both_roots(a, A, ra, dec, gst)})
    roots.append({"args": [20.0, 90.0, 10.0, 80.0, 0.0], "truth": None, "want": S.both_roots(20.0, 90.0, 10.0, 80.0, 0.0)})
    e["roots"] = roots
    e["choose"] = [
        [[[[40.35, 128.6], [69.65, -51.4]], 68.0, -48.0, 5.0], S.choose([(40.35, 128.6), (69.65, -51.4)], 68.0, -48.0)],
        [[[[63.15, -19.68], [64.17, -21.98]], 64.0, -21.2, 5.0], S.choose([(63.15, -19.68), (64.17, -21.98)], 64.0, -21.2)],
        [[[[63.15, -19.68], [64.17, -21.98]], 64.0, -21.2, 0.5], S.choose([(63.15, -19.68), (64.17, -21.98)], 64.0, -21.2, 0.5)],
        [[[[-34.1, 179.6]], -33.0, -178.9, 5.0], S.choose([(-34.1, 179.6)], -33.0, -178.9)],
        [[[[88.0, 10.0]], 87.5, -170.0, 5.0], S.choose([(88.0, 10.0)], 87.5, -170.0)],
        [[[[35.0, 10.0]], 45.0, 10.0, 5.0], S.choose([(35.0, 10.0)], 45.0, 10.0)],
        [[[], 45.0, 10.0, 5.0], S.choose([], 45.0, 10.0)],
    ]
    e["error_km"] = [[[t, h, a], S.error_km(t, h, a)] for t, h, a in ((0.5, 0.0, 70.0), (0.3, 2.0, 45.0),
                                                                     (0.0, 1.5, 75.0), (1.0, 3.0, 90.0))]
    return e


def runner_numbers():
    tmp = tempfile.mkdtemp(prefix="exp26_")
    try:
        shutil.copytree(os.path.join(ROOT, "courses", "26-stars", "files"), tmp, dirs_exist_ok=True)
        shutil.rmtree(os.path.join(tmp, "navera_lite"))
        shutil.copytree(os.path.join(HERE, "navera_lite"), os.path.join(tmp, "navera_lite"))
        env = dict(os.environ, STARS_DATA=os.path.join(ROOT, "datasets", "26-stars"), MPLBACKEND="Agg")

        def run(*a):
            r = subprocess.run([sys.executable, "run_stars.py", *a], cwd=tmp, env=env, capture_output=True, text=True,
                               timeout=600)
            if r.returncode:
                raise SystemExit(f"run_stars.py {' '.join(a)} failed:\n{r.stdout}\n{r.stderr}")
            return r.stdout

        def f(rx, text, g=1):
            m = re.search(rx, text, re.S)
            if not m:
                raise SystemExit(f"not found: {rx}\n{text}")
            return float(m.group(g))
        n = {}
        cat = S.load_catalogue(os.path.join(ROOT, "datasets", "26-stars", "bright_stars.csv"))
        n["N_VOTE_STARS"] = int(np.sum(cat["vmag"] <= 4.5))
        out = run("clock")
        n["TRANSIT_SHIFT_S"] = f(r"comes ([0-9.]+) s earlier", out)
        n["VEGA_SHIFT_ARCMIN"] = f(r"Vega .*?moved\s+([0-9.]+)′", out)
        n["VEGA_SHIFT_KM"] = round(n["VEGA_SHIFT_ARCMIN"] * 1.852, 2)
        out = run("sky", "capetown")
        n["ACHERNAR_ALT_DEG"] = f(r"Achernar\s+([-0-9.]+)\s+([0-9.]+)", out, 1)
        n["ACHERNAR_AZ_DEG"] = f(r"Achernar\s+([-0-9.]+)\s+([0-9.]+)", out, 2)
        n["POLARIS_CAPE_ALT_DEG"] = f(r"Polaris: alt ([-+0-9.]+)°", out)
        out = run("polaris")
        rows = re.findall(r"^\s+(\w+)\s+[-0-9.]+\s+([0-9.]+)\s+([0-9.]+)\s*$", out, re.M)
        n["NAIVE_MAX_ERR_KM"] = max(float(r[1]) for r in rows)
        n["CORRECTED_MAX_ERR_KM"] = max(float(r[2]) for r in rows)
        out = run("detect", "1")
        n["N_STARS_01"] = int(f(r"found (\d+) stars", out))
        n["CENTROID_RMS_PX"] = f(r"centre error: RMS ([0-9.]+) px", out)
        out = run("solve", "1")
        n["PIXEL_ARCMIN"] = f(r"one pixel at the image centre = ([0-9.]+)′", out)
        n["PIXEL_KM"] = round(n["PIXEL_ARCMIN"] * 1.852, 2)
        n["SOLVE_RMS_ARCSEC"] = f(r"fit residual: ([0-9.]+)″", out)
        a, A = 37.13, 295.02
        n["TRACE_PSI_DEG"] = round(math.degrees(math.atan2(math.cos(math.radians(a)) * math.cos(math.radians(A)),
                                                           math.sin(math.radians(a)))), 2)
        out = run("fix")
        n["MEDIAN_FIX_KM"] = f(r"error median ([0-9.]+) km", out)
        n["FIX_KM"] = {int(k): float(v) for k, v in re.findall(r"^\s+(\d)\s.*?→\s+\(.*?\)\s+([0-9.]+) km", out, re.M)}
        n["NO_FIX_PHOTO"] = [int(k) for k in re.findall(r"^\s+(\d)\s.*?no position", out, re.M)]
        out = run("fix", "truth")
        n["PERFECT_MAX_KM"] = f(r"largest ([0-9.]+) km", out)
        out = run("fix", "magnetic")
        n["MAGNETIC_ERR_01_KM"] = f(r"(?m)^\s+1\s[^\n]*?\)\s+([0-9.]+) km", out)
        out = run("fix", "oneroot")
        n["ONE_ROOT_ERR_03_KM"] = f(r"(?m)^\s+3\s[^\n]*?\)\s+([0-9.]+) km", out)
        out = run("budget")
        n["FORMULA_KM"] = f(r"=\s+([0-9.]+) km\s+\(the formula\)", out)
        n["MC_RMS_KM"] = f(r"RMS\s+([0-9.]+) km", out)
        n["MC_MEDIAN_KM"] = f(r"median\s+([0-9.]+) km", out)
        n["MOUNT_BIAS_MAX_DEG"] = round(55.0 / S.KM_PER_DEG, 3)
        return n
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    e = unseen()
    e["lab"] = runner_numbers()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(e, f, indent=1)
    print(json.dumps(e["lab"], indent=1))
    print("written:", OUT)


if __name__ == "__main__":
    main()

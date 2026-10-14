#!/usr/bin/env python3
"""Teacher only — writes courses/27-uncertainty/hidden/expected.json, the check's sealed expected values.

    python3 solutions/27-uncertainty/make_dataset.py --hidden      # first (datasets + hidden/drive.csv)
    python3 solutions/27-uncertainty/make_expected.py

1. Unseen inputs (seed 2777 and hand-picked edge cases) and the course reference's outputs for TODOs 1–3, 5–9.
2. The reference policy "gate, then fuse" on the hidden drive (hidden/drive.csv, street at −25°).
3. Every lab number, read back from run_uncertainty.py run on the complete solution in a temporary lesson folder
   (so the check's constants are exactly what a correct student sees).
"""
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite import uncertainty as U                     # noqa: E402

COURSE = os.path.join(ACADEMY, "courses", "27-uncertainty")
DATA = os.path.join(ACADEMY, "datasets", "27-uncertainty")


def L(a):
    return np.asarray(a, dtype=float).round(10).tolist()


def rand_cov(rng, lo=0.5, hi=40.0):
    a, b = sorted(rng.uniform(lo, hi, 2), reverse=True)
    t = math.radians(rng.uniform(-180, 180))
    R = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    return (R @ np.diag([a * a, b * b]) @ R.T).round(4)


def functions():
    rng = np.random.default_rng(2777)
    E = {}
    clouds = [rng.normal([3.0, -2.0], [2.0, 5.0], (5, 2)).round(3), rng.normal(0, 4, (7, 2)).round(3),
              (rng.standard_normal((40, 2)) @ np.array([[3.0, 0.0], [1.5, 1.0]])).round(3) + [100.0, 50.0]]
    E["sample_cov"] = [[L(c), L(U.sample_cov(c))] for c in clouds]
    mats = [rand_cov(rng) for _ in range(4)] + [np.array([[2.0, 0.0], [0.0, 50.0]]), np.array([[30.0, 0.0], [0.0, 30.0]]),
                                                np.array([[16.0, -12.0], [-12.0, 9.0]]), np.array([[5.0, 4.0], [4.0, 5.0]]),
                                                np.array([[1.0, 0.0], [0.0, 1.0]]) * 1e-4]
    ks = [1.0, 2.0, 1.0, 3.0, 1.0, 2.0, 1.0, 1.5, 1.0]
    E["ellipse"] = [[L(P), k, list(U.ellipse(P, k=k))] for P, k in zip(mats, ks)]
    cases = []
    for _ in range(3):
        S = rand_cov(rng)
        r = rng.normal(0, 8, 2).round(2)
        cases.append([L(r), L(S), U.mahalanobis2(r, S)])
    S3 = np.array([[4.0, 1.0, 0.5], [1.0, 9.0, -2.0], [0.5, -2.0, 16.0]])
    cases.append([[1.0, -2.0, 3.0], L(S3), U.mahalanobis2([1.0, -2.0, 3.0], S3)])
    E["mahalanobis2"] = cases
    props = []
    for shape in ((2, 2), (1, 2), (3, 2), (2, 3)):
        J = rng.normal(0, 2, shape).round(3)
        n = shape[1]
        A = rng.normal(0, 1.5, (n, n))
        P = (A @ A.T + np.eye(n)).round(4)
        props.append([L(J), L(P), L(U.propagate(J, P))])
    E["propagate"] = props
    polars = [(4500.0, 215.0, 12.0, 0.8), (800.0, 10.0, 3.0, 2.5), (2500.0, 135.0, 20.0, 0.25)]
    E["polar_to_en"] = [[list(a), L(U.polar_to_en(*a)[0]), L(U.polar_to_en(*a)[1])] for a in polars]
    S = [[400.0, 0.0], [0.0, 25.0]]
    gates = [([50.0, 0.0], S, 0.99), ([0.0, 14.0], S, 0.99),            # d² 6.25 / 7.84: dof 1 (6.63) says no
             ([0.0, 14.8], S, 0.99), ([60.0, 0.0], S, 0.99),            # d² 8.76 → yes; 9.0 → yes (k = 3 says no)
             ([40.0, 8.0], S, 0.95), ([30.0, 6.0], S, 0.95),            # 6.56 → no at 95 %; 3.69 → yes
             ([300.0, 0.0], S, 0.99), ([11.0, -9.0], [[50.0, 40.0], [40.0, 50.0]], 0.99),
             ([1.0, 2.0, 2.0], [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], 0.99)]
    gl = []
    for r, SS, p in gates:
        if len(r) == 3:
            continue                                                 # chi2_threshold is for 1–2 dof: not graded
        gl.append([r, L(SS), p, U.gate(r, SS, p)])
    E["gate"] = gl
    fuses = []
    for _ in range(3):
        P1, P2 = rand_cov(rng, 2, 30), rand_cov(rng, 2, 30)
        x1, x2 = rng.normal(0, 20, 2).round(2), rng.normal(0, 20, 2).round(2)
        x, P = U.fuse(x1, P1, x2, P2)
        fuses.append([L(x1), L(P1), L(x2), L(P2), L(x), L(P)])
    E["fuse"] = fuses
    mc = []
    for P2, up in (([[49.0, -14.0], [-14.0, 16.0]], 6.0), ([[49.0, 0.0], [0.0, 16.0]], 6.0),
                   ([[49.0, -14.0], [-14.0, 16.0]], None), ([[4.0, 0.0], [0.0, 81.0]], None)):
        cov9, kind = U.make_covariance(P2, sigma_up_m=up)
        mc.append([P2, up, cov9, kind])
    E["make_covariance"] = mc
    E["make_covariance_bad"] = [[[[9.0, 4.0], [3.0, 9.0]], 2.0, "not symmetric"],
                                [[[9.0, 10.0], [10.0, 9.0]], 2.0, "not positive semi-definite"],
                                [[[-9.0, 0.0], [0.0, 9.0]], None, "negative variance"],
                                [[[9.0, 0.0], [0.0, 9.0]], float("nan"), "not finite"]]
    return E


def drive_policy(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    thr = U.chi2_threshold(0.95)
    errs, cover, caught, fa = [], [], 0, 0
    for row in rows:
        truth = np.array([float(row["true_e"]), float(row["true_n"])])
        g = np.array([float(row["gps_e"]), float(row["gps_n"])])
        Pg = np.array([[float(row["gps_a"]), float(row["gps_b"])], [float(row["gps_b"]), float(row["gps_c"])]])
        v = np.array([float(row["vis_e"]), float(row["vis_n"])])
        Pv = float(row["vis_sigma_m"]) ** 2 * np.eye(2)
        if U.gate(v - g, Pg + Pv, 0.99):
            x, P = U.fuse(g, Pg, v, Pv)
        else:
            x, P = g, Pg
            caught += row["vis_wrong"] == "1"
            fa += row["vis_wrong"] != "1"
        e = x - truth
        errs.append(math.hypot(*e))
        cover.append(U.mahalanobis2(e, P) <= thr)
    errs = np.array(errs)
    return {"rms_m": float(np.sqrt(np.mean(errs ** 2))), "cover_pct": float(100 * np.mean(cover)),
            "caught": int(caught), "false_alarms": int(fa), "n": len(rows)}


def lab_numbers():
    tmp = tempfile.mkdtemp(prefix="exp27_")
    try:
        for name in os.listdir(os.path.join(COURSE, "files")):
            src = os.path.join(COURSE, "files", name)
            (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(tmp, name))
        sol = os.path.join(ACADEMY, "solutions", "27-uncertainty")
        shutil.rmtree(os.path.join(tmp, "navera_lite"))
        shutil.copytree(os.path.join(sol, "navera_lite"), os.path.join(tmp, "navera_lite"))
        shutil.copy(os.path.join(sol, "chi2_sim.py"), tmp)
        env = dict(os.environ, UNCERTAINTY_DATA=DATA, MPLBACKEND="Agg")
        for cmd in (["cloud"], ["radar"], ["radar", "wide"], ["judge"], ["attack"], ["fuse"], ["publish"]):
            subprocess.run([sys.executable, "run_uncertainty.py", *cmd], cwd=tmp, env=env, check=True,
                           stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, "chi2_sim.py"], cwd=tmp, env=env, check=True, stdout=subprocess.DEVNULL)
        with open(os.path.join(tmp, "out", "results.json")) as f:
            return json.load(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    E = functions()
    E["drive"] = drive_policy(os.path.join(COURSE, "hidden", "drive.csv"))
    E["lab"] = lab_numbers()
    os.makedirs(os.path.join(COURSE, "hidden"), exist_ok=True)
    out = os.path.join(COURSE, "hidden", "expected.json")
    with open(out, "w") as f:
        json.dump(E, f, indent=1)
    print("wrote", out)
    print("drive:", E["drive"])
    lab = E["lab"]
    print("lab:", json.dumps({k: v for k, v in lab.items() if k != "fuse"}, indent=None))
    print("fuse:", {k: (v["rms_m"], v["cover_pct"], v["false_alarms"]) for k, v in lab["fuse"].items()})


if __name__ == "__main__":
    main()

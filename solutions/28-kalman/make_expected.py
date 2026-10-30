#!/usr/bin/env python3
"""Teacher only — writes courses/28-kalman/hidden/expected.json: the check's unseen inputs and the reference's
outputs (TODOs 1–5 and 7), the reference band of TODO 6 (many trials), and every lab number, read from
run_kalman.py's own functions run on the reference (so the check's constants are exactly what a correct student
sees).

    python3 solutions/28-kalman/make_expected.py          (after make_dataset.py)
"""
import contextlib
import io
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
REF = os.path.join(ACADEMY, "solutions", "_navera_lite")
sys.path.insert(0, REF)
from navera_lite import kalman as K   # noqa: E402

OUT = os.path.join(ACADEMY, "courses", "28-kalman", "hidden", "expected.json")
rng = np.random.default_rng(2830)


def spd(n, scale):
    A = rng.normal(size=(n, n))
    return (A @ A.T + n * np.eye(n)) * scale


def tolist(a):
    return np.asarray(a, dtype=float).tolist()


def main():
    E = {}
    # TODO 1
    E["cv"] = []
    for dt, q, dims in ((0.7, 2.5, 1), (1.3, 0.4, 2), (0.25, 9.0, 3), (2.0, 0.0, 2)):
        F, Q = K.cv_model(dt, q, dims)
        E["cv"].append({"args": [dt, q, dims], "F": tolist(F), "Q": tolist(Q)})
    # TODO 2
    E["predict"] = []
    F, Q = K.cv_model(0.8, 0.6, 2)
    x, P = rng.normal(size=4) * [50, 50, 5, 5], spd(4, 3.0)
    xp, Pp = K.kf_predict(x, P, F, Q)
    E["predict"].append({"x": tolist(x), "P": tolist(P), "F": tolist(F), "Q": tolist(Q), "xp": tolist(xp),
                         "Pp": tolist(Pp)})
    F, Q = K.cv_model(1.7, 0.09, 1)
    x, P = [212.0, -1.3], [[6.0, 1.1], [1.1, 0.7]]
    xp, Pp = K.kf_predict(x, P, F, Q)
    E["predict"].append({"x": x, "P": P, "F": tolist(F), "Q": tolist(Q), "xp": tolist(xp), "Pp": tolist(Pp),
                         "lists": True})
    # TODO 3
    E["update"] = []
    x, P = rng.normal(size=4) * [40, 40, 4, 4], spd(4, 6.0)
    H = np.hstack([np.eye(2), np.zeros((2, 2))])
    z = x[:2] + np.array([7.5, -4.0])
    R = np.array([[16.0, 3.0], [3.0, 9.0]])
    xu, Pu, nis = K.kf_update(x, P, z, H, R)
    E["update"].append({"x": tolist(x), "P": tolist(P), "z": tolist(z), "H": tolist(H), "R": tolist(R),
                        "xu": tolist(xu), "Pu": tolist(Pu), "nis": nis})
    x, P = [57.0, 0.4], [[11.0, 2.5], [2.5, 1.8]]
    xu, Pu, nis = K.kf_update(x, P, [53.2], [[1.0, 0.0]], [[6.25]])
    E["update"].append({"x": x, "P": P, "z": [53.2], "H": [[1.0, 0.0]], "R": [[6.25]], "xu": tolist(xu),
                        "Pu": tolist(Pu), "nis": nis})
    # TODO 4: an unseen height sequence: starts with "no reading", same time twice, negative, nan, climb_accel 0.3
    seq = [(0.0, 0.0, 2.0), (0.6, 151.2, 2.0), (1.1, 149.8, 4.5), (1.1, 152.9, 1.2), (2.9, 155.0, 3.0),
           (3.4, -5.0, 3.0), (4.0, 158.7, 1.2), (4.0, float("nan"), 1.2), (6.5, 161.0, 4.8), (7.2, 0.0, 1.0),
           (9.8, 166.4, 1.5), (10.0, 164.9, 3.3), (13.5, 171.2, 2.1), (14.1, 170.3, 5.1), (17.0, 169.0, 1.2)]
    f = K.Height1D(0.3)
    outs = []
    for t, h, s in seq:
        o = f.update(t, h, s)
        outs.append(None if o is None else list(o))
    E["height"] = {"climb_accel": 0.3, "seq": [[t, (None if math.isnan(h) else h), s] for t, h, s in seq],
                   "out": outs}
    f = K.Height1D()
    E["height_default"] = [list(f.update(10.0, 300.0, 6.0)), list(f.update(12.5, 296.0, 3.0))]
    # TODO 5
    E["nees"] = []
    for err, P in (([4.0, -2.5], [[9.0, 4.0], [4.0, 6.0]]), ([1.5, -0.5, 2.0], tolist(spd(3, 0.5))),
                   ([-3.0], [[2.25]])):
        E["nees"].append({"err": err, "P": P, "v": K.nees(err, P)})
    # TODO 6: reference bands from many trials (the student's 4 000 trials vary by a few %)
    def band(n, N, p, trials=200000, seed=7):
        g = np.random.default_rng(seed)
        m = np.zeros(trials)
        step = 20000
        for i in range(0, trials, step):
            m[i:i + step] = (g.standard_normal((step, N, n)) ** 2).sum(axis=2).mean(axis=1)
        c = 100.0 * (1.0 - p) / 2.0
        return [float(v) for v in np.percentile(m, [c, 100.0 - c])]
    E["band"] = [{"args": [2, 1, 0.95], "v": band(2, 1, 0.95)}, {"args": [3, 50, 0.9], "v": band(3, 50, 0.9)},
                 {"args": [1, 200, 0.95], "v": band(1, 200, 0.95)}]
    # TODO 7: an unseen flight with irregular times, a gap, two wrong fixes
    g = np.random.default_rng(2831)
    times, zs, t, xs = [0.0], [], 0.0, np.array([10.0, -5.0, 6.0, -3.0])
    truth = [xs.copy()]
    for k in range(1, 70):
        dt = float(g.choice([0.5, 1.0, 1.0, 1.5, 2.0]))
        t += dt
        a = math.sqrt(0.5) * g.standard_normal(2)
        xs = np.array([xs[0] + xs[2] * dt + 0.5 * a[0] * dt * dt, xs[1] + xs[3] * dt + 0.5 * a[1] * dt * dt,
                       xs[2] + a[0] * dt, xs[3] + a[1] * dt])
        times.append(round(t, 3))
        truth.append(xs.copy())
    for k, s in enumerate(truth):
        if 30 <= k <= 41:
            zs.append(None)
        elif k in (12, 55):
            zs.append([round(float(s[0]) + 120.0, 3), round(float(s[1]) - 60.0, 3)])
        else:
            zs.append([round(float(s[0] + 4.0 * g.standard_normal()), 3), round(float(s[1] + 4.0 * g.standard_normal()), 3)])
    E["flight"] = {"times": times, "zs": zs, "sigma_z": 4.0, "q": 0.5, "runs": {}}
    for gate in (None, 0.95):
        r = K.run_filter(times, [None if z is None else tuple(z) for z in zs], 4.0, 0.5, gate_p=gate)
        E["flight"]["runs"][str(gate)] = {"x": [tolist(v) for v in r["x"]], "P00": [float(P[0, 0]) for P in r["P"]],
                                          "P23": [float(P[2, 3]) for P in r["P"]], "d2": r["d2"],
                                          "accepted": r["accepted"]}
    r = K.run_filter(times, [None if z is None else tuple(z) for z in zs], 4.0, 0.5, v0_sigma=5.0)
    E["flight"]["v0_5"] = [tolist(v) for v in r["x"]]
    E["lab"] = lab_numbers()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(E, fh, indent=0)
    print("wrote", OUT, os.path.getsize(OUT), "bytes")
    print(json.dumps(E["lab"], indent=1))


def lab_numbers():
    """The lab's numbers, computed with run_kalman.py's own functions on the reference solution."""
    tmp = tempfile.mkdtemp()
    try:
        for name in ("run_kalman.py", "runner_kit.py"):
            shutil.copy(os.path.join(ACADEMY, "courses", "28-kalman", "files", name), tmp)
        shutil.copy(os.path.join(HERE, "band_sim.py"), tmp)
        shutil.copytree(os.path.join(HERE, "navera_lite"), os.path.join(tmp, "navera_lite"))
        os.environ["KALMAN_DATA"] = os.path.join(ACADEMY, "datasets", "28-kalman")
        old = os.getcwd()
        os.chdir(tmp)
        sys.path.insert(0, tmp)
        for m in [m for m in sys.modules if m == "navera_lite" or m.startswith("navera_lite.")]:
            del sys.modules[m]
        import run_kalman as rkal
        import band_sim
        L = {}
        with contextlib.redirect_stdout(io.StringIO()):
            # Step 1: grow (same numbers as rkal.grow)
            x, P = np.array([0.0, 0.0, 12.0, 0.0]), np.diag([9.0, 9.0, 1.0, 1.0])
            F, Q = rkal.model(1.0, 0.3, 2)
            for _ in range(40):
                x, P = rkal.predict(x, P, F, Q)
            L["SIGMA_40S_M"] = math.sqrt(P[0, 0])
            x2, P2, nis = rkal.update(np.array([120.0, 0.0]), np.array([[16.0, 4.0], [4.0, 2.0]]), [126.0],
                                      [[1.0, 0.0]], [[4.0]])
            L["TRACE_HEIGHT_M"], L["TRACE_CLIMB_MPS"], L["TRACE_SIGMA_M"] = float(x2[0]), float(x2[1]), \
                math.sqrt(P2[0, 0])
            rows = rkal.read_heights()
            truth = [r[4] for r in rows]
            usable = [i for i, r in enumerate(rows) if r[1] > 0]
            for a, key in ((0.5, "RACE_RMSE_FILTER_M"), (0.05, "RMSE_CA_005_M"), (5.0, "RMSE_CA_5_M")):
                mine = rkal.run_height(a, rows)
                L[key] = rkal.rms([mine[i][0] - truth[i] for i in usable])
            L["RACE_RMSE_RAW_M"] = rkal.rms([rows[i][1] - truth[i] for i in usable])
            lo, hi = band_sim.nees_band(2, 361)
            L["BAND_LOW"], L["BAND_HIGH"] = lo, hi
            f = rkal.flight(0.3, None)
            L["NEES_NO_GATE"] = rkal.summary(f)[3]
            j1 = f["jam"][-1]
            L["SIGMA_END_JAM_M"] = math.sqrt(f["P"][j1][0, 0])
            L["ERR_END_JAM_M"] = float(math.hypot(*f["err"][j1]))
            L["D2_AFTER_JAM_NOGATE"] = float(f["r"]["d2"][j1 + 1])
            f = rkal.flight(0.3, 0.99)
            w, g, rmse, mn = rkal.summary(f)
            L["NEES_GATE"], L["WRONG_REFUSED"], L["GOOD_REFUSED"], L["RMSE_GATE_M"] = mn, w, g, rmse
            L["ERR_END_JAM_GATE_M"] = float(math.hypot(*f["err"][j1]))
            L["D2_AFTER_JAM"] = float(f["r"]["d2"][j1 + 1])
            L["SWEEP"] = {}
            for q in rkal.SWEEP_Q:
                f = rkal.flight(q, 0.99)
                w, g, rmse, mn = rkal.summary(f)
                L["SWEEP"][str(q)] = [rmse, mn, w, g]
            L["Q_BEST"] = 0.3
        os.chdir(old)
        return L
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

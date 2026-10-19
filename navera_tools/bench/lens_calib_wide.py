#!/usr/bin/env python3
"""Calibrate the 360 camera's lenses out to their edges: the screen's dot grid seen at many angles.

    python3 navera_tools/bench/lens_calib_wide.py [--minutes 4] [--save] [--from-views X_views.pkl]

Why: lens_calib_screen.py measures only the ~60 degrees of a lens that see the screen square on, but a
standing camera sees the stars 50-100 degrees off each lens's axis, where that fit is extrapolated
(two fits equally good in the centre differ by ~0.6 degree at 60-90 degrees). Here the camera is turned
by hand, standing, in steps; each time it is still for 2 s after a turn of more than 8 degrees, the dots
are captured. The dots are paired with the prediction from the first view turned by the camera's own
gyro, then every lens's f, k1 and centre are fitted together with one screen pose per view.

The first view needs a lens facing the screen square on: the screen is found by flashing it
(view360.Bench360) and its pose fitted with that lens's current model. --save updates insta360_usb_lens.json (the old file
is kept as insta360_usb_lens.json.bak).
"""
import argparse
import json
import math
import os
import shutil
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    sys.path.insert(0, p)

from navera_tools.bench.attitude_check import angle_deg, detect, pair  # noqa: E402
from navera_tools.bench.lens_calib_screen import LENS_FILE, SH, SW, grid  # noqa: E402
from navera_tools.bench.view360 import Bench360  # noqa: E402
from navera_tools.field.reprocess360 import rotvec  # noqa: E402
from navera_tools.field.sky360 import Lens, default_lenses  # noqa: E402

W = "NAVERA lens wide"
MAX_THETA_DEG = 98.0                                       # beyond: the circle's edge, dots too squeezed
VERBOSE = 0


def project(lens, Rs, T, P):
    X = P @ Rs.T + T
    v = X @ lens.R_lens_imu.T
    x, y, th = lens.project(v)
    return np.c_[x, y], np.degrees(th)


def fit_lenses(views, lenses, P, R_att0, Rs0, T0, rounds=3):
    """Every lens's f, k1, cx, cy with one screen pose per (view, lens): the two lenses' centres are ~3 cm
    apart, which at 45 cm is ~4 degrees, so a view seen by both lenses cannot share one pose. After each
    fit the dots are paired again with the fitted model (tight tolerance), from all the spots found."""
    from scipy.optimize import least_squares
    from scipy.spatial.transform import Rotation
    keys, init, obs = [], [], {}
    for k, v in enumerate(views):
        Rs, T = v["R_att"].T @ R_att0 @ Rs0, v["R_att"].T @ R_att0 @ T0
        for li, ip, det, det_all in v["obs"]:
            keys.append((k, li))
            init.append(np.r_[Rotation.from_matrix(Rs).as_rotvec(), T])
            obs[(k, li)] = (ip, det, det_all)
    nl = len(lenses)
    x = np.r_[sum(([L.f, L.k1, L.cx, L.cy] for L in lenses), []), np.concatenate(init)].astype(float)

    def unpack(x):
        ls = [Lens(L.name, x[4 * i + 2], x[4 * i + 3], x[4 * i], L.R_lens_imu, k1=x[4 * i + 1], radius=L.radius)
              for i, L in enumerate(lenses)]
        return ls, x[4 * nl:].reshape(-1, 6)

    def res(x):
        ls, vp = unpack(x)
        return np.concatenate([(project(ls[li], rotvec(vp[g, :3]), vp[g, 3:], P[obs[key][0]])[0] - obs[key][1]).ravel()
                               for g, key in enumerate(keys) for li in [key[1]]])

    def sparsity():                                     # a group's residuals depend on its lens and its own pose only
        from scipy.sparse import lil_matrix
        rows = sum(2 * len(obs[key][0]) for key in keys)
        J = lil_matrix((rows, len(x)), dtype=int)
        r0 = 0
        for g, key in enumerate(keys):
            n = 2 * len(obs[key][0])
            J[r0:r0 + n, 4 * key[1]:4 * key[1] + 4] = 1
            J[r0:r0 + n, 4 * nl + 6 * g:4 * nl + 6 * g + 6] = 1
            r0 += n
        return J

    for rnd in range(rounds):
        x = least_squares(res, x, x_scale="jac", loss="soft_l1", f_scale=1.0, jac_sparsity=sparsity(), max_nfev=200, verbose=VERBOSE).x
        ls, vp = unpack(x)
        tol = (6.0, 4.0, 3.0)[min(rnd, 2)]
        for g, key in enumerate(keys):                  # pair again with the fitted model
            pred, th = project(ls[key[1]], rotvec(vp[g, :3]), vp[g, 3:], P)
            ok = np.nonzero(th < MAX_THETA_DEG)[0]
            from scipy.spatial import cKDTree
            d, j = cKDTree(obs[key][2]).query(pred[ok], distance_upper_bound=tol)
            m = np.isfinite(d)
            jj = j[m]
            uniq = np.array([np.sum(jj == u) == 1 for u in jj], bool)
            obs[key] = (ok[m][uniq], obs[key][2][jj[uniq]], obs[key][2])
        n = sum(len(o[0]) for o in obs.values())
        print(f"fit round {rnd + 1}: {n} dots paired again (tolerance {tol:.0f} px)", flush=True)
    x = least_squares(res, x, x_scale="jac", loss="soft_l1", f_scale=1.0, jac_sparsity=sparsity(), max_nfev=200, verbose=VERBOSE).x
    ls, vp = unpack(x)
    groups = {key: (rotvec(vp[g, :3]), vp[g, 3:], obs[key][0], obs[key][1]) for g, key in enumerate(keys)}
    return ls, groups


def finish(a, views, lenses, P, R_att0, Rs0, T0):
    """Fit both lenses on the captured views, print the report and (with --save) update the lens file."""
    if len(views) < 3:
        print("too few views: turn the camera in steps of ~15-20 degrees and hold each 2 s")
        os._exit(1)

    ls, groups = fit_lenses(views, lenses, P, R_att0, Rs0, T0)
    used_lenses = sorted({li for v in views for li, *_ in v["obs"]})
    report = {"views": len(views), "lenses": {}}
    for li in used_lenses:
        L = ls[li]
        r_all, th_all = [], []
        for (k, lj), (Rs_g, T_g, ip, det) in groups.items():
            if lj == li:
                pr, th = project(L, Rs_g, T_g, P[ip])
                r_all.append(np.hypot(*(pr - det).T))
                th_all.append(th)
        r, th = np.concatenate(r_all), np.concatenate(th_all)
        bands = {}
        for lo, hi in ((0, 30), (30, 60), (60, 80), (80, 100)):
            m = (th >= lo) & (th < hi)
            if m.any():
                bands[f"{lo}-{hi} deg"] = {"dots": int(m.sum()), "rms_deg": round(math.degrees(float(np.sqrt(np.mean(r[m] ** 2))) / L.f), 3)}
        old = lenses[li]
        # how far the old model was from the new one at the angles the stars are seen at
        thg = np.radians(np.arange(10, 100, 10))
        d_old = np.degrees((old.f * (thg + old.k1 * thg ** 3) - L.f * (thg + L.k1 * thg ** 3)) / L.f)
        report["lenses"][L.name] = {"f": round(float(L.f), 2), "k1": round(float(L.k1), 5), "cx": round(float(L.cx), 2),
                                   "cy": round(float(L.cy), 2), "dots": int(len(r)), "max_theta_deg": round(float(th.max()), 1),
                                   "rms_deg_by_angle": bands,
                                   "old_model_error_deg_at_10_to_90": [round(float(v), 2) for v in d_old]}
    print(json.dumps(report, indent=1))
    json.dump(report, open(a.out, "w"), indent=1)
    if a.save:
        d = json.load(open(LENS_FILE)) if os.path.exists(LENS_FILE) else {}
        shutil.copy(LENS_FILE, LENS_FILE + ".bak") if os.path.exists(LENS_FILE) else None
        for name, m in report["lenses"].items():
            if m["max_theta_deg"] < 70.0:
                print(f"{name}: dots only to {m['max_theta_deg']} deg: not saved (turn further)")
                continue
            d[name] = {k: m[k] for k in ("f", "k1", "cx", "cy")}
            d[name].update(measured="screen dots to %.0f deg, %d views %s" % (m["max_theta_deg"], len(views), time.strftime("%Y-%m-%d")))
        json.dump(d, open(LENS_FILE, "w"), indent=1)
        print("saved", LENS_FILE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=4.0)
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--out", default="lens_calib_wide.json")
    ap.add_argument("--from-views", help="refit a saved <out>_views.pkl instead of capturing")
    a = ap.parse_args()
    if a.from_views:
        import pickle
        with open(a.from_views, "rb") as fh:
            v = pickle.load(fh)
        finish(a, v["views"], default_lenses(), v["P"], v["R_att0"], v["Rs0"], v["T0"])
        os._exit(0)
    ap_mm = 527.0
    lenses = default_lenses()
    mm = ap_mm / SW
    G = grid(16, 9)
    P = np.c_[(G - [SW / 2, SH / 2]) * mm, np.zeros(len(G))]
    img = np.zeros((SH, SW), np.uint8)
    for x, y in G:
        cv2.circle(img, (int(x), int(y)), 8, 255, -1, cv2.LINE_AA)
    cv2.namedWindow(W, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(W, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    bench = Bench360(W)
    info = bench.find_screen(100.0, 1200, 900, screen_mm=ap_mm, distance_mm=420.0)
    print("screen:", info, flush=True)
    cam = bench.cam
    lens0 = next(L for L in lenses if L.name == info["lens"])
    R_view = bench.view.R_view_imu
    dist = (ap_mm / 2) / math.tan(math.radians(info["screen_width_deg"]) / 2)
    Rs0, T0 = np.stack([R_view[0], R_view[1], R_view[2]], axis=1), R_view[2] * dist
    end = time.time() + 4.0
    while time.time() < end:
        cv2.imshow(W, img)
        cv2.waitKey(40)
    # the first pose: coarse pairing, then fine (lens fixed at its current model)
    from navera_tools.bench.attitude_check import fit_pose
    f0, _, ms0 = cam.latest_stamped()
    R_att_first = cam.attitude_at(ms0)                   # the attitude the first pose belongs to
    g0 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY).astype(np.float32)
    for tol in (60.0, 25.0, 10.0):
        pred = project(lens0, Rs0, T0, P)[0]
        c = pred.mean(axis=0)
        det = detect(g0, c, radius=float(np.hypot(*(pred - c).T).max()) + 60.0)   # only around the screen
        pi, di, _ = pair(pred, det, tol)
        if len(pi) < 12:
            raise SystemExit(f"only {len(pi)} dots paired on the first view ({len(det)} spots): is a lens facing the screen?")
        Rs0, T0, rms0 = fit_pose(lens0, Rs0, T0, P[pi], det[di])
        print(f"first view: {len(pi)} dots paired (tolerance {tol:.0f} px), fit {rms0:.2f} px", flush=True)
    R_att0, views, last_R, t0 = None, [], None, time.time()
    still_since, last_ms = None, None
    while time.time() - t0 < 60.0 * a.minutes:
        cv2.imshow(W, img)
        cv2.waitKey(30)
        f, _, ms = cam.latest_stamped()
        if f is None or ms == last_ms:
            continue
        last_ms = ms
        R_att = cam.attitude_at(ms)
        # still enough for a sharp frame (a hand may still touch the camera: no accelerometer test)
        rows = cam._rows(1.0, ms, 0.3)
        w = np.array([r[5:8] for r in rows]) - cam.gyro_bias if len(rows) >= 400 else None
        still = w is not None and float(np.degrees(np.linalg.norm(
            w[:len(w) // 50 * 50].reshape(-1, 50, 3).mean(axis=1), axis=1)).max()) < 1.5
        if R_att is None or not still:
            still_since = None
            continue
        still_since = still_since or time.time()
        if time.time() - still_since < 0.3:
            continue
        if R_att0 is None:
            R_att0 = R_att_first if R_att_first is not None else R_att
        if last_R is not None and angle_deg(last_R.T @ R_att) < 8.0:
            continue                                       # not turned enough since the last view
        Rs, T = R_att.T @ R_att0 @ Rs0, R_att.T @ R_att0 @ T0
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        got = []
        for li, lens in enumerate(lenses):
            pred, th = project(lens, Rs, T, P)
            vis = th < MAX_THETA_DEG
            if vis.sum() < 12:
                continue
            c = pred[vis].mean(axis=0)
            det = detect(g, c, radius=float(np.hypot(*(pred[vis] - c).T).max()) + 80.0)
            idx = np.nonzero(vis)[0]
            pi, di, off = pair(pred[vis], det, 25.0)
            if len(pi) >= 12:
                got.append((li, idx[pi], det[di], det))       # all spots kept: pairs are redone after the fit
        turned = angle_deg(R_att0.T @ R_att)
        if not got:
            print(f"{time.time() - t0:6.1f}s turned {turned:5.1f} deg: no dots paired", flush=True)
            last_R = R_att
            continue
        views.append({"R_att": R_att, "obs": got})
        last_R = R_att
        desc = ", ".join(f"{lenses[li].name} {len(ip)} dots (to {project(lenses[li], Rs, T, P)[1][ip].max():.0f} deg)" for li, ip, _, _ in got)
        print(f"{time.time() - t0:6.1f}s view {len(views)}: turned {turned:5.1f} deg | {desc}", flush=True)
    cam.close()
    cv2.destroyAllWindows()
    import pickle
    with open(os.path.splitext(a.out)[0] + "_views.pkl", "wb") as fh:
        pickle.dump({"views": views, "R_att0": R_att0, "Rs0": Rs0, "T0": T0, "P": P,
                     "lenses": [(L.name, L.cx, L.cy, L.f, L.k1, L.R_lens_imu, L.radius) for L in lenses]}, fh)
    finish(a, views, lenses, P, R_att0, Rs0, T0)
    os._exit(0)


if __name__ == "__main__":
    main()

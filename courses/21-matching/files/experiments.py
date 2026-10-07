"""Lesson 21 — the measurements for your report.   python3 experiments.py

Uses YOUR geometry.py and matching.py (all TODOs done) and writes results.json:
  1. ransac_N        the RANSAC formula N(p = 0.99, w, s) for s = 2 (similarity) and s = 4 (homography)
  2. monte_carlo     does N really give probability p?  20 000 simulated RANSAC runs
  3. normalisation   DLT with / without Hartley normalisation: condition number and error
  4. pairs           OpenCV's RANSAC vs yours on the four pairs, and NAVERA's trust gates
  5. ratio_sweep     the ratio test from 0.6 to 1.0 on the 'otherdate' pair
Takes about 30 s.
"""
import json
import math
import time

import numpy as np

import geometry
import matching

P = 0.99


def ransac_table():
    out = {}
    for s in (2, 4):
        out[f"s{s}"] = {str(w): geometry.ransac_iterations(P, w, s) for w in (0.9, 0.7, 0.5, 0.3, 0.1)}
    return out


def monte_carlo(w=0.5, s=4, runs=20000, seed=7):
    """Draw N samples of s items from an infinite set with inlier ratio w; how often does at
    least one sample hold only inliers?"""
    n = geometry.ransac_iterations(P, w, s)
    rng = np.random.default_rng(seed)
    good_sample = (rng.random((runs, n, s)) < w).all(axis=2)     # each sample: all inliers?
    return {"w": w, "s": s, "N": n, "runs": runs, "success_rate": round(float(good_sample.any(axis=1).mean()), 4),
            "predicted": P}


def normalisation():
    """DLT from 8 noisy pairs (1 px), with the map side in two coordinate systems: patch pixels
    (0..800) and global zoom-18 tile pixels (~3.55e7, what NAVERA's map points are in)."""
    src, dst, H_true, _ = geometry.synthetic_pairs(n=300, outlier_ratio=0.0, noise_px=1.0, seed=3)
    grid = np.stack(np.meshgrid(np.linspace(0, 640, 9), np.linspace(0, 480, 7)), -1).reshape(-1, 2)
    out = {}
    for label, off in (("patch_px", 0.0), ("global_px", 3.55e7)):
        rng = np.random.default_rng(0)
        errs = {True: [], False: []}
        for _ in range(200):
            i = rng.choice(len(src), 8, replace=False)
            for norm in (True, False):
                H = geometry.dlt_homography(src[i], dst[i] + off, normalise=norm)
                e = np.linalg.norm(geometry.apply_homography(H, grid) - (geometry.apply_homography(H_true, grid) + off),
                                   axis=1)
                errs[norm].append(float(e.mean()))
        sn, _ = geometry.normalise_points(src[:50])
        dn, _ = geometry.normalise_points(dst[:50] + off)
        out[label] = {"cond_raw": float(np.linalg.cond(geometry.build_dlt_matrix(src[:50], dst[:50] + off))),
                      "cond_normalised": float(np.linalg.cond(geometry.build_dlt_matrix(sn, dn))),
                      "median_err_raw_px": round(float(np.median(errs[False])), 3),
                      "median_err_normalised_px": round(float(np.median(errs[True])), 3)}
    return out


def pairs():
    truth = matching.load_truth()
    out = {}
    for name in ("city", "olives", "otherdate", "sea"):
        view, patch = matching.load_pair(name)
        t = truth[name]
        row = {}
        for method in ("opencv", "mine"):
            t0 = time.time()
            H, inl, det = matching.match_views(view, patch, method=method)
            r = {"good": len(det["good"]), "inliers": int(inl), "ms": round((time.time() - t0) * 1000.0)}
            if H is not None:
                sp = geometry.similarity_params(H)
                cx, cy = matching.where_is_centre(H, view)
                r.update(rotation_deg=round(sp["rotation_deg"], 3), scale=round(sp["scale"], 4),
                         anisotropy=round(sp["anisotropy"], 4), perspective=float(sp["perspective"]),
                         centre_error_px=round(math.hypot(cx - t["centre"][0], cy - t["centre"][1]), 3))
                ok, why = matching.trust(H, det["src"][det["mask"]], view.shape, t["scale"], t["rotation_deg"])
            else:
                ok, why = matching.trust(None, np.zeros((0, 2)), view.shape, t["scale"], t["rotation_deg"])
            r.update(trusted=bool(ok), reason=why)
            row[method] = r
        out[name] = row
    return out


def ratio_sweep(name="otherdate"):
    truth = matching.load_truth()[name]
    view, patch = matching.load_pair(name)
    out = {}
    for ratio in (0.6, 0.7, 0.8, 0.9, 1.0):
        H, inl, det = matching.match_views(view, patch, ratio=ratio)
        r = {"good": len(det["good"]), "inliers": int(inl)}
        if H is not None:
            cx, cy = matching.where_is_centre(H, view)
            r["centre_error_px"] = round(math.hypot(cx - truth["centre"][0], cy - truth["centre"][1]), 2)
            r["inlier_ratio"] = round(inl / max(1, len(det["good"])), 3)
            ok, why = matching.trust(H, det["src"][det["mask"]], view.shape, truth["scale"], truth["rotation_deg"])
        else:
            ok, why = False, "no homography"
        r.update(trusted=bool(ok), reason=why)
        out[str(ratio)] = r
    return out


def main():
    res = {}
    for key, fn in (("ransac_N", ransac_table), ("monte_carlo", monte_carlo), ("normalisation", normalisation),
                    ("pairs", pairs), ("ratio_sweep", ratio_sweep)):
        print(f"--- {key}")
        res[key] = fn()
        print(json.dumps(res[key], indent=1))
    with open("results.json", "w") as f:
        json.dump(res, f, indent=1)
    print("\n→ saved results.json — use these numbers in analysis.md")


if __name__ == "__main__":
    try:
        main()
    except NotImplementedError as e:
        print(f"\n{e} is not done yet: finish geometry.py and matching.py first.")

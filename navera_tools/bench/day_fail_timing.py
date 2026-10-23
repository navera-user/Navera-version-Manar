#!/usr/bin/env python3
"""Time per FAILED day frame on the coast (F4): does a frame that gives no position still cost seconds?

Campaigns 6/7 (screen bench, coast, 2026-10-15) took 6-20 s per failed frame, so about half the frames
were never processed. Here the product matcher (day_perf.make_matcher: LearnedMatcher, the node's gates)
locates frames cut from the coast terrain (campaign 4's other-date imagery, day_perf.Terrain) at points
on a grid over land, shore and sea, with the search radius of a tracked vehicle (150 m) and of a lost
one (400 / 600 m, local_max_radius_m). Per frame: accepted or the refusal reason, and the time; the
summary splits the failed frames by why they failed (uniform frame: rejected before the map window is
gathered, 1a97204 / learned_matcher._locate_learned; too few matches; geometry).

    flock /tmp/claude-1000/navera_gpu.lock python3 navera_tools/bench/day_fail_timing.py [--n 40] [--height 520]
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import day_perf as P  # noqa: E402


def kind(reason: str) -> str:
    r = reason or ""
    if "too few features in the frame" in r:
        return "uniform frame"
    if "feature matches" in r or "geometric inliers" in r:
        return "too few matches"
    if "no map tiles" in r:
        return "no map"
    return "geometry / scale / other"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--terrain", default="coast")
    ap.add_argument("--n", type=int, default=40, help="frames (grid points)")
    ap.add_argument("--height", type=float, default=P.H0)
    ap.add_argument("--radii", default="150,400,600")
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    tdir, mdir, lat, lon = P.terrain_setup(a.terrain)
    T = P.Terrain(tdir, lat, lon)
    M = P.make_matcher(mdir)
    rng = np.random.default_rng(a.seed)
    radii = [float(x) for x in a.radii.split(",")]
    try:
        M.warm(lat, lon, 2500)
        pts = [(rng.uniform(-1200, 1200), rng.uniform(-1200, 1200), rng.uniform(0, 360)) for _ in range(a.n)]
        # one warm-up frame (CUDA kernels, first map windows) not counted
        M.locate(T.view(pts[0][:2], pts[0][2], a.height, rng), T.latlon(pts[0][:2]), 150.0,
                 P.frame_mpp(a.height, P.FRAME[0]), scale_tol=0.15, heading_deg=pts[0][2], heading_tol_deg=20.0)
        rows = []
        for e, n, hdg in pts:
            img = T.view((e, n), hdg, a.height, rng)
            truth = T.latlon((e, n))
            for R in radii:
                off = rng.uniform(0, 2 * np.pi)
                d = rng.uniform(0, 0.5 * R)
                prior = T.latlon((e + d * np.sin(off), n + d * np.cos(off)))
                t0 = time.time()
                r = M.locate(img, prior, R, P.frame_mpp(a.height, img.shape[1]), scale_tol=0.15, heading_deg=hdg,
                             heading_tol_deg=20.0)
                ms = (time.time() - t0) * 1000
                ok = bool(r.get("accepted"))
                err = P.metres((r["predicted_lat"], r["predicted_lon"]), truth) if ok else None
                rows.append(dict(R=R, ok=ok, err=err, ms=ms, why="accepted" if ok else kind(r.get("reason"))))
        print(f"{a.terrain}, {a.n} frames at {a.height:.0f} m, product matcher ({type(M).__name__})")
        print("| search radius | frames | accepted (wrong > 50 m) | failed | failed: ms median / p90 / max "
              "| by reason (n, median ms) |")
        print("|---|---|---|---|---|---|")
        for R in radii:
            rr = [x for x in rows if x["R"] == R]
            acc = [x for x in rr if x["ok"]]
            fail = sorted(x["ms"] for x in rr if not x["ok"])
            by = {}
            for x in rr:
                if not x["ok"]:
                    by.setdefault(x["why"], []).append(x["ms"])
            reasons = "; ".join(f"{k} {len(v)}, {np.median(v):.0f}" for k, v in sorted(by.items()))
            acc_ms = np.median([x["ms"] for x in acc]) if acc else float("nan")
            print(f"| {R:.0f} m | {len(rr)} | {len(acc)} ({sum(1 for x in acc if x['err'] > 50)}), "
                  f"{acc_ms:.0f} ms median | {len(fail)} | "
                  + (f"{np.median(fail):.0f} / {np.percentile(fail, 90):.0f} / {fail[-1]:.0f}" if fail else "-")
                  + f" | {reasons} |")
    finally:
        P.release(M)


if __name__ == "__main__":
    main()

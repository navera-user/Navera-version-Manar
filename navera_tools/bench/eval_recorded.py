#!/usr/bin/env python3
"""Compare day-matcher variants on REAL camera frames recorded by screen_flight.py --record.

    python3 navera_tools/bench/eval_recorded.py REC_DIR [REC_DIR ...] --area AREA \
        [--variant NAME:opt=val,opt=val ...] [--lost-only] [--json out.json]

Every variant sees the identical frames, in order (stateful helpers like the lens mask see the same
sequence), with the recorded truth. Each frame is located around the truth moved by a fixed random
offset (up to 150 m: a carried position after a gap), so the score is the matcher's, not the track's.
Options of a variant:
    lens=1         mask what stays fixed on the lens + saturated glow (image_quality.LensMask)
    sharp=X        refuse frames whose sharpness is below X
    retry=N        describe again with N features a frame that fills its budget and finds too few inliers
Per run and variant: frames, accepted, error median / p90 / max (m), wrong (> 50 m), within 3 sigma,
ms per frame. Frames whose bench truth is uncertain (truth_unc_m > 10: 'wind' shakes the scene faster
than the frame time is known) are scored apart.
"""
import argparse
import json
import math
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common")):
    sys.path.insert(0, p)

from day_pkg import image_quality  # noqa: E402
from day_pkg.local_matcher import LocalMatcher  # noqa: E402


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(q[0]))
    return math.hypot(de, dn)


def parse_variant(s):
    name, _, opts = s.partition(":")
    d = {}
    for kv in filter(None, opts.split(",")):
        k, _, v = kv.partition("=")
        d[k] = float(v)
    return name, d


def summary(rows):
    acc = [r for r in rows if r["accepted"]]
    e = sorted(r["err"] for r in acc)
    q = (lambda p: round(e[min(len(e) - 1, int(p * len(e)))], 1)) if e else (lambda p: None)
    return {"frames": len(rows), "accepted": len(acc), "median": q(0.5), "p90": q(0.9), "max": e[-1] if e else None,
            "wrong": sum(x > 50 for x in e), "in3sigma": sum(r["err"] <= 3 * r["sigma"] for r in acc),
            "ms": round(float(np.median([r["ms"] for r in rows])), 0) if rows else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--area", default=os.path.expanduser("~/.navera_sim/bench_2026-10-06/area"))
    ap.add_argument("--variant", action="append", default=[])
    ap.add_argument("--lost-only", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    variants = [parse_variant(v) for v in (a.variant or ["base:"])]
    M = LocalMatcher(a.area)
    retry = {}
    rng = np.random.default_rng(7)
    out = {}
    for d in a.dirs:
        meta = [json.loads(line) for line in open(os.path.join(d, "frames.jsonl"))]
        meta = [m for m in meta if m.get("mpp") and m.get("truth")]
        if a.lost_only:
            meta = [m for m in meta if m["phase"] == "lost"]
        offs = [(rng.uniform(0, 150.0), rng.uniform(0, 2 * math.pi)) for _ in meta]
        imgs = [cv2.imread(os.path.join(d, m["file"])) for m in meta]
        run = os.path.basename(d.rstrip("/")).replace("rec_", "")
        for name, opt in variants:
            lens = image_quality.LensMask() if opt.get("lens") else None
            rows = []
            for m, img, (r_off, b_off) in zip(meta, imgs, offs):
                if img is None:
                    continue
                truth = tuple(m["truth"])
                prior = (truth[0] + r_off * math.cos(b_off) / 111320.0,
                         truth[1] + r_off * math.sin(b_off) / (111320.0 * math.cos(math.radians(truth[0]))))
                t0 = time.time()
                mask = None
                if lens is not None:
                    lens.update(img)
                    mask = lens.mask(img.shape)
                if opt.get("retry") and int(opt["retry"]) not in retry:
                    retry[int(opt["retry"])] = LocalMatcher(a.area, retry_features=int(opt["retry"]))
                    retry[int(opt["retry"])].tiles = M.tiles
                Mv = retry[int(opt["retry"])] if opt.get("retry") else M
                r = Mv.locate(img, prior, 400.0, m["mpp"], scale_tol=0.15, heading_deg=m.get("rot_deg") or 0.0,
                              heading_tol_deg=15.0, mask=mask)
                ok = bool(r["accepted"]) and r.get("sharpness", 1.0) >= opt.get("sharp", 0.0)
                err = metres((r["predicted_lat"], r["predicted_lon"]), truth) if ok else None
                sig = r.get("sigma_m") or 30.0
                rows.append({"accepted": ok, "err": err, "sigma": sig, "ms": (time.time() - t0) * 1000,
                             "unc": m.get("truth_unc_m") or 0.0, "sharp": r.get("sharpness"),
                             "inliers": r.get("inliers")})
            fair = [r for r in rows if r["unc"] <= 10.0]
            s = summary(fair)
            s["truth_uncertain_frames"] = len(rows) - len(fair)
            s["sharp_median"] = round(float(np.median([r["sharp"] for r in rows if r["sharp"] is not None])), 3)
            out.setdefault(run, {})[name] = s
            print(f"{run:18s} {name:14s} " + "  ".join(f"{k} {v}" for k, v in s.items()), flush=True)
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()

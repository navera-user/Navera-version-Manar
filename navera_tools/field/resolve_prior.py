#!/usr/bin/env python3
"""Solve a 360 field test's saved frames again, lost-in-space and with a position prior, side by side.

    python3 -m navera_tools.field.resolve_prior <session> --prior LAT,LON,KM [--truth LAT,LON,KM] [--every N]
        [--up-err-deg D] [--images DIR] [--out FILE]

The product always starts with GPS: a rough position (last GPS or last fix, grown by the distance flown since)
is known. With it, allsky.locate(prior=...) identifies the stars over far fewer hypotheses (allsky.identify_prior),
so the same stars give an honestly lower chance probability; the fix itself still comes from the stars and the
same gate. The prior's angular radius is KM / 111.2 + the error of 'up' (--up-err-deg, default 0.5).

--truth: where the camera really was (and how far off still counts as right): every accepted fix is marked
right or WRONG. --images: solve the PNG/JPG files of another folder instead (e.g. deep stacks), each with an
index.jsonl row {"image", "up_imu", "t_exp"}. Light on memory (one frame at a time): fine on the Jetson.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.field.reprocess360 import haversine_km  # noqa: E402


def triple(s: str):
    a = [float(v) for v in s.split(",")]
    if len(a) != 3:
        raise argparse.ArgumentTypeError("expected LAT,LON,KM")
    return a


def rows_of(session: str, images: str = None):
    """(folder, row) of every saved frame with an image and 'up'."""
    folder = images or session
    name = "index.jsonl" if images else "frames.jsonl"
    with open(os.path.join(folder, name)) as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("image") and r.get("up_imu"):
                yield folder, r


def solve(img, r, cat, prior, f_scale):
    import numpy as np
    from navera_tools.field import allsky
    t = r.get("t_exp") or r["t"]
    utc = r.get("utc_used") or datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return allsky.locate(img, np.asarray(r["up_imu"], float), utc, cat, f_scales=(f_scale,), prior=prior)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session")
    ap.add_argument("--prior", type=triple, required=True, help="LAT,LON,KM")
    ap.add_argument("--truth", type=triple, help="LAT,LON,KM: fixes further than KM are WRONG")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--up-err-deg", type=float, default=0.5)
    ap.add_argument("--f-scale", type=float, default=1.0)
    ap.add_argument("--images", help="folder with index.jsonl (e.g. deep stacks) instead of the saved frames")
    ap.add_argument("--out", help="JSON lines of every result")
    a = ap.parse_args(argv)
    import cv2
    from navera_tools.field import allsky
    cat = allsky.Catalogue(limit_mag=4.0)
    rad = a.prior[2] / allsky.KM_PER_DEG + a.up_err_deg
    prior = (a.prior[0], a.prior[1], rad)
    tally = {"lost-in-space": [0, 0, 0], "prior": [0, 0, 0]}          # frames, fixes, wrong
    out = open(a.out, "w") if a.out else None
    for n, (folder, r) in enumerate(rows_of(a.session, a.images)):
        if n % a.every:
            continue
        img = cv2.imread(os.path.join(folder, r["image"]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        line = [f"{r.get('idx', n):>5}"]
        for name, pr in (("lost-in-space", None), ("prior", prior)):
            res = solve(img, r, cat, pr, a.f_scale)
            t = tally[name]
            t[0] += 1
            verdict = ""
            if res.get("solved"):
                t[1] += 1
                if a.truth:
                    err = haversine_km(res["lat"], res["lon"], a.truth[0], a.truth[1])
                    wrong = err > a.truth[2]
                    t[2] += wrong
                    verdict = f" {'WRONG' if wrong else 'right'} {err:.0f} km"
            line.append(f"{name}: {'FIX' if res.get('solved') else '-'} m={res.get('matched', 0)} "
                        f"p={res.get('p_chance', 1.0):.2g} rms={res.get('rms_deg', 0):.2f}{verdict}")
            if out:
                out.write(json.dumps({"idx": r.get("idx", n), "mode": name,
                                      **{k: v for k, v in res.items() if k != "R_icrs_imu"}}) + "\n")
        print(" | ".join(line), flush=True)
    for name, (nf, fx, wr) in tally.items():
        print(f"{name}: {nf} frames, {fx} fixes, {wr} wrong" + ("" if a.truth else " (no truth given)"))
    if out:
        out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

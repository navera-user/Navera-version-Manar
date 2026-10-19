#!/usr/bin/env python3
"""Table of a real-camera day campaign (campaign_day_real.sh): one row per screen_flight CSV.

    python3 navera_tools/bench/summarise_day_real.py <out_dir> [--md]

Columns: frames matched / total; vision error median / p90 with GPS lost (the matcher's
accepted matches); wrong accepts = NAVERA output (source vision) > 50 m from the truth, with
GPS lost or after its refusal; gated = matches the track gate refused; spoof refusal = the time
and GPS drift when NAVERA stopped using the drifting GPS (first non-GPS source in the drift
phase); ms/frame median.
"""
import csv
import glob
import os
import sys

import numpy as np


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def summarise(path: str) -> dict:
    rows = list(csv.DictReader(open(path)))
    if not rows:
        return dict(run=os.path.basename(path)[:-4], frames=0)
    lost = [r for r in rows if r["phase"] == "lost"]
    vis = [f(r["vision_err_m"]) for r in lost if r["matched"] == "1" and f(r["vision_err_m"]) is not None]
    out_vis = [r for r in rows if r["phase"] != "gps" and r["source"] == "vision"]
    wrong = sum(1 for r in out_vis if (f(r["navera_err_m"]) or 0) > 50)
    nerr = [f(r["navera_err_m"]) for r in lost if f(r["navera_err_m"]) is not None]
    ref = next((r for r in rows if r["phase"] == "drift" and r["source"] != "gps"), None)
    return dict(run=os.path.basename(path)[:-4], frames=len(rows),
                matched=sum(r["matched"] == "1" for r in rows),
                lost=len(lost), lost_matched=len(vis),
                vis_med=float(np.median(vis)) if vis else None, vis_p90=float(np.percentile(vis, 90)) if vis else None,
                out_med=float(np.median(nerr)) if nerr else None, out_max=max(nerr) if nerr else None,
                wrong=wrong, out_vis=len(out_vis), gated=sum(r.get("gated") == "1" for r in rows),
                refused=None if ref is None else f"t={float(ref['t']):.1f} s, drift {float(ref['gps_drift_m']):.0f} m",
                ms=float(np.median([f(r["ms"]) for r in rows])))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    paths = sorted(glob.glob(os.path.join(sys.argv[1], "*.csv")))
    g = (lambda v: "-" if v is None else f"{v:.1f}" if v < 10 else f"{v:.0f}")
    print("| run | matched/total | GPS lost: matched | vision err median / p90 m | NAVERA out median / max m | "
          "WRONG accepts (>50 m) | gated | spoof refused at | ms/frame |")
    print("|---|---|---|---|---|---|---|---|---|")
    for p in paths:
        s = summarise(p)
        if not s["frames"]:
            print(f"| {s['run']} | empty | | | | | | | |")
            continue
        print(f"| {s['run']} | {s['matched']}/{s['frames']} | {s['lost_matched']}/{s['lost']} | "
              f"{g(s['vis_med'])} / {g(s['vis_p90'])} | {g(s['out_med'])} / {g(s['out_max'])} | "
              f"{s['wrong']}/{s['out_vis']} | {s['gated']} | {s['refused'] or 'never'} | {g(s['ms'])} |")


if __name__ == "__main__":
    main()

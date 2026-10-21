#!/usr/bin/env python3
"""Day accuracy vs map resolution on the UAV-VisLoc flights: one table from uavvisloc_eval.py runs.

    python3 navera_tools/bench/resolution_table.py <dir> [--native-dir DIR] [--exclude 06_0099-06_0180]

<dir> holds g<gsd>_f<flight>.json (degrade_map.py maps; g1 = the native map) and s2_f<flight>.json
(real Sentinel-2, sentinel2_area.py). Per resolution and flight: accepted share, error median /
p90 / max of the accepted fixes, accepted fixes > 100 m off, and the camera footprint in map
pixels (2 h tan(hfov/2) / gsd: what the matcher has to work with). --native-dir: the full native
runs (f<flight>_guard4.json, stride 1), reduced to the same frames, as a second reference.
"""
import argparse
import glob
import json
import math
import os
import re
import statistics as st

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("dir")
ap.add_argument("--native-dir", default="")
ap.add_argument("--exclude", nargs="*", default=["06_0099-06_0180"])
ap.add_argument("--wrong-m", type=float, default=100.0)
ap.add_argument("--json", default="", help="also write the rows here")
a = ap.parse_args()


def excluded(name):
    for r in a.exclude:
        lo, hi = r.split("-")
        if lo[:3] == name[:3] and lo <= name.split(".")[0] <= hi:
            return True
    return False


def row(label, flight, frames, hfov):
    frames = [f for f in frames if not excluded(f["file"])]
    acc = [f for f in frames if f["accepted"] and f["err_m"] is not None]
    e = sorted(f["err_m"] for f in acc)
    h = st.median(f["height_m"] for f in frames)
    gsd = 1.0 if label in ("g1", "native") else 10.0 if label == "s2" else float(label[1:])
    return dict(map=label, flight=flight, height_m=round(h), images=len(frames), accepted=len(acc),
                accepted_pct=round(100 * len(acc) / len(frames), 1) if frames else 0.0,
                median=round(st.median(e), 1) if e else None,
                p90=round(e[max(0, math.ceil(0.9 * len(e)) - 1)], 1) if e else None,
                max=round(e[-1], 1) if e else None, wrong=sum(x > a.wrong_m for x in e),
                footprint_px=round(2 * h * math.tan(math.radians(hfov) / 2) / gsd))


rows = []
for p in sorted(glob.glob(os.path.join(a.dir, "*_f*.json"))):
    m = re.fullmatch(r"(g[\d.]+|s2)_f(\d+)\.json", os.path.basename(p))
    if not m:
        continue
    d = json.load(open(p))
    rows.append(row(m.group(1), m.group(2), d["frames"], d["summary"]["hfov"]))
if a.native_dir:
    stride_frames = {r["flight"]: {f["file"] for f in
                                   json.load(open(os.path.join(a.dir, f"g1_f{r['flight']}.json")))["frames"]}
                     for r in rows if r["map"] == "g1"}
    for p in sorted(glob.glob(os.path.join(a.native_dir, "f*_guard4.json"))):
        fl = re.search(r"f(\d+)_", os.path.basename(p)).group(1)
        d = json.load(open(p))
        keep = stride_frames.get(fl)
        fr = [f for i, f in enumerate(d["frames"]) if (f["file"] in keep if keep else i % 3 == 0)]
        rows.append(row("native", fl, fr, d["summary"]["hfov"]))


def order(r):
    k = {"native": -1, "s2": 99}.get(r["map"], None)
    return (k if k is not None else float(r["map"][1:]), r["height_m"])


rows.sort(key=order)
print("map | flight | height m | footprint px | images | accepted | median / p90 / max m | > %d m" % a.wrong_m)
for r in rows:
    print(f"{r['map']} | {r['flight']} | {r['height_m']} | {r['footprint_px']} | {r['images']} | "
          f"{r['accepted']} ({r['accepted_pct']} %) | {r['median']} / {r['p90']} / {r['max']} | {r['wrong']}")
# pooled per map
print()
print("map | flights | images | accepted | wrong > %d m" % a.wrong_m)
for label in dict.fromkeys(r["map"] for r in rows):
    rs = [r for r in rows if r["map"] == label]
    n, k = sum(r["images"] for r in rs), sum(r["accepted"] for r in rs)
    print(f"{label} | {len(rs)} | {n} | {k} ({100 * k / n:.1f} %) | {sum(r['wrong'] for r in rs)}")
if a.json:
    json.dump(rows, open(a.json, "w"), indent=1)

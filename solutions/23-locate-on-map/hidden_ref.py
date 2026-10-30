#!/usr/bin/env python3
"""hidden_ref.py — the reference's results on the check's hidden photos (teacher only): the outcomes check.py's
locate test relies on, and the TileNet hidden-test medians of weight files given on the command line.
    python3 solutions/23-locate-on-map/hidden_ref.py [my_tiles.pt …]"""
import json
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
os.environ.setdefault("NAVERA_LITE_MAP", os.path.expanduser("~/academy-data/osm_sousse.mbtiles"))
sys.path.insert(0, os.path.join(REPO, "solutions", "_navera_lite"))
from navera_lite import geo, locate as L, retrieval as R  # noqa: E402

HID = os.path.join(REPO, "courses", "23-locate-on-map", "hidden")
Q = json.load(open(os.path.join(HID, "queries.json")))


def tilenet_median(path):
    import torch
    torch.set_num_threads(2)
    net = R.load_tilenet(path)
    small = R.SmallTiles()
    views = np.load(os.path.join(HID, "views64.npz"))["views"]
    qe = R.embed_tilenet(net, views)
    errs, prior_e = [], []
    for q, e in zip(Q, qe):
        cand = [tuple(c) for c in q["cand400"]]
        te = R.embed_tilenet(net, np.stack([small.tile(*c) for c in cand]))
        j = int(np.argmax(te @ e))
        c_lat, c_lon = R.tile_centre(*cand[j])
        errs.append(geo.haversine_m(q["lat"], q["lon"], c_lat, c_lon))
        prior_e.append(geo.haversine_m(q["lat"], q["lon"], *q["priors"]["400"]))
    return float(np.median(errs)), float(np.median(prior_e)), errs


if len(sys.argv) > 1 and sys.argv[1] == "dino":
    land = [q for q in Q if q["terrain"] != "sea"]
    d = [geo.haversine_m(q["lat"], q["lon"], q["dino400"][0][2], q["dino400"][0][3]) for q in land]
    p = [geo.haversine_m(q["lat"], q["lon"], *q["priors"]["400"]) for q in land]
    print(f"over land ({len(land)}): DINOv2 {np.median(d):.1f} m, prior {np.median(p):.1f} m")
    sys.exit(0)
if len(sys.argv) > 1:
    for p in sys.argv[1:]:
        m, pm, errs = tilenet_median(p)
        land = [e for e, q in zip(errs, Q) if q["terrain"] != "sea"]
        print(f"{p}: hidden median {m:.1f} m (prior {pm:.1f} m); over land {np.median(land):.1f} m")
    sys.exit(0)

cfg = dict(L.DEFAULTS)
for q in Q:
    img = cv2.imread(os.path.join(HID, q["id"] + ".jpg"))
    meta = {"alt_m": q["alt_m"], "heading_deg": q["heading_deg"], "hfov_deg": q["hfov_deg"]}
    out = [q["id"], q["terrain"]]
    calls = []
    for s in ("40", "400"):
        plat, plon = q["priors"][s]

        def finder(view, lat, lon, r, k):
            calls.append(1)
            return [tuple(c) for c in q["dino400"][:k]]
        la, lo, why = L.locate(img, meta, (plat, plon, float(s)), finder, cfg)
        out.append(f"σ{s}: " + (f"{geo.haversine_m(q['lat'], q['lon'], la, lo):.1f} m" if la is not None else "—")
                   + f" ({why})")
    best = [geo.haversine_m(q["lat"], q["lon"], c[2], c[3]) for c in q["dino400"][:3]]
    out.append(f"dino top3 errors {[round(b) for b in best]}")
    print(" | ".join(out), flush=True)

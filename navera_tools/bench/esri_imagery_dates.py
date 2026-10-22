#!/usr/bin/env python3
"""Capture dates of the Esri World Imagery (NAVERA's evaluation map) under a list of points.

Asks the World_Imagery MapServer's metadata layer 0 (SRC_DATE, SRC_DESC, SRC_RES) for each point
and prints how many points fall on each source image: the map's age against a flight date.

    python3 navera_tools/bench/esri_imagery_dates.py --points lat,lon lat,lon ... [--json]
    python3 navera_tools/bench/esri_imagery_dates.py --csv flight.csv  (columns lat, lon; every --step-th row)
"""
import argparse
import collections
import csv
import json
import urllib.parse
import urllib.request

URL = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/0/query"


def source_at(lat: float, lon: float, zoom: int = 17) -> dict:
    """The top source image drawn at this point and zoom (lowest DrawOrder among those covering the level)."""
    q = urllib.parse.urlencode(dict(geometry=f"{lon},{lat}", geometryType="esriGeometryPoint", inSR=4326,
                                    spatialRel="esriSpatialRelIntersects", outFields="*", returnGeometry="false",
                                    f="json"))
    req = urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "NAVERA-eval/0.5"})
    with urllib.request.urlopen(req, timeout=30) as r:
        feats = [f["attributes"] for f in json.load(r).get("features", [])]
    feats = [f for f in feats if (f.get("MinMapLevel") or 0) <= zoom <= (f.get("MaxMapLevel") or 99)] or feats
    if not feats:
        return {}
    f = min(feats, key=lambda f: f.get("DrawOrder") or 0)
    return dict(date=str(f.get("SRC_DATE")), desc=f.get("SRC_DESC"), res_m=f.get("SRC_RES"),
                release=f.get("ReleaseName"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", nargs="*", default=[])
    ap.add_argument("--csv", default="")
    ap.add_argument("--step", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    pts = [tuple(float(v) for v in p.split(",")) for p in a.points]
    if a.csv:
        rows = list(csv.DictReader(open(a.csv)))
        pts += [(float(r["lat"]), float(r["lon"])) for r in rows[::a.step]]
    c = collections.Counter()
    for lat, lon in pts:
        s = source_at(lat, lon)
        c[(s.get("date"), s.get("desc"), s.get("res_m"))] += 1
    out = [dict(date=d, sensor=s, res_m=r, points=n) for (d, s, r), n in sorted(c.items(), key=lambda kv: str(kv[0][0]))]
    if a.json:
        print(json.dumps(out))
    else:
        for o in out:
            print(f"{o['date']}  {o['sensor']}  {o['res_m']} m  {o['points']} points")


if __name__ == "__main__":
    main()

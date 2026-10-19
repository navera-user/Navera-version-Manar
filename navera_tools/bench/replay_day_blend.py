"""Replay a real day campaign (campaign_day_real.sh csv files) through VisionNavigator: the logged
vision errors on a synthetic circuit truth, output without and with blend_fixes.

    python3 navera_tools/bench/replay_day_blend.py <campaign dir>
"""
import csv, glob, math, os, re, sys, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(ROOT, "day_pkg"), ROOT]
from day_pkg.vision_nav import VisionNavigator, _move, _en
from day_pkg.local_matcher import fix_sigma_m
LAT0, LON0, R = 35.82227, 10.61691, 900.0
MPP = 156543.03392 * math.cos(math.radians(LAT0)) / 2 ** 17

def run(path, blend, below=10**9):
    speed = float(re.search(r"_v(\d+)\.csv", path).group(1))
    rows = list(csv.DictReader(open(path)))
    g = [r for r in rows if r["phase"] == "gps" and r["vis_de"] not in ("", "None")]
    if len(g) < 3:
        return None
    ax = (st.median(float(r["vis_de"]) for r in g), st.median(float(r["vis_dn"]) for r in g))
    w = speed / R
    def truth(t):
        a = w * t
        return _move((LAT0, LON0), R * math.sin(a), R * (1 - math.cos(a))), math.degrees(math.atan2(math.cos(a), math.sin(a)))
    nav = VisionNavigator(max_speed_mps=1.5 * speed, blend_fixes=blend, blend_below_inliers=below)
    raw, out = [], []
    for r in rows:
        t = float(r["t"]); tr, hdg = truth(t)
        if r["phase"] != "lost":
            nav.gps(t, *tr, heading_deg=hdg)
            continue
        if r["vis_de"] not in ("", "None"):
            e = (float(r["vis_de"]) - ax[0], float(r["vis_dn"]) - ax[1])
            z = _move(tr, *e)
            inl = int(float(r["inliers"] or 0))
            res = dict(accepted=True, predicted_lat=z[0], predicted_lon=z[1], inliers=inl,
                       sigma_m=fix_sigma_m(inl, MPP), spread=1.0)
            nav.update(t, res, None, hdg, gps_valid=False)
            raw.append(math.hypot(*e))
        lat, lon, sig, mode = nav.output(t, hdg)
        if lat is not None:
            out.append(math.hypot(*_en((lat, lon), tr)))
    return raw, out

def q(v):
    v = sorted(v); return f"{v[len(v)//2]:5.1f} / {v[int(0.95*(len(v)-1))]:5.1f} / {v[-1]:5.1f}" if v else "-"
d = sys.argv[1]; ALL = {}
print(f"{'run (error m: median / p95 / max)':34s} {'no blend':22s} {'blend all':22s} {'blend <100 inliers':22s} {'blend <50 inliers':22s}")
for p in sorted(glob.glob(os.path.join(d, "*_v*.csv"))):
    a = run(p, False); b = run(p, True); c = run(p, True, 100); dd = run(p, True, 50)
    if a is None: continue
    print(f"{os.path.basename(p)[:-4]:34s} {q(a[1]):22s} {q(b[1]):22s} {q(c[1]):22s} {q(dd[1]):22s}")
    for k, x in zip("abcd", (a, b, c, dd)): ALL.setdefault(k, []).extend(x[1])
print(f"{'ALL':34s}", *(q(ALL[k]) for k in "abcd"))

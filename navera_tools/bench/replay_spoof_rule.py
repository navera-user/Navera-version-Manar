"""Replay day campaign CSVs (screen_flight) through the former bench rule (2 frames > 33.5 m) and the
product's GPS refusal rule (navera_common.GpsCrossCheck, vision sigma max(fix, 30 m)).

    python3 navera_tools/bench/replay_spoof_rule.py <campaign dir> [...]
"""
import csv, glob, math, os, statistics as st, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "day_pkg")]
from navera_common.gps_crosscheck import GpsCrossCheck
from day_pkg.local_matcher import fix_sigma_m
MPP = 156543.03392 * math.cos(math.radians(35.82227)) / 2 ** 17
def run(path):
    R = list(csv.DictReader(open(path)))
    g = [r for r in R if r["phase"] == "gps" and r["vis_de"] not in ("", "None")]
    if len(g) < 5: return None
    ax = (st.median(float(r["vis_de"]) for r in g), st.median(float(r["vis_dn"]) for r in g))
    old_doubt, old_at, new_at, x, ncal = 0, None, None, GpsCrossCheck(), 0
    for r in R:
        if r["phase"] == "lost": break
        t, drift = float(r["t"]), float(r["gps_drift_m"])
        if r["vis_de"] in ("", "None"):
            x.no_reference(t); continue
        ncal += 1
        gap = math.hypot(float(r["vis_de"]) - ax[0] - drift, float(r["vis_dn"]) - ax[1])
        if ncal < 5: continue
        if old_at is None:
            old_doubt = old_doubt + 1 if gap > 3 * math.hypot(5.0, 10.0) else 0
            if old_doubt >= 2: old_at = drift
        if new_at is None:
            sig = max(fix_sigma_m(int(float(r["inliers"] or 0)), MPP), 30.0)
            if x.update(t, gap, 5 * sig + 50, 3 * sig, t) is not None: new_at = drift
    return old_at, new_at
rows = []
for d in sys.argv[1:]:
    for p in sorted(glob.glob(os.path.join(d, "*.csv"))):
        o = run(p)
        if o: rows.append((os.path.basename(p)[:-4], *o))
def fmt(v): return "never" if v is None else f"{v:.0f}"
false_old = [r for r in rows if r[1] is not None and r[1] < 10]
false_new = [r for r in rows if r[2] is not None and r[2] < 10]
print("runs", len(rows), "| false refusals (drift < 10 m): old", len(false_old), "new", len(false_new))
for name, o, n in rows:
    if (o is not None and o < 10) or (n is not None and n < 10) or name.startswith(("clear", "fog_a0.3")):
        print(f"  {name:28s} old refused at {fmt(o):>5} m drift, product rule at {fmt(n):>5} m")
ok = [n for _, o, n in rows if n is not None and n >= 10]; oo = [o for _, o, n in rows if o is not None and o >= 10]
def med(v): return f"{st.median(v):.0f} m (n={len(v)})" if v else "- (n=0)"
print(f"refusal drift, genuine (>= 10 m): old {med(oo)}, product rule {med(ok)}; never refused: "
      f"old {sum(o is None for _, o, _ in rows)}, product rule {sum(n is None for _, _, n in rows)}")

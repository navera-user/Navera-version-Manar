#!/usr/bin/env python3
"""measure.py — measure a recorded flight honestly.

    python3 measure.py /data/academy/29-measuring/flight_target.csv
    python3 measure.py /data/academy/29-measuring/flight_*.csv          # the three flights
    python3 measure.py ~/lessons/28-simulator/flight.csv                # your own flight of lesson 28

For each flight it prints the numbers, saves error_<name>.png and results_<name>.json.
A flight file has one row per second (lesson 28's sim_ctl.py record): the TRUE position
(truth_lat, truth_lon), what NAVERA said (navera_state, navera_source, navera_lat, navera_lon),
the flight phase and the GPS fault (gps_mode: ok / jammed / spoof_jump …).
The confidence intervals come from bootstrap.py (TODO 7–8 there).
"""
import csv
import json
import math
import os
import sys
import warnings

warnings.filterwarnings("ignore", message="Unable to import Axes3D")   # harmless on this Jetson
import matplotlib                          # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt            # noqa: E402

import bootstrap                           # noqa: E402  (your bootstrap.py, same folder)

USABLE = ("FIX", "DEGRADED")
BLOCK = 10                                 # block length (s) for the moving-block bootstrap


def errors(rows):
    """[(t, error_m)] for every row of the flight phase "enroute" where NAVERA gave a position
    (navera_lat is not None): the great-circle distance between NAVERA's position and the truth."""
    out = []
    # TODO 1: for each row r: if r["phase"] == "enroute" and r["navera_lat"] is not None,
    #         append (r["t_s"], haversine_m(truth_lat, truth_lon, navera_lat, navera_lon))
    return out


def percentile(values, p):
    """The p-th percentile (0..100) by the nearest-rank rule of NAVERA's evaluate_session.py:
    sort, then take the value at index round(p/100 * (n-1)) (never beyond the last index)."""
    return None   # TODO 2: s = sorted(values), then one line with round() and min()


def stats(values):
    """Summary of a list of horizontal errors (m):
    {"n", "mean", "rmse", "cep50", "p90", "cep95", "max"}
    rmse = sqrt(mean of the squared errors); cep50 = percentile 50; cep95 = percentile 95."""
    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "rmse": None, "cep50": None, "p90": None, "cep95": None, "max": None}
    return None   # TODO 3: the dict with the 7 keys; use percentile() for cep50, p90 and cep95


def availability(rows, gps_mode=None):
    """The percentage (0..100) of "enroute" rows where NAVERA had a usable position: state FIX or
    DEGRADED and a position (navera_lat is not None). With gps_mode, only the rows where the GPS
    receiver was in that mode (e.g. "jammed"). None when no row is selected."""
    return None   # TODO 4a: select the rows, count the usable ones (usable(r) is below the line)


def longest_gap_s(rows):
    """Continuity: the longest run of CONSECUTIVE "enroute" rows without a usable position, in
    seconds (one row = one second). 0 when NAVERA always had a position."""
    return None   # TODO 4b: walk the en-route rows, count the current run of unusable rows, keep the max


def baseline_errors(rows):
    """The "repeat the last position" baseline during the GPS jam.

    Find the first row where gps_mode == "jammed". The baseline position is the LAST NAVERA
    position given by GPS (navera_source == "GPS", navera_lat not None) BEFORE that row. For every
    jammed "enroute" row, the baseline error is the distance from the truth to that position.
    Returns [(t, error_m)] ([] when there is no jam)."""
    return []     # TODO 5: 1) index of the first jammed row  2) last GPS position before it
    #                3) one (t, error) per jammed "enroute" row


# ---- you don't need to change anything below this line (but you can read it!) ----
NUMBERS = ("t_s", "navera_lat", "navera_lon", "truth_lat", "truth_lon")


def usable(r):
    return r["navera_state"] in USABLE and r["navera_lat"] is not None


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (the same formula as the estimator's _haversine_m)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))


def load(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            for k in NUMBERS:
                r[k] = float(r[k]) if r.get(k) not in (None, "") else None
            rows.append(r)
    return rows


def median_nr(v):
    """The median by the same nearest-rank rule as the tables (so the CI is about that number)."""
    return percentile(v, 50)


def fmt(s):
    if not s or not s.get("n"):
        return "no data"
    try:
        return (f"n={s['n']:3d}  CEP50 {s['cep50']:6.1f}  mean {s['mean']:6.1f}  RMSE {s['rmse']:6.1f}  "
                f"p90 {s['p90']:6.1f}  CEP95 {s['cep95']:6.1f}  max {s['max']:6.1f} m")
    except (KeyError, TypeError, ValueError):
        return f"(stats() incomplete: {s!r})"


def fci(ci, pct=False):
    if not ci:
        return "—"
    k = 100.0 if pct else 1.0
    return f"[{k * ci[0]:.0f}, {k * ci[1]:.0f}]"


def safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except NotImplementedError:
        return None


def main(path):
    name = os.path.splitext(os.path.basename(path))[0]
    rows = load(path)
    errs = errors(rows) or []
    by_t = dict(errs)
    jam_t = [r["t_s"] for r in rows if r["gps_mode"] == "jammed" and r["phase"] == "enroute"]
    gps_t = [r["t_s"] for r in rows if r["gps_mode"] == "ok" and r["navera_source"] == "GPS"
             and r["phase"] == "enroute"]
    base = baseline_errors(rows) or []
    jam_e = [by_t[t] for t in jam_t if t in by_t]
    pairs = [(by_t[t], e) for t, e in base if t in by_t]          # same second: NAVERA and baseline
    k300 = sum(1 for t in jam_t if t in by_t and by_t[t] < 300.0)  # usable AND within 300 m
    w = safe(bootstrap.wilson, k300, len(jam_t)) if jam_t else None
    res = {
        "flight": name, "rows": len(rows),
        "enroute_s": sum(1 for r in rows if r["phase"] == "enroute"), "jam_s": len(jam_t),
        "all": stats([e for _, e in errs]),
        "gps": stats([by_t[t] for t in gps_t if t in by_t]),
        "jam": stats(jam_e),
        "baseline": stats([e for _, e in base]),
        "availability_pct": availability(rows),
        "availability_jam_pct": availability(rows, "jammed"),
        "longest_gap_s": longest_gap_s(rows),
        "jam_within_300": {"k": k300, "n": len(jam_t),
                           "wilson_pct": [100 * w[0], 100 * w[1]] if w else None},
        "ci": {
            "jam_cep50_iid": safe(bootstrap.bootstrap_ci, jam_e, median_nr) if jam_e else None,
            "jam_cep50_block": safe(bootstrap.bootstrap_ci, jam_e, median_nr, block=BLOCK) if jam_e else None,
            "diff_cep50_block": safe(bootstrap.paired_diff_ci, [a for a, _ in pairs], [b for _, b in pairs],
                                     median_nr, block=BLOCK) if pairs else None,
        },
    }
    print(f"{name}: {len(rows)} rows (one per second), {res['enroute_s']} en route, {len(jam_t)} jammed")
    print(f"  NAVERA, whole flight : {fmt(res['all'])}")
    print(f"  NAVERA, GPS in use   : {fmt(res['gps'])}")
    print(f"  NAVERA, GPS jammed   : {fmt(res['jam'])}")
    print(f"  baseline (jammed)    : {fmt(res['baseline'])}   <- 'repeat the last GPS position'")
    a, aj = res["availability_pct"], res["availability_jam_pct"]
    print(f"  availability         : {a if a is None else round(a, 1)} % of the flight, "
          f"{aj if aj is None else round(aj, 1)} % while jammed; longest gap {res['longest_gap_s']} s")
    ci = res["ci"]
    print(f"  95 % CI, jam CEP50   : iid {fci(ci['jam_cep50_iid'])} m   block {BLOCK} s {fci(ci['jam_cep50_block'])} m")
    print(f"  95 % CI, CEP50 NAVERA - baseline (paired, block {BLOCK} s): {fci(ci['diff_cep50_block'])} m")
    print(f"  jammed seconds with a position within 300 m: {k300}/{len(jam_t)}, "
          f"Wilson 95 % {fci(w, pct=True)} %")

    fig, ax = plt.subplots(figsize=(9, 4.2))
    if errs:
        ax.plot([t for t, _ in errs], [e for _, e in errs], ".", ms=3, color="#2563eb", label="NAVERA error")
    # TODO 6: plot the baseline errors too, as a line (color "#dc2626", label "baseline: last GPS position")
    pass                                   # <- replace this line (if base: ax.plot(times, errors, "-", lw=2, ...))
    if jam_t:
        ax.axvspan(min(jam_t), max(jam_t), color="#fde68a", alpha=0.5, label="GPS jammed")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("error vs truth (m)")
    ax.set_title(f"{name} (simulated flight)")
    ax.grid(alpha=0.3)
    ax.legend(loc="center right", fontsize=8)
    fig.tight_layout()
    fig.savefig(f"error_{name}.png", dpi=100)
    plt.close(fig)
    with open(f"results_{name}.json", "w") as f:
        json.dump(res, f, indent=1)
    print(f"  saved error_{name}.png and results_{name}.json\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        main(p)

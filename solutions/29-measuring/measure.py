#!/usr/bin/env python3
"""measure.py — measure a recorded flight honestly.

    python3 measure.py /data/academy/29-measuring/flight_target.csv
    python3 measure.py /data/academy/29-measuring/flight_measured.csv
    python3 measure.py ~/lessons/28-simulator/flight.csv          # your own flight of lesson 28

For each flight it prints the numbers, saves error_<name>.png and results_<name>.json.
A flight file has one row per second (lesson 28's sim_ctl.py record): the TRUE position
(truth_lat, truth_lon), what NAVERA said (navera_state, navera_source, navera_lat, navera_lon),
the flight phase and the GPS fault (gps_mode: ok / jammed / spoof_jump …).
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

USABLE = ("FIX", "DEGRADED")


def errors(rows):
    """[(t, error_m)] for every row of the flight phase "enroute" where NAVERA gave a position
    (navera_lat is not None): the distance between NAVERA's position and the truth."""
    out = []
    for r in rows:
        if r["phase"] == "enroute" and r["navera_lat"] is not None and r["truth_lat"] is not None:
            out.append((r["t_s"], haversine_m(r["truth_lat"], r["truth_lon"], r["navera_lat"], r["navera_lon"])))
    return out


def percentile(values, p):
    """The p-th percentile (0..100) by the nearest-rank rule of NAVERA's evaluate_session.py:
    sort, then take the value at index round(p/100 * (n-1))."""
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))]


def stats(values):
    """{"n", "mean", "median", "p90", "max"} of a list of errors. median = percentile 50."""
    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "median": None, "p90": None, "max": None}
    return {"n": len(values), "mean": sum(values) / len(values), "median": percentile(values, 50),
            "p90": percentile(values, 90), "max": max(values)}


def availability(rows, gps_mode=None):
    """The percentage (0..100) of "enroute" rows where NAVERA had a usable position: state FIX or
    DEGRADED and a position (navera_lat is not None). With gps_mode, only the rows where the GPS
    receiver was in that mode (e.g. "jammed")."""
    sel = [r for r in rows if r["phase"] == "enroute" and (gps_mode is None or r["gps_mode"] == gps_mode)]
    if not sel:
        return None
    ok = sum(1 for r in sel if r["navera_state"] in USABLE and r["navera_lat"] is not None)
    return 100.0 * ok / len(sel)


def baseline_errors(rows):
    """The "repeat the last position" baseline during the GPS jam.

    Find the first row where gps_mode == "jammed". The baseline position is the LAST NAVERA
    position given by GPS (navera_source == "GPS", navera_lat not None) BEFORE that row. For every
    jammed "enroute" row, the baseline error is the distance from the truth to that position.
    Returns [(t, error_m)] ([] when there is no jam)."""
    jam = next((i for i, r in enumerate(rows) if r["gps_mode"] == "jammed"), None)
    if jam is None:
        return []
    last = None
    for r in rows[:jam]:
        if r["navera_source"] == "GPS" and r["navera_lat"] is not None:
            last = (r["navera_lat"], r["navera_lon"])
    if last is None:
        return []
    return [(r["t_s"], haversine_m(r["truth_lat"], r["truth_lon"], *last)) for r in rows
            if r["gps_mode"] == "jammed" and r["phase"] == "enroute" and r["truth_lat"] is not None]


# ---- you don't need to change anything below this line (but you can read it!) ----
NUMBERS = ("t_s", "navera_lat", "navera_lon", "truth_lat", "truth_lon")


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


def fmt(s):
    if not s or not s.get("n"):
        return "no data"
    return (f"n={s['n']:4d}  median {s['median']:7.1f} m  mean {s['mean']:7.1f} m  "
            f"p90 {s['p90']:7.1f} m  max {s['max']:7.1f} m")


def main(path):
    name = os.path.splitext(os.path.basename(path))[0]
    rows = load(path)
    errs = errors(rows) or []
    by_t = dict(errs)
    jam_t = [r["t_s"] for r in rows if r["gps_mode"] == "jammed" and r["phase"] == "enroute"]
    gps_t = [r["t_s"] for r in rows if r["gps_mode"] == "ok" and r["navera_source"] == "GPS"
             and r["phase"] == "enroute"]
    base = baseline_errors(rows) or []
    res = {
        "flight": name, "rows": len(rows),
        "enroute_s": sum(1 for r in rows if r["phase"] == "enroute"),
        "all": stats([e for _, e in errs]),
        "gps": stats([by_t[t] for t in gps_t if t in by_t]),
        "jam": stats([by_t[t] for t in jam_t if t in by_t]),
        "baseline": stats([e for _, e in base]),
        "availability_pct": availability(rows),
        "availability_jam_pct": availability(rows, "jammed"),
    }
    print(f"{name}: {len(rows)} rows (one per second), {res['enroute_s']} en route, {len(jam_t)} jammed")
    print(f"  NAVERA, whole flight : {fmt(res['all'])}")
    print(f"  NAVERA, GPS in use   : {fmt(res['gps'])}")
    print(f"  NAVERA, GPS jammed   : {fmt(res['jam'])}")
    print(f"  baseline (jammed)    : {fmt(res['baseline'])}   <- 'repeat the last GPS position'")
    a, aj = res["availability_pct"], res["availability_jam_pct"]
    print(f"  availability         : {a if a is None else round(a, 1)} % of the flight, "
          f"{aj if aj is None else round(aj, 1)} % while jammed")

    fig, ax = plt.subplots(figsize=(9, 4.2))
    if errs:
        ax.plot([t for t, _ in errs], [e for _, e in errs], ".", ms=3, color="#2563eb", label="NAVERA error")
    # TODO 6: plot the baseline errors too, as a line (color "#dc2626", label "baseline: last GPS position")
    if base:
        ax.plot([t for t, _ in base], [e for _, e in base], "-", lw=2, color="#dc2626",
                label="baseline: last GPS position")
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
    with open(f"results_{name}.json", "w") as f:
        json.dump(res, f, indent=1)
    print(f"  saved error_{name}.png and results_{name}.json")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        main(p)

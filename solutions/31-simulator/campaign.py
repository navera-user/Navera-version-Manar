"""campaign.py — the fault-injection campaign of mission 31: fly the scenarios, measure, compare with the
requirements, PASS or FAIL. You write TODO 9 and TODO 10 (the rest is given).

    python3 campaign.py test               the examples of TODO 9 and TODO 10
    python3 campaign.py one jam            the measurements of ONE run (my_runs/jam.csv)
    python3 campaign.py run                fly every campaign scenario with the course's parts → my_runs/
    python3 campaign.py report             measurements + verdicts of my_runs/ → results.json, out/campaign.png
    python3 campaign.py run --mine         the same flights with YOUR parts (missions 21–30) → my_runs/mine/
    python3 campaign.py report --mine      → results_mine.json, out/campaign_mine.png

A run is a list of rows (dicts) read from my_runs/<name>.csv: "t_s" (mission time, s, a float), "lite_state",
"lite_source" ("" when none), "lite_err_m" (float or None), "guard", "gps_mode", "gps_err_m", "ap_mode", …
(the columns are listed in navera_lite/sim/world.py, COLUMNS). One row every 0.2 s.
"""
import csv
import json
import os
import subprocess
import sys

import numpy as np

import runner_kit as rk

RUNS = ["baseline", "jam", "off", "jump", "drift", "blind", "plane_late"]
# id, run, metric, operator, limit, the requirement in words
REQUIREMENTS = [
    ("R1", "baseline", "error95_m", "<=", 10.0, "GPS healthy: 95 % of NAVERA Lite's errors ≤ 10 m"),
    ("R2", "jam", "switch_s", "<=", 1.0, "GPS jammed: NAVERA Lite stops using the GPS within 1 s"),
    ("R3", "off", "switch_s", "<=", 4.0, "GPS silent: NAVERA Lite stops using the GPS within 4 s"),
    ("R4", "jam", "recover_s", "<=", 5.0, "GPS back after a jam: used again within 5 s"),
    ("R5", "jam", "availability", ">=", 0.95, "GPS jammed: a position (FIX or DEGRADED) ≥ 95 % of the time"),
    ("R6", "jump", "leak_s", "<=", 0.0, "2 km jump: never flies on a GPS more than 100 m wrong"),
    ("R7", "drift", "max_err_m", "<=", 100.0, "slow drift: NAVERA Lite's error stays ≤ 100 m"),
    ("R8", "blind", "failsafe_s", "<=", 10.0, "no source at all: the autopilot's failsafe within 10 s"),
    ("R9", "plane_late", "false_refusal_s", "<=", 0.0, "an honest GPS is never refused"),
]
NUMERIC = ("t_s", "lite_sigma_m", "lite_err_m", "gps_err_m", "vis_err_m", "ap_err_m", "truth_speed_mps")


# ---------------------------------------------------------------------------------------------------------- TODO 9
# 🧰 The first item that passes a test:  next((r for r in rows if r["t_s"] >= 30.0), None)  → the first row at or
# after 30 s, or None when there is none.


def latencies(rows, t0, t1):
    """The two latencies of a GPS fault (lesson §5): the fault starts at t0 and ends at t1 (mission seconds).
    switch_s  = the time of the FIRST row at or after t0 whose "lite_source" is not "gps", minus t0;
    recover_s = the time of the FIRST row at or after t1 whose "lite_source" is "gps", minus t1.
    Either is None when that row does not exist (it never happened), and recover_s is None when t1 is None (the
    fault never ended).

    rows: list of dicts with "t_s" (float) and "lite_source" (str), in time order. Returns (switch_s, recover_s).
    Example: rows at t = 29.8, 30.0, 30.2, 30.4 with sources gps, gps, day, day and then t = 40.0, 40.2, 40.4 with
             day, day, gps → latencies(rows, 30.0, 40.0) → (0.2, 0.4)   (to rounding)
    """
    first = next((r for r in rows if r["t_s"] >= t0 and r["lite_source"] != "gps"), None)
    switch = None if first is None else first["t_s"] - t0
    back = None
    if t1 is not None:
        r = next((r for r in rows if r["t_s"] >= t1 and r["lite_source"] == "gps"), None)
        back = None if r is None else r["t_s"] - t1
    return switch, back


# ---------------------------------------------------------------------------------------------------------- TODO 10
def verdict(value, op, limit):
    """PASS or FAIL for one measured value against one requirement (lesson §5): op is "<=" (the value must be at most
    the limit) or ">=" (at least); any other op: ValueError. A value of None (it was never measured: the event
    never happened) FAILS. Returns (verdict, why): "PASS" or "FAIL", and a short text with the value, the operator
    that holds, and the limit.
    Example: verdict(0.2, "<=", 1.0) → ("PASS", "0.2 <= 1")      verdict(3.4, "<=", 1.0) → ("FAIL", "3.4 > 1")
             verdict(None, "<=", 1.0) → ("FAIL", "never happened")
    """
    if op not in ("<=", ">="):
        raise ValueError(f'op must be "<=" or ">=", got {op!r}')
    if value is None:
        return "FAIL", "never happened"
    ok = value <= limit if op == "<=" else value >= limit
    shown = op if ok else (">" if op == "<=" else "<")
    return ("PASS" if ok else "FAIL"), f"{value:g} {shown} {limit:g}"


# ---- you don't need to change anything below this line ----------------------------------------------------------
def pair(fn, *args):
    """Call YOUR latencies()/verdict(): a crash, a TODO or a wrong shape stops the runner with one plain sentence."""
    v, err = rk.call(sys.modules[__name__], fn, *args)
    if err:
        sys.exit(err)
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        sys.exit(f"{fn}() must return two things, like (0.2, None) or ('PASS', '0.2 <= 1'), but it returned {v!r}")
    return tuple(v)


def load_run(path):
    """The rows of a run CSV, numbers as floats (None when empty)."""
    try:
        with open(path) as f:
            rows = list(csv.DictReader(f))
    except OSError:
        sys.exit(f"{path} is missing: fly it first (python3 campaign.py run, or python3 -m navera_lite.sim.run …)")
    for r in rows:
        for k in NUMERIC:
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
    return rows


def scenario(name):
    """The scenario of a run: campaign/<name>.json, or my_scenario.json when its "name" is <name>."""
    path = os.path.join("campaign", name + ".json")
    if not os.path.exists(path):
        try:
            with open("my_scenario.json") as f:
                mine = json.load(f)
            if isinstance(mine, dict) and mine.get("name") == name:
                return mine
        except (OSError, ValueError):
            pass
    try:
        with open(path) as f:
            return json.load(f)
    except OSError:
        sys.exit(f"{path} is missing (and my_scenario.json is not named {name!r})")


def window(sc):
    """(t0, t1): the first fault's time and the time the GPS (or the faulty sensor) came back, from the scenario."""
    faults = sc.get("faults", [])
    if not faults:
        return None, None
    t0, sensor = faults[0][0], faults[0][1]
    back = [f[0] for f in faults[1:] if f[1] == sensor and f[2] in ("ok", "day")]
    return float(t0), (float(back[0]) if back else None)


def measure(rows, sc):
    """Every metric of one run (lesson §5); TODO 9 gives the two latencies."""
    t0, t1 = window(sc)
    end = rows[-1]["t_s"] if rows else 0.0
    a, b = (t0 if t0 is not None else 0.0), (t1 if t1 is not None else end + 1.0)
    win = [r for r in rows if a <= r["t_s"] < b]
    m = {"t0_s": t0, "t1_s": t1}
    if t0 is not None:
        lat = pair("latencies", rows, t0, t1)
        if not all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)) for v in lat):
            sys.exit(f"latencies() must return two numbers or None, but it returned {lat!r}")
        m["switch_s"], m["recover_s"] = (None if v is None else round(float(v), 3) for v in lat)
    else:
        m["switch_s"] = m["recover_s"] = None
    errs = [r["lite_err_m"] for r in rows if r["lite_err_m"] is not None]
    werrs = [r["lite_err_m"] for r in win if r["lite_err_m"] is not None]
    m["availability"] = round(sum(r["lite_state"] in ("FIX", "DEGRADED") for r in win) / len(win), 4) if win else None
    m["leak_s"] = round(0.2 * sum(r["lite_source"] == "gps" and (r["lite_err_m"] or 0) > 100.0 for r in win), 1)
    m["max_err_m"] = round(max(werrs), 1) if werrs else None
    m["error95_m"] = round(float(np.percentile(errs, 95)), 1) if errs else None
    fs = next((r["t_s"] for r in rows if r["t_s"] >= a and r["ap_mode"] in ("LAND", "HOLD")), None)
    m["failsafe_s"] = None if fs is None else round(fs - a, 1)
    m["false_refusal_s"] = round(0.2 * sum(r["guard"] == "REFUSED" and r["gps_mode"] == "ok"
                                            and r["gps_err_m"] is not None and r["gps_err_m"] < 20.0 for r in rows), 1)
    m["ap_max_err_m"] = round(max(r["ap_err_m"] for r in rows if r["ap_err_m"] is not None), 1)
    return m


def run_dir(mine):
    return os.path.join("my_runs", "mine") if mine else "my_runs"


def fly_all(mine):
    for name in RUNS:
        cmd = [sys.executable, "-m", "navera_lite.sim.run", os.path.join("campaign", name + ".json"), "--quiet"]
        if mine:
            cmd.append("--mine")
        print(f"— {name}", flush=True)
        r = subprocess.run(cmd)
        if r.returncode:
            sys.exit(f"the flight {name} stopped (above): fix that first")


def parts_of(d):
    """The 'part' lines of the runs' event logs: which parts flew (yours or the course's)."""
    out = {}
    for name in RUNS:
        try:
            with open(os.path.join(d, name + "_events.log")) as f:
                for line in f:
                    if line.startswith("# part "):
                        k, v = line[7:].split(":", 1)
                        out.setdefault(k.strip(), v.strip())
        except OSError:
            pass
    return out


def report(mine):
    d = run_dir(mine)
    runs = {name: measure(load_run(os.path.join(d, name + ".csv")), scenario(name)) for name in RUNS}
    print(f"Runs of {d}/ — metrics (lesson §5):")
    print("  run          switch_s  recover_s  avail.  leak_s  max_err_m  error95_m  failsafe_s  false_ref_s")
    f = lambda v: "-" if v is None else f"{v:g}"                      # noqa: E731
    for name, m in runs.items():
        print(f"  {name:12s} {f(m['switch_s']):>8} {f(m['recover_s']):>10} {f(m['availability']):>7} {f(m['leak_s']):>7}"
              f" {f(m['max_err_m']):>10} {f(m['error95_m']):>10} {f(m['failsafe_s']):>11} {f(m['false_refusal_s']):>12}")
    print("\nRequirements:")
    verdicts = []
    for rid, run, metric, op, limit, words in REQUIREMENTS:
        value = runs[run][metric]
        out = pair("verdict", value, op, limit)
        verdicts.append({"id": rid, "run": run, "metric": metric, "op": op, "limit": limit, "value": value,
                         "verdict": out[0], "why": out[1]})
        print(f"  {rid}  {out[0]:4s}  {words:60s} {run}.{metric}: {out[1]}")
    res = {"runs": runs, "verdicts": verdicts, "parts": parts_of(d)}
    name = "results_mine.json" if mine else "results.json"
    with open(name, "w") as fh:
        json.dump(res, fh, indent=1)
    print(f"\nwrote {name}")
    plot(d, runs, "campaign_mine.png" if mine else "campaign.png")


def plot(d, runs, fname):
    plt = rk.plt_or_none()
    if plt is None:
        return
    colours = {"gps": "#1f77b4", "day": "#ff7f0e", "night": "#7f3fbf", "": "#999999"}
    fig, axes = plt.subplots(len(RUNS), 1, figsize=(9, 1.6 * len(RUNS)), sharex=True)
    for ax, name in zip(axes, RUNS):
        rows = load_run(os.path.join(d, name + ".csv"))
        t = [r["t_s"] for r in rows]
        e = [r["lite_err_m"] if r["lite_err_m"] is not None else np.nan for r in rows]
        ax.plot(t, [r["ap_err_m"] if r["ap_err_m"] is not None else np.nan for r in rows], color="#444444", lw=0.8,
                label="autopilot")
        for src, col in colours.items():
            ax.scatter([ti for ti, r in zip(t, rows) if r["lite_source"] == src],
                       [ei for ei, r in zip(e, rows) if r["lite_source"] == src], s=3, color=col, label=src or "none")
        t0, t1 = window(scenario(name))
        if t0 is not None:
            ax.axvspan(t0, t1 if t1 is not None else t[-1], color="#f2d0d0", alpha=0.5, lw=0)
        ax.set_yscale("symlog", linthresh=10)
        ax.set_ylabel(name, rotation=0, ha="right", fontsize=8)
    axes[0].legend(fontsize=7, ncol=5, loc="upper right")
    axes[-1].set_xlabel("mission time (s) — red band: the fault; dots: NAVERA Lite's error by source; line: autopilot")
    fig.tight_layout()
    os.makedirs("out", exist_ok=True)
    fig.savefig(os.path.join("out", fname), dpi=80)
    rk.saved("out/" + fname)


def test():
    me = sys.modules[__name__]
    rows = [{"t_s": t, "lite_source": s} for t, s in
            [(29.8, "gps"), (30.0, "gps"), (30.2, "day"), (30.4, "day"), (40.0, "day"), (40.2, "day"), (40.4, "gps")]]
    cases = [("latencies(<example rows>, 30.0, 40.0)", lambda: latencies(rows, 30.0, 40.0), (0.2, 0.4)),
             ("latencies(<example rows>, 30.0, None)", lambda: latencies(rows, 30.0, None), (0.2, None)),
             ("latencies(<only gps>, 30.0, 40.0)", lambda: latencies([dict(r, lite_source="gps") for r in rows], 30.0,
                                                                     40.0), (None, 0.0)),
             ('verdict(0.2, "<=", 1.0)', lambda: verdict(0.2, "<=", 1.0), ("PASS", "0.2 <= 1")),
             ('verdict(3.4, "<=", 1.0)', lambda: verdict(3.4, "<=", 1.0), ("FAIL", "3.4 > 1")),
             ('verdict(0.9, ">=", 0.95)', lambda: verdict(0.9, ">=", 0.95), ("FAIL", "0.9 < 0.95")),
             ('verdict(None, "<=", 1.0)', lambda: verdict(None, "<=", 1.0), ("FAIL", "never happened"))]
    for what, fn, want in cases:
        name = what.split("(")[0]
        if rk.is_stub(getattr(me, name)):
            print(f"✘ {what}: {name}() is still a TODO")
            continue
        try:
            got = fn()
        except Exception as e:                                    # noqa: BLE001 — one plain sentence
            print(f"✘ {what}: {type(e).__name__}: {e}")
            continue
        ok = isinstance(got, tuple) and len(got) == 2 and all(
            (g is None and w is None) or (isinstance(w, float) and isinstance(g, (int, float)) and abs(g - w) < 1e-6)
            or g == w for g, w in zip(got, want))
        print(f"{'✔' if ok else '✘'} {what} → {got!r}" + ("" if ok else f"   (expected {want!r})"))


def main():
    args = sys.argv[1:]
    mode = args[0] if args else ""
    mine = "--mine" in args
    if mode == "test":
        test()
    elif mode == "one" and len(args) > 1:
        m = measure(load_run(os.path.join(run_dir(mine), args[1] + ".csv")), scenario(args[1]))
        for k, v in m.items():
            print(f"  {k:16s} {v}")
    elif mode == "run":
        fly_all(mine)
    elif mode == "report":
        report(mine)
    else:
        sys.exit(__doc__.split("\n\n")[1])


if __name__ == "__main__":
    main()

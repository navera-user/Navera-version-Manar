"""run_logbook.py — runs YOUR functions of navera_lite/logbook.py on the campaign, and draws them.

    python3 run_logbook.py naive      Step 0: the campaign analysed with no cleaning at all (no code needed)
    python3 run_logbook.py test       check each function on its docstring example
    python3 run_logbook.py clean      TODO 1 on the campaign                               (Step 2)
    python3 run_logbook.py motion     TODO 2: time steps, distances and speeds per flight  (Step 3)
    python3 run_logbook.py outages    TODO 3–4: every GPS outage, and a picture            (Steps 4–5)
    python3 run_logbook.py shares     TODO 5: what the judge reported, per flight          (Step 5)
    python3 run_logbook.py schedule   the outages against the jammer's schedule             (Step 6)
    python3 run_logbook.py noise      TODO 6: how noisy each source's speed is             (Step 7)
    python3 run_logbook.py units      TODO 7: the unit detector on the campaign            (Step 8)
    python3 run_logbook.py report     everything: results.json                             (Step 9)

From "schedule" on, the corrections you write in answers.py (CLOCK_FIX_S, SPEED_FACTOR) are applied
before any statistic. The raw files in /data/academy/04-python-data/ are read only: they never change.
Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import json
import os
import sys

import runner_kit as rk

DATA = os.environ.get("LOGBOOK_DATA", "/data/academy/04-python-data")
CAMPAIGN = os.path.join(DATA, "campaign.csv")
SHEET = os.path.join(DATA, "flight_sheet.csv")

lb = rk.load_student("navera_lite.logbook")
import numpy as np      # noqa: E402  (after the student's module: a broken logbook.py is reported first)
import pandas as pd     # noqa: E402

pd.set_option("display.width", 130)
pd.set_option("display.max_columns", 20)


def raw_log():
    if not os.path.exists(CAMPAIGN):
        sys.exit(f"{CAMPAIGN} is missing: the course data is not mounted. Tell your teacher.")
    return lb.load_log(CAMPAIGN)


def corrections():
    """CLOCK_FIX_S and SPEED_FACTOR from answers.py (empty dicts if not written yet)."""
    a = rk.load_student("answers")
    clock, speed = getattr(a, "CLOCK_FIX_S", {}), getattr(a, "SPEED_FACTOR", {})
    for name, d in (("CLOCK_FIX_S", clock), ("SPEED_FACTOR", speed)):
        if not isinstance(d, dict):
            sys.exit(f"{name} in answers.py must be a dict like {{\"flight_x\": 1.5}}, not {d!r}")
        for k, v in d.items():
            if not isinstance(k, str) or isinstance(v, bool) or not isinstance(v, (int, float)):
                sys.exit(f"{name} in answers.py: {k!r}: {v!r} — keys are flight ids in quotes, values numbers")
    return clock, speed


def need_df(fn, *args, columns=()):
    v = rk.need_ok(lb, fn, *args)
    if not isinstance(v, pd.DataFrame):
        sys.exit(f"{fn}() must return a pandas DataFrame, but it returned a {type(v).__name__}.")
    missing = [c for c in columns if c not in v.columns]
    if missing:
        sys.exit(f"{fn}() returned a DataFrame without the column(s) {missing} — check the names in its docstring.")
    return v


def cleaned():
    v = rk.need_ok(lb, "clean", raw_log())
    if not (isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], pd.DataFrame) and isinstance(v[1], dict)):
        sys.exit(f"clean() must return TWO things, (clean_df, removed): a DataFrame and a dict — it returned "
                 f"{type(v).__name__}{' of length ' + str(len(v)) if isinstance(v, tuple) else ''}.")
    return v


def with_motion(fixed=False):
    df, _ = cleaned()
    if fixed:
        clock, speed = corrections()
        df = lb.apply_corrections(df, clock, speed)
    return need_df("add_motion", df, columns=("dt_s", "step_m", "pos_speed_mps"))


def hms(s):
    s = int(round(s)) % 86400
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def sec_of_day(text):
    h, m, s = (int(x) for x in text.split(":"))
    return 3600 * h + 60 * m + s


# ------------------------------------------------------------------------------------------ scenarios
def naive():
    """Step 0: what the raw log says when nobody cleans it (written for you, no TODO)."""
    raw = raw_log()
    step = lb.haversine_m(raw["lat"].shift(), raw["lon"].shift(), raw["lat"], raw["lon"])
    speed = step / (raw["time_s"] - raw["time_s"].shift())
    t = pd.DataFrame({"flight_id": raw["flight_id"], "step_km": step / 1000, "speed": speed, "alt": raw["alt_m"]})
    table = t.groupby("flight_id").agg(distance_km=("step_km", "sum"), top_speed_mps=("speed", "max"),
                                       max_alt_m=("alt", "max"))
    print("The campaign, analysed with NO cleaning (one row after the other, whatever the flight):\n")
    print(table.round(1).to_string())
    print(f"\nlogged speed_mps, highest value: {raw['speed_mps'].max():.1f} m/s")
    print("\nA small drone, flying 10 to 15 minutes per flight. Does any of this look possible to you?")
    plt = rk.plt_or_none()
    if plt:
        os.makedirs("out", exist_ok=True)
        f = raw[raw["flight_id"] == "monastir_coast"]
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.plot(f["lon"], f["lat"], "-", color="#0b6e8a", lw=1)
        ax.plot(f["lon"], f["lat"], ".", color="#0b6e8a", ms=3)
        ax.annotate("the flight area\n(Monastir, Tunisia)", (10.83, 35.77), xytext=(1.0, 31.0),
                    arrowprops=dict(arrowstyle="->"))
        ax.annotate("and this?", (0.0, 0.0), xytext=(3.0, 2.0), arrowprops=dict(arrowstyle="->"))
        ax.set_xlabel("longitude (°)")
        ax.set_ylabel("latitude (°)")
        ax.set_title("monastir_coast, raw log")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig("out/naive.png", dpi=90)
        plt.close(fig)
        rk.saved("out/naive.png")


def test():
    """Each function on the example of its docstring, plus the traps the checker also tests."""
    def show(name, got, err, ok, want):
        if err:
            print(f"✘ {name}: {err}")
        elif ok:
            print(f"✔ {name}: {got}")
        else:
            print(f"✘ {name}: got {got}, expected {want}")

    seven = pd.DataFrame({"flight_id": ["b", "a", "a", "a", "a", "a", "b"], "time_s": [0, 4, 0, 2, 2, 4, 2],
                          "lat": [36.0, 35.0, 35.0, 0.0, 0.0, 35.0, np.nan], "lon": [11.0, 10.0, 10.0, 0.0, 0.0, 10.0, np.nan],
                          "alt_m": [50.0, 60.0, 55.0, 58.0, 58.0, 60.0, 52.0]})        # rows 3-4 and 1-5: written twice
    want = {"duplicates": 2, "null_island": 1, "bad_altitude": 0}
    v, err = rk.call(lb, "clean", seven)
    ok = False
    if not err and not (isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], pd.DataFrame)):
        v = f"a {type(v).__name__}, not two things: return (clean_df, removed)"
    elif not err:
        ok = len(v[0]) == 4 and isinstance(v[1], dict) and {k: int(x) for k, x in v[1].items()} == want \
            and v[0]["lat"].isna().sum() == 1 and list(v[0].index) == [0, 1, 2, 3]
        v = f"{len(v[0])} rows ({int(v[0]['lat'].isna().sum())} with an empty position), index {list(v[0].index)}, {v[1]}"
    show("clean(7-row log, the (0, 0) row written twice)", v, err, ok,
         "4 rows (1 with an empty position), index [0, 1, 2, 3], {'duplicates': 2, 'null_island': 1, 'bad_altitude': 0}")

    d = pd.DataFrame({"flight_id": ["f1", "f1", "f1", "f2"], "time_s": [0, 2, 6, 0], "lat": [35.0, 35.0002, 35.0004, 36.0],
                      "lon": [10.0, 10.0, 10.0, 11.0]})
    v, err = rk.call(lb, "add_motion", d)
    ok = False
    if not err and isinstance(v, pd.DataFrame) and {"dt_s", "step_m", "pos_speed_mps"} <= set(v.columns):
        r2 = lambda col: [round(float(x), 2) if x == x else "NaN" for x in v[col]]
        ok = r2("dt_s") == ["NaN", 2.0, 4.0, "NaN"] and r2("pos_speed_mps") == ["NaN", 11.12, 5.56, "NaN"] \
            and r2("step_m")[3] == "NaN"
        v = f"dt_s {r2('dt_s')}, step_m {r2('step_m')}, pos_speed_mps {r2('pos_speed_mps')}"
    elif not err and isinstance(v, pd.DataFrame):
        v = f"a DataFrame without dt_s, step_m and pos_speed_mps (columns: {list(v.columns)})"
    show("add_motion(f1: 0, 2, 6 s; f2: 0 s)", v, err, ok,
         "dt_s [NaN, 2.0, 4.0, NaN], step_m [NaN, 22.24, 22.24, NaN], pos_speed_mps [NaN, 11.12, 5.56, NaN]")

    for arg, want in (([1, 0, 0, 1, 0], [(1, 3), (4, 5)]), ([1, 1], []), ([0, 0, 1], [(0, 2)])):
        v, err = rk.call(lb, "outage_runs", arg)
        ok = False
        try:
            ok = not err and isinstance(v, list) and [tuple(int(i) for i in p) for p in v] == want
        except (TypeError, ValueError):
            pass
        show(f"outage_runs({arg})", v, err, ok, want)

    t = pd.DataFrame({"flight_id": ["a"] * 4 + ["b"] * 2, "time_s": [0, 2, 4, 6, 0, 2], "gps_valid": [1, 0, 0, 1, 1, 1]})
    v, err = rk.call(lb, "outage_table", t)
    ok = False
    if not err and isinstance(v, pd.DataFrame):
        try:
            ok = (list(v.index) == ["a", "b"] and float(v.loc["a", "longest_s"]) == 4.0
                  and float(v.loc["b", "total_s"]) == 0.0 and int(v.loc["a", "n_outages"]) == 1)
        except (KeyError, TypeError, ValueError):
            ok = False
        v = v.to_dict(orient="index")
    show("outage_table(a: 1 0 0 1, b: 1 1)", v, err, ok, "a: 1, 4.0, 4.0; b: 0, 0.0, 0.0")

    s = pd.DataFrame({"flight_id": ["a"] * 4, "state": ["FIX", "FIX", "FIX", "DEGRADED"]})
    v, err = rk.call(lb, "state_shares", s)
    want = {"a": {"FIX": 75.0, "DEGRADED": 25.0, "NO_FIX": 0.0}}
    ok = v == want and all(type(x) is float for row in v.values() for x in row.values())
    if not err and v == want and not ok:
        v = f"{v} — the right numbers, but not plain Python floats: write float(x)"
    show("state_shares(FIX FIX FIX DEGRADED)", v, err, ok, want)

    e = np.array([-1.0, 0.0, 0.0, 1.0, 1.0, 2.0, 30.0])
    n = pd.DataFrame({"source": ["gps"] * 7, "pos_speed_mps": e + 5.0, "speed_mps": [5.0] * 7})
    v, err = rk.call(lb, "noise_by_source", n)
    ok = False
    if not err and isinstance(v, pd.DataFrame):
        try:
            r = v.loc["gps"]
            ok = all(abs(float(r[k]) - w) < 0.01 for k, w in (("n", 7), ("mean_mps", 4.714), ("std_mps", 11.19),
                     ("median_mps", 1.0), ("mad_sigma_mps", 1.483), ("p95_abs_mps", 21.6)))
            v = {k: round(float(x), 3) for k, x in r.items()}
        except (KeyError, TypeError, ValueError) as ex:
            v = f"a DataFrame without the row 'gps' or a column ({ex})"
    show("noise_by_source(errors −1 0 0 1 1 2 30)", v, err, ok,
         "n 7, mean 4.714, std 11.19, median 1.0, mad_sigma 1.483, p95_abs 21.6")

    u = pd.DataFrame({"flight_id": ["a"] * 2 + ["b"] * 2 + ["c"] * 2, "speed_mps": [19.5, 19.5, 10.1, 10.1, 5.0, 5.0],
                      "pos_speed_mps": [10.0] * 6})
    v, err = rk.call(lb, "unit_suspects", u)
    show("unit_suspects(ratios 1.95, 1.01, 0.5)", v, err, v == {"a": "kn", "c": "?"}, {"a": "kn", "c": "?"})


def clean_step():
    raw = raw_log()
    df, removed = cleaned()
    print(f"raw log: {len(raw)} rows   →   clean log: {len(df)} rows")
    print(f"removed by each rule: {removed}")
    print(f"rows with an empty position kept (NO_FIX moments): {int(df['lat'].isna().sum())}")
    print(f"index starts {list(df.index[:3])}, flights in order: {list(dict.fromkeys(df['flight_id']))}")
    if len(df) + sum(int(x) for x in removed.values()) != len(raw):
        print(f"\n⚠ {len(raw)} raw rows, but {len(df)} kept + {sum(removed.values())} removed ≠ {len(raw)}: "
              "a rule removes rows it does not count, or counts rows it does not remove.")


def motion_step():
    df = with_motion()
    first = df.groupby("flight_id").head(2)
    print("The first two rows of each flight:\n")
    print(first[["flight_id", "time_s", "dt_s", "step_m", "pos_speed_mps", "speed_mps", "source"]].round(2).to_string())
    print("\nFastest step of each flight (speed from the positions):\n")
    i = df.groupby("flight_id")["pos_speed_mps"].idxmax()
    print(df.loc[i, ["flight_id", "time_s", "step_m", "pos_speed_mps", "speed_mps", "source"]].round(1).to_string(index=False))


def outages_step():
    df = with_motion()
    print("outage_runs on each flight's gps_valid (row numbers inside the flight):")
    for fid, f in df.groupby("flight_id"):
        print(f"  {fid:15s} {rk.need_ok(lb, 'outage_runs', f['gps_valid'].to_numpy())}")
    v, err = rk.call(lb, "outage_table", df)
    if err:
        print(f"\noutage_table: {err}")
        return
    print("\noutage_table:\n")
    print(v.to_string())
    plt = rk.plt_or_none()
    if plt:
        os.makedirs("out", exist_ok=True)
        fig, axes = plt.subplots(4, 1, figsize=(9, 9))
        for ax, (fid, f) in zip(axes, df.groupby("flight_id")):
            t = (f["time_s"] - f["time_s"].iloc[0]).to_numpy(dtype=float)
            ax.plot(t, f["alt_m"], color="#0b6e8a", lw=1.2)
            for k, (a, b) in enumerate(rk.need_ok(lb, "outage_runs", f["gps_valid"].to_numpy())):
                ax.axvspan(t[a], t[b - 1] + lb.DT_S, color="#e8706a", alpha=0.3, label="GPS outage" if k == 0 else None)
            ax.set_title(fid, fontsize=10, loc="left")
            ax.set_ylabel("altitude (m)")
            if ax.get_legend_handles_labels()[0]:
                ax.legend(loc="lower center", fontsize=8)
        axes[-1].set_xlabel("time since the first row of the flight (s)")
        fig.tight_layout()
        fig.savefig("out/outages.png", dpi=90)
        plt.close(fig)
        rk.saved("out/outages.png")


def shares_step():
    df = with_motion()
    v = rk.need_ok(lb, "state_shares", df)
    if not isinstance(v, dict):
        sys.exit(f"state_shares() must return a dict, but it returned a {type(v).__name__}.")
    print("What the judge reported, % of each flight's rows:\n")
    print(f"  {'flight':15s} {'FIX':>7s} {'DEGRADED':>9s} {'NO_FIX':>7s}")
    for fid, row in sorted(v.items()):
        try:
            print(f"  {fid:15s} {row['FIX']:7.1f} {row['DEGRADED']:9.1f} {row['NO_FIX']:7.1f}")
        except (KeyError, TypeError):
            sys.exit(f"state_shares(): the value for {fid!r} must be a dict with the keys FIX, DEGRADED, NO_FIX; got {row!r}")


def schedule_rows(df, sheet):
    """(rows, windows without outage): every outage in UTC, planned (inside a jamming window) or not."""
    rows, seen = [], set()
    for fid, f in df.groupby("flight_id"):
        t = f["time_s"].to_numpy(dtype=float)
        s = sheet.loc[fid] if fid in sheet.index else None
        for a, b in rk.need_ok(lb, "outage_runs", f["gps_valid"].to_numpy()):
            t0, t1 = t[a], t[b - 1] + lb.DT_S
            planned = False
            if s is not None:
                j0, j1 = sec_of_day(s["jam_start_utc"]), sec_of_day(s["jam_end_utc"])
                planned = t0 < j1 and t1 > j0
                if planned:
                    seen.add(fid)
            rows.append((fid, t0, t1, planned))
    lonely = [fid for fid in sheet.index if fid not in seen]
    return rows, lonely


def schedule_step():
    clock, speed = corrections()
    df, _ = cleaned()
    df = lb.apply_corrections(df, clock, speed)
    sheet = pd.read_csv(SHEET).set_index("flight_id")
    print(f"corrections from answers.py: CLOCK_FIX_S = {clock}   SPEED_FACTOR = {speed}\n")
    rows, lonely = schedule_rows(df, sheet)
    print("Every GPS outage of the log (clock as corrected), against the jammer's schedule (UTC):\n")
    for fid, t0, t1, planned in rows:
        print(f"  {fid:15s} {hms(t0)} → {hms(t1)}  ({t1 - t0:5.0f} s)   "
              + ("planned: the jammer was on" if planned else "UNPLANNED: no jamming at that time"))
    for fid in lonely:
        s = sheet.loc[fid]
        print(f"  {fid:15s} jammer on {s['jam_start_utc']} → {s['jam_end_utc']}, but NO outage in the log then")
    if clock or speed:
        print("\nYour corrections, checked against the sheet and the positions:")
        m = need_df("add_motion", df, columns=("pos_speed_mps",))
        for fid in clock:
            if fid in sheet.index:
                first = df.loc[df["flight_id"] == fid, "time_s"].min()
                print(f"  {fid:15s} first row now {hms(first)} UTC, take-off on the sheet {sheet.loc[fid, 'takeoff_utc']}")
            else:
                print(f"  {fid!r} is not a flight of the sheet: check the spelling")
        for fid in speed:
            f = m[m["flight_id"] == fid]
            if len(f):
                print(f"  {fid:15s} corrected logged speed / speed from positions (medians): "
                      f"{f['speed_mps'].median() / f['pos_speed_mps'].median():.2f}")
            else:
                print(f"  {fid!r} is not a flight of the log: check the spelling")


def noise_step():
    for fixed in (False, True):
        df = with_motion(fixed)
        v = need_df("noise_by_source", df, columns=("n", "std_mps", "mad_sigma_mps"))
        print("WITH your corrections (answers.py)" if fixed else "WITHOUT any correction", "— speed error per source:\n")
        print(v.round(3).to_string(), "\n")
    plt = rk.plt_or_none()
    if plt:
        os.makedirs("out", exist_ok=True)
        err = (df["pos_speed_mps"] - df["speed_mps"])
        fig, ax = plt.subplots(figsize=(8, 4))
        bins = np.linspace(-20, 20, 81)
        for src, colour in (("gps", "#0b6e8a"), ("day", "#d17a00")):
            e = err[df["source"] == src].dropna()
            out = int((e.abs() > 20).sum())
            ax.hist(e.clip(-20, 20), bins=bins, alpha=0.6, color=colour, density=True,
                    label=f"{src} ({len(e)} errors, {out} beyond ±20 m/s, piled at the edges)")
        ax.set_xlabel("speed from positions − logged speed (m/s), with your corrections")
        ax.set_ylabel("density")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig("out/noise.png", dpi=90)
        plt.close(fig)
        rk.saved("out/noise.png")


def num(key, v):
    return int(v) if key in ("n", "n_outages") else float(v)


def report_step():
    raw = raw_log()
    df, removed = cleaned()
    clock, speed = corrections()
    df = need_df("add_motion", lb.apply_corrections(df, clock, speed), columns=("pos_speed_mps",))
    out = need_df("outage_table", df, columns=("n_outages", "longest_s", "total_s"))
    shares = rk.need_ok(lb, "state_shares", df)
    noise = need_df("noise_by_source", df, columns=("n", "mean_mps", "std_mps", "median_mps", "mad_sigma_mps",
                                                    "p95_abs_mps"))
    sheet = pd.read_csv(SHEET).set_index("flight_id")
    rows, lonely = schedule_rows(df, sheet)
    worst = out["longest_s"].idxmax()
    results = {
        "rows_raw": int(len(raw)), "removed": {k: int(v) for k, v in removed.items()}, "rows_clean": int(len(df)),
        "corrections": {"clock_fix_s": clock, "speed_factor": speed},
        "outages": {fid: {k: num(k, v) for k, v in r.items()} for fid, r in out.to_dict(orient="index").items()},
        "longest_outage": {"flight_id": str(worst), "duration_s": float(out.loc[worst, "longest_s"])},
        "unplanned_outages": [{"flight_id": f, "start_utc": hms(a), "end_utc": hms(b)} for f, a, b, p in rows if not p],
        "jamming_without_outage": lonely,
        "state_shares": shares,
        "noise": {src: {k: num(k, v) for k, v in r.items()} for src, r in noise.to_dict(orient="index").items()},
    }
    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"→ results.json written ({len(results)} sections: {', '.join(results)}).")
    print("Open it in the 📝 Code tab, or: python3 -m json.tool results.json. Pictures: `outages` and `noise` (out/).")


def units_step():
    df = with_motion()
    v = rk.need_ok(lb, "unit_suspects", df)
    if not isinstance(v, dict):
        sys.exit(f"unit_suspects() must return a dict, but it returned a {type(v).__name__}.")
    print("unit_suspects on the campaign (raw speeds, before your corrections):", v)


MODES = {"naive": naive, "test": test, "clean": clean_step, "motion": motion_step, "outages": outages_step,
         "shares": shares_step, "schedule": schedule_step, "noise": noise_step, "units": units_step, "report": report_step}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        print(__doc__)
        sys.exit(0 if not mode else 1)
    MODES[mode]()

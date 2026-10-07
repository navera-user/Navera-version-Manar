import contextlib
import io
import json
import math
import os
import re
import tempfile
import warnings

from academy_check import CheckFailed, Checker, load_student, need, sh

warnings.filterwarnings("ignore")
c = Checker()
LESSON = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_CSV = os.path.join(LESSON, "files", "campaign.csv")       # the untouched data
FLIGHTS = ["barr_al_hikman", "muscat_coast", "nizwa_foothills", "sohar_port"]

# Expected values, computed once from the deterministic campaign.csv.
SUMMARY = {   # rows, duration_s, distance_km, max_alt_m, mean_speed_mps, min_battery_pct
    "barr_al_hikman": (361, 720, 13.0354, 151.5, 18.0526, 54.9),
    "muscat_coast": (341, 682, 7.80654, 101.5, 11.2099, 54.9),
    "nizwa_foothills": (487, 974, 9.05311, 251.5, 8.83621, 55.0),
    "sohar_port": (362, 722, 8.78555, 121.5, 12.9319, 54.8),
}
OUTAGES = {"barr_al_hikman": (1, 16.0, 16.0), "muscat_coast": (1, 60.0, 60.0),
           "nizwa_foothills": (1, 416.0, 416.0), "sohar_port": (2, 100.0, 160.0)}
SHARES = {"barr_al_hikman": (97.7839, 2.21607, 0.0), "muscat_coast": (91.2023, 8.79765, 0.0),
          "nizwa_foothills": (57.2895, 40.4518, 2.25873), "sohar_port": (77.9006, 16.5746, 5.52486)}
SPEED_ERR = {"gps": (0.769304, 2.27378), "day_vision": (3.25246, 7.79998)}


def fa(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        m = load_student("flight_analysis.py")
    return need(m, *names)


def call(fn, *args, **kw):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args, **kw)
    except NotImplementedError as e:
        raise CheckFailed(f"{fn.__name__}() is not written yet ({e})")


def pd_():
    import pandas as pd
    return pd


def raw():
    return pd_().read_csv(ORIGINAL_CSV)


def prepared():
    """clean() + add_motion() of the student, on the original data."""
    clean, add_motion = fa("clean", "add_motion")
    return call(add_motion, call(clean, raw()))


def frame(obj, what):
    c.ok(isinstance(obj, pd_().DataFrame), f"{what} returned {type(obj).__name__}, expected a DataFrame")
    return obj


def small():
    import numpy as np
    return pd_().DataFrame({
        "flight_id": ["b", "a", "a", "a", "b", "a"], "time_s": [0, 0, 2, 4, 2, 6],
        "lat": [20.0, 23.0, 23.0001, np.nan, 20.0, 23.0001], "lon": [58.0, 58.0, 58.0, np.nan, 58.0001, 58.0]})


# ---------------------------------------------------------------- Part A
@c.test("TODO 1: clean() removes duplicates and glitches, keeps NO_FIX rows, sorts and renumbers",
        hint="drop_duplicates(); a mask for lat == 0 & lon == 0 and one for alt_m outside the limits; "
             "keep the rows NOT in them (~); sort_values([...]); reset_index(drop=True).")
def _():
    (clean,) = fa("clean")
    r = raw()
    d = frame(call(clean, r), "clean(df)")
    c.ok(len(r) == 1556, "clean() changed the DataFrame it received: build and return a NEW one")
    c.eq(len(d), 1551, "the number of rows after clean()")
    c.ok(not d.duplicated().any(), "duplicate rows are still there")
    c.ok(not ((d["lat"] == 0) & (d["lon"] == 0)).any(), "the (0, 0) glitch row is still there")
    c.ok(d["alt_m"].max() < 5000, "the impossible altitude is still there")
    c.eq(int(d["lat"].isna().sum()), 31, "the number of rows with an empty position (NO_FIX rows must be kept)")
    c.eq(list(d.index[:3]), [0, 1, 2], "the first index values (renumber with reset_index(drop=True))")
    c.ok(list(d["flight_id"]) == sorted(d["flight_id"]), "the rows are not sorted by flight_id")
    for fid, f in d.groupby("flight_id"):
        c.ok(f["time_s"].is_monotonic_increasing, f"flight {fid} is not sorted by time_s")


# ---------------------------------------------------------------- Part B
@c.test("TODO 2: haversine_m() — numbers, arrays, NaN",
        hint="np.radians / np.sin / np.cos / np.arcsin / np.sqrt work element by element; math.* refuse arrays.")
def _():
    import numpy as np
    (h,) = fa("haversine_m")
    c.near(call(h, 23.588, 58.383, 22.933, 57.533), 113333.49, 0.5, "haversine_m(Muscat, Nizwa)")
    r = call(h, np.array([23.588, 24.347]), np.array([58.383, 56.709]), 23.588, 58.383)
    c.ok(np.shape(r) == (2,), f"with arrays of 2 points the result should have shape (2,), got {np.shape(r)}")
    c.near(r[0], 0.0, 1e-6, "distance of Muscat to itself")
    c.near(r[1], 189875.29, 0.5, "haversine_m(Sohar, Muscat)")
    c.ok(math.isnan(float(call(h, float("nan"), 58.0, 23.0, 58.0))), "a NaN latitude should give NaN")


@c.test("TODO 3: add_motion() — dt_s, step_m, gs_mps within each flight",
        hint="Work on df.copy(); g = out.groupby('flight_id'); the previous value in the same flight is "
             "g['lat'].shift(); step_m = haversine_m(previous, current); gs = step / dt.")
def _():
    (add_motion,) = fa("add_motion")
    s = small()
    out = frame(call(add_motion, s), "add_motion(df)")
    c.ok("dt_s" not in s.columns, "add_motion() changed its input: work on a copy (df.copy())")
    for col in ("dt_s", "step_m", "gs_mps"):
        c.ok(col in out.columns, f"add_motion() did not add the column {col}")
    c.ok(math.isnan(out.loc[0, "step_m"]) and math.isnan(out.loc[1, "step_m"]),
         "the FIRST row of each flight must have step_m = NaN (no previous row in that flight)")
    c.near(out.loc[2, "dt_s"], 2.0, 1e-9, "dt_s of row 2")
    c.near(out.loc[2, "step_m"], 11.1195, 1e-3, "step_m of row 2 (0.0001° north)")
    c.near(out.loc[4, "step_m"], 10.4489, 1e-3, "step_m of row 4 (flight b, 0.0001° east) — previous row of the SAME flight")
    c.near(out.loc[4, "gs_mps"], 5.22445, 1e-3, "gs_mps of row 4")
    c.ok(math.isnan(out.loc[3, "step_m"]) and math.isnan(out.loc[5, "step_m"]),
         "a step to or from an empty position must be NaN")


@c.test("TODO 4: flight_summary() per flight (groupby + agg)",
        hint="One groupby('flight_id').agg(...) with named aggregations; duration = last − first time; "
             "distance_km = sum of step_m / 1000 (sum skips NaN); the mean of speed_mps skips empty cells.")
def _():
    import numpy as np
    pd = pd_()
    (fs,) = fa("flight_summary")
    tiny = pd.DataFrame({"flight_id": ["x", "x", "x", "y"], "time_s": [10, 12, 16, 0],
                         "step_m": [np.nan, 20.0, 30.0, np.nan], "alt_m": [5.0, 50.0, 40.0, 1.0],
                         "speed_mps": [1.0, np.nan, 3.0, 2.0], "battery_pct": [90.0, 80.0, np.nan, 99.0]})
    t = frame(call(fs, tiny), "flight_summary(df)")
    for col, want in (("rows", 3), ("duration_s", 6), ("distance_km", 0.05), ("max_alt_m", 50.0),
                      ("mean_speed_mps", 2.0), ("min_battery_pct", 80.0)):
        c.ok(col in t.columns, f"flight_summary() has no column {col}")
        c.near(t.loc["x", col], want, 1e-9, f"{col} of a small 3-row flight (with empty cells)")
    s = frame(call(fs, prepared()), "flight_summary(df)")
    c.eq(sorted(s.index), FLIGHTS, "the index of flight_summary() (one row per flight_id)")
    cols = ["rows", "duration_s", "distance_km", "max_alt_m", "mean_speed_mps", "min_battery_pct"]
    for col in cols:
        c.ok(col in s.columns, f"flight_summary() has no column {col}")
    for fid, want in SUMMARY.items():
        for col, w in zip(cols, want):
            c.near(s.loc[fid, col], w, 1e-3, f"{col} of {fid}")


# ---------------------------------------------------------------- Part C
@c.test("TODO 5: outage_runs() — runs of 0 as (start, stop) pairs",
        hint="Pad the 0/1 'lost' array with a 0 at both ends; np.diff is +1 at a start and −1 at a stop.")
def _():
    (runs,) = fa("outage_runs")
    for seq, want in (([1, 0, 0, 1, 0], [(1, 3), (4, 5)]), ([1, 1, 1], []), ([0, 0, 1], [(0, 2)]),
                      ([1, 0, 1, 0, 0, 0], [(1, 2), (3, 6)]), ([0], [(0, 1)]), ([], [])):
        got = call(runs, seq)
        c.ok(isinstance(got, list), f"outage_runs({seq}) returned {type(got).__name__}, expected a list")
        c.eq([tuple(int(x) for x in p) for p in got], want, f"outage_runs({seq})")


@c.test("TODO 6: outage_table() — number, longest and total outage per flight",
        hint="Per flight: duration of a run = time_s[stop−1] − time_s[start] + dt_s. No outage → 0, 0.0, 0.0. "
             "Think of an outage that lasts until the last row.")
def _():
    pd = pd_()
    (ot,) = fa("outage_table")
    s = pd.DataFrame({"flight_id": ["x"] * 5 + ["y"] * 3, "time_s": [0, 2, 4, 6, 8, 0, 2, 4],
                      "gps_valid": [1, 1, 0, 0, 0, 1, 1, 1]})
    t = frame(call(ot, s), "outage_table(df)")
    c.near(t.loc["x", "longest_outage_s"], 6.0, 1e-9, "longest_outage_s of a flight lost for its last 3 rows")
    c.eq(int(t.loc["y", "n_outages"]), 0, "n_outages of a flight without outage")
    c.near(t.loc["y", "longest_outage_s"], 0.0, 1e-9, "longest_outage_s of a flight without outage")
    t = frame(call(ot, prepared()), "outage_table(df)")
    for col in ("n_outages", "longest_outage_s", "total_outage_s"):
        c.ok(col in t.columns, f"outage_table() has no column {col}")
    for fid, (n, longest, total) in OUTAGES.items():
        c.eq(int(t.loc[fid, "n_outages"]), n, f"n_outages of {fid}")
        c.near(t.loc[fid, "longest_outage_s"], longest, 1e-6, f"longest_outage_s of {fid}")
        c.near(t.loc[fid, "total_outage_s"], total, 1e-6, f"total_outage_s of {fid}")


@c.test("TODO 7: state_shares() — % of FIX / DEGRADED / NO_FIX per flight",
        hint="pd.crosstab(rows, columns, normalize='index') × 100, then .reindex(columns=STATES, fill_value=0.0).")
def _():
    pd = pd_()
    (ss,) = fa("state_shares")
    t = call(ss, pd.DataFrame({"flight_id": ["x", "x", "x", "x"], "state": ["FIX", "FIX", "FIX", "DEGRADED"]}))
    c.eq(list(t.columns), ["FIX", "DEGRADED", "NO_FIX"], "the columns when NO_FIX never occurs")
    c.near(t.loc["x", "NO_FIX"], 0.0, 1e-9, "NO_FIX % when it never occurs")
    c.near(t.loc["x", "FIX"], 75.0, 1e-9, "FIX % for 3 FIX rows out of 4")
    t = frame(call(ss, prepared()), "state_shares(df)")
    c.eq(list(t.columns), ["FIX", "DEGRADED", "NO_FIX"], "the columns of state_shares()")
    for fid, want in SHARES.items():
        for col, w in zip(["FIX", "DEGRADED", "NO_FIX"], want):
            c.near(t.loc[fid, col], w, 1e-3, f"{col} % of {fid}")


@c.test("TODO 8: speed_error() — logged speed vs speed from positions, per source",
        hint="err = |gs_mps − speed_mps|; drop NaN; groupby('source'); median and quantile(0.95).")
def _():
    import numpy as np
    pd = pd_()
    (se,) = fa("speed_error")
    tiny = pd.DataFrame({"source": ["gps"] * 5 + ["none"], "gs_mps": [10.0, 11.0, 12.0, np.nan, 14.0, np.nan],
                         "speed_mps": [10.5, 10.0, 12.0, 9.0, np.nan, 3.0]})
    t = frame(call(se, tiny), "speed_error(df)")
    c.near(t.loc["gps", "median_mps"], 0.5, 1e-9, "median error of 3 gps rows with errors 0.5, 1, 0 (NaN rows ignored)")
    c.ok("none" not in t.index, "rows without a position (source none) cannot have a speed error: drop the NaN")
    t = frame(call(se, prepared()), "speed_error(df)")
    for col in ("median_mps", "p95_mps"):
        c.ok(col in t.columns, f"speed_error() has no column {col}")
    c.ok("none" not in t.index, "rows without a position (source none) cannot have a speed error: drop the NaN")
    for src, (med, p95) in SPEED_ERR.items():
        c.ok(src in t.index, f"speed_error() has no row for the source {src}")
        c.near(t.loc[src, "median_mps"], med, 1e-3, f"median error of {src}")
        c.near(t.loc[src, "p95_mps"], p95, 1e-3, f"95th percentile of {src}")


# ---------------------------------------------------------------- Part D and the deliverables
def is_png(path):
    with open(path, "rb") as fh:
        return fh.read(8) == b"\x89PNG\r\n\x1a\n"


@c.test("TODO 9: plot_altitude() saves a PNG",
        hint="fig, ax = plt.subplots(); ax.plot(...); ax.axvspan(...) per outage; fig.savefig(path). "
             "Never plt.show(): there is no screen.")
def _():
    (pa,) = fa("plot_altitude")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "alt.png")
        tiny = pd_().DataFrame({"flight_id": ["x"] * 6, "time_s": [0, 2, 4, 6, 8, 10],
                                "alt_m": [0.0, 20.0, 40.0, 40.0, 20.0, 0.0], "gps_valid": [1, 1, 0, 0, 1, 0]})
        call(pa, tiny, "x", p)
        c.ok(os.path.exists(p), "plot_altitude() did not create the file it was given")
        c.ok(is_png(p), "the file is not a PNG image")


def results():
    c.file_exists("results.json")
    try:
        with open("results.json") as f:
            return json.load(f)
    except ValueError as e:
        raise CheckFailed(f"results.json is not valid JSON: {e}")


@c.test("flight_analysis.py runs and writes results.json, tracks.png and altitude.png",
        hint="Run `python3 flight_analysis.py` and read its last line.")
def _():
    for f in ("results.json", "tracks.png", "altitude.png"):
        if os.path.exists(f):
            os.remove(f)
    code, out = sh("python3 flight_analysis.py", timeout=120)
    if "not written yet" in out:
        raise CheckFailed(out.strip().splitlines()[-1])
    if code != 0:
        last = [l for l in out.strip().splitlines() if l.strip()][-1:] or ["(no output)"]
        raise CheckFailed("flight_analysis.py stopped with an error — run it and read the last line: " + last[0])
    for f in ("results.json", "tracks.png", "altitude.png"):
        c.file_exists(f)
    c.ok(is_png("tracks.png") and is_png("altitude.png"), "tracks.png / altitude.png are not PNG images")


@c.test("results.json holds the campaign's numbers",
        hint="results.json is written by main() from your functions: if a number is wrong, the check of "
             "that function above tells you which one.")
def _():
    r = results()
    for k, want in (("rows_raw", 1556), ("duplicates_removed", 3), ("glitches_removed", 2), ("rows_clean", 1551)):
        c.eq(r.get(k), want, k)
    c.eq(r.get("longest_outage", {}).get("flight_id"), "nizwa_foothills", "longest_outage.flight_id")
    c.near(r["longest_outage"].get("duration_s"), 416.0, 1e-6, "longest_outage.duration_s")
    fl = r.get("flights", {})
    c.eq(sorted(fl), FLIGHTS, "the flights in results.json")
    c.near(fl["sohar_port"].get("total_outage_s"), 160.0, 1e-6, "flights.sohar_port.total_outage_s")
    c.near(fl["barr_al_hikman"].get("distance_km"), 13.0354, 1e-3, "flights.barr_al_hikman.distance_km")


def numbers_in(text):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))]


@c.test("report.md: four sections, your own words, with the key numbers",
        hint="Keep the four ## headings, replace every '(write here)'. Quote the rows removed, the longest "
             "outage (flight and seconds) and the median speed error of GPS and of day vision.")
def _():
    c.file_exists("report.md")
    with open("report.md") as f:
        text = f.read()
    low = text.lower()
    for h in ("## data cleaning", "## flights", "## outages", "## speed check"):
        c.ok(h in low, f'report.md has no section starting with "{h}"')
    c.ok("(write here)" not in low, 'report.md still contains "(write here)"')
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    c.ok(words >= 150, f"report.md has about {words} words — write at least 150")
    nums = numbers_in(text)
    c.ok("nizwa" in low and any(abs(x - 416) < 0.5 for x in nums),
         "I can't find the longest outage (flight name and duration in s) in report.md")
    c.ok(any(abs(x - 5) < 0.01 for x in nums) or any(abs(x - 1551) < 0.5 for x in nums),
         "I can't find how many rows cleaning removed (or how many are left) in report.md")
    c.ok(any(abs(x - 0.77) <= 0.02 for x in nums) and any(abs(x - 3.25) <= 0.02 for x in nums),
         "I can't find the median speed errors of GPS and of day vision (m/s, 2 decimals) in report.md")


c.run()

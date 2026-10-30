import contextlib
import io
import json
import math
import os
import re

from academy_check import (CheckFailed, Checker, explained, load_student, need, predicted, run,
                           sh, words)

c = Checker()


def quiet_load(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name)


def answers(*names):
    return need(load_student("answers.py", fresh=True), *names)


def functions(*names):
    return need(quiet_load("navera_lite.logbook"), *names)


def number(v, name):
    if isinstance(v, (bool, str)) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def text(v, name):
    if not isinstance(v, str) or not v.strip():
        raise CheckFailed(f"{name} is still empty — write it in quotes, like \"abc\"")
    return v.strip()


import numpy as np    # noqa: E402
import pandas as pd   # noqa: E402

nan = float("nan")


def frame(v, fn, columns=()):
    if not isinstance(v, pd.DataFrame):
        raise CheckFailed(f"{fn}() should return a pandas DataFrame, got {type(v).__name__}")
    missing = [col for col in columns if col not in v.columns]
    if missing:
        raise CheckFailed(f"{fn}() returned a DataFrame without the column(s) {missing} (columns: {list(v.columns)})")
    return v


def same(a, b, tol=1e-3):
    return (isinstance(a, float) and math.isnan(a) and math.isnan(b)) if (a != a or b != b) else abs(a - b) <= tol


# ---------------------------------------------------------------- session 1: your functions, on unseen tables
def raw_table():
    rows = [("y", 4, -33.91, 18.42, 50.0), ("x", 2, 35.81, 10.62, 120.0), ("x", 0, 35.80, 10.62, 118.0),
            ("x", 2, 35.81, 10.62, 120.0), ("y", 0, 0.0, 0.0, 49.0), ("x", 4, nan, nan, 121.0),
            ("y", 2, 0.0, 18.42, 6000.0), ("x", 6, 35.82, 10.62, -150.0), ("x", 2, 35.81, 10.62, 120.0),
            ("y", 0, 0.0, 0.0, 49.0),
            ("y", 6, -33.91, 18.43, nan), ("y", 8, 0.0, 18.44, 51.0)]
    return pd.DataFrame(rows, columns=["flight_id", "time_s", "lat", "lon", "alt_m"])


MASK_HELP = " — combine masks with | or &, with brackets around each comparison (Step 2 hint 6)"


def run_masks(fn, *args):
    """run(), plus one sentence for the and/or-between-masks errors."""
    try:
        return run(fn, *args)
    except CheckFailed as e:
        if any(k in str(e) for k in ("truth value of a Series is ambiguous", "'ror_'", "'rand_'")):
            raise CheckFailed(str(e) + MASK_HELP)
        raise


@c.test("TODO 1: clean() applies the three rules on a table it has never seen",
        hint="Lesson §2 and the docstring: one mask per rule, each on what the previous rule left; write each rule as "
             "'remove where …' so that empty cells stay; return (clean_df, removed).")
def _():
    (clean,) = functions("clean")
    df = raw_table()
    before = df.copy()
    got = run_masks(clean, df)
    if isinstance(got, pd.DataFrame):
        raise CheckFailed("clean() returned only the DataFrame: return two things, `return out, removed`")
    c.ok(isinstance(got, tuple) and len(got) == 2, f"clean() should return (clean_df, removed), got {type(got).__name__}")
    out, removed = got
    frame(out, "clean")
    c.ok(df.equals(before), "clean() changed the table it received: work on new DataFrames (df[mask] gives a new one)")
    c.ok(isinstance(removed, dict), f"the second result should be a dict of counts, got {type(removed).__name__}")
    c.ok(set(removed) == {"duplicates", "null_island", "bad_altitude"},
         f"removed should have exactly the keys duplicates, null_island, bad_altitude; got {sorted(removed)}")
    if out["lat"].isna().sum() == 0:
        raise CheckFailed("the row with an EMPTY position was removed: empty cells are kept (no dropna, and write "
                          "the (0, 0) rule as 'remove where lat == 0 and lon == 0')")
    if out["alt_m"].isna().sum() == 0:
        raise CheckFailed("the row with an EMPTY altitude was removed: the altitude rule removes values outside the "
                          "range, and NaN is not outside it")
    c.ok(int(removed["duplicates"]) == 3, f"on a table where one row appears three times and another twice, "
                                          f"duplicates = {removed['duplicates']!r} — every copy after the first is counted")
    if int(removed["null_island"]) == 2:
        raise CheckFailed("null_island = 2 on a table where the (0, 0) row is also written twice: the copy was already "
                          "removed as a duplicate — compute each mask on what the previous rule left, not on df")
    c.ok(int(removed["null_island"]) == 1, f"null_island = {removed['null_island']!r} — only rows where lat AND lon "
                                           "are both 0 (a row at lat 0, lon 18.4 stays)")
    c.ok(int(removed["bad_altitude"]) == 2, f"bad_altitude = {removed['bad_altitude']!r} — below ALT_MIN_M OR above "
                                            "ALT_MAX_M (both sides of the range)")
    c.ok(len(out) == 6, f"the clean table has {len(out)} rows: the counts are right but the rows removed are not")
    keys = list(zip(out["flight_id"], out["time_s"]))
    c.ok(keys == sorted(keys), f"the rows are not sorted by flight_id then time_s: {keys}")
    c.ok(list(out.index) == list(range(len(out))), f"the index is {list(out.index)}: renumber it with "
                                                     "reset_index(drop=True)")


@c.test("TODO 2: add_motion() works within each flight, with empty positions",
        hint="Lesson §3: g = out.groupby('flight_id'); dt from g['time_s'].shift(); step with haversine_m between "
             "the shifted lat/lon and the current ones; speed = step / dt. Work on out = df.copy().")
def _():
    (add_motion,) = functions("add_motion")
    df = pd.DataFrame({"flight_id": ["p", "p", "p", "p", "q", "q"], "time_s": [10, 12, 16, 18, 500, 504],
                       "lat": [-33.9000, -33.8998, nan, -33.8990, 64.1400, 64.1400],
                       "lon": [18.4200, 18.4200, 18.4210, 18.4215, -21.9400, -21.9396]})
    before = df.copy()
    out = frame(run(add_motion, df), "add_motion", ("dt_s", "step_m", "pos_speed_mps"))
    c.ok(df.equals(before), "add_motion() changed the table it received: start with out = df.copy()")
    c.ok(len(out) == 6, f"add_motion() returned {len(out)} rows instead of 6: it must only ADD columns")
    dt = [float(x) for x in out["dt_s"]]
    if not math.isnan(dt[4]):
        raise CheckFailed(f"the first row of flight q has dt_s = {dt[4]:g}: your shift() crosses from one flight to the "
                          "next — shift inside df.groupby('flight_id')")
    c.ok(math.isnan(dt[0]), "the first row of a flight must have NaN in dt_s (there is no previous row)")
    c.ok([dt[1], dt[2], dt[3], dt[5]] == [2.0, 4.0, 2.0, 4.0], f"dt_s is {dt}: time minus the previous time of the flight")
    st = [float(x) for x in out["step_m"]]
    sp = [float(x) for x in out["pos_speed_mps"]]
    c.ok(math.isnan(st[0]) and math.isnan(st[4]), "step_m on the first row of a flight must be NaN: shift lat and lon "
                                                  "inside the groupby too, not only time_s")
    c.ok(math.isnan(st[2]) and math.isnan(st[3]), "a step from or to an empty position must be NaN (haversine_m gives "
                                                  "NaN on NaN: do not fill the holes)")
    c.ok(same(st[1], 22.239, 0.01) and same(st[5], 19.4001, 0.01),
         f"step_m is {[round(x, 3) for x in st]} — use haversine_m(previous lat, previous lon, lat, lon), in metres")
    if same(sp[5], 9.7001, 0.01):
        raise CheckFailed("pos_speed_mps divides by a fixed 2 s: after a gap of 4 s the speed is twice too big — divide by dt_s")
    c.ok(same(sp[1], 11.1195, 0.01) and same(sp[5], 4.8500, 0.01),
         f"pos_speed_mps is {[round(x, 3) for x in sp]} — step_m divided by dt_s")


@c.test("TODO 3: outage_runs() finds every run, at the start, in the middle and at the end",
        hint="Lesson §4: pad the lost array with a 0 at both ends, np.diff, starts at +1, stops at −1 (stop excluded). "
             "Return a list of (int, int) pairs.")
def _():
    (outage_runs,) = functions("outage_runs")
    cases = [([1, 0, 1, 1, 0, 0], [(1, 2), (4, 6)]), ([0], [(0, 1)]), ([1], []), ([0, 0, 0], [(0, 3)]),
             ([1, 0, 0, 0, 1, 0], [(1, 4), (5, 6)]), (np.array([True, False, False, True]), [(1, 3)]),
             (np.array([1, 1, 0, 1]), [(2, 3)])]
    for arg, want in cases:
        got = run(outage_runs, arg)
        shown = list(arg) if isinstance(arg, np.ndarray) else arg
        c.ok(isinstance(got, list), f"outage_runs({shown}) should return a list, got {type(got).__name__}")
        try:
            pairs = [(int(a), int(b)) for a, b in got]
        except (TypeError, ValueError):
            raise CheckFailed(f"outage_runs({shown}) should return (start, stop) pairs, got {got!r}")
        if pairs != want and len(pairs) == len(want) and all(b == w[1] + 1 for (_, b), w in zip(pairs, want)):
            raise CheckFailed(f"outage_runs({shown}) gives {pairs}: each stop is one too far (a stop is the first "
                              "row AFTER the run, the −1 position itself)")
        c.ok(pairs == want, f"outage_runs({shown}) gives {pairs} — not the right runs"
             + (" (a run at the start or the end is missing: pad BOTH ends)" if len(pairs) < len(want) else ""))


# ---------------------------------------------------------------- session 1: what you saw
@c.test("Step 1: the raw campaign seen from the shell and from pandas (ROWS_RAW, MOST_ROWS_FLIGHT, EMPTY_LAT_ROWS, DROPNA_ROWS_LOST)",
        hint="wc -l counts the header line too. One pipeline of mission 02 (cut, sort, uniq -c, sort -rn) gives the rows per "
             "flight; an empty lat is an empty 3rd field. len(df) - len(df.dropna()) in python3. A NameError in answers.py "
             "almost always means text without quotes.")
def _():
    rows, most, empty, lost, pred = answers("ROWS_RAW", "MOST_ROWS_FLIGHT", "EMPTY_LAT_ROWS", "DROPNA_ROWS_LOST",
                                            "PREDICT_CLEAN")
    r = number(rows, "ROWS_RAW")
    c.ok(r != 1403, "ROWS_RAW = 1403 counts the header line: wc -l counts every line of the file")
    c.ok(r == 1402, f"ROWS_RAW = {rows!r} is not the number of data rows of campaign.csv")
    m = text(most, "MOST_ROWS_FLIGHT")
    c.ok(m != "flight_id", "MOST_ROWS_FLIGHT = \"flight_id\" is the header line: the flight ids are below it")
    c.ok(m == "sahel_hills", f"MOST_ROWS_FLIGHT = {most!r} is not the flight with the most rows (copy the id exactly)")
    c.ok(number(empty, "EMPTY_LAT_ROWS") == 31, f"EMPTY_LAT_ROWS = {empty!r} — count the rows whose 3rd field (lat) is empty")
    c.ok(number(lost, "DROPNA_ROWS_LOST") == 119, f"DROPNA_ROWS_LOST = {lost!r} — run len(df) - len(df.dropna()) in python3")
    predicted("PREDICT_CLEAN", pred)


@c.test("Steps 2–4: NO_FIX rows, the fastest steps, and your outage prediction",
        hint="Step 2: what is a NO_FIX row, and what would dropping it do to an outage? Step 3: the `motion` run prints "
             "the source of each flight's fastest step. Step 4: write your guess before you test.")
def _():
    why, fastest, pred = answers("EXPLAIN_KEEP_NOFIX", "FASTEST_SOURCE", "PREDICT_RUNS")
    explained("EXPLAIN_KEEP_NOFIX", why,
              ((r"outage", r"lost", r"gap", r"coupure"), "what the rows mean for the outages"),
              ((r"short", r"duration", r"long", r"hide", r"underestim", r"less", r"miss", r"shrink", r"vanish", r"disappear",
                r"smaller", r"fewer", r"split", r"wrong", r"lose", r"lost"), "what dropping them would do"))
    f = text(fastest, "FASTEST_SOURCE").lower()
    c.ok(f in ("gps", "day", "none"), f"FASTEST_SOURCE = {fastest!r} should be \"gps\", \"day\" or \"none\"")
    c.ok(f == "day", "not this source: run python3 run_logbook.py motion and read the `source` column of the fastest steps")
    predicted("PREDICT_RUNS", pred)


# ---------------------------------------------------------------- session 2: your functions, on unseen tables
@c.test("TODO 4: outage_table() gives every flight, with durations that include one logging period",
        hint="Lesson §4: a run i0 … i1−1 lasts t[i1−1] − t[i0] + dt_s, with t the times of THAT flight; a flight without "
             "outage still has a row (0, 0.0, 0.0); build the table with pd.DataFrame.from_dict(rows, orient='index').")
def _():
    (outage_table,) = functions("outage_table")
    t = pd.DataFrame({"flight_id": ["m"] * 6 + ["k"] * 3, "time_s": [0, 2, 4, 8, 10, 12, 100, 102, 104],
                      "gps_valid": [0, 1, 0, 0, 1, 0, 1, 1, 1]})
    out = frame(run(outage_table, t), "outage_table", ("n_outages", "longest_s", "total_s"))
    c.ok(set(out.index) == {"m", "k"}, f"the index should hold every flight (m and k), got {list(out.index)} — a flight "
                                       "without outage needs a row too")
    c.ok(list(out.index) == ["k", "m"], f"the index should be sorted: {list(out.index)}")
    c.ok(int(out.loc["m", "n_outages"]) == 3, f"flight m has {out.loc['m', 'n_outages']!r} outages — runs at the start, "
                                              "in the middle and at the end all count")
    lo, to = float(out.loc["m", "longest_s"]), float(out.loc["m", "total_s"])
    c.ok(not (lo == 4.0 and to == 4.0), "durations without + dt_s: one lost row lasts one logging period, not 0 s")
    c.ok(lo == 6.0 and to == 10.0, f"flight m: longest_s {lo:g}, total_s {to:g} — not right; the rows are NOT evenly "
                                   "spaced here: use the flight's own time_s values")
    c.ok(float(out.loc["k", "longest_s"]) == 0.0 and float(out.loc["k", "total_s"]) == 0.0
         and int(out.loc["k", "n_outages"]) == 0, "a flight without outage should have 0, 0.0, 0.0")
    out1 = frame(run(outage_table, t, 1.0), "outage_table", ("longest_s", "total_s"))
    c.ok(float(out1.loc["m", "longest_s"]) == 5.0 and float(out1.loc["m", "total_s"]) == 7.0,
         "with dt_s = 1.0 the durations do not change: use the dt_s argument, not DT_S")
    t2 = pd.DataFrame({"flight_id": ["a"] * 4 + ["b"] * 4, "time_s": [0, 5, 10, 15, 100, 102, 104, 106],
                       "gps_valid": [1, 1, 1, 1, 1, 0, 0, 1]})
    out2 = frame(run(outage_table, t2, 2.0), "outage_table", ("longest_s",))
    c.ok(float(out2.loc["b", "longest_s"]) == 4.0,
         f"flight b (the 2nd flight, times 100–106) has longest_s {float(out2.loc['b', 'longest_s']):g} instead of a "
         "short outage: the run's indices are positions INSIDE the flight — take the times from the flight's own rows "
         "(f['time_s'].to_numpy()), not from df (Step 5, hint 2)")


@c.test("TODO 5: state_shares() gives percentages per flight, with all three states",
        hint="Per flight: value_counts(normalize=True) × 100, then one float per state of STATES (0.0 when absent).")
def _():
    (state_shares,) = functions("state_shares")
    s = pd.DataFrame({"flight_id": ["u"] * 5 + ["v"] * 3,
                      "state": ["FIX", "DEGRADED", "DEGRADED", "NO_FIX", "FIX", "FIX", "FIX", "FIX"]})
    got = run(state_shares, s)
    c.ok(isinstance(got, dict), f"state_shares() should return a dict, got {type(got).__name__}")
    c.ok(set(got) == {"u", "v"}, f"the keys should be the flight ids u and v, got {sorted(map(str, got))}")
    for fid, want in (("u", {"FIX": 40.0, "DEGRADED": 40.0, "NO_FIX": 20.0}), ("v", {"FIX": 100.0, "DEGRADED": 0.0, "NO_FIX": 0.0})):
        row = got[fid]
        c.ok(isinstance(row, dict) and set(row) == set(want),
             f"the value for flight {fid} should be a dict with exactly FIX, DEGRADED, NO_FIX; got {row!r}")
        if all(abs(float(row[k]) - want[k] / 100) < 1e-9 for k in want):
            raise CheckFailed("the shares are fractions (0.4), not percentages (40.0): multiply by 100")
        if abs(sum(float(x) for x in row.values()) - 100.0) > 0.01:
            raise CheckFailed(f"flight {fid} gives {row}: the shares of one flight must add up to 100 — divide by that "
                              "flight's rows, not by all the rows of df")
        c.ok(all(abs(float(row[k]) - want[k]) < 1e-6 for k in want), f"flight {fid} gives {row} — not the right shares")
        c.ok(all(type(v) is float for v in row.values()), f"the values should be plain Python floats (float(x)), got "
                                                           f"{[type(v).__name__ for v in row.values()]}")


@c.test("TODO 6: noise_by_source() describes each source's speed error, robustly and not",
        hint="err = pos_speed_mps − speed_mps, rows with NaN dropped; per source: n, mean, std (ddof 1), median, "
             "MAD × MAD_TO_SIGMA, and the 95th percentile of |err| (linear). The docstring example is your first test.")
def _():
    (noise_by_source,) = functions("noise_by_source")
    day = [-3, 1, 2, 2, 4, 5, 60, -2]
    gps = [0.5, -0.5, 1.0, 0.2, -3.0]
    rows = ([("day", 10.0 + e, 10.0) for e in day] + [("gps", 8.0 + e, 8.0) for e in gps]
            + [("gps", nan, 8.0), ("gps", 9.0, nan), ("none", nan, 7.0)])
    n = pd.DataFrame(rows, columns=["source", "pos_speed_mps", "speed_mps"])
    n["battery_pct"] = 80.0
    n.loc[0, "battery_pct"] = nan          # an empty cell in ANOTHER column, on a usable day row
    cols = ("n", "mean_mps", "std_mps", "median_mps", "mad_sigma_mps", "p95_abs_mps")
    out = frame(run(noise_by_source, n), "noise_by_source", cols)
    c.ok("none" not in list(out.index), "a source with no usable error (all NaN) should not appear: drop NaN rows first")
    c.ok(list(out.index) == ["day", "gps"], f"the index should be the sources, sorted: got {list(out.index)}")
    if int(out.loc["day", "n"]) == 7:
        raise CheckFailed("day has n = 7 instead of 8: a row with an empty battery_pct was dropped — drop only the rows "
                          "where the error is NaN, not df.dropna() on the whole log")
    c.ok(int(out.loc["gps", "n"]) == 5, f"gps has n = {out.loc['gps', 'n']!r}: count only rows where BOTH speeds are known")
    want = {"day": (8.625, 20.9348, 2.0, 3.7065, 40.75), "gps": (-0.36, 1.57258, 0.2, 1.03782, 2.6)}
    for src, (mean, std, med, mad, p95) in want.items():
        r = out.loc[src]
        if abs(float(r["mean_mps"]) + mean) < 1e-3 and mean != 0:
            raise CheckFailed("the errors have the wrong sign: err = pos_speed_mps − speed_mps")
        c.near(r["mean_mps"], mean, 1e-3, f"{src}: mean_mps")
        if abs(float(r["std_mps"]) - std * math.sqrt((len(day if src == 'day' else gps) - 1) / len(day if src == 'day' else gps))) < 1e-3:
            raise CheckFailed(f"{src}: std_mps is numpy's std (ddof 0); the docstring asks for pandas' default, ddof 1")
        c.near(r["std_mps"], std, 1e-3, f"{src}: std_mps")
        c.near(r["median_mps"], med, 1e-3, f"{src}: median_mps")
        if abs(float(r["mad_sigma_mps"]) - mad / 1.4826) < 1e-3:
            raise CheckFailed(f"{src}: mad_sigma_mps is the raw MAD: multiply it by MAD_TO_SIGMA")
        c.near(r["mad_sigma_mps"], mad, 1e-3, f"{src}: mad_sigma_mps (median of |err − median| × 1.4826)")
        if src == "gps" and abs(float(r["p95_abs_mps"]) - 0.9) < 1e-3:
            raise CheckFailed("gps: p95_abs_mps is the 95th percentile of the SIGNED errors: take it on |err| (.abs())")
        c.near(r["p95_abs_mps"], p95, 1e-3, f"{src}: p95_abs_mps (95th percentile of |err|, linear)")


# ---------------------------------------------------------------- session 2: what you found
@c.test("Step 6: the detective — CLOCK_FIX_S, SPEED_FACTOR and your evidence",
        hint="Lab Step 6: compare the log with independent records (lesson §6), flight by flight. Corrections are what "
             "you ADD to time_s and what MULTIPLIES speed_mps; `schedule` shows each correction checked.")
def _():
    clock, speed, why = answers("CLOCK_FIX_S", "SPEED_FACTOR", "EXPLAIN_DETECTIVE")
    c.ok(isinstance(clock, dict) and isinstance(speed, dict), "CLOCK_FIX_S and SPEED_FACTOR should be dicts, "
                                                              "like {\"some_flight\": -120.0}")
    c.ok(len(clock) > 0 and len(speed) > 0, "CLOCK_FIX_S or SPEED_FACTOR is still empty: that is lab Step 6")
    c.ok(len(clock) == 1, f"CLOCK_FIX_S should correct exactly one flight, it has {len(clock)}")
    (cf, cv), = clock.items()
    c.ok(cf == "sahel_hills", f"CLOCK_FIX_S corrects {cf!r}: compare every flight's first time_s with the sheet's take-off")
    cv = number(cv, "the clock correction")
    c.ok(cv != 3600, "+3600 moves the flight the wrong way: its log is AHEAD of UTC, so you ADD a negative number")
    c.ok(cv == -3600, f"the clock correction {cv:g} s is not the difference between the log and the sheet")
    c.ok(len(speed) == 1, f"SPEED_FACTOR should correct exactly one flight, it has {len(speed)}")
    (sf, sv), = speed.items()
    c.ok(sf == "grid_survey", f"SPEED_FACTOR corrects {sf!r}: which flight's logged speed is far from its speed from positions?")
    sv = number(sv, "the speed factor")
    c.ok(abs(sv - 3.6) > 0.01, "3.6 makes the speeds even bigger: the factor MULTIPLIES speed_mps to give m/s")
    c.ok(abs(sv - 1 / 3.6) < 0.002, f"the speed factor {sv:g} does not turn that unit into m/s")
    explained("EXPLAIN_DETECTIVE", why,
              ((r"sheet", r"take.?off", r"utc", r"local", r"time ?zone", r"overlap", r"same time"), "the evidence for the clock"),
              ((r"km/?h", r"kilomet", r"3\.6", r"ratio", r"30 ?m/s", r"vehicle", r"position"), "the evidence for the speed unit"))


@c.test("Step 6: the outage the jamming plan does not explain (UNPLANNED_FLIGHT, UNPLANNED_START_UTC)",
        hint="With your corrections in answers.py, run python3 run_logbook.py schedule and read the UNPLANNED line.")
def _():
    f, t = answers("UNPLANNED_FLIGHT", "UNPLANNED_START_UTC")
    f = text(f, "UNPLANNED_FLIGHT")
    c.ok(f != "sahel_hills", "sahel_hills looks unplanned only while its clock is wrong: write CLOCK_FIX_S first, then "
                             "run schedule again")
    c.ok(f == "sousse_port", f"UNPLANNED_FLIGHT = {f!r} is not the flight of the UNPLANNED line")
    c.ok(text(t, "UNPLANNED_START_UTC").replace(" ", "") == "08:27:00",
         f"UNPLANNED_START_UTC = {t!r} — copy the start time of the UNPLANNED line, as hh:mm:ss")


@c.test("Step 7: how noisy each source is (PREDICT_NOISE, EXPLAIN_ROBUST)",
        hint="Run python3 run_logbook.py noise and compare the two tables. EXPLAIN: the day-vision steps of Step 3, which "
             "number is the typical noise, what a report must add, and how the gps rows change between the two tables.")
def _():
    pred, why = answers("PREDICT_NOISE", "EXPLAIN_ROBUST")
    predicted("PREDICT_NOISE", pred)
    explained("EXPLAIN_ROBUST", why,
              ((r"jump", r"outlier", r"glitch", r"wild", r"extreme", r"few", r"wrong match", r"squar"), "why std is so big"),
              ((r"mad", r"median", r"robust"), "which number is the typical noise"),
              ((r"p95", r"percentile", r"tail", r"max", r"sample", r"\bn\b", r"count"), "what a report must add"),
              ((r"km/?h", r"unit", r"systematic", r"grid", r"speed factor", r"correction", r"bias"),
               "what the median did not protect you from"))


@c.test("TODO 7: unit_suspects() spots the flights logged in another unit",
        hint="The docstring is the whole specification (no hints in the lab on purpose): medians per flight, a ratio, "
             "and a RELATIVE tolerance |ratio / r − 1| ≤ tol.")
def _():
    (unit_suspects,) = functions("unit_suspects")
    rows = [("p", 27.75, 7.5), ("p", 27.6, 7.5), ("p", nan, 7.6), ("p", 27.8, 7.4),
            ("q", 3.9, 2.0), ("q", 3.88, 2.0), ("q", 3.92, 2.0), ("q", 3.9, 40.0),
            ("r", 10.4, 10.0), ("r", 10.4, 10.0), ("r", 10.4, nan), ("s", 13.0, 10.0), ("s", 13.0, 10.0),
            ("t", 19.5, 10.0), ("t", 19.4, 10.0), ("w", 5.0, 10.0), ("w", 5.0, 10.0)]
    u = pd.DataFrame(rows, columns=["flight_id", "speed_mps", "pos_speed_mps"])
    got = run(unit_suspects, u)
    c.ok(isinstance(got, dict), f"unit_suspects() should return a dict, got {type(got).__name__}")
    c.ok("r" not in got, f"flight r (ratio 1.04) looks right with tol 0.05 and must be left out; got {got}")
    if got.get("t") != "kn":
        raise CheckFailed(f"flight t (ratio 1.945, knots) gives {got.get('t')!r}: ratio = median logged speed / median "
                          "speed from positions, compared with KN_PER_MPS (1 m/s = 1.944 kn)")
    if "w" not in got:
        raise CheckFailed("flight w (ratio 0.5) is missing: a ratio far BELOW 1 is suspect too ('?'): "
                          "|ratio − 1| > tol on both sides")
    if got.get("q") == "?":
        raise CheckFailed("flight q (knots, one wild position speed of 40 m/s) gives '?': use the MEDIANS, not the means")
    if got.get("p") == "?":
        raise CheckFailed("flight p (ratio 3.70, 2.8 % from 3.6) gives '?': the tolerance is RELATIVE, |ratio / 3.6 − 1| ≤ tol")
    c.ok(got == {"p": "km/h", "q": "kn", "s": "?", "t": "kn", "w": "?"}, f"unit_suspects gives {got} — not the right labels")
    got2 = run(unit_suspects, u, 0.02)
    c.ok(got2 == {"p": "?", "q": "kn", "r": "?", "s": "?", "t": "kn", "w": "?"}, f"with tol = 0.02 it gives {got2}: use the tol argument")


@c.test("Step 9: results.json, made by the runner with your functions and your corrections",
        hint="Run python3 run_logbook.py report after the other steps. A wrong value here comes from one of your "
             "functions (see the TODO checks) or from answers.py's corrections.")
def _():
    code, out = sh("python3 run_logbook.py report", timeout=120)
    c.ok(code == 0 and os.path.exists("results.json"),
         "python3 run_logbook.py report did not finish: run it in the terminal and read its last line\n"
         + "\n".join(out.strip().splitlines()[-3:]))
    with open("results.json") as f:
        r = json.load(f)
    c.ok(r.get("rows_raw") == 1402 and r.get("rows_clean") == 1397, f"results.json: {r.get('rows_raw')} raw rows, "
         f"{r.get('rows_clean')} clean rows — check clean() (TODO 1)")
    lo = r.get("longest_outage", {})
    c.ok(lo.get("flight_id") == "sahel_hills" and lo.get("duration_s") == 292.0, f"results.json: longest outage {lo}, expected sahel_hills with 292 s — check outage_table (TODO 4) and your clock correction")
    c.ok(r.get("jamming_without_outage") == [], "results.json: a jamming window still has no outage: the clock "
                                                "correction is missing or wrong")
    un = r.get("unplanned_outages", [])
    c.ok(len(un) == 1 and un[0].get("flight_id") == "sousse_port", f"results.json: unplanned outages {un}")
    nz = r.get("noise", {})
    c.ok("gps" in nz and "day" in nz, f"results.json: noise should have gps and day, has {sorted(nz)}")
    c.near(nz["gps"].get("mad_sigma_mps"), 1.188, 0.01, "results.json: gps mad_sigma_mps")
    c.near(nz["day"].get("mad_sigma_mps"), 3.745, 0.01, "results.json: day mad_sigma_mps")


@c.test("Step 9: report.md — five sections, your own words, the key numbers",
        hint="Keep the five ## headings, replace every (write here), at least 200 words. Give: the rows left (or removed), "
             "both corrections with their numbers, the longest outage (flight and seconds), the unplanned one (flight "
             "and UTC time), and both robust σ (mad_sigma_mps, with your corrections) with two decimals.")
def _():
    c.file_exists("report.md")
    rep = open("report.md").read()
    heads = re.findall(r"^##\s+(.+)$", rep, re.M)
    c.ok(len(heads) >= 5, f"report.md has {len(heads)} '##' headings: keep the five of the template")
    body = rep[rep.find("## "):] if "## " in rep else rep
    c.ok("(write here)" not in body, "report.md still contains '(write here)' under a heading: replace each one with your text")
    n = len(words(re.sub(r"^#.*$", "", rep, flags=re.M)))
    c.ok(n >= 200, f"report.md has {n} words of text: write at least 200, in full sentences")
    low = rep.lower()
    if "1.98" in low and "1.19" not in low:
        raise CheckFailed("report.md gives the gps σ of the table WITHOUT corrections (1.98): use the second table")
    if re.search(r"3\.7(?![0-9])", low) and not re.search(r"3\.7[45]", low):
        raise CheckFailed("report.md gives day vision's robust σ with one decimal: write it with two (as in results.json)")
    if re.search(r"(?<![0-9])1\.2(?![0-9])", low) and not re.search(r"1\.19", low):
        raise CheckFailed("report.md gives the gps robust σ with one decimal: write it with two (as in results.json)")
    if re.search(r"4\.2[78]", low) and not re.search(r"3\.7[45]", low):
        raise CheckFailed("report.md gives day vision's robust σ of the table WITHOUT corrections (4.28): use the "
                          "corrected table (the second table, or results.json)")
    if re.search(r"35\.69", low) and not re.search(r"3\.7[45]", low):
        raise CheckFailed("report.md gives day vision's std (35.69) but not its robust σ (mad_sigma_mps)")
    for pats, what in (((r"1\s?397", r"1\s?402"), "the number of rows (raw or left)"),
                       ((r"3\s?600", r"\b1 ?h", r"one hour", r"utc ?\+ ?1"), "the clock correction (3600 s, 1 h)"),
                       ((r"km/?h",), "the km/h speed column"),
                       ((r"292",), "the longest outage in seconds (292)"),
                       ((r"sahel",), "the flight of the longest outage"),
                       ((r"sousse",), "the flight of the unplanned outage"),
                       ((r"08:27",), "the UTC start of the unplanned outage"),
                       ((r"1\.19",), "the robust σ of gps (two decimals)"),
                       ((r"3\.7[45]",), "the robust σ of day vision (two decimals)")):
        c.ok(any(re.search(p, low) for p in pats), f"report.md does not give {what} yet")


# Session 1 (Steps 0–4) earns "Log keeper"; the whole mission earns "Flight-test analyst".
c.milestone("log-keeper", "TODO 1:", "TODO 2:", "TODO 3:", "Step 1:", "Steps 2–4:",
            label="Session 1 complete: Log keeper badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("flight-test-analyst", "TODO", "Step", label="Mission complete: Log keeper and Flight-test analyst badges earned")

c.run()

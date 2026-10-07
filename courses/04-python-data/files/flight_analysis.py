"""flight_analysis.py — analyse a flight-test campaign with pandas, NumPy and matplotlib (lab 4).

The data, campaign.csv, is a SYNTHETIC campaign of four test flights near Sousse, one row every 2 s:
    flight_id, time_s, lat, lon, alt_m, speed_mps, battery_pct, gps_valid, source, state
It is messy on purpose (duplicates, glitches, empty cells). Clean it, measure it, plot it.

Each TODO replaces a line  raise NotImplementedError("TODO n").
Run:   python3 flight_analysis.py      -> results.json, tracks.png, altitude.png
"""
import json

import matplotlib
matplotlib.use("Agg")                    # no window: figures are saved as PNG files
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402

EARTH_RADIUS_M = 6_371_000.0             # same value as navera_common/geo.py
DT_S = 2.0                               # logging period: one row every 2 s
ALT_MIN_M, ALT_MAX_M = -100.0, 5000.0    # a plausible altitude for these vehicles
STATES = ["FIX", "DEGRADED", "NO_FIX"]


def load_log(path):
    """Read the CSV into a DataFrame (already written)."""
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Part A — cleaning
# ---------------------------------------------------------------------------


def clean(df):
    """Return a NEW, clean DataFrame (do not modify df):
      1. drop exact duplicate rows;
      2. drop glitch rows: lat == 0 AND lon == 0, or alt_m outside [ALT_MIN_M, ALT_MAX_M];
      3. sort by flight_id then time_s, and renumber the index from 0 (reset_index(drop=True)).
    Rows with an EMPTY position (NaN lat/lon: NO_FIX) are kept: they are part of an outage."""
    # TODO 1: drop_duplicates(), two boolean masks combined with & | ~, sort_values, reset_index
    raise NotImplementedError("TODO 1")


# ---------------------------------------------------------------------------
# Part B — distances and speeds (NumPy, vectorised)
# ---------------------------------------------------------------------------


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance (m) between points given in degrees. Works on numbers, NumPy
    arrays and pandas Series (element by element); NaN in -> NaN out.
        a = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)      d = 2 R · asin(√a)"""
    # TODO 2: the formula above with np.radians, np.sin, np.cos, np.arcsin, np.sqrt (not math.*)
    raise NotImplementedError("TODO 2")


def add_motion(df):
    """Return a copy of df with three new columns, computed WITHIN each flight:
      dt_s    time since the previous row of the same flight (NaN on the first row)
      step_m  distance from the previous row's position (NaN if either position is missing)
      gs_mps  ground speed from positions = step_m / dt_s"""
    # TODO 3: work on a copy; g = out.groupby("flight_id"); g["lat"].shift() is the previous row's
    #         latitude IN THE SAME FLIGHT (NaN on each flight's first row). Then haversine_m().
    raise NotImplementedError("TODO 3")


def flight_summary(df):
    """One row per flight (index: flight_id, sorted), columns:
      rows, duration_s, distance_km (sum of step_m / 1000), max_alt_m,
      mean_speed_mps (the LOGGED speed_mps), min_battery_pct.
    duration_s = last time_s - first time_s of the flight (NO extra + DT_S here).
    df already has the columns of add_motion()."""
    # TODO 4: df.groupby("flight_id").agg(name=("column", "function"), ...), then derived columns
    #         (e.g. t_first=("time_s", "min") and t_last=("time_s", "max"), then duration = t_last - t_first)
    raise NotImplementedError("TODO 4")


# ---------------------------------------------------------------------------
# Part C — outages (run-length logic with NumPy)
# ---------------------------------------------------------------------------


def outage_runs(gps_valid):
    """Runs of consecutive 0 in a 1-D sequence of 0/1, as a list of (start, stop) index pairs,
    stop EXCLUDED.   [1, 0, 0, 1, 0] -> [(1, 3), (4, 5)]      [1, 1] -> []"""
    # TODO 5: lost = 1 where gps_valid == 0; pad with a 0 at both ends; np.diff gives +1 where a
    #         run starts and -1 where it stops; np.flatnonzero finds those indices. No loop needed.
    raise NotImplementedError("TODO 5")


def outage_table(df, dt_s=DT_S):
    """One row per flight (index: flight_id, sorted): n_outages, longest_outage_s, total_outage_s.
    An outage of rows start..stop-1 lasts  time_s[stop-1] - time_s[start] + dt_s  seconds
    (a single lost row = one logging period). A flight without outage has 0, 0.0, 0.0."""
    # TODO 6: for fid, f in df.groupby("flight_id"): use outage_runs() on that flight's gps_valid
    #         and its time_s values (.to_numpy()); build a dict {flight_id: {column: value}},
    #         then pd.DataFrame.from_dict(rows, orient="index") (course, section 2: "A table from a dict").
    raise NotImplementedError("TODO 6")


def state_shares(df):
    """Percentage of rows in each NAVERA state, per flight: index flight_id (sorted),
    columns exactly STATES (FIX, DEGRADED, NO_FIX), 0.0 where a state never occurs."""
    # TODO 7: pd.crosstab(..., normalize="index") gives fractions per row; × 100; then make sure
    #         the three columns exist in the order of STATES (reindex with fill_value).
    raise NotImplementedError("TODO 7")


def speed_error(df):
    """|gs_mps - speed_mps| per row, summarised per `source` (rows where both are known):
    index source, columns median_mps and p95_mps (the 95th percentile)."""
    # TODO 8: absolute difference, drop the rows where it is NaN, group by source, median and
    #         95th percentile. In .agg(), "median" is a name pandas knows; for the 95th percentile
    #         pass a lambda: p95_mps=("err", lambda x: x.quantile(0.95)) (course, section 2).
    raise NotImplementedError("TODO 8")


# ---------------------------------------------------------------------------
# Part D — plots
# ---------------------------------------------------------------------------


def plot_altitude(df, flight_id, path):
    """Altitude (m) against time (s) of ONE flight, with every outage shaded
    (plt.axvspan from the outage's first time to its last time + DT_S), axis labels,
    a title with the flight_id, saved to path."""
    # TODO 9: select the flight; fig, ax = plt.subplots(); ax.plot(...); one ax.axvspan(...) per
    #         outage_runs() pair; labels, title; fig.savefig(path); plt.close(fig)
    raise NotImplementedError("TODO 9")


# ---- you don't need to change anything below this line (but read it!) ----

COLORS = {"gps": "tab:blue", "day_vision": "tab:orange"}


def plot_tracks(df, path):
    """Every flight in its own panel, local east/north metres (flat-Earth formula, course section 3)."""
    flights = sorted(df["flight_id"].unique())
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))
    for ax, fid in zip(axes.ravel(), flights):
        f = df[(df["flight_id"] == fid)].dropna(subset=["lat", "lon"])
        lat0, lon0 = f["lat"].iloc[0], f["lon"].iloc[0]
        east = EARTH_RADIUS_M * np.radians(f["lon"] - lon0) * np.cos(np.radians(lat0))
        north = EARTH_RADIUS_M * np.radians(f["lat"] - lat0)
        for src, color in COLORS.items():
            m = (f["source"] == src).to_numpy()
            ax.scatter(east[m], north[m], s=4, color=color, label=src)
        ax.set_title(fid)
        ax.set_xlabel("east (m)")
        ax.set_ylabel("north (m)")
        ax.set_aspect("equal", adjustable="datalim")
        ax.legend(markerscale=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)


def main(path="campaign.csv"):
    raw = load_log(path)
    dedup = raw.drop_duplicates()
    df = add_motion(clean(raw))
    summary = flight_summary(df)
    out = outage_table(df)
    shares = state_shares(df)
    err = speed_error(df)
    worst = out["longest_outage_s"].idxmax()

    results = {
        "rows_raw": int(len(raw)),
        "duplicates_removed": int(len(raw) - len(dedup)),
        "glitches_removed": int(len(dedup) - len(df)),
        "rows_clean": int(len(df)),
        "flights": {},
        "longest_outage": {"flight_id": str(worst), "duration_s": float(out.loc[worst, "longest_outage_s"])},
        "speed_error": {src: {"median_mps": float(r["median_mps"]), "p95_mps": float(r["p95_mps"])}
                        for src, r in err.iterrows()},
    }
    for fid in summary.index:
        row = {k: float(v) for k, v in summary.loc[fid].items()}
        row.update({k: float(v) for k, v in out.loc[fid].items()})
        row["rows"], row["n_outages"] = int(row["rows"]), int(row["n_outages"])
        row.update({f"pct_{k}": float(v) for k, v in shares.loc[fid].items()})
        results["flights"][fid] = row
    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)

    plot_tracks(df, "tracks.png")
    plot_altitude(df, worst, "altitude.png")

    pd.set_option("display.width", 120)
    pd.set_option("display.max_columns", 20)
    print(f"rows: {results['rows_raw']} raw, {results['duplicates_removed']} duplicates, "
          f"{results['glitches_removed']} glitches -> {results['rows_clean']} clean\n")
    print(summary.round(2), "\n")
    print(out, "\n")
    print(shares.round(1), "\n")
    print(err.round(2), "\n")
    print("-> results.json, tracks.png, altitude.png")


if __name__ == "__main__":
    try:
        main()
    except NotImplementedError as e:
        print(f"{e} is not written yet — main() needs it. Write it, then run again.")

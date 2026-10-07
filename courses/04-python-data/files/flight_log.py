# Lab 4 — reading a flight log.
#
# flight_log.csv holds one row every 2 seconds of a test flight near Sousse:
#   time_s, lat, lon, alt_m, speed_mps, battery_pct, gps_valid (1 = GPS OK, 0 = GPS lost), source
#
# Write the TODO functions, save (Ctrl+S) and run:      python3 flight_log.py
# Every function receives `rows`: the LIST of DICTS that read_log() returns, one dict per row, e.g.
#   {"time_s": 0.0, "lat": 35.824514, "lon": 10.633998, "alt_m": 0.0, "speed_mps": 0.3,
#    "battery_pct": 99.8, "gps_valid": 1, "source": "gps"}

import csv

LOG_FILE = "flight_log.csv"


def read_log(path):
    """Read the CSV file and return a list of dicts, one per row, with NUMBERS converted:
    time_s, lat, lon, alt_m, speed_mps, battery_pct -> float;  gps_valid -> int;  source stays a str."""
    rows = []
    with open(path, newline="") as f:
        for line in csv.DictReader(f):
            # `line` is a dict of STRINGS, e.g. line["alt_m"] is "120.4" (text, not a number yet)
            # TODO 1: build a new dict with the converted values and append it to rows
            pass
    return rows


def max_altitude(rows):
    """The highest alt_m of the flight (a float)."""
    # TODO 2
    return 0


def average_speed(rows):
    """The average of speed_mps over all the rows."""
    # TODO 3: add up all the speeds, then divide by how many there are
    return 0


def count_gps_lost(rows):
    """How many rows have gps_valid == 0."""
    # TODO 4
    return 0


def longest_outage_rows(rows):
    """The longest run of CONSECUTIVE rows with gps_valid == 0 (0 when the GPS was never lost).
    Example: gps_valid = 1 1 0 0 0 1 0 0 1  ->  3"""
    # TODO 5: walk through the rows with a counter that grows on 0 and goes back to 0 on 1;
    #         remember the biggest value it reached
    return 0


def count_by_source(rows):
    """A dict {source name: number of rows}, e.g. {"gps": 217, "day_vision": 61}."""
    # TODO 6
    return {}


def write_summary(rows, path):
    """Write a text file with EXACTLY these 6 lines (floats with 1 decimal), e.g.:
        rows: 278
        duration_s: 554.0
        max_altitude_m: 151.4
        average_speed_mps: 12.6
        gps_lost_rows: 61
        longest_outage_rows: 31
    duration_s = time_s of the last row - time_s of the first row.
    Use your functions above!"""
    # TODO 7: open(path, "w") and write the lines (each ends with "\n")
    pass


def ascii_altitude(rows, every=10):
    """A text chart of the altitude: one line for every `every`-th row (rows 0, every, 2*every, ...).
    Each line is the time on 5 characters, " s |", then one "#" per 10 m of altitude (rounded):
        "    0 s |"
        "   20 s |########"            (alt_m = 80.0)
        "   40 s |############"        (alt_m = 121.3 -> round(12.13) = 12)
    Return the LIST of lines (strings)."""
    # TODO 8: loop over range(0, len(rows), every); build each line with an f-string ({...:5.0f})
    #         and "#" * a whole number
    return []


# ---- you don't need to change anything below this line (but you can read it!) ----

def plot_track(rows, png_path="track.png"):
    """Draw the track seen from above: blue = GPS, red = GPS lost (day vision)."""
    import warnings
    warnings.filterwarnings("ignore", message="Unable to import Axes3D")   # a harmless warning on this computer
    import matplotlib
    matplotlib.use("Agg")                      # no window: draw into a file
    import matplotlib.pyplot as plt
    if not rows:
        print("No rows to plot yet (write read_log first)")
        return
    gps = [r for r in rows if r["gps_valid"] == 1]
    lost = [r for r in rows if r["gps_valid"] == 0]
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([r["lon"] for r in rows], [r["lat"] for r in rows], color="#bbbbbb", linewidth=1, zorder=1)
    ax.scatter([r["lon"] for r in gps], [r["lat"] for r in gps], s=8, color="#1f77b4", label="GPS", zorder=2)
    ax.scatter([r["lon"] for r in lost], [r["lat"] for r in lost], s=8, color="#d62728",
               label="GPS lost (day vision)", zorder=3)
    ax.plot(rows[0]["lon"], rows[0]["lat"], "k^", markersize=10, label="home")
    ax.set_xlabel("longitude (deg)")
    ax.set_ylabel("latitude (deg)")
    ax.set_title("Test flight seen from above")
    ax.set_aspect(1 / 0.81)                    # cos(35.8 deg): 1 deg of longitude is shorter here
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.savefig(png_path, dpi=80, bbox_inches="tight")
    plt.close(fig)
    print("Track saved in", png_path, "- open it in the editor")


if __name__ == "__main__":
    rows = read_log(LOG_FILE)
    print("rows read          :", len(rows))
    if rows:
        print("first row          :", rows[0])
    print("max altitude (m)   :", max_altitude(rows))
    print("average speed (m/s):", average_speed(rows))
    print("rows without GPS   :", count_gps_lost(rows))
    print("longest outage     :", longest_outage_rows(rows), "rows")
    print("rows per source    :", count_by_source(rows))
    print("altitude (one # = 10 m):")
    for line in ascii_altitude(rows, every=10):
        print("   ", line)
    write_summary(rows, "summary.txt")
    plot_track(rows, "track.png")

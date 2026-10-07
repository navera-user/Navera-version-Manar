import contextlib
import csv
import io
import os
import tempfile

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()
LESSON = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_CSV = os.path.join(LESSON, "files", "flight_log.csv")     # the untouched log
FLOATS = ("time_s", "lat", "lon", "alt_m", "speed_mps", "battery_pct")


def parse(path):
    """The checker's own reading of a log (the right answer)."""
    out = []
    with open(path, newline="") as f:
        for line in csv.DictReader(f):
            r = {k: float(line[k]) for k in FLOATS}
            r["gps_valid"] = int(line["gps_valid"])
            r["source"] = line["source"]
            out.append(r)
    return out


REAL = parse(ORIGINAL_CSV)


def make_rows(gps, alts=None, speeds=None, sources=None):
    """Small invented flights to test the functions on other data than the lab's log."""
    n = len(gps)
    alts = alts or [50.0 + 10 * i for i in range(n)]
    speeds = speeds or [10.0] * n
    sources = sources or ["gps" if g else "day_vision" for g in gps]
    return [{"time_s": 2.0 * i + 100, "lat": 36.0 + i * 1e-4, "lon": 10.0, "alt_m": float(alts[i]),
             "speed_mps": float(speeds[i]), "battery_pct": 90.0 - i, "gps_valid": gps[i], "source": sources[i]}
            for i in range(n)]


def fl(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        m = load_student("flight_log.py")
    return need(m, *names)


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


@c.test("TODO 1: read_log() returns one dict per row",
        hint="Inside the for loop, build a dict for each line and rows.append(it). Don't skip the first row.")
def _():
    (read_log,) = fl("read_log")
    rows = quiet(read_log, ORIGINAL_CSV)
    c.ok(isinstance(rows, list), f"read_log() returned {type(rows).__name__}, expected a list")
    c.ok(len(rows) > 0, "read_log() returned an empty list — did you append each new dict to rows?")
    c.eq(len(rows), len(REAL), "the number of rows")
    c.ok(all(isinstance(r, dict) for r in rows), "each row should be a dict")


@c.test("TODO 1: read_log() converts the numbers (float / int) and keeps source as text",
        hint='float(line["alt_m"]) turns the text "120.4" into the number 120.4; gps_valid uses int(...).')
def _():
    (read_log,) = fl("read_log")
    rows = quiet(read_log, ORIGINAL_CSV)
    c.ok(rows, "read_log() returned no rows")
    got, want = rows[5], REAL[5]
    for k in FLOATS:
        c.ok(k in got, f'a row has no key "{k}" — use exactly the column names of the CSV')
        c.ok(isinstance(got[k], float), f'{k} is {got[k]!r} ({type(got[k]).__name__}), it should be a float')
        c.near(got[k], want[k], tol=1e-9, what=f"row 5 [{k!r}]")
    c.ok(isinstance(got.get("gps_valid"), int), f'gps_valid is {got.get("gps_valid")!r}, it should be an int (0 or 1)')
    c.eq(got["gps_valid"], want["gps_valid"], "row 5 ['gps_valid']")
    c.eq(got.get("source"), want["source"], "row 5 ['source']")


@c.test("TODO 1: read_log() reads the file it is given (not always flight_log.csv)",
        hint="Use the parameter path in open(path, ...), not the name of the file.")
def _():
    (read_log,) = fl("read_log")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "other.csv")
        with open(p, "w") as f:
            f.write("time_s,lat,lon,alt_m,speed_mps,battery_pct,gps_valid,source\n"
                    "0,36.1,10.2,5.5,1.0,99.0,1,gps\n2,36.2,10.3,7.5,3.0,98.5,0,day_vision\n")
        rows = quiet(read_log, p)
    c.eq(len(rows), 2, "the number of rows read from a 2-row file")
    c.near(rows[1]["alt_m"], 7.5, tol=1e-9, what="alt_m of the 2nd row")
    c.eq(rows[1]["gps_valid"], 0, "gps_valid of the 2nd row")


@c.test("TODO 2: max_altitude()",
        hint="Start with the first row's altitude, then for each row: if it is higher, keep it. (Or: max(...) of a list.)")
def _():
    (f,) = fl("max_altitude")
    c.near(quiet(f, REAL), max(r["alt_m"] for r in REAL), tol=1e-9, what="max_altitude(the lab's log)")
    c.near(quiet(f, make_rows([1, 1, 1], alts=[-5, -2, -9])), -2, tol=1e-9,
           what="max_altitude of a flight whose altitudes are -5, -2, -9 (below the take-off point)")


@c.test("TODO 3: average_speed()", hint="total = 0, add every speed_mps in a for loop, then total / len(rows).")
def _():
    (f,) = fl("average_speed")
    c.near(quiet(f, REAL), sum(r["speed_mps"] for r in REAL) / len(REAL), tol=1e-6, what="average_speed(the lab's log)")
    c.near(quiet(f, make_rows([1, 1, 1, 1], speeds=[2, 4, 6, 12])), 6.0, tol=1e-9, what="average of 2, 4, 6, 12")


@c.test("TODO 4: count_gps_lost()", hint='A counter that grows by 1 when r["gps_valid"] == 0.')
def _():
    (f,) = fl("count_gps_lost")
    c.eq(quiet(f, REAL), sum(r["gps_valid"] == 0 for r in REAL), "count_gps_lost(the lab's log)")
    c.eq(quiet(f, make_rows([1, 0, 1, 0, 0])), 3, "count_gps_lost for gps_valid 1 0 1 0 0")
    c.eq(quiet(f, make_rows([1, 1])), 0, "count_gps_lost when the GPS is never lost")


@c.test("TODO 5: longest_outage_rows()",
        hint="Two variables: run (the current outage) and best (the longest so far). On a 0: run += 1 and "
             "update best; on a 1: run = 0. Think about an outage that lasts until the very last row.")
def _():
    (f,) = fl("longest_outage_rows")
    for seq, want in (([1, 1, 0, 0, 0, 1, 0, 0, 1], 3), ([1, 1, 1], 0), ([0, 0, 1, 0], 2),
                      ([1, 0, 1, 0, 0, 0, 0], 4), ([0], 1)):
        c.eq(quiet(f, make_rows(seq)), want, f"longest_outage_rows for gps_valid {' '.join(map(str, seq))}")
    best = run = 0
    for r in REAL:
        run = run + 1 if r["gps_valid"] == 0 else 0
        best = max(best, run)
    c.eq(quiet(f, REAL), best, "longest_outage_rows(the lab's log)")


@c.test("TODO 6: count_by_source() returns a dict",
        hint="Start from an empty dict {}. For each row, add 1 to the number stored under its source; "
             "counts.get(name, 0) gives 0 the first time a name is seen.")
def _():
    (f,) = fl("count_by_source")
    want = {}
    for r in REAL:
        want[r["source"]] = want.get(r["source"], 0) + 1
    c.eq(quiet(f, REAL), want, "count_by_source(the lab's log)")
    c.eq(quiet(f, make_rows([1, 0, 0], sources=["gps", "night_vision", "gps"])), {"gps": 2, "night_vision": 1},
         "count_by_source for the sources gps, night_vision, gps")


@c.test("TODO 7: write_summary() writes the 6 lines",
        hint='One f.write(f"name: {value}\\n") per line; floats with :.1f. Compare with the example in the docstring.')
def _():
    (f,) = fl("write_summary")
    best = run = 0
    for r in REAL:
        run = run + 1 if r["gps_valid"] == 0 else 0
        best = max(best, run)
    want = [f"rows: {len(REAL)}",
            f"duration_s: {REAL[-1]['time_s'] - REAL[0]['time_s']:.1f}",
            f"max_altitude_m: {max(r['alt_m'] for r in REAL):.1f}",
            f"average_speed_mps: {sum(r['speed_mps'] for r in REAL) / len(REAL):.1f}",
            f"gps_lost_rows: {sum(r['gps_valid'] == 0 for r in REAL)}",
            f"longest_outage_rows: {best}"]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "summary.txt")
        quiet(f, REAL, p)
        c.ok(os.path.exists(p), "write_summary() did not create the file it was given")
        with open(p) as fh:
            got = [l.rstrip() for l in fh if l.strip()]
    c.ok(len(got) == 6, f"the summary has {len(got)} lines, expected 6")
    for g, w in zip(got, want):
        c.ok(g == w, f'the line "{g}" should be "{w}"')


@c.test("TODO 8: ascii_altitude()",
        hint='range(0, len(rows), every) gives the row numbers 0, every, 2×every…; :5.0f writes the time on 5 '
             'characters; "#" * 12 makes 12 hashes; round() makes a whole number.')
def _():
    (f,) = fl("ascii_altitude")
    rows = make_rows([1] * 7, alts=[0, 80, 121.3, 54, 9, 150, 300])
    got = quiet(f, rows, 2)
    c.ok(isinstance(got, list), f"ascii_altitude() returned {type(got).__name__}, expected a list of strings")
    c.eq(len(got), 4, "the number of lines for 7 rows with every=2")
    for i, g in zip(range(0, 7, 2), got):
        r = rows[i]
        ok = {f"{r['time_s']:5.0f} s |" + "#" * round(r["alt_m"] / 10),
              f"{r['time_s']:5.0f} s |" + "#" * int(r["alt_m"] / 10 + 0.5)}
        c.ok(g in ok, f'line for row {i} is {g!r}, expected {sorted(ok)[0]!r}')
    c.eq(len(quiet(f, REAL)), len(range(0, len(REAL), 10)), "the number of lines for the lab's log (every=10)")


@c.test("flight_log.py runs, writes summary.txt and draws track.png",
        hint="Run `python3 flight_log.py` in the terminal and read the error.")
def _():
    code, out = sh("python3 flight_log.py", timeout=60)
    c.ok(code == 0, "flight_log.py stopped with an error:\n" + out[-700:])
    c.file_exists("summary.txt")
    c.file_exists("track.png")
    with open("track.png", "rb") as fh:
        c.ok(fh.read(8) == b"\x89PNG\r\n\x1a\n", "track.png is not a PNG image")


c.run()

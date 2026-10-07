import csv
import math
import os

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
SAMPLE = "/data/academy/28-simulator"
SIM = os.path.expanduser("~/.navera_sim")


def F():
    return load_student("flight_log.py")


def sample_rows():
    (load,) = need(F(), "load_flight")
    rows = load(f"{SAMPLE}/sample_flight.csv")
    if not rows:
        raise CheckFailed("load_flight() returned no rows (TODO 1)")
    return rows


def no_simulator():
    try:
        return bool(getattr(load_student("answers.py"), "NO_SIMULATOR", False))
    except Exception:
        return False


@c.test("load_flight(): rows as dicts, numbers as floats, empty cells as None",
        hint="csv.DictReader gives text; convert the NUMBERS columns with float(), and '' to None.")
def _():
    rows = sample_rows()
    c.eq(len(rows), 393, "number of rows of the sample flight")
    r = rows[100]
    c.ok(isinstance(r["t_s"], float) and isinstance(r["truth_lat"], float),
         f"t_s and truth_lat should be floats, got {type(r['t_s']).__name__} and {type(r['truth_lat']).__name__}")
    c.ok(rows[0]["navera_lat"] is None, f"an empty navera_lat should become None, got {rows[0]['navera_lat']!r}")
    c.ok(isinstance(r["phase"], str), "phase should stay text")


@c.test("first_time(): when something happened", hint="Loop over the rows; return r['t_s'] at the first row with "
                                                      "r['t_s'] >= after and r[column] == value; None if none.")
def _():
    (ft,) = need(F(), "first_time")
    rows = sample_rows()
    c.near(ft(rows, "gps_mode", "jammed"), 110.8, 0.05, "first_time(rows, 'gps_mode', 'jammed')")
    c.near(ft(rows, "gps_mode", "spoof_jump"), 210.6, 0.05, "first_time(rows, 'gps_mode', 'spoof_jump')")
    c.near(ft(rows, "gps_mode", "ok", after=150.0), 171.2, 0.05, "first_time(rows, 'gps_mode', 'ok', after=150)")
    c.eq(ft(rows, "gps_mode", "off"), None, "first_time(rows, 'gps_mode', 'off')")


@c.test("switch_delay(): from the jam to NAVERA leaving GPS",
        hint="t_jam = first_time(rows, 'gps_mode', 'jammed'); then the first row with t_s >= t_jam and "
             "navera_source != 'GPS'. None when there is no jam.")
def _():
    (sd,) = need(F(), "switch_delay")
    c.near(sd(sample_rows()), 0.0, 0.05, "switch_delay(sample)")
    mk = lambda t, g, s: {"t_s": float(t), "gps_mode": g, "navera_source": s}      # noqa: E731
    rows = [mk(0, "ok", "GPS"), mk(1, "ok", "GPS"), mk(2, "jammed", "GPS"), mk(3, "jammed", "GPS"),
            mk(4, "jammed", "DAY VISION")]
    c.near(sd(rows), 2.0, 1e-9, "switch_delay(jam at 2 s, switch at 4 s)")
    c.eq(sd(rows[:2]), None, "switch_delay(no jam)")


@c.test("median_error(): the typical error of each source",
        hint="Keep r['navera_err_m'] of the rows with that source, skip None, sort, take the middle "
             "(the average of the two middle ones for an even count).")
def _():
    (me,) = need(F(), "median_error")
    rows = sample_rows()
    c.near(me(rows, "GPS"), 2.8, 0.05, "median_error(sample, 'GPS')")
    c.near(me(rows, "DAY VISION"), 20.4, 0.05, "median_error(sample, 'DAY VISION')")
    mk = lambda e: {"navera_source": "X", "navera_err_m": e}                        # noqa: E731
    c.near(me([mk(1.0), mk(None), mk(9.0), mk(3.0), mk(5.0)], "X"), 4.0, 1e-9, "median of 1, 9, 3, 5 (None skipped)")
    c.eq(me(rows, "CELESTIAL"), None, "median_error(sample, 'CELESTIAL')")


@c.test("log_lines(): the lines of a log containing a word",
        hint="with open(path, errors='replace') as f: keep ln.rstrip('\\n') for each line ln that contains word.")
def _():
    (ll,) = need(F(), "log_lines")
    err = ll(f"{SAMPLE}/sample_estimator.log", "[ERROR]")
    c.eq(len(err), 1, "number of [ERROR] lines in the sample estimator log")
    c.ok("implausible jump" in err[0] and not err[0].endswith("\n"), f"unexpected line: {err[0]!r}")
    c.eq(len(ll(f"{SAMPLE}/sample_estimator.log", "re-accepted")), 2, "lines with 're-accepted'")


@c.test("your own simulator run: NAVERA's logs exist in ~/.navera_sim",
        hint="Take the simulator (Hardware button), then Step 2: run_sim.sh. (No simulator today? set NO_SIMULATOR = True in "
             "answers.py — the teacher must agree.)")
def _():
    if no_simulator():
        c.skip("NO_SIMULATOR = True: you worked on the recorded sample")
    p = os.path.join(SIM, "estimator.log")
    c.ok(os.path.exists(p), "~/.navera_sim/estimator.log does not exist: run the simulator first (Step 2)")
    c.ok("start: ros2 run navera_estimator" in open(p, errors="replace").read(),
         "~/.navera_sim/estimator.log has no start line: did the simulator really start?")


@c.test("your own flight: recorded, en route, GPS jammed, NAVERA switched",
        hint="Record with `python3 sim_ctl.py record` during the whole flight (Step 3), jam the GPS 60 s while "
             "the drone is flying to the destination (Step 5).")
def _():
    if no_simulator():
        c.skip("NO_SIMULATOR = True: you worked on the recorded sample")
    c.ok(os.path.exists("flight.csv"), "flight.csv does not exist: record your flight (Step 3)")
    with open("flight.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    enroute = [r for r in rows if r.get("phase") == "enroute"]
    c.ok(len(enroute) >= 60, f"flight.csv has {len(enroute)} s en route (at least 60 needed)")
    jam = [r for r in enroute if r.get("gps_mode") == "jammed"]
    c.ok(len(jam) >= 30, f"only {len(jam)} s with the GPS jammed while en route (jam it about 60 s)")
    c.ok(any(r.get("navera_source") not in ("GPS", "", "—") and r.get("navera_state") in ("FIX", "DEGRADED")
             for r in jam), "while jammed, NAVERA never used another source — which vision profile did you choose?")


@c.test("your own flight: the spoof was refused by the arbiter",
        hint="Step 5: Faults → GPS → Spoof jump for 30 s while en route. Then grep implausible "
             "~/.navera_sim/estimator.log")
def _():
    if no_simulator():
        c.skip("NO_SIMULATOR = True: you worked on the recorded sample")
    p = os.path.join(SIM, "estimator.log")
    c.ok(os.path.exists(p), "~/.navera_sim/estimator.log does not exist: run the simulator first")
    text = open(p, errors="replace").read()
    c.ok("GPS refused" in text, "the arbiter never refused the GPS in your runs (no 'GPS refused' in estimator.log)")


ANSWERS = {"Q1": "b", "Q3": "estimator.log"}


@c.test("quiz (answers.py)", hint="Q4: first_time(rows, 'navera_source', 'GPS', after=t_ok) - t_ok. "
                                  "Q5: the formula of lesson 27. Q6: median_error(rows, 'DAY VISION').")
def _():
    m = load_student("answers.py")
    wrong = []
    for q, good in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().lower().strip(")").split("/")[-1]
        if v != good:
            wrong.append(f"{q} = {v!r}" if v else f"{q} is empty")
    for q, good, tol in (("Q2", 8181, 0), ("Q4", 2.0, 0.5), ("Q5", 50.0, 0.5), ("Q6", 20.4, 0.15)):
        (v,) = need(m, q)
        try:
            ok = math.isfinite(float(v)) and abs(float(v) - good) <= tol
        except (TypeError, ValueError):
            ok = False
        if not ok:
            wrong.append(f"{q} = {v!r}")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


c.run()

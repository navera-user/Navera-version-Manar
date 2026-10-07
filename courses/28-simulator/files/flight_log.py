#!/usr/bin/env python3
"""flight_log.py — read a simulator flight like an engineer.

    python3 flight_log.py                      # YOUR flight: flight.csv, events.log, ~/.navera_sim/estimator.log
    python3 flight_log.py --sample             # the recorded sample flight in /data/academy/28-simulator/

flight.csv has one line per second (written by `python3 sim_ctl.py record`):
    t_s, phase, gps_mode, navera_state, navera_source, navera_lat, navera_lon, navera_err_m,
    truth_lat, truth_lon, truth_alt_m, truth_speed_mps, ap_mode, ap_err_m, reason
Empty cells mean "no value" (e.g. no NAVERA position at that second).
"""
import csv
import os
import sys

NUMBERS = ("t_s", "navera_lat", "navera_lon", "navera_err_m", "truth_lat", "truth_lon",
           "truth_alt_m", "truth_speed_mps", "ap_err_m")
SAMPLE = "/data/academy/28-simulator"


def load_flight(path):
    """The rows of flight.csv as a list of dicts. The columns in NUMBERS become floats,
    and an empty cell becomes None. The other columns stay text."""
    rows = []
    # TODO 1: open the file, read it with csv.DictReader(f), and for each row r:
    #         for k in NUMBERS: r[k] = float(r[k]) if the cell is not empty, else None
    #         then rows.append(r)
    return rows


def first_time(rows, column, value, after=0.0):
    """t_s of the first row at or after `after` where row[column] == value, or None."""
    return None   # TODO 2: a for loop over rows, return r["t_s"] at the first match


def switch_delay(rows):
    """Seconds between the first row where the GPS receiver is 'jammed' and the first row
    after it where NAVERA's source is no longer 'GPS'. None if there is no jam or no switch."""
    return None   # TODO 3: use first_time() for the jam, then a loop for the switch


def median_error(rows, source):
    """The median of navera_err_m over the rows whose navera_source == source (rows without
    an error are skipped). None when there is no such row."""
    return None   # TODO 4: collect the errors of that source (skip None), sort, take the middle


def log_lines(path, word):
    """The lines of a log file that contain `word` (a list of strings, without the newline)."""
    return []     # TODO 5: open(path, errors="replace"), keep the lines containing word, without "\n"


# ---- you don't need to change anything below this line (but you can read it!) ----

def report(flight, events, estimator):
    rows = load_flight(flight)
    if not rows:
        print("load_flight() returned nothing: complete TODO 1 first")
        return
    print(f"{flight}: {len(rows)} rows (one per second)")
    for phase in ("waiting_gps", "arming", "takeoff", "enroute"):
        t = first_time(rows, "phase", phase)
        print(f"  phase {phase:12s} from t = {t if t is None else round(t)} s")
    t_jam = first_time(rows, "gps_mode", "jammed")
    print(f"  GPS jammed at t = {t_jam if t_jam is None else round(t_jam)} s; "
          f"NAVERA left GPS {switch_delay(rows)} s later")
    t_sp = first_time(rows, "gps_mode", "spoof_jump")
    print(f"  GPS spoofed (2 km jump) at t = {t_sp if t_sp is None else round(t_sp)} s")
    for src in ("GPS", "DAY VISION"):
        n = sum(1 for r in rows if r["navera_source"] == src)
        print(f"  NAVERA used {src:10s} {n:4d} s, median error {median_error(rows, src)} m")
    if os.path.exists(events):
        print(f"\n{events}: the simulator's events about faults and NAVERA's state")
        for ln in log_lines(events, "FAULT") + log_lines(events, "NAVERA:")[:12]:
            print("  " + ln[:160])
    if os.path.exists(estimator):
        print(f"\n{estimator}: what the arbiter itself logged (ERROR / WARN)")
        for ln in (log_lines(estimator, "[ERROR]") + log_lines(estimator, "[WARN]"))[:12]:
            print("  " + ln[:160])


if __name__ == "__main__":
    if "--sample" in sys.argv:
        report(f"{SAMPLE}/sample_flight.csv", f"{SAMPLE}/sample_events.log", f"{SAMPLE}/sample_estimator.log")
    else:
        report("flight.csv", "events.log", os.path.expanduser("~/.navera_sim/estimator.log"))

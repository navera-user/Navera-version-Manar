#!/usr/bin/env python3
"""measure_project.py — before/after measurement of the example project
"refuse GPS fixes computed from fewer than 4 satellites".

    python3 measure_project.py

Plays /data/academy/30-final-project/nmea_bench.txt (1800 s of a SIMULATED receiver standing
still at a point in Sousse, Tunisia) through the same parsing as gps_node (pynmea2,
checksum required) and compares two acceptance rules on the SAME epochs:
  BEFORE  the base rule: checksum OK, GGA quality 1, 2, 4 or 5 and a position
  AFTER   gps_node.fix_problem() from your project branch returns "" (usable fix)
One epoch = one GGA line of the file (1 per second), even when its checksum is wrong.

Primary metric : p95 horizontal error of the ACCEPTED fixes (m), lower is better.
Guard-rail     : availability = accepted epochs / all epochs, higher is better.
Confidence     : moving-block bootstrap over epochs (blocks of 60 s, 2000 resamples, seed 30),
                 the SAME resampled epochs for before and after (a paired comparison).
Writes results.json (the format of stats_tools.write_results).
"""
import json
import math

import numpy as np
import pynmea2

from stats_tools import block_bootstrap_ci, percentile, write_results

DATA = "/data/academy/30-final-project"
BLOCK_LEN, N_BOOT, SEED = 60, 2000, 30
VALID_QUAL = (1, 2, 4, 5)
MAX_AVAILABILITY_LOSS = 0.10          # acceptance criterion, fixed in the proposal BEFORE measuring

FIX_IMPORT_ERROR = None
try:                                   # exists only once you made the change on your branch
    from gps_pkg.nodes.gps_node import fix_problem
except Exception as e:                 # ImportError, or a SyntaxError in your edited gps_node.py
    fix_problem = None
    FIX_IMPORT_ERROR = e


def explain_import_error(e):
    """Say why gps_node.fix_problem could not be imported, with the real error and the likely fix."""
    err = f"{type(e).__name__}: {e}"
    if isinstance(e, ImportError) and "cannot import name 'fix_problem'" in str(e):
        print("AFTER : gps_node.fix_problem() does not exist yet on your branch — make the change "
              "(Step 9), then run me again")
    elif isinstance(e, ImportError):
        print(f"AFTER : NAVERA's gps_node cannot be imported ({err}).")
        print("        Likely cause: ROS and your NAVERA copy are not sourced in this terminal. Run")
        print("            source ~/navera/install/setup.bash")
        print("        then run me again. Still failing? `python3 -c \"import gps_pkg.nodes.gps_node\"` "
              "shows the full error.")
    else:
        print(f"AFTER : your gps_node.py does not load ({err}).")
        print("        Fix that line in ~/navera/gps_pkg/gps_pkg/nodes/gps_node.py; "
              "`python3 -c \"import gps_pkg.nodes.gps_node\"` shows the full error.")


def error_m(lat, lon, truth):
    """Horizontal distance (m) between (lat, lon) and the true point (local flat Earth)."""
    m_lat = 111_195.0
    return math.hypot((lat - truth["lat"]) * m_lat,
                      (lon - truth["lon"]) * m_lat * math.cos(math.radians(truth["lat"])))


def summary(accepted, errors):
    """TODO 4 — the metrics of one rule.

    accepted: bool array (one per epoch), errors: float array (one per epoch, nan when the epoch
    has no position). Use only the errors of ACCEPTED epochs. Returns a dict:
      n_epochs, n_accepted, availability (n_accepted / n_epochs),
      cep50 (= percentile 50), p95 (= percentile 95), max  — all nan when nothing is accepted."""
    # TODO 4: convert to numpy arrays, keep errors[accepted], build and return the dict.
    #         Use percentile() from stats_tools (imported above), not np.percentile.
    return None


# ---- you don't need to change anything below this line (except TODO 5 in main) ----

def load_epochs(path=f"{DATA}/nmea_bench.txt", truth_path=f"{DATA}/truth.json"):
    """One dict per GGA line: crc_ok, qual, has_pos, sats (None if empty), error (nan if no pos)."""
    truth = json.load(open(truth_path))
    epochs = []
    for line in open(path):
        line = line.strip()
        if not line.startswith("$GPGGA"):
            continue
        try:
            m = pynmea2.parse(line, check=True)
        except pynmea2.ParseError:
            epochs.append({"crc_ok": False, "qual": 0, "has_pos": False, "sats": None, "error": math.nan})
            continue
        has_pos = bool(m.lat) and bool(m.lon)
        epochs.append({"crc_ok": True, "qual": int(m.gps_qual or 0), "has_pos": has_pos,
                       "sats": int(m.num_sats) if m.num_sats else None,
                       "error": error_m(m.latitude, m.longitude, truth) if has_pos else math.nan})
    return epochs


def rule_before(e):
    return e["crc_ok"] and e["has_pos"] and e["qual"] in VALID_QUAL


def rule_after(e):
    return e["crc_ok"] and fix_problem(e["qual"], e["has_pos"], e["sats"]) == ""


def show(name, s):
    print(f"{name:6s}: {s['n_accepted']:4d} of {s['n_epochs']} epochs accepted "
          f"(availability {100 * s['availability']:.1f} %), CEP50 {s['cep50']:.2f} m, "
          f"p95 {s['p95']:.2f} m, max {s['max']:.1f} m")


def main():
    epochs = load_epochs()
    err = np.array([e["error"] for e in epochs])
    acc_b = np.array([rule_before(e) for e in epochs])
    sb = summary(acc_b, err)
    if sb is None:
        print("summary() returns None — complete TODO 4")
        return
    print(f"{len(epochs)} epochs (GGA lines), {sum(e['crc_ok'] for e in epochs)} with a valid checksum")
    show("BEFORE", sb)
    if fix_problem is None:
        explain_import_error(FIX_IMPORT_ERROR)
        return
    acc_a = np.array([rule_after(e) for e in epochs])
    sa = summary(acc_a, err)
    show("AFTER", sa)

    # TODO 5 — the paired block bootstrap and results.json
    # a) Write small functions metric(idx) -> float that compute, on the resampled epochs idx:
    #    the p95 of a rule (use summary(acc[idx], err[idx])), the availability of a rule, and the
    #    DIFFERENCES after - before of both (same idx for both rules: a paired comparison).
    # b) A 95 % CI for each with block_bootstrap_ci(len(epochs), metric, BLOCK_LEN, N_BOOT, 0.05, SEED).
    # c) The decision from the acceptance criterion of the proposal (MAX_AVAILABILITY_LOSS):
    #    "accept" when both CIs are on the good side, "reject" when one CI is entirely on the bad
    #    side, otherwise "inconclusive".
    # d) write_results("results.json", ...) — see its docstring in stats_tools.py; put the
    #    availability under secondary={"availability": {"before": ..., "after": ..., "difference": ...,
    #    "limit": -MAX_AVAILABILITY_LOSS, "better": "higher"}}  (a guard-rail: the check applies its limit).
    print("TODO 5: bootstrap + results.json not written yet")


if __name__ == "__main__":
    main()

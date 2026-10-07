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

try:                                   # exists only once you made the change on your branch
    from gps_pkg.nodes.gps_node import fix_problem
except ImportError:
    fix_problem = None


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
    accepted = np.asarray(accepted, dtype=bool)
    errors = np.asarray(errors, dtype=float)
    e = errors[accepted]
    n = len(accepted)
    if len(e) == 0:
        return {"n_epochs": n, "n_accepted": 0, "availability": 0.0 if n else math.nan,
                "cep50": math.nan, "p95": math.nan, "max": math.nan}
    return {"n_epochs": n, "n_accepted": int(len(e)), "availability": len(e) / n,
            "cep50": percentile(e, 50), "p95": percentile(e, 95), "max": float(np.max(e))}


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
        print("AFTER : gps_node.fix_problem() does not exist yet on your branch — make the change "
              "(Step 9), then run me again")
        return
    acc_a = np.array([rule_after(e) for e in epochs])
    sa = summary(acc_a, err)
    show("AFTER", sa)

    # TODO 5 — the paired block bootstrap and results.json
    n = len(epochs)

    def p95(acc):
        return lambda idx: summary(acc[idx], err[idx])["p95"]

    def avail(acc):
        return lambda idx: float(np.mean(acc[idx]))

    def ci(metric):
        return list(block_bootstrap_ci(n, metric, BLOCK_LEN, N_BOOT, 0.05, SEED))

    d_p95 = {"value": sa["p95"] - sb["p95"], "ci95": ci(lambda idx: p95(acc_a)(idx) - p95(acc_b)(idx))}
    d_av = {"value": sa["availability"] - sb["availability"],
            "ci95": ci(lambda idx: avail(acc_a)(idx) - avail(acc_b)(idx))}
    improves = d_p95["ci95"][1] < 0
    affordable = d_av["ci95"][0] >= -MAX_AVAILABILITY_LOSS
    if improves and affordable:
        decision = "accept"
    elif d_p95["ci95"][0] > 0 or d_av["ci95"][1] < -MAX_AVAILABILITY_LOSS:
        decision = "reject"
    else:
        decision = "inconclusive"
    out = write_results(
        "results.json", project="min-satellites",
        metric="p95 horizontal error of accepted GPS fixes", unit="m", better="lower",
        data="nmea_bench.txt, 1800 s simulated receiver standing still (Sousse)", n=n,
        before={"value": sb["p95"], "ci95": ci(p95(acc_b))},
        after={"value": sa["p95"], "ci95": ci(p95(acc_a))},
        difference=d_p95,
        bootstrap={"method": "moving-block", "block_len": BLOCK_LEN, "n_boot": N_BOOT, "seed": SEED},
        acceptance=f"accept if the 95 % CI of the p95 difference is below 0 m and the 95 % CI of the "
                   f"availability difference stays above -{MAX_AVAILABILITY_LOSS:.2f}",
        decision=decision,
        secondary={"availability": {"before": {"value": sb["availability"], "ci95": ci(avail(acc_b))},
                                    "after": {"value": sa["availability"], "ci95": ci(avail(acc_a))},
                                    "difference": d_av}})
    print(f"\np95 difference (after - before): {out['difference']['value']:+.2f} m, "
          f"95 % CI [{out['difference']['ci95'][0]:+.2f}, {out['difference']['ci95'][1]:+.2f}] m")
    print(f"availability difference: {100 * d_av['value']:+.1f} points, 95 % CI "
          f"[{100 * d_av['ci95'][0]:+.1f}, {100 * d_av['ci95'][1]:+.1f}]")
    print(f"decision: {decision}  -> results.json written")


if __name__ == "__main__":
    main()

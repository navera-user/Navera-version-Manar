#!/usr/bin/env python3
"""Teacher only: recompute every number of mission 15 (check.py constants, TEACHER.md answer key) from the
course reference (solutions/_navera_lite/navera_lite/gnss.py) and the data made by make_dataset.py.

    python3 solutions/15-gps-nmea/expected.py

Paste the printed values into courses/15-gps-nmea/check.py (EXAM_*, LAB) if the data or the reference change.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite import gnss as g          # noqa: E402
from navera_lite import geo                # noqa: E402

LOG = os.path.join(ACADEMY, "datasets", "15-gps-nmea", "sousse_drive.nmea")
EXAM = os.path.join(ACADEMY, "courses", "15-gps-nmea", "hidden", "exam_drive.nmea")
FORGE_BASE = "$GPGGA,052200.00,3545.89257,N,01045.14417,E,1,12,0.77,2.1,M,32.0,M,,*59"


def chain_counts(lines):
    """What check.py measures on the exam log: is_valid over all lines, fix_state(parse_gga) over GGA-like lines."""
    bad = sum(1 for ln in lines if not g.is_valid(ln))
    count, reasons = {}, {}
    for ln in lines:
        if ln.startswith("$") and ln[3:6] == "GGA":
            st = g.fix_state(g.parse_gga(ln))
            count[st[0]] = count.get(st[0], 0) + 1
            if st[0] != "FIX" and not st[1].startswith("σ ") or st[1] == "σ unknown":
                reasons[st[1]] = reasons.get(st[1], 0) + 1
    return bad, count, reasons


def main():
    size = os.path.getsize(LOG)
    lines = g.read_log(LOG)
    print(f"public log: {len(lines)} lines, {size} bytes, {size / 1069:.1f} B/s, {size / 1069 / 960 * 100:.1f} % of 9600 baud")
    bad, count, reasons = chain_counts(lines)
    print(f"public: bad lines {bad}; GGA-like states {count}; reasons {reasons}")
    imp = [ln for ln in lines if (p := g.parse_gga(ln)) and p["qual"] in g.USABLE_QUALITIES and p["lat"] is None]
    print("IMPOSSIBLE_UTC lines:", imp)
    st = g.dops([5, 350, 175, 190, 120, 260], [30, 55, 40, 65, 75, 80])
    print(f"STREET_EDOP {st['EDOP']:.4f}  STREET_NDOP {st['NDOP']:.4f}")
    exam = g.read_log(EXAM)
    bad, count, reasons = chain_counts(exam)
    print(f"EXAM_BAD = {bad}\nEXAM_STATES = {count}\nEXAM_REASONS = {reasons}")
    # a forged example (degree digits of the latitude swapped: 35 → 53)
    forged = FORGE_BASE.replace("3545.89257", "5345.89257")
    a, b = g.parse_gga(FORGE_BASE), g.parse_gga(forged)
    print(f"forge example: valid {g.is_valid(forged)}, moved {geo.haversine_m(a['lat'], a['lon'], b['lat'], b['lon']) / 1000:.3f} km:"
          f" {forged}")
    print("Run python3 run_gnss.py dop / drive with the solution for HDOP_MAX, DOP_MAX_DIFF, N_*, SIGMA_MAX_M, JUMP_UTC.")


if __name__ == "__main__":
    main()

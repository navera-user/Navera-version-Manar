#!/usr/bin/env python3
"""measure_project.py — the before/after measurement of the example project
"refuse GPS fixes computed from fewer than 4 satellites".

    python3 measure_project.py

Plays /data/academy/30-final-project/nmea_bench.txt (600 s, simulated receiver standing still)
through the same parsing as gps_node (pynmea2, checksum required) and compares:
  BEFORE  the base rule: GGA quality 1, 2, 4 or 5 and a position = a fix
  AFTER   gps_node.fix_problem() from my branch (also refuses fewer than 4 satellites)
For every accepted fix: the error against the true point (truth.json).
"""
import json
import math

import pynmea2

from gps_pkg.nodes.gps_node import fix_problem

DATA = "/data/academy/30-final-project"


def error_m(lat, lon, t):
    m_lat = 111_195.0
    return math.hypot((lat - t["lat"]) * m_lat, (lon - t["lon"]) * m_lat * math.cos(math.radians(t["lat"])))


def pct(v, q):
    s = sorted(v)
    return s[min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1))))]


def main():
    truth = json.load(open(f"{DATA}/truth.json"))
    before, after, n_gga = [], [], 0
    for line in open(f"{DATA}/nmea_bench.txt"):
        try:
            m = pynmea2.parse(line.strip(), check=True)
        except pynmea2.ParseError:
            continue
        if not isinstance(m, pynmea2.types.talker.GGA):
            continue
        n_gga += 1
        qual = int(m.gps_qual or 0)
        has_pos = bool(m.lat) and bool(m.lon)
        sats = int(m.num_sats) if m.num_sats else None
        if has_pos and qual in (1, 2, 4, 5):
            before.append(error_m(m.latitude, m.longitude, truth))
        if fix_problem(qual, has_pos, sats) == "":
            after.append(error_m(m.latitude, m.longitude, truth))
    print(f"{n_gga} GGA sentences with a valid checksum")
    for name, e in (("BEFORE", before), ("AFTER", after)):
        print(f"{name:6s}: {len(e):3d} fixes accepted ({100 * len(e) / n_gga:.0f} %), error median "
              f"{pct(e, 50):.1f} m, p90 {pct(e, 90):.1f} m, max {max(e):.1f} m")


if __name__ == "__main__":
    main()

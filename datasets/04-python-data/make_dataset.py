#!/usr/bin/env python3
"""Make the synthetic flight-test campaign of lesson 04 (deterministic: same file every time).

Four flights in Oman (SYNTHETIC numbers, made for the course; NAVERA's real recordings cover
Sousse, Tunisia). One row every 2 s per flight. Columns:
    flight_id, time_s, lat, lon, alt_m, speed_mps, battery_pct, gps_valid, source, state
The log is deliberately messy, like real logs:
  * exact duplicate rows (the logger wrote a line twice),
  * glitch rows: one fix at lat = lon = 0 ("Null Island"), one altitude of 9999 m,
  * empty cells: some battery_pct and speed_mps values are missing,
  * GPS outages (gps_valid = 0): day vision gives the position (state DEGRADED), and
    sometimes nothing does (source "none", empty lat/lon, state NO_FIX).

    python3 make_dataset.py ../../courses/04-python-data/files/campaign.csv
"""
import csv
import math
import random
import sys

M_PER_DEG = 111_320.0
DT = 2.0

FLIGHTS = [
    # id, home (lat, lon), waypoints (east, north m), cruise m/s, alt m, outages [(t0, t1, kind)]
    ("muscat_coast", (23.6140, 58.5900), [(0, 0), (2500, 600), (3200, 1800), (0, 0)], 12.0, 100.0,
     [(300, 360, "day_vision")]),
    ("sohar_port", (24.3600, 56.7400), [(0, 0), (1800, 2200), (3500, 2000), (1500, -400), (0, 0)], 14.0, 120.0,
     [(200, 260, "day_vision"), (420, 480, "day_vision"), (480, 520, "none")]),
    ("nizwa_foothills", (22.9300, 57.5300), [(0, 0), (-1200, 2600), (800, 3400), (0, 0)], 10.0, 250.0,
     [(560, 1e9, "day_vision")]),
    ("barr_al_hikman", (20.6000, 58.4000),
     [(0, 0), (3000, 0), (3000, 400), (0, 400), (0, 800), (3000, 800), (0, 0)], 20.0, 150.0,
     [(600, 616, "day_vision")]),
]


def to_latlon(home, e, n):
    return home[0] + n / M_PER_DEG, home[1] + e / (M_PER_DEG * math.cos(math.radians(home[0])))


def fly(rnd, waypoints, cruise, alt):
    """[(t, e, n, alt, v)] : climb, waypoints, descent."""
    rows, t = [], 0.0
    climb = int(alt / 8.0)
    for i in range(climb):
        rows.append([t, 0.0, 0.0, 8.0 * i, 0.4 + rnd.random() * 0.3]); t += DT
    for (e0, n0), (e1, n1) in zip(waypoints, waypoints[1:]):
        length = math.hypot(e1 - e0, n1 - n0)
        done = 0.0
        while done < length - 1e-9:
            v = cruise + rnd.uniform(-0.6, 0.6)
            done = min(length, done + v * DT)
            f = done / length
            rows.append([t, e0 + f * (e1 - e0), n0 + f * (n1 - n0), alt + rnd.uniform(-1.5, 1.5), v]); t += DT
    for i in range(climb):
        rows.append([t, 0.0, 0.0, max(0.0, alt - 8.0 * (i + 1)), 0.4 + rnd.random() * 0.3]); t += DT
    return rows


def main(out):
    rnd = random.Random(404)
    lines = []
    for fid, home, wps, cruise, alt, outages in FLIGHTS:
        rows = fly(rnd, wps, cruise, alt)
        total = len(rows)
        for k, (t, e, n, a, v) in enumerate(rows):
            kind = next((kd for t0, t1, kd in outages if t0 <= t < t1), None)
            if kind == "day_vision" and fid == "nizwa_foothills" and t >= rows[-1][0] - 20:
                kind = "none"                         # vision gives up over the landing site
            sig = 1.5 if kind is None else 6.0
            e += rnd.gauss(0, sig); n += rnd.gauss(0, sig)
            lat, lon = to_latlon(home, e, n)
            batt = 100.0 - 45.0 * k / (total - 1) + rnd.uniform(-0.3, 0.3)
            speed = f"{v + rnd.gauss(0, 0.3):.2f}" if rnd.random() > 0.03 else ""
            battery = f"{min(100.0, batt):.1f}" if rnd.random() > 0.04 else ""
            if kind is None:
                valid, src, state = 1, "gps", "FIX"
            elif kind == "day_vision":
                valid, src, state = 0, "day_vision", "DEGRADED"
            else:
                valid, src, state = 0, "none", "NO_FIX"
            slat, slon = (f"{lat:.6f}", f"{lon:.6f}") if src != "none" else ("", "")
            alt_s = f"{a:.1f}"
            if fid == "muscat_coast" and t == 100.0:
                slat, slon = "0.000000", "0.000000"    # glitch: Null Island
            if fid == "nizwa_foothills" and t == 200.0:
                alt_s = "9999.0"                        # glitch: impossible altitude
            line = [fid, f"{t:.0f}", slat, slon, alt_s, speed, battery, valid, src, state]
            lines.append(line)
            if (fid, t) in (("muscat_coast", 50.0), ("sohar_port", 150.0), ("sohar_port", 700.0)):
                lines.append(list(line))               # the logger wrote it twice
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flight_id", "time_s", "lat", "lon", "alt_m", "speed_mps", "battery_pct",
                    "gps_valid", "source", "state"])
        w.writerows(lines)
    print(out, len(lines), "rows")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "campaign.csv")

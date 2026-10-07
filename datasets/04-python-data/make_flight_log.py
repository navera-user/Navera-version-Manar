#!/usr/bin/env python3
"""Make the synthetic flight log of lesson 04 (deterministic: same file every time).

A multirotor takes off near Sousse, climbs to 120 m, flies a 5-leg loop at ~14 m/s
(150 m over the third leg), comes home and lands. The GPS is lost twice (jamming);
day vision gives the position meanwhile (a little noisier). One row every 2 s.

    python3 make_flight_log.py ../../courses/04-python-data/files/flight_log.csv
"""
import csv
import math
import random
import sys

HOME = (35.8245, 10.6340)            # lat, lon (deg)
M_PER_DEG = 111_320.0                # metres per degree of latitude (same constant as day_pkg/vision_nav.py)
DT = 2.0
WAYPOINTS = [(0, 0), (1500, 300), (2200, 1400), (800, 2000), (-300, 1000), (0, 0)]   # east, north (m)
CRUISE = 14.0
LOST = [(150, 210), (330, 392)]      # GPS lost for time_s in [start, end)


def to_latlon(e, n):
    lat = HOME[0] + n / M_PER_DEG
    lon = HOME[1] + e / (M_PER_DEG * math.cos(math.radians(HOME[0])))
    return lat, lon


def main(out):
    rnd = random.Random(2026)
    rows = []
    t = 0.0
    # 1. climb to 120 m (15 rows)
    for i in range(15):
        rows.append([t, 0.0, 0.0, 8.0 * i, 0.3 + rnd.random() * 0.4])
        t += DT
    # 2. the loop
    e, n = 0.0, 0.0
    for leg, ((e0, n0), (e1, n1)) in enumerate(zip(WAYPOINTS, WAYPOINTS[1:])):
        length = math.hypot(e1 - e0, n1 - n0)
        done = 0.0
        while done < length:
            v = CRUISE + rnd.uniform(-0.9, 0.9)
            done = min(length, done + v * DT)
            f = done / length
            e, n = e0 + f * (e1 - e0), n0 + f * (n1 - n0)
            alt = 150.0 if leg == 2 else 120.0
            rows.append([t, e, n, alt + rnd.uniform(-1.5, 1.5), v])
            t += DT
    # 3. land (15 rows)
    for i in range(15):
        rows.append([t, 0.0, 0.0, max(0.0, 112.0 - 8.0 * i), 0.3 + rnd.random() * 0.4])
        t += DT
    total = len(rows)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "lat", "lon", "alt_m", "speed_mps", "battery_pct", "gps_valid", "source"])
        for k, (t, e, n, alt, v) in enumerate(rows):
            lost = any(a <= t < b for a, b in LOST)
            if lost:      # day vision: a few metres of noise
                e += rnd.gauss(0, 6)
                n += rnd.gauss(0, 6)
            else:
                e += rnd.gauss(0, 1.5)
                n += rnd.gauss(0, 1.5)
            lat, lon = to_latlon(e, n)
            batt = 100.0 - 38.0 * k / (total - 1) + rnd.uniform(-0.3, 0.3)
            w.writerow([f"{t:.0f}", f"{lat:.6f}", f"{lon:.6f}", f"{alt:.1f}", f"{v:.1f}",
                        f"{min(100.0, batt):.1f}", 0 if lost else 1, "day_vision" if lost else "gps"])
    print(out, total, "rows")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "flight_log.csv")

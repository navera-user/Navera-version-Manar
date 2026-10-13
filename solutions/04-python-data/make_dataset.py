#!/usr/bin/env python3
"""Make the flight-test campaign of mission 04 (deterministic: the same files every time).

    python3 solutions/04-python-data/make_dataset.py              # writes into datasets/04-python-data/
    python3 solutions/04-python-data/make_dataset.py --seed 7 --out /tmp/x   # another campaign (Monte Carlo)

TEACHER ONLY (this file lists the planted defects: it must never be in datasets/). Writes, into
datasets/04-python-data/ (seen by students, read only, as /data/academy/04-python-data/):
  campaign.csv      the logger's file: 4 flights of one drone, one row every 2 s
  flight_sheet.csv  the test director's sheet: take-off/landing times (UTC) and the planned jamming windows
  README.txt        what the files are

SYNTHETIC data, made for the course (no NAVERA code, no NAVERA recording), placed in NAVERA's test area
around Sousse and Monastir, Tunisia. It is messy on purpose, like real logs; every defect is listed here
for the teacher (students find them in the lab):
  * 3 exact duplicate rows (the logger wrote a line twice);
  * 1 "Null Island" row (lat = lon = 0) on monastir_coast at t = 100 s;
  * 1 impossible altitude (9999 m) on sahel_hills at t = 200 s;
  * empty cells: ~3 % of speed_mps, ~4 % of battery_pct, and lat/lon on NO_FIX rows;
  * GPS outages: day vision takes over (source "day", state DEGRADED), sometimes nothing (source
    "none", state NO_FIX); 4 day-vision matches jump 300–520 m for one row; 2 GPS multipath spikes;
  * sahel_hills: the logger's clock was set to LOCAL time (Tunisia, UTC+1): its time_s is 3600 s ahead;
  * grid_survey: the logger wrote the speed in km/h in the column speed_mps (a mislabelled column);
  * sousse_port has one outage that the sheet does not plan (near the port's cranes): 420–520 s.
"""
import csv
import math
import os
import random

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "datasets", "04-python-data")
M_PER_DEG = 111_320.0          # small-area conversion used to place the synthetic tracks
DT = 2
SIG_GPS, SIG_DAY, SIG_SPEED = 1.5, 6.0, 0.3

# id, home (lat, lon), waypoints (east, north m), cruise m/s, alt m, take-off UTC (s of day),
# logger clock offset (s), outages [(t0, t1, source)], planned jamming (t0, t1) relative to take-off,
# speed unit factor written by the logger, notes
FLIGHTS = [
    ("monastir_coast", (35.7700, 10.8300), [(0, 0), (2500, 600), (3200, 1800), (0, 0)], 12.0, 100.0,
     7 * 3600 + 30 * 60, 0, [(300, 360, "day")], (300, 360), 1.0, "coastal route, jammer test 1"),
    ("sousse_port", (35.8250, 10.6400), [(0, 0), (1800, 2200), (3500, 2000), (1500, -400), (0, 0)], 14.0, 120.0,
     8 * 3600 + 20 * 60, 0, [(200, 260, "day"), (420, 480, "day"), (480, 520, "none")], (200, 260), 1.0,
     "harbour loop, jammer test 2"),
    ("sahel_hills", (35.6800, 10.5500), [(0, 0), (-1200, 2600), (800, 3400), (0, 0)], 10.0, 250.0,
     9 * 3600 + 10 * 60, 3600, [(560, 10 ** 6, "day")], (560, 1500), 1.0, "inland hills, jammer left on past the landing (until 09:35)"),
    ("grid_survey", (35.6500, 10.9000),
     [(0, 0), (3000, 0), (3000, 400), (0, 400), (0, 800), (3000, 800), (0, 0)], 20.0, 150.0,
     10 * 3600 + 5 * 60, 0, [(600, 616, "day")], (600, 616), 3.6, "survey grid over the shore, short jamming"),
]
DUPLICATES = {("monastir_coast", 50), ("sousse_port", 150), ("sousse_port", 600)}
DAY_JUMPS = {("monastir_coast", 330): (300.0, 0.0), ("sousse_port", 440): (380.0, 0.0),
             ("sahel_hills", 700): (450.0, 0.0), ("sahel_hills", 800): (0.0, -520.0)}
GPS_SPIKES = {("monastir_coast", 600): (14.0, 0.0), ("grid_survey", 300): (0.0, 16.0)}


def hms(s):
    s = int(round(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def to_latlon(home, e, n):
    return home[0] + n / M_PER_DEG, home[1] + e / (M_PER_DEG * math.cos(math.radians(home[0])))


def fly(rnd, waypoints, cruise, alt):
    """[(t, e, n, alt, v)]: the drone leaves the launch point at cruise speed, climbs at 4 m/s along the
    first leg, flies the waypoints and descends at 4 m/s on the way back."""
    legs = list(zip(waypoints, waypoints[1:]))
    total = sum(math.hypot(e1 - e0, n1 - n0) for (e0, n0), (e1, n1) in legs)

    def at(s):                                     # the point at arc length s along the route
        for (e0, n0), (e1, n1) in legs:
            length = math.hypot(e1 - e0, n1 - n0)
            if s <= length:
                return e0 + s / length * (e1 - e0), n0 + s / length * (n1 - n0)
            s -= length
        return waypoints[-1]

    pts, t, s = [], 0, 0.0
    v = cruise
    while True:
        pts.append([t, *at(s), v])                 # v: the speed over the interval that ends here
        v = cruise + rnd.uniform(-0.6, 0.6)
        s += v * DT
        t += DT
        if s > total:
            break
    end = pts[-1][0]
    return [(t, e, n, max(0.0, min(alt, 4.0 * t, 4.0 * (end - t))) + (rnd.uniform(-1.5, 1.5) if 0 < t < end else 0.0), v)
            for t, e, n, v in pts]


def main(out_dir=OUT, seed=404):
    rnd = random.Random(seed)
    lines, sheet = [], []
    for fid, home, wps, cruise, alt, takeoff, clock, outages, jam, unit, notes in FLIGHTS:
        rows = fly(rnd, wps, cruise, alt)
        last_t = rows[-1][0]
        for k, (t, e, n, a, v) in enumerate(rows):
            src = next((s for t0, t1, s in outages if t0 <= t < t1), "gps")
            if fid == "sahel_hills" and src == "day" and t >= last_t - 20:
                src = "none"                                   # vision gives up over the landing site
            sig = SIG_GPS if src == "gps" else SIG_DAY
            e += rnd.gauss(0, sig)
            n += rnd.gauss(0, sig)
            if src == "day" and (fid, t) in DAY_JUMPS:
                e += DAY_JUMPS[(fid, t)][0]
                n += DAY_JUMPS[(fid, t)][1]
            if src == "gps" and (fid, t) in GPS_SPIKES:
                e += GPS_SPIKES[(fid, t)][0]
                n += GPS_SPIKES[(fid, t)][1]
            lat, lon = to_latlon(home, e, n)
            batt = 100.0 - 45.0 * k / (len(rows) - 1) + rnd.uniform(-0.3, 0.3)
            speed = f"{(v + rnd.gauss(0, SIG_SPEED)) * unit:.2f}" if rnd.random() > 0.03 else ""
            battery = f"{min(100.0, batt):.1f}" if rnd.random() > 0.04 else ""
            valid, state = {"gps": (1, "FIX"), "day": (0, "DEGRADED"), "none": (0, "NO_FIX")}[src]
            slat, slon = (f"{lat:.6f}", f"{lon:.6f}") if src != "none" else ("", "")
            alt_s = f"{a:.1f}"
            if (fid, t) == ("monastir_coast", 100):
                slat, slon = "0.000000", "0.000000"           # glitch: Null Island
            if (fid, t) == ("sahel_hills", 200):
                alt_s = "9999.0"                               # glitch: impossible altitude
            line = [fid, str(takeoff + clock + t), slat, slon, alt_s, speed, battery, valid, src, state]
            lines.append(line)
            if (fid, t) in DUPLICATES:
                lines.append(list(line))                       # the logger wrote it twice
        sheet.append([fid, "LITE-2", hms(takeoff), hms(takeoff + last_t), hms(takeoff + jam[0]),
                      hms(takeoff + jam[1]), notes])
    with open(os.path.join(out_dir, "campaign.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flight_id", "time_s", "lat", "lon", "alt_m", "speed_mps", "battery_pct",
                    "gps_valid", "source", "state"])
        w.writerows(lines)
    with open(os.path.join(out_dir, "flight_sheet.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flight_id", "drone", "takeoff_utc", "landing_utc", "jam_start_utc", "jam_end_utc", "notes"])
        w.writerows(sheet)
    with open(os.path.join(out_dir, "README.txt"), "w") as f:
        f.write(
            "Mission 04 — flight-test campaign of 15 September 2026 (SYNTHETIC: made for the course,\n"
            "placed in NAVERA's test area around Sousse and Monastir, Tunisia). Read only.\n\n"
            "campaign.csv      the logger's file, one row every 2 s, four flights of the drone LITE-2. Columns:\n"
            "                  flight_id, time_s (the logger's clock, seconds since 00:00), lat, lon (degrees),\n"
            "                  alt_m, speed_mps (logged by the autopilot), battery_pct, gps_valid (1/0),\n"
            "                  source (gps | day | none), state (FIX | DEGRADED | NO_FIX)\n"
            "flight_sheet.csv  the test director's sheet, times in UTC (hh:mm:ss): take-off, landing and\n"
            "                  the window when the range's GPS jammer was switched on\n")
    print(os.path.join(out_dir, "campaign.csv"), len(lines), "rows;", len(sheet), "flights in flight_sheet.csv")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=404)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    main(os.path.realpath(a.out), a.seed)

#!/usr/bin/env python3
"""Regenerates the NMEA log of lesson 15 (courses/15-gps-nmea/files/drive.nmea).

A simulated u-blox receiver ("GN" talker, like NAVERA's Neo-M8N) on a car driving a loop
around M'saken (Sousse), 1 sentence group per second. Written with the same checksum rule
as navera_tools/sim/nmea_gps.py. On purpose the log contains what a real serial line gives:
  * the first seconds with no fix (quality 0, empty position, RMC status V)
  * a stretch under a bridge where the receiver reports its own dead reckoning (quality 6)
  * a stretch with differential corrections (quality 2)
  * other sentence types (GSA, GSV, VTG) that a GGA/RMC reader must skip
  * corrupted lines: a flipped character, cut lines, two lines glued together, garbage.
    With this seed the glued line (09:31:38) happens to keep a matching checksum — the
    1-in-256 chance of an 8-bit checksum. Lesson 15 uses it on purpose: keep the seed.

    python3 datasets/15-gps-nmea/make_dataset.py
It is deterministic (fixed random seed). The expected answers in check.py come from it.
"""
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "courses", "15-gps-nmea", "files", "drive.nmea")

LAT0, LON0 = 35.734001, 10.575849          # start: the Neo-M8N's real fix in NAVERA's test
M_PER_DEG = 111_320.0
WAYPOINTS = [(0, 0), (40, 0), (820, 30), (850, 620), (230, 910), (-20, 300), (0, 0)]   # east, north (m)
SPEED = 11.0                                # m/s (about 40 km/h)
GEO_SEP = 32.1
ALT_MSL = 95.3


def cs(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"${body}*{c:02X}"


def dm_lat(v):
    a = abs(v)
    d = int(a)
    return f"{d:02d}{(a - d) * 60:08.5f}", "N" if v >= 0 else "S"


def dm_lon(v):
    a = abs(v)
    d = int(a)
    return f"{d:03d}{(a - d) * 60:08.5f}", "E" if v >= 0 else "W"


def path_points():
    """True positions (east, north, course deg) every second along the waypoints."""
    pts = []
    for (e0, n0), (e1, n1) in zip(WAYPOINTS, WAYPOINTS[1:]):
        L = math.hypot(e1 - e0, n1 - n0)
        course = math.degrees(math.atan2(e1 - e0, n1 - n0)) % 360
        steps = max(1, int(round(L / SPEED)))
        for k in range(steps):
            f = k / steps
            pts.append((e0 + f * (e1 - e0), n0 + f * (n1 - n0), course, L / steps))
    pts.append((0.0, 0.0, pts[-1][2], 0.0))
    return pts


def main():
    rng = random.Random(15)
    lines = []
    noise = [0.0, 0.0]
    t0 = 9 * 3600 + 30 * 60                      # 09:30:00 UTC
    still = 8                                    # waiting for the first fix, not moving
    moving = path_points()
    timeline = [(0.0, 0.0, 0.0, 0.0)] * still + moving
    n = len(timeline)
    bridge = range(still + 120, still + 132)     # quality 6: dead reckoning under a bridge
    dgps = range(still + 200, still + 230)       # quality 2: differential corrections
    corrupt_at = {still + 15: "flip", still + 47: "cut", still + 90: "glue", still + 133: "flip",
                  still + 170: "nochk", still + 211: "flip", still + 240: "garbage"}
    for i, (e, nn, course, step) in enumerate(timeline):
        t = t0 + i
        hms = f"{t // 3600:02d}{t % 3600 // 60:02d}{t % 60:02d}.00"
        group = []
        if i < still:                                         # no fix yet
            sats = min(3, i // 2)
            group.append(cs(f"GNGGA,{hms},,,,,0,{sats:02d},99.99,,,,,,"))
            group.append(cs(f"GNRMC,{hms},V,,,,,,,071026,,,N"))
        else:
            for k in (0, 1):                                  # receiver noise (random walk)
                noise[k] += -noise[k] * 0.05 + rng.gauss(0, 0.25)
            ee, en = e + noise[0], nn + noise[1]
            lat = LAT0 + en / M_PER_DEG
            lon = LON0 + ee / (M_PER_DEG * math.cos(math.radians(LAT0)))
            la, ns = dm_lat(lat)
            lo, ew = dm_lon(lon)
            q = 6 if i in bridge else 2 if i in dgps else 1
            sats = 0 if q == 6 else rng.choice([10, 11, 12, 12, 13])
            hdop = 0.0 if q == 6 else round(rng.uniform(0.6, 1.1) if q == 1 else rng.uniform(0.5, 0.7), 2)
            hdop_s = "" if q == 6 else f"{hdop:.2f}"
            alt = ALT_MSL + rng.gauss(0, 0.4)
            group.append(cs(f"GNGGA,{hms},{la},{ns},{lo},{ew},{q},{sats:02d},{hdop_s},{alt:.1f},M,{GEO_SEP},M,,"))
            kn = step / 0.514444
            status, mode = ("A", "D" if q == 2 else "A") if q != 6 else ("A", "E")
            group.append(cs(f"GNRMC,{hms},{status},{la},{ns},{lo},{ew},{kn:.3f},"
                            f"{course:.2f},071026,,,{mode}"))
            group.append(cs(f"GNVTG,{course:.2f},T,,M,{kn:.3f},N,{kn * 1.852:.3f},K,{mode}"))
        if i % 5 == 0:
            group.append(cs("GNGSA,A,3,05,13,15,18,20,23,24,29,,,,,1.32,0.82,1.03,1"))
            group.append(cs("GPGSV,3,1,11,05,45,077,38,13,32,192,35,15,58,284,41,18,24,048,33,0"))
        kind = corrupt_at.get(i)
        if kind == "flip":                       # one character changed by noise on the wire
            s = group[0]
            j = 20 + (i % 7)
            ch = s[j]
            group[0] = s[:j] + ("7" if ch != "7" else "1") + s[j + 1:]
        elif kind == "cut":                      # line cut in the middle
            group[0] = group[0][:31]
        elif kind == "glue":                     # end of line lost: two sentences glued
            group[0] = group[0][:40] + group[1]
            del group[1]
        elif kind == "nochk":                    # a sentence without its checksum
            group[0] = group[0].split("*")[0]
        elif kind == "garbage":
            group.insert(0, "$GN#@!~~,,0,12,,1.0*ZZ")
        lines.extend(group)
    with open(OUT, "w", newline="") as f:
        for ln in lines:
            f.write(ln + "\r\n")
    print(f"{len(lines)} lines, {n} seconds -> {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Make nmea_bench.txt (synthetic, reproducible): 600 s of a receiver standing on NAVERA's GPS
test site (M'saken, 35.734 N 10.576 E), 1 GGA + 1 RMC sentence per second, as gps_node reads them.

Most fixes use 7-12 satellites (error ~2.5 m per axis). Some seconds are degraded the way real
receivers degrade: few satellites (3: error ~60 m), no fix (quality 0), the receiver's own
dead-reckoning (quality 6), a corrupted line (bad checksum). truth.json gives the true point.
SIMULATED DATA — for bench tests of NMEA handling, not a measurement of a receiver.

    python3 make_dataset.py
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
LAT0, LON0 = 35.734, 10.576
M_LAT = 111_195.0
M_LON = M_LAT * math.cos(math.radians(LAT0))


def cs(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"${body}*{c:02X}"


def dm(v, lon=False):
    a = abs(v)
    d = int(a)
    return (f"{d:03d}" if lon else f"{d:02d}") + f"{(a - d) * 60:08.5f}"


def main():
    rng = random.Random(30)
    out = []
    for k in range(600):
        hh, mm, ss = 14, 16 + k // 60, k % 60
        t = f"{hh:02d}{mm:02d}{ss:02d}.00"
        r = rng.random()
        qual, sats, sig = 1, rng.randint(7, 12), 2.5
        if 120 <= k < 150 or 400 <= k < 415:          # under trees / near a wall: few satellites
            sats, sig = 3, 60.0
        elif 300 <= k < 320:                          # lost
            qual, sats = 0, 0
        elif 500 <= k < 510:                          # the receiver's own dead-reckoning
            qual, sats, sig = 6, 0, 30.0
        e, n = rng.gauss(0, sig), rng.gauss(0, sig)
        lat, lon = LAT0 + n / M_LAT, LON0 + e / M_LON
        hdop = 0.9 if sats >= 7 else (4.5 if sats else 0)
        if qual == 0:
            body = f"GPGGA,{t},,,,,0,00,99.9,,M,,M,,"
        else:
            body = f"GPGGA,{t},{dm(lat)},N,{dm(lon, True)},E,{qual},{sats:02d},{hdop:.1f},25.0,M,33.0,M,,"
        line = cs(body)
        if r < 0.01:                                  # a corrupted line: the checksum no longer matches
            line = line[:20] + "7" + line[21:]
        out.append(line)
        st = "A" if qual in (1, 2, 4, 5) else "V"
        out.append(cs(f"GPRMC,{t},{st},{dm(lat)},N,{dm(lon, True)},E,0.0,0.0,071026,,,A"))
    with open(os.path.join(HERE, "nmea_bench.txt"), "w") as f:
        f.write("\r\n".join(out) + "\r\n")
    with open(os.path.join(HERE, "truth.json"), "w") as f:
        json.dump({"lat": LAT0, "lon": LON0, "note": "simulated receiver standing on this point"}, f)


if __name__ == "__main__":
    main()

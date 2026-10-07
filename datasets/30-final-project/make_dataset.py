#!/usr/bin/env python3
"""Make nmea_bench.txt + truth.json (synthetic, reproducible) for lesson 30.

30 minutes (1800 s) of a SIMULATED GPS receiver standing still on a point near Sultan Qaboos
University, Al Khoudh, Muscat (approximate coordinates), 1 GGA + 1 RMC sentence per second, as
NAVERA's gps_node reads them. SIMULATED DATA — for bench tests of NMEA handling and of the
measurement method, not a measurement of a real receiver.

Error model (per axis, metres):
  * normal epochs: 7-12 satellites, HDOP 0.7-1.6, sigma = 1.6 m x HDOP;
  * the error is time-correlated (multipath changes slowly): first-order autoregressive,
    e[k] = RHO e[k-1] + sqrt(1 - RHO^2) sigma w[k], RHO = 0.9 (correlation time ~10 s);
  * degraded episodes, as contiguous blocks (next to buildings, under a car-park roof...):
      - 3 satellites, HDOP 4-9, sigma 40 m        (the receiver extrapolates: large errors)
      - 4 satellites, HDOP 3-5, sigma 1.6 x HDOP  (weak but honest geometry)
      - quality 0 (no fix), quality 6 (the receiver's own dead-reckoning, sigma 30 m)
  * about 1 % of the lines are corrupted (checksum no longer matches).

    python3 make_dataset.py
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
LAT0, LON0 = 23.5880, 58.1700           # near Sultan Qaboos University, Muscat (approximate)
M_LAT = 111_195.0
M_LON = M_LAT * math.cos(math.radians(LAT0))
N = 1800
RHO = 0.9
UERE = 1.6

THREE_SATS = [(200, 240), (610, 650), (1100, 1125), (1500, 1530)]
FOUR_SATS = [(800, 840), (1300, 1330)]
NO_FIX = [(900, 930)]
DEAD_RECKONING = [(1650, 1665)]


def inside(k, blocks):
    return any(a <= k < b for a, b in blocks)


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
    we = wn = 0.0                                    # the unit-variance AR(1) states (east, north)
    for k in range(N):
        t0 = 6 * 3600 + 30 * 60 + k                  # 06:30:00 UTC = 10:30 in Muscat
        t = f"{t0 // 3600:02d}{t0 // 60 % 60:02d}{t0 % 60:02d}.00"
        we = RHO * we + math.sqrt(1 - RHO ** 2) * rng.gauss(0, 1)
        wn = RHO * wn + math.sqrt(1 - RHO ** 2) * rng.gauss(0, 1)
        qual = 1
        if inside(k, THREE_SATS):
            sats, hdop, sig = 3, rng.uniform(4.0, 9.0), 40.0
        elif inside(k, FOUR_SATS):
            sats, hdop = 4, rng.uniform(3.0, 5.0)
            sig = UERE * hdop
        elif inside(k, NO_FIX):
            qual, sats, hdop, sig = 0, 0, 99.9, 0.0
        elif inside(k, DEAD_RECKONING):
            qual, sats, hdop, sig = 6, 0, 0.0, 30.0
        else:
            sats = rng.randint(7, 12)
            hdop = rng.uniform(0.7, 1.6)
            sig = UERE * hdop
        e, n = we * sig, wn * sig
        lat, lon = LAT0 + n / M_LAT, LON0 + e / M_LON
        if qual == 0:
            body = f"GPGGA,{t},,,,,0,00,99.9,,M,,M,,"
        else:
            hd = f"{hdop:.1f}" if hdop > 0 else ""
            body = (f"GPGGA,{t},{dm(lat)},N,{dm(lon, True)},E,{qual},{sats:02d},{hd},"
                    f"48.0,M,-33.0,M,,")
        line = cs(body)
        if rng.random() < 0.01:                      # a corrupted line: the checksum no longer matches
            line = line[:20] + ("7" if line[20] != "7" else "8") + line[21:]
        out.append(line)
        st = "A" if qual in (1, 2, 4, 5) else "V"
        out.append(cs(f"GPRMC,{t},{st},{dm(lat)},N,{dm(lon, True)},E,0.0,0.0,071026,,,A"))
    with open(os.path.join(HERE, "nmea_bench.txt"), "w") as f:
        f.write("\r\n".join(out) + "\r\n")
    with open(os.path.join(HERE, "truth.json"), "w") as f:
        json.dump({"lat": LAT0, "lon": LON0,
                   "note": "SIMULATED receiver standing still near Sultan Qaboos University, Muscat "
                           "(approximate point); 1800 s, 1 Hz"}, f)


if __name__ == "__main__":
    main()

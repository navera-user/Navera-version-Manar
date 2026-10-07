#!/usr/bin/env python3
"""Regenerates the data of lesson 15 (GNSS and NMEA 0183).

    python3 datasets/15-gps-nmea/make_dataset.py

Writes, next to this script:
  sousse_drive.nmea  a SYNTHETIC NMEA 0183 log (GPS-only receiver, talker "GP", 1 Hz)
  truth.csv          the true position of the car every second (utc,lat,lon,alt_msl)

The drive: a car leaves the Sousse port area and drives south-east along the coast to the
Ribat of Monastir (about 19 km, roads approximate), in NAVERA's test area (Tunisia). The places are real; the log is invented, so that we
know the truth exactly. What the synthetic receiver does, on purpose:
  * cold start: 12 s without a fix (GGA quality 0, RMC status V, GSA mode 1)
  * satellites move slowly across the sky (12 GPS satellites, integer az/el in GSV)
  * the receiver uses satellites above 10 deg that are not hidden; it computes PDOP/HDOP/VDOP
    from the geometry of the INTEGER az/el it writes (unweighted least squares), so a student
    can recompute them exactly from GSV + GSA
  * position error = least-squares solution of per-satellite range errors
    (Gauss-Markov 1.6 m, tau 60 s, + white 1.2 m  ->  UERE = 2.0 m)
  * port area: container stacks hide low satellites to the south-west
  * an (invented) underpass: 5 s of receiver dead reckoning (quality 6), then no fix
  * town centre: buildings hide everything except along the street -> HDOP spikes,
    some seconds with < 4 satellites (no fix)
  * corrupted lines: flipped characters, a cut line, a missing checksum, garbage, two lines
    glued together, a non-ASCII byte, and TWO swapped-digit lines whose checksum is still
    correct (XOR does not see the order of characters): one with minutes >= 60, one with a
    plausible-looking latitude a few tenths of a minute off
    (in this log 0.36', about 0.67 km).
Deterministic (fixed seeds). check.py of lesson 15 holds numbers computed from this output:
if you change anything here, recompute them with the solution (analyze_drive.py).
"""
import math
import os
import random

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_LOG = os.path.join(HERE, "sousse_drive.nmea")
OUT_TRUTH = os.path.join(HERE, "truth.csv")

R_EARTH = 6371000.0
WAYPOINTS = [(35.8270, 10.6420),     # near the port of Sousse
             (35.8150, 10.6560), (35.8000, 10.6750), (35.7850, 10.7000),
             (35.7700, 10.7300), (35.7620, 10.7650), (35.7650, 10.7950),
             (35.7720, 10.8150),
             (35.7780, 10.8265)]     # Ribat of Monastir
T0 = 5 * 3600 + 12 * 60              # 05:12:00 UTC = 06:12 in Tunisia (UTC+1)
DATE = "121026"                       # 12 October 2026
COLD = 12                             # seconds without a fix at start (car parked)
GEO_SEP = 32.0                        # value written by this synthetic receiver (geoid near Sousse)
MASK_USE = 10.0                       # elevation mask for use (deg)
MASK_LIST = 5.0                       # satellites listed in GSV above this


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


def to_enu(lat, lon, lat0, lon0):
    e = math.radians(lon - lon0) * R_EARTH * math.cos(math.radians(lat0))
    n = math.radians(lat - lat0) * R_EARTH
    return e, n


def from_enu(e, n, lat0, lon0):
    return (lat0 + math.degrees(n / R_EARTH),
            lon0 + math.degrees(e / (R_EARTH * math.cos(math.radians(lat0)))))


def route():
    """Polyline in local metres (east, north) from the first waypoint."""
    lat0, lon0 = WAYPOINTS[0]
    pts = [to_enu(la, lo, lat0, lon0) for la, lo in WAYPOINTS]
    seg = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    return pts, seg


def point_at(s, pts, seg):
    for (a, b), L in zip(zip(pts, pts[1:]), seg):
        if s <= L:
            f = s / L
            return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), \
                math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360
        s -= L
    a, b = pts[-2], pts[-1]
    return b[0], b[1], math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360


def speed_profile(s_total):
    """Speed (m/s) as a function of the distance s already driven."""
    def v(s, t_move):
        ramp = min(1.0, t_move / 18.0)
        if s > s_total - 3200:           # town: slower
            target = 11.0
        elif 9800 < s < 10300:           # approach and underpass
            target = 12.0
        else:
            target = 22.0
        return max(0.8, ramp * target) if s < s_total else 0.0
    return v


def sky(rng):
    """12 GPS satellites: (prn, az0, el0, daz/dt, del/dt) in degrees and deg/s."""
    prns = [2, 5, 7, 9, 13, 15, 18, 20, 23, 24, 29, 30]
    azs = [12, 47, 95, 128, 160, 200, 228, 255, 288, 318, 343, 175]
    els = [62, 33, 18, 47, 71, 26, 13, 39, 55, 21, 8, 84]
    sats = []
    for p, a, e in zip(prns, azs, els):
        sats.append((p, a + rng.uniform(-4, 4), e + rng.uniform(-2, 2),
                     rng.uniform(-0.009, 0.009), rng.uniform(-0.007, 0.007)))
    # PRN 29 is rising: it crosses the 10 deg mask during the drive
    sats[10] = (29, 343.0, 7.0, 0.004, 0.0075)
    return sats


def los(az, el):
    a, e = np.radians(az), np.radians(el)
    return np.column_stack([np.cos(e) * np.sin(a), np.cos(e) * np.cos(a), np.sin(e)])


def dops_from(az, el):
    G = np.column_stack([-los(az, el), np.ones(len(az))])
    Q = np.linalg.inv(G.T @ G)
    return G, Q


def hidden(az, el, zone, course):
    """True when a building/container stack hides this satellite."""
    if zone == "port":
        return 190 <= az <= 300 and el < 28
    if zone.startswith("town"):
        # buildings along the street: off-axis satellites below a limit elevation are hidden.
        # The limit changes from block to block (town0 = low houses ... town4 = tall buildings).
        limit = {"town0": 20, "town1": 38, "town2": 52, "town3": 64, "town4": 80}[zone]
        d = min(abs((az - course + 180) % 360 - 180), abs((az - course) % 360 - 180))
        return el < limit and d > 22
    if zone == "under":
        return True
    return False


def main():
    rng = random.Random(1507)
    nrng = np.random.default_rng(1507)
    pts, seg = route()
    s_total = sum(seg)
    vfun = speed_profile(s_total)
    sats = sky(rng)
    lat0, lon0 = WAYPOINTS[0]

    # --- timeline of the true motion
    timeline = []                         # (t, e, n, course, speed)
    s, t, t_move = 0.0, 0, 0.0
    course0 = point_at(0.0, pts, seg)[2]
    while True:
        if t < COLD:
            e, n, c = 0.0, 0.0, course0
            v = 0.0
        else:
            v = vfun(s, t_move)
            e, n, c = point_at(s, pts, seg)
        timeline.append((t, e, n, c, v))
        if t >= COLD:
            s += v
            t_move += 1.0
            if s >= s_total:
                e, n, c = point_at(s_total, pts, seg)
                timeline.append((t + 1, e, n, c, 0.0))
                break
        t += 1
    N = len(timeline)

    # zones by distance along the route
    def zone_of(i):
        tt = timeline[i][0]
        if tt < COLD:
            return "cold"
        ss = sum(r[4] for r in timeline[COLD:i])
        if ss < 1600:
            return "port"
        if 10000 <= ss < 10450:
            return "under"
        if ss > s_total - 2600:
            k = int((ss - (s_total - 2600)) // 160)
            return "town" + "0102310240132010"[k % 16]
        return "open"

    zones = [zone_of(i) for i in range(N)]
    # range errors: Gauss-Markov (1.6 m, tau 60 s) + white (1.2 m), per satellite
    gm = {p: nrng.normal(0, 1.6) for p, *_ in sats}
    a_gm = math.exp(-1.0 / 60.0)

    lines, truth = [], []
    last_fix = None                       # (e, n, ve, vn) for dead reckoning
    dr_left = 0
    alt_true = 9.0
    corrupt = {60: "flip_gga", 150: "cut_gga", 230: "nochk_rmc", 300: "garbage",
               520: "glue", 610: "nonascii_gsv", 680: "flip_gsa"}
    swap60_done = swapdec_done = False
    for i, (tt, e, n, course, v) in enumerate(timeline):
        sec = T0 + tt
        hms = f"{sec // 3600:02d}{sec % 3600 // 60:02d}{sec % 60:02d}.00"
        lat_t, lon_t = from_enu(e, n, lat0, lon0)
        alt_true = 9.0 + 4.0 * math.sin(tt / 140.0)
        truth.append(f"{hms},{lat_t:.8f},{lon_t:.8f},{alt_true:.2f}")
        for p in gm:
            gm[p] = a_gm * gm[p] + math.sqrt(1 - a_gm ** 2) * nrng.normal(0, 1.6)
        zone = zones[i]
        # satellite sky at this second (integer degrees, as written in GSV)
        vis = []
        for p, a0, e0, da, de in sats:
            az = int(round((a0 + da * tt) % 360)) % 360
            el = int(round(e0 + de * tt))
            if el >= MASK_LIST:
                vis.append((p, az, el))
        used = []
        if zone != "cold" or tt >= COLD - 4:
            used = [(p, az, el) for p, az, el in vis
                    if el >= MASK_USE and not hidden(az, el, zone, course)]
        if zone == "cold":
            used = used[: max(0, tt - (COLD - 4))] if tt >= COLD - 4 else []
            used = used[:3]
        group = []
        fix = len(used) >= 4 and zone != "cold"
        if fix:
            az = np.array([u[1] for u in used], float)
            el = np.array([u[2] for u in used], float)
            G, Q = dops_from(az, el)
            eps = np.array([gm[u[0]] + nrng.normal(0, 1.2) for u in used])
            dx = Q @ G.T @ eps
            pdop = math.sqrt(Q[0, 0] + Q[1, 1] + Q[2, 2])
            hdop = math.sqrt(Q[0, 0] + Q[1, 1])
            vdop = math.sqrt(Q[2, 2])
            me, mn = e + dx[0], n + dx[1]
            lat, lon = from_enu(me, mn, lat0, lon0)
            alt = alt_true + dx[2]
            la, ns = dm_lat(lat)
            lo, ew = dm_lon(lon)
            gga = (f"GPGGA,{hms},{la},{ns},{lo},{ew},1,{len(used):02d},{hdop:.2f},"
                   f"{alt:.1f},M,{GEO_SEP:.1f},M,,")
            kn = v / 0.514444
            crs = f"{course:.1f}" if v > 0.5 else ""
            rmc = f"GPRMC,{hms},A,{la},{ns},{lo},{ew},{kn:.2f},{crs},{DATE},,,A"
            prn_f = [f"{u[0]:02d}" for u in used] + [""] * (12 - len(used))
            gsa = f"GPGSA,A,3,{','.join(prn_f)},{pdop:.2f},{hdop:.2f},{vdop:.2f}"
            ve = v * math.sin(math.radians(course))
            vn = v * math.cos(math.radians(course))
            last_fix = (me, mn, ve, vn, alt)
            dr_left = 5
        elif zone == "under" and dr_left > 0 and last_fix is not None:
            me, mn, ve, vn, alt = last_fix
            me, mn = me + ve, mn + vn
            last_fix = (me, mn, ve, vn, alt)
            dr_left -= 1
            lat, lon = from_enu(me, mn, lat0, lon0)
            la, ns = dm_lat(lat)
            lo, ew = dm_lon(lon)
            gga = f"GPGGA,{hms},{la},{ns},{lo},{ew},6,00,,{alt:.1f},M,{GEO_SEP:.1f},M,,"
            kn = math.hypot(ve, vn) / 0.514444
            rmc = f"GPRMC,{hms},A,{la},{ns},{lo},{ew},{kn:.2f},{course:.1f},{DATE},,,E"
            gsa = "GPGSA,A,1,,,,,,,,,,,,,99.99,99.99,99.99"
        else:
            if zone != "under":
                dr_left = 0
            gga = f"GPGGA,{hms},,,,,0,{len(used):02d},99.99,,,,,,"
            rmc = f"GPRMC,{hms},V,,,,,,,{DATE},,,N"
            gsa = "GPGSA,A,1,,,,,,,,,,,,,99.99,99.99,99.99"
        # GSV: all listed satellites, 4 per sentence; SNR empty when hidden
        used_p = {u[0] for u in used}
        nmsg = (len(vis) + 3) // 4
        gsv = []
        for k in range(nmsg):
            chunk = vis[4 * k: 4 * k + 4]
            parts = []
            for p, az, el in chunk:
                snr = "" if (zone == "cold" and p not in used_p) or hidden(az, el, zone, course) \
                    else f"{int(30 + 18 * math.sin(math.radians(el)) + rng.uniform(-2, 2)):02d}"
                parts.append(f"{p:02d},{el:02d},{az:03d},{snr}")
            gsv.append(f"GPGSV,{nmsg},{k + 1},{len(vis):02d}," + ",".join(parts))
        group = [cs(gga), cs(rmc), cs(gsa)] + [cs(x) for x in gsv]

        kind = corrupt.get(tt)
        if kind == "flip_gga":
            s_ = group[0]
            j = 22
            group[0] = s_[:j] + ("7" if s_[j] != "7" else "1") + s_[j + 1:]
        elif kind == "cut_gga":
            group[0] = group[0][:31]
        elif kind == "nochk_rmc":
            group[1] = group[1].split("*")[0]
        elif kind == "garbage":
            group.insert(0, "$GP#@!~~,,0,12,,1.0*ZZ")
        elif kind == "glue":
            group[0] = group[0][:40] + group[1]
            del group[1]
        elif kind == "nonascii_gsv":
            s_ = group[3]
            group[3] = s_[:15] + "°" + s_[16:]
        elif kind == "flip_gsa":
            s_ = group[2]
            j = s_.rfind(",") + 2
            group[2] = s_[:j] + ("9" if s_[j] != "9" else "3") + s_[j + 1:]
        # swapped digits: XOR is blind to order -> checksum still correct
        if fix and zone == "open" and tt > 330 and not swap60_done:
            mm = la[2:4]                        # latitude minutes "ab"
            if int(mm[1]) >= 6 and mm[0] != mm[1]:
                bad = la[:2] + mm[1] + mm[0] + la[4:]
                group[0] = cs(gga.replace(f",{la},", f",{bad},", 1))
                swap60_done = True
        elif fix and zone == "open" and tt > 740 and not swapdec_done:
            d1, d2 = la[5], la[6]              # first two decimals of the minutes
            if abs(int(d1) - int(d2)) >= 4:
                bad = la[:5] + d2 + d1 + la[7:]
                group[0] = cs(gga.replace(f",{la},", f",{bad},", 1))
                swapdec_done = True
        lines.extend(group)

    with open(OUT_LOG, "w", newline="", encoding="latin-1") as f:
        for ln in lines:
            f.write(ln + "\r\n")
    with open(OUT_TRUTH, "w") as f:
        f.write("utc,lat,lon,alt_msl\n")
        f.write("\n".join(truth) + "\n")
    print(f"{len(lines)} lines, {N} s, route {s_total:.0f} m -> {OUT_LOG}")
    print(f"swap60 {swap60_done}, swapdec {swapdec_done}; zones:",
          {z: zones.count(z) for z in sorted(set(zones))})


if __name__ == "__main__":
    main()

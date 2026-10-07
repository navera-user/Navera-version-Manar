"""Compare YOUR parser (nmea_tools.py) with the parser NAVERA really uses.

NAVERA's gps_node (gps_pkg/gps_pkg/nodes/gps_node.py) reads each line with the
pynmea2 library:   msg = pynmea2.parse(raw, check=True)
and keeps a GGA as a fix only when its quality is 1, 2, 4 or 5.
This script does the same thing next to your functions and prints the differences.

    python3 compare_with_navera.py            (uses drive.nmea)
    python3 compare_with_navera.py other.nmea
"""
import sys

import pynmea2

import nmea_tools as mine

VALID_GPS_QUAL = {1, 2, 4, 5}          # gps_node.py: _VALID_GPS_QUAL


def navera_reads(raw):
    """What gps_node does with one line: ('rejected', None) / ('other', None) / ('gga', fix or None)."""
    raw = raw.strip()
    if not raw.startswith("$"):
        return "rejected", None
    try:
        msg = pynmea2.parse(raw, check=True)
    except pynmea2.ParseError:
        return "rejected", None
    if not isinstance(msg, pynmea2.types.talker.GGA):
        return "other", None
    try:
        qual = int(msg.gps_qual) if msg.gps_qual else 0
    except (TypeError, ValueError):
        qual = 0
    if not (msg.lat and msg.lon) or qual not in VALID_GPS_QUAL:
        return "gga", None                 # published as "no fix" (valid = False)
    try:
        return "gga", (msg.latitude, msg.longitude)
    except (TypeError, ValueError):
        return "gga", None


def main(path):
    lines = open(path, errors="replace").read().splitlines()
    n_rej_navera = n_rej_mine = n_fix_navera = n_fix_mine = 0
    worst = 0.0
    problems = []
    for no, raw in enumerate(lines, 1):
        kind, fix = navera_reads(raw)
        ok_mine = mine.is_valid(raw)
        g = mine.parse_gga(raw)
        my_fix = None
        if g and g.get("quality") in mine.USABLE_QUALITIES and g.get("lat") is not None and g.get("lon") is not None:
            my_fix = (g["lat"], g["lon"])
        n_rej_navera += kind == "rejected"
        n_rej_mine += not ok_mine
        n_fix_navera += fix is not None
        n_fix_mine += my_fix is not None
        if (kind == "rejected") == bool(ok_mine):
            problems.append(f"line {no}: NAVERA {'rejects' if kind == 'rejected' else 'accepts'} it, "
                            f"your is_valid says {ok_mine!r}:  {raw[:60]}")
        if (fix is None) != (my_fix is None):
            problems.append(f"line {no}: NAVERA fix {fix}, yours {my_fix}:  {raw[:60]}")
        elif fix is not None:
            d = max(abs(fix[0] - my_fix[0]), abs(fix[1] - my_fix[1]))
            worst = max(worst, d)
            if d > 1e-7:
                problems.append(f"line {no}: positions differ by {d:.2e} deg:  NAVERA {fix}, yours {my_fix}")
    print(f"{len(lines)} lines in {path}")
    print(f"{'':28}{'NAVERA (pynmea2)':>18}{'yours':>10}")
    print(f"{'lines rejected (checksum)':28}{n_rej_navera:>18}{n_rej_mine:>10}")
    print(f"{'usable fixes':28}{n_fix_navera:>18}{n_fix_mine:>10}")
    print(f"largest position difference: {worst:.2e} deg (about {worst * 111320:.4f} m)")
    if problems:
        print(f"\n{len(problems)} difference(s) — the first ones:")
        for p in problems[:12]:
            print("  " + p)
    else:
        print("\nNo difference: your parser agrees with NAVERA's on every line. 🎉")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "drive.nmea")

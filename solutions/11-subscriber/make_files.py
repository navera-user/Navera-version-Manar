"""make_files.py (teacher only) — regenerates courses/11-subscriber/files/bad_fixes.csv, the replay scenario of
lab Step 6. Run from the repository root:  python3 solutions/11-subscriber/make_files.py

A vehicle drives east at 10 m/s near Sousse, one GPS fix per second (20 rows); four rows are bad:
t = 5 no position (valid 0), t = 8 latitude NaN, t = 11 a 5 km jump, t = 14 a fix measured 2.5 s
earlier (delay_s 2.5, so its stamp is older than the fix accepted at t = 13).
Expected with a correct trip computer: 16 fixes, 4 refused, last refusal "old fix", distance 190.0 m.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_navera_lite"))
from navera_lite.geo import offset  # noqa: E402

START = (35.8256, 10.6084)
OUT = os.path.join(HERE, "..", "..", "courses", "11-subscriber", "files", "bad_fixes.csv")


def main():
    lines = ["t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s"]
    for k in range(20):
        east, valid, delay = 10.0 * k, 1, 0.0
        if k == 11:
            east += 5000.0
        if k == 14:
            east, delay = 115.0, 2.5
        lat, lon = offset(START[0], START[1], east, 0.0)
        if k == 5:
            valid = 0
        lat_s = "nan" if k == 8 else f"{lat:.7f}"
        lines.append(f"{float(k):.1f},gps,{lat_s},{lon:.7f},9.0,0.0,9.0,1,{valid},{delay}")
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", os.path.relpath(OUT))


if __name__ == "__main__":
    main()

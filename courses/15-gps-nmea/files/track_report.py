"""A report on an NMEA log, made with YOUR functions from nmea_tools.py.

    python3 track_report.py                 (uses drive.nmea)

Prints what happened during the drive and draws track.png (open it in the editor).
"""
import sys
import warnings

import matplotlib
matplotlib.use("Agg")                       # no window: we save a picture
warnings.filterwarnings("ignore", message="Unable to import Axes3D")
import matplotlib.pyplot as plt  # noqa: E402

import nmea_tools as t  # noqa: E402

COLORS = {1: ("tab:blue", "1 GPS fix"), 2: ("tab:green", "2 DGPS fix"),
          6: ("tab:red", "6 receiver's own guess (rejected)")}


def seconds(hhmmss):
    """'093014.00' -> seconds since midnight."""
    return int(hhmmss[0:2]) * 3600 + int(hhmmss[2:4]) * 60 + float(hhmmss[4:])


def main(path):
    lines = open(path, errors="replace").read().splitlines()
    ggas = [g for g in (t.parse_gga(ln) for ln in lines) if g]
    bad = sum(1 for ln in lines if not t.is_valid(ln))
    pts = t.usable_fixes(path)
    length = t.track_length_m(pts) if pts is not None else None
    if not ggas or pts is None or length is None:
        sys.exit("Finish TODO 1 to 6 in nmea_tools.py first (parse_gga, usable_fixes and "
                 "track_length_m still return None).")
    print(f"{len(lines)} lines, {bad} corrupted, {len(ggas)} GGA sentences")
    by_q = {}
    for g in ggas:
        by_q[g["quality"]] = by_q.get(g["quality"], 0) + 1
    for q in sorted(by_q, key=lambda q: (q is None, q)):
        print(f"   quality {q!s:>4}: {by_q[q]:4d} sentences")
    hd = [g["hdop"] for g in ggas if g["hdop"] is not None and g["quality"] in t.USABLE_QUALITIES]
    if hd:
        print(f"HDOP of the usable fixes: best {min(hd):.2f}, worst {max(hd):.2f}, "
              f"average {sum(hd) / len(hd):.2f}  ->  NAVERA's sigma = HDOP x 2 m = "
              f"{2 * min(hd):.1f} to {2 * max(hd):.1f} m")
    print(f"usable fixes: {len(pts)},  track length: {length:.1f} m")
    good = [g for g in ggas
            if g["quality"] in t.USABLE_QUALITIES and g["lat"] is not None and g["lon"] is not None]
    if len(good) > 1 and seconds(good[-1]["time"]) > seconds(good[0]["time"]):
        duration = seconds(good[-1]["time"]) - seconds(good[0]["time"])
        print(f"first usable fix at {good[0]['time'][:6]}, last at {good[-1]['time'][:6]} UTC (hhmmss): "
              f"{duration:.0f} s, average speed {length / duration:.1f} m/s")

    fig, ax = plt.subplots(figsize=(7, 7))
    for q, (col, label) in COLORS.items():
        sel = [g for g in ggas if g["quality"] == q and g["lat"] is not None and g["lon"] is not None]
        if sel:
            ax.scatter([g["lon"] for g in sel], [g["lat"] for g in sel], s=8, c=col, label=label)
    if pts:
        ax.plot([p[1] for p in pts], [p[0] for p in pts], "-", lw=0.6, c="grey")
        ax.plot(pts[0][1], pts[0][0], "k*", ms=14, label="first usable fix")
    ax.set_xlabel("longitude (deg)")
    ax.set_ylabel("latitude (deg)")
    ax.set_title(f"{path}: {len(pts)} usable fixes, {length:.0f} m")
    ax.set_aspect(1 / 0.811)                 # 1 deg of longitude is cos(35.7 deg) = 0.81 deg of latitude here
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("track.png", dpi=110)
    print("saved track.png — click it in the file list to see it")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "drive.nmea")

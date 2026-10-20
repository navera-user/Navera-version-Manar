#!/usr/bin/env python3
"""When is the sky dark enough for the star test? Dark (sun below -15 deg) AND no moon above the horizon.

    python3 -m navera_tools.field.sky_window                      # next 14 nights, Tunis
    python3 -m navera_tools.field.sky_window --start 2026-10-31 --nights 7 --lat 36.8 --lon 10.18 --tz 1

A bright moon washes out the faint stars the 360 camera's video barely shows, so the drive is planned
inside these windows (runbook "Choose the night"). Works offline: astropy's built-in ephemeris and the
bundled IERS table (celestial_math.configure_offline_iers).
"""
import argparse
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import astropy.units as u  # noqa: E402
from astropy.coordinates import AltAz, EarthLocation, get_body  # noqa: E402
from astropy.time import Time  # noqa: E402

from cn_pkg.nodes.celestial_math import configure_offline_iers  # noqa: E402

SUN_DARK_DEG = -15.0      # sun below this: sky glow low enough (astronomical dark is -18)
STEP_MIN = 5


def windows(day, lat, lon, tz_h):
    """[(start, end, moon illumination)] in local time for the night that starts on `day` (noon to noon)."""
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    t0 = Time(dt.datetime(day.year, day.month, day.day, 12) - dt.timedelta(hours=tz_h))
    ts = t0 + np.arange(0, 24 * 60, STEP_MIN) * u.min
    fr = AltAz(obstime=ts, location=loc)
    sun = get_body("sun", ts, loc)
    moon = get_body("moon", ts, loc)
    ok = (sun.transform_to(fr).alt.deg < SUN_DARK_DEG) & (moon.transform_to(fr).alt.deg < 0)
    illum = float(np.mean((1 - np.cos(sun.separation(moon).rad)) / 2))
    out, start = [], None
    for t, good in zip(ts, ok):
        local = (t + tz_h * u.hour).datetime
        if good and start is None:
            start = local
        if not good and start is not None:
            out.append((start, local, illum))
            start = None
    if start is not None:
        out.append((start, (ts[-1] + tz_h * u.hour).datetime, illum))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default=dt.date.today().isoformat(), help="first night, YYYY-MM-DD (local)")
    ap.add_argument("--nights", type=int, default=14)
    ap.add_argument("--lat", type=float, default=36.8)
    ap.add_argument("--lon", type=float, default=10.18)
    ap.add_argument("--tz", type=float, default=1.0, help="local time minus UTC, hours")
    a = ap.parse_args()
    configure_offline_iers()
    d0 = dt.date.fromisoformat(a.start)
    print(f"dark (sun < {SUN_DARK_DEG:g} deg) and moon below the horizon, local time (UTC{a.tz:+g}):")
    for i in range(a.nights):
        day = d0 + dt.timedelta(days=i)
        ws = windows(day, a.lat, a.lon, a.tz)
        illum = ws[0][2] if ws else None
        txt = ", ".join(f"{s:%H:%M}-{e:%H:%M} ({(e - s).seconds // 60} min)" for s, e, _ in ws) or "none"
        moon = f"moon {illum:.0%}" if illum is not None else ""
        print(f"  night of {day:%a %Y-%m-%d}: {txt}  {moon}")


if __name__ == "__main__":
    main()

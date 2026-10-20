#!/usr/bin/env python3
"""Fetch the IERS Earth-orientation table (finals2000A, IERS-A: measured + ~1 year predicted) for offline use.

    python3 navera_tools/fetch_iers.py [--out FILE]

Run with the map download before departure (internet needed only here). The celestial pipeline reads it from
NAVERA_IERS_FILE (default ~/navera_data/iers/finals2000A.all) and never downloads in operation
(cn_pkg celestial_math.configure_offline_iers). Prints the date range it covers.
"""
import argparse
import os
import shutil
import sys
import tempfile
import urllib.request

URLS = ("https://datacenter.iers.org/data/9/finals2000A.all", "https://maia.usno.navy.mil/ser7/finals2000A.all")


def main():
    default = os.path.expanduser(os.environ.get("NAVERA_IERS_FILE", "~/navera_data/iers/finals2000A.all"))
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=default)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    for url in URLS:
        try:
            with urllib.request.urlopen(url, timeout=60) as r, tempfile.NamedTemporaryFile(
                    "wb", delete=False, dir=os.path.dirname(a.out)) as f:
                shutil.copyfileobj(r, f)
            from astropy.utils import iers
            t = iers.IERS_A.open(f.name)                 # must parse before it replaces the old one
            os.replace(f.name, a.out)
            mjd = t["MJD"]
            from astropy.time import Time
            print(f"saved {a.out} from {url}: {Time(mjd.min(), format='mjd').iso[:10]} .. "
                  f"{Time(mjd.max(), format='mjd').iso[:10]} (predictions included)")
            return 0
        except Exception as e:
            print(f"{url}: {e}", file=sys.stderr)
    print("no IERS table fetched: the celestial fix will use the bundled table (< 0.4 km extra)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

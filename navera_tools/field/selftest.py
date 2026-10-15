#!/usr/bin/env python3
"""Prove the field chain works before a real night: a known sky photo goes through the whole
server (star check, solver, comparison with the "phone") and the answer must match.

    python3 -m navera_tools.field.selftest

The photo (a real sky, solved by astrometry.net: centre RA 106.1123, Dec 37.6187) is shown
to the server as if the camera pointed straight up. The fake phone sits where that sky is
overhead at this very second, so the right answer is known to a few hundred metres. It
passes when the solver's position is within 5 km of the phone and every frame was saved.
This checks the wiring, the time and longitude conventions and the saved files. It does not
check the camera: only a clear night can show whether the Insta360 sees enough stars.
"""
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    sys.path.insert(0, p)

from cn_pkg.nodes.celestial_math import apparent_radec, gast_deg  # noqa: E402
from navera_tools.field import server  # noqa: E402

PHOTO = os.environ.get("NAVERA_SELFTEST_PHOTO",
                       "/media/shadow-team/ADATA SD620/nour/sky_localization_v0/sky_localization/ImageTest.jpeg")
RA, DEC = 106.1123, 37.6187


class PhotoCamera:
    device, cal_path, latency_s, hfov, error = "photo", "none", 0.0, 60.7, None   # its width in degrees, from the Siril solution

    def __init__(self, path):
        self.img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if self.img is None:
            sys.exit(f"cannot read {path}")

    def latest(self):
        return self.img, time.time()


def overhead_now():
    utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ra, dec = apparent_radec(RA, DEC, utc)
    return dec, (ra - gast_deg(utc) + 540.0) % 360.0 - 180.0


def main():
    root = tempfile.mkdtemp(prefix="navera_selftest_")
    f = server.Field(root, PhotoCamera(PHOTO))
    f.usable_skies = ("clear", "hazy", "cloudy")     # the processed photo has a brightness gradient
    f.interval_s = 5.0
    t_end = time.time() + 20
    while time.time() < t_end and f.live.get("confirmed") is None:
        time.sleep(0.5)
    print(f"stars confirmed in the photo: {f.live.get('confirmed')} (sky: {f.live.get('sky')})")

    def feed():
        lat, lon = overhead_now()
        f.on_phone({"lat": lat, "lon": lon, "acc": 5, "speed": 0, "beta": 0.0, "gamma": 0.0, "compass": 0,
                    "phone_t_ms": int(time.time() * 1000)})
    for _ in range(4):
        feed()
        time.sleep(0.3)
    f.go(2), f.go(3), f.go(4)
    deadline = time.time() + 240
    while time.time() < deadline:
        feed()
        time.sleep(1.0)
        if f.last_fix:
            break
    time.sleep(1.0)
    fix = dict(f.last_fix)
    report = f.finish()
    sdir = os.path.join(root, report["id"])
    saved = sorted(os.listdir(sdir))
    print("fix:", fix)
    print("saved:", saved)
    ok = bool(fix) and fix.get("err_km") is not None and fix["err_km"] < 5.0 and "report.json" in saved \
        and "frames.jsonl" in saved and "phone.jsonl" in saved
    print("SELFTEST", "PASSED" if ok else "FAILED", "error", fix.get("err_km"), "km; folder", sdir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

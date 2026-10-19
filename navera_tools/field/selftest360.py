#!/usr/bin/env python3
"""Prove the 360 field chain before a real night: a synthetic full-360 sky, as the standing Insta360
would see it now at a place where it is night, goes through the whole server (live star count,
all-sky identification with the focal length search, gravity, comparison with the "phone").

    python3 -m navera_tools.field.selftest360 [limit_mag]

The sky is the Yale catalogue drawn with refraction through the lens model in sky360, the camera
standing with a few degrees of tilt and a random heading; its gravity is exact plus noise. The
focal length is drawn 4% off the model's guess, so the search must find it. Passes when the fix
is within 20 km of the phone and every frame was saved. It checks the wiring and the maths, not
the camera: only a clear night shows how many stars the real video exposure keeps.
"""
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg"), os.path.join(ROOT, "navera_tools", "sim")):
    sys.path.insert(0, p)

from navera_tools.field import allsky, server, sky360  # noqa: E402

LAT = 36.8
F_TRUE = 1.04


def night_longitude(now):
    return round((-15.0 * (now.hour + now.minute / 60.0) + 180.0) % 360.0 - 180.0, 1)


def render(utc, lat, lon, limit_mag, seed=5):
    """(grey 3840x1920 frame, 'up' in the IMU frame) of a standing camera."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
    from sky_view import _enu, load_bsc5
    rng = np.random.default_rng(seed)
    ra, dec, mag = load_bsc5(os.path.expanduser("~/.navera_sim"))
    keep = mag <= limit_mag
    aa = SkyCoord(ra=ra[keep] * u.deg, dec=dec[keep] * u.deg).transform_to(
        AltAz(obstime=Time(utc), location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg)))
    alt = aa.alt.deg + allsky.refraction_deg(aa.alt.deg)
    v_enu, m = _enu(alt, aa.az.deg), mag[keep]
    heading, tilt = rng.uniform(0, 360), rng.normal(0, 3, 2)
    up, hd = np.array([0, 0, 1.0]), np.array([math.sin(math.radians(heading)), math.cos(math.radians(heading)), 0])

    def rot(axis, deg):
        a = np.asarray(axis, float) / np.linalg.norm(axis)
        t = math.radians(deg)
        K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
        return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K
    R_world_imu = rot([1, 0, 0], tilt[0]) @ rot([0, 1, 0], tilt[1]) @ np.stack([up, hd, np.cross(up, hd)], axis=1)
    v_imu = v_enu @ R_world_imu
    frame = rng.normal(10, 3, (1920, 3840)).astype(np.float32)
    ys, xs = np.mgrid[-4:5, -4:5]
    psf = np.exp(-(xs ** 2 + ys ** 2) / (2 * 1.2 ** 2))
    for lens in sky360.default_lenses():
        lens.f *= F_TRUE
        x, y, th = lens.project(v_imu @ lens.R_lens_imu.T)
        ok = (alt > 0.5) & (th < math.radians(100)) & (x > 4) & (x < 3835) & (y > 4) & (y < 1915)
        for xi, yi, mi in zip(x[ok], y[ok], m[ok]):
            cx, cy = int(round(xi)), int(round(yi))
            frame[cy - 4:cy + 5, cx - 4:cx + 5] += 900 * 10 ** (-0.4 * (mi - 1)) * psf
    return np.clip(frame, 0, 255).astype(np.uint8), R_world_imu.T @ up


class SimCamera360:
    device, cal_path, hfov, latency_s, error = "synthetic 360", "none", None, 0.0, None

    def __init__(self, frame, up):
        self.frame, self.up = frame, up

    def latest(self):
        return self.frame, time.time()

    def gravity(self, at_frame=False):
        return self.up + np.random.default_rng().normal(0, 0.0005, 3), 1.0, 0.001


def main():
    limit = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    now = datetime.now(timezone.utc)
    lon = night_longitude(now)
    frame, up = render(now.strftime("%Y-%m-%d %H:%M:%S"), LAT, lon, limit)
    root = tempfile.mkdtemp(prefix="navera_selftest360_")
    f = server.Field(root, SimCamera360(frame, up))
    f.interval_s = 5.0
    t_end = time.time() + 15
    while time.time() < t_end and not f.live:
        time.sleep(0.5)
    print(f"spots above the horizon: {f.live.get('confirmed')} (sky: {f.live.get('sky')})")

    def feed():
        f.on_phone({"lat": LAT, "lon": lon, "acc": 5, "speed": 0, "phone_t_ms": int(time.time() * 1000)})
    for _ in range(4):
        feed()
        time.sleep(0.3)
    f.go(2), f.go(3), f.go(4)
    deadline = time.time() + 400
    while time.time() < deadline and not f.last_fix:
        feed()
        time.sleep(1.0)
    fix = dict(f.last_fix)
    report = f.finish()
    sdir = os.path.join(root, report["id"])
    saved = sorted(os.listdir(sdir))
    print("fix:", fix, "| focal scale found:", f.f_scale, f"(true {F_TRUE})")
    print("saved:", saved)
    ok = bool(fix) and fix.get("err_km") is not None and fix["err_km"] < 20.0 and "frames.jsonl" in saved
    print("SELFTEST360", "PASSED" if ok else "FAILED", "error", fix.get("err_km"), "km; folder", sdir)
    sys.stdout.flush()
    os._exit(0 if ok else 1)                 # background threads (camera, decoder) must not abort the exit


if __name__ == "__main__":
    main()

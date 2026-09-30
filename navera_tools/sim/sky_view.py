"""Simulated star camera: the real sky seen from the true position, time and attitude.

Stars come from the Yale Bright Star Catalogue (BSC5, 9110 stars to V≈6.5,
J2000; public, fetched once to <work>/bsc5.dat). They are placed with astropy
(apparent alt/az at the given UTC), projected through a pinhole camera
(gnomonic) with the camera's true boresight and roll, and drawn with a
Gaussian blur, brightness from their magnitude and sky noise. With the Sun
above -12° (nautical twilight) the sky is too bright: no stars.

The picture is made from a catalogue, not photographed: it tests the chain
(plate solving, time, attitude, geometry), not a real sensor's sensitivity,
clouds or light pollution.
"""
import gzip
import math
import os
import urllib.request

import numpy as np
from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_sun
from astropy.time import Time

BSC5_URL = "http://tdc-www.harvard.edu/catalogs/bsc5.dat.gz"


def load_bsc5(work_dir):
    path = os.path.join(work_dir, "bsc5.dat")
    if not os.path.exists(path):
        with urllib.request.urlopen(BSC5_URL, timeout=60) as r:
            data = gzip.decompress(r.read())
        with open(path, "wb") as f:
            f.write(data)
    ra, dec, mag = [], [], []
    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("latin-1")
            try:
                rah, ram, ras = int(line[75:77]), int(line[77:79]), float(line[79:83])
                sign = -1.0 if line[83] == "-" else 1.0
                ded, dem, des = int(line[84:86]), int(line[86:88]), int(line[88:90])
                v = float(line[102:107])
            except ValueError:
                continue                       # a few entries have no position (novae…)
            ra.append(15.0 * (rah + ram / 60.0 + ras / 3600.0))
            dec.append(sign * (ded + dem / 60.0 + des / 3600.0))
            mag.append(v)
    return np.array(ra), np.array(dec), np.array(mag)


def _enu(alt_deg, az_deg):
    a, A = np.radians(alt_deg), np.radians(az_deg)
    return np.stack([np.cos(a) * np.sin(A), np.cos(a) * np.cos(A), np.sin(a)], axis=-1)


class SkyCamera:
    def __init__(self, work_dir, hfov_deg=60.0, size=(1024, 768), limit_mag=6.0, seed=11):
        self.ra, self.dec, self.mag = load_bsc5(work_dir)
        keep = self.mag <= limit_mag
        self.ra, self.dec, self.mag = self.ra[keep], self.dec[keep], self.mag[keep]
        self.stars = SkyCoord(ra=self.ra * u.deg, dec=self.dec * u.deg, frame="icrs")
        self.hfov = hfov_deg
        self.w, self.h = size
        self.f = (self.w / 2) / math.tan(math.radians(hfov_deg) / 2)
        self.rng = np.random.default_rng(seed)

    def sun_altitude(self, lat, lon, utc):
        t = Time(utc, scale="utc")
        loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
        return float(get_sun(t).transform_to(AltAz(obstime=t, location=loc)).alt.deg)

    def render(self, lat, lon, utc, alt_deg, az_deg, roll_deg=0.0):
        """8-bit grey image of the sky; (image, n_stars_in_view, sun_altitude)."""
        t = Time(utc, scale="utc")
        loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
        frame = AltAz(obstime=t, location=loc)
        aa = self.stars.transform_to(frame)
        s_alt, s_az = aa.alt.deg, aa.az.deg
        sun = float(get_sun(t).transform_to(frame).alt.deg)

        img = self.rng.normal(12.0, 3.0, (self.h, self.w))
        if sun > -12.0:                      # twilight / day: washed-out sky
            level = min(255.0, 60.0 + 12.0 * (sun + 12.0))
            img = self.rng.normal(level, 4.0, (self.h, self.w))
            return np.clip(img, 0, 255).astype(np.uint8), 0, sun

        fwd = _enu(alt_deg, az_deg)
        up_world = np.array([0.0, 0.0, 1.0])
        ref = up_world if abs(fwd @ up_world) < 0.99 else np.array([0.0, 1.0, 0.0])
        right = np.cross(fwd, ref)
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        r = math.radians(roll_deg)
        right, up = (math.cos(r) * right + math.sin(r) * up,
                     -math.sin(r) * right + math.cos(r) * up)
        v = _enu(s_alt, s_az)
        z = v @ fwd
        vis = (z > 0.1) & (s_alt > 5.0)
        x = self.w / 2 + self.f * (v[vis] @ right) / z[vis]
        y = self.h / 2 - self.f * (v[vis] @ up) / z[vis]
        m = self.mag[vis]
        inside = (x >= 2) & (x < self.w - 2) & (y >= 2) & (y < self.h - 2)
        x, y, m = x[inside], y[inside], m[inside]
        ys, xs = np.mgrid[-4:5, -4:5]
        sigma = 1.3
        psf = np.exp(-(xs ** 2 + ys ** 2) / (2 * sigma ** 2))
        for xi, yi, mi in zip(x, y, m):
            flux = 900.0 * 10 ** (-0.4 * (mi - 1.0))
            cx, cy = int(round(xi)), int(round(yi))
            x0, x1 = max(cx - 4, 0), min(cx + 5, self.w)
            y0, y1 = max(cy - 4, 0), min(cy + 5, self.h)
            img[y0:y1, x0:x1] += flux * psf[y0 - cy + 4:y1 - cy + 4, x0 - cx + 4:x1 - cx + 4]
        return np.clip(img, 0, 255).astype(np.uint8), int(len(x)), sun

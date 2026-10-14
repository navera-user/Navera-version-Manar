"""Tests of navera_lite/stars.py (mission 26). Shipped from mission 27 on (finished part); not in mission 26 itself."""
import math

import numpy as np

from navera_lite import stars as S


def test_julian_date_and_gmst():
    assert S.julian_date(2000, 1, 1, 12) == 2451545.0
    assert abs(S.julian_date(1987, 4, 10, 19, 21) - 2446896.30625) < 1e-6        # Meeus, example 12.b
    assert abs(S.gmst_deg(2451545.0) - 280.46061837) < 1e-8
    g = S.gmst_deg(np.array([2451545.0, 2451546.0]))
    assert g.shape == (2,) and np.all((g >= 0) & (g < 360))


def test_altaz_and_both_roots_round_trip():
    gst = 123.4
    for lat, lon, alt, az in ((51.5, -0.12, 19.0, 37.9), (-33.9, 18.4, 65.0, 170.0), (69.65, 18.96, 55.0, 0.0)):
        a, A, phi = map(math.radians, (alt, az, lat))
        dec = math.degrees(math.asin(math.sin(a) * math.sin(phi) + math.cos(a) * math.cos(phi) * math.cos(A)))
        H = math.degrees(math.atan2(-math.cos(a) * math.sin(A), math.sin(a) * math.cos(phi) - math.cos(a) * math.sin(phi) * math.cos(A)))
        ra = (gst + lon - H) % 360.0
        a2, z2 = S.altaz(ra, dec, lat, lon, gst)
        assert abs(a2 - alt) < 1e-6 and abs((z2 - az + 180) % 360 - 180) < 1e-6
        roots = S.both_roots(alt, az, ra, dec, gst)
        assert any(S.sep_deg(r[0], r[1], lat, lon) < 1e-6 for r in roots)
        assert S.choose(roots, lat + 0.5, lon) is not None


def test_lat_from_polaris_and_error_km():
    assert S.lat_from_polaris(40.0) == 40.0
    assert abs(S.lat_from_polaris(40.0, 0.0, 0.6) - 39.4) < 1e-12
    assert abs(S.error_km(1.0) - S.KM_PER_DEG) < 1e-9
    assert abs(S.error_km(0.0, 2.0, 60.0) - S.KM_PER_DEG) < 1e-9


def test_detect_one_star():
    img = np.zeros((9, 9), np.uint8)
    img[3:6, 3:6] = [[10, 20, 10], [20, 80, 40], [10, 20, 10]]
    pts, flux = S.detect_stars(img)
    assert pts.shape == (1, 2) and abs(pts[0, 0] - 4.0909) < 1e-3 and abs(pts[0, 1] - 4.0) < 1e-9 and flux[0] == 220.0

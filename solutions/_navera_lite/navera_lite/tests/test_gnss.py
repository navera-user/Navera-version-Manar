"""Tests of navera_lite/gnss.py (mission 15). Written for the course; it is not NAVERA code.

Run from the lesson folder:  python3 -m pytest navera_lite/tests/test_gnss.py -q
"""
import math

import numpy as np
import pytest

from navera_lite import gnss


def sentence(body):
    return f"${body}*{gnss.nmea_checksum(body)}"


def test_checksum_has_two_upper_case_digits():
    assert gnss.nmea_checksum("GPGSA,A,1") == "32"
    assert gnss.nmea_checksum("GPGSA,A,18") == "0A"
    assert gnss.nmea_checksum("") == "00"


def test_is_valid_never_crashes_and_refuses_damage():
    good = sentence("GPGGA,101010.00,0013.50000,S,07829.10000,W,4,21,0.45,2850.4,M,,M,,")
    assert gnss.is_valid(good + "\r\n")
    assert gnss.is_valid("$GNGSA,A,3,07,12,30,05,,,,,,,,,3.1,1.8,2.5,1*3f")      # lower-case hex
    for bad in (good[:40], good.split("*")[0], good[:-1], sentence("GPGGA,1$GPGGA,2"), None, "", 42,
                good.replace("2850.4", "2850.5")):
        assert gnss.is_valid(bad) is False


def test_a_swap_keeps_the_checksum():
    good = sentence("GPGGA,052200.00,3545.89257,N,01045.14417,E,1,12,0.77,2.1,M,32.0,M,,")
    swapped = good.replace("3545.89257", "5345.89257")
    assert gnss.is_valid(swapped)


def test_degrees_minutes_and_ranges():
    assert gnss.dm_to_deg("3544.04006", "N") == pytest.approx(35.734001, abs=1e-6)
    assert gnss.dm_to_deg("02156.77700", "W") == pytest.approx(-21.946283, abs=1e-6)
    for args in (("3560.0", "N"), ("9000.1", "N"), ("18000.1", "E"), ("", "N"), ("3544.0", "X")):
        assert gnss.dm_to_deg(*args) is None


def test_parse_gga_heights_and_empty_fields():
    g = gnss.parse_gga("$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,*70")
    assert g["qual"] == 1 and g["sats"] == 12 and g["h_ell_m"] == pytest.approx(127.4)
    g = gnss.parse_gga("$GPGGA,052009.00,,,,,0,00,99.99,,,,,,*68")
    assert g["lat"] is None and g["h_ell_m"] is None and g["qual"] == 0
    assert gnss.parse_gga("$GPRMC,051217.00,A,3549.61531,N,01038.52535,E,11.88,136.6,121026,,,A*5F") is None


def test_parse_gsa_accepts_nmea_410():
    g = gnss.parse_gsa("$GNGSA,M,2,07,,12,30,,,,,,,,,4.10,3.95,1.10,2*02")
    assert g["prns"] == [7, 12, 30] and g["vdop"] == pytest.approx(1.10)


def test_dops_worked_example_and_singular_geometry():
    d = gnss.dops([0, 90, 180, 270, 0], [30, 30, 30, 30, 90])
    assert d["HDOP"] == pytest.approx(2 / math.sqrt(3), abs=1e-9)
    assert d["VDOP"] == pytest.approx(math.sqrt(5), abs=1e-9)
    assert gnss.dops([0, 90, 180, 270], [30] * 4) is None          # numpy's inv does not fail here
    assert gnss.dops([0, 120, 240], [30, 50, 70]) is None


def test_dops_do_not_depend_on_a_rotation_of_the_sky():
    az, el = np.array([10, 80, 150, 200, 300, 250.0]), np.array([15, 50, 35, 70, 25, 60.0])
    a, b = gnss.dops(az, el), gnss.dops(az + 37.0, el)
    assert a["HDOP"] == pytest.approx(b["HDOP"]) and a["VDOP"] == pytest.approx(b["VDOP"])


def test_decision_covariance_and_state():
    assert gnss.fix_decision({"qual": 6, "lat": 1.0, "lon": 2.0}) == (False, "receiver dead reckoning (quality 6)")
    assert gnss.fix_decision({"qual": 2, "lat": 1.0, "lon": 2.0}) == (True, "satellite fix")
    cov, t = gnss.covariance_from_hdop(1.35)
    assert t == gnss.COV_TYPE_APPROXIMATED and cov[0] == pytest.approx(7.29) and cov[8] == pytest.approx(29.16)
    assert gnss.covariance_from_hdop(None) == ([0.0] * 9, gnss.COV_TYPE_UNKNOWN)
    ok = {"qual": 1, "lat": 1.0, "lon": 2.0}
    assert gnss.fix_state(dict(ok, hdop=12.5)) == ("FIX", "σ 25.0 m")
    assert gnss.fix_state(dict(ok, hdop=20.0))[0] == "DEGRADED"
    assert gnss.fix_state(dict(ok, hdop=None)) == ("DEGRADED", "σ unknown")
    assert gnss.fix_state(None) == ("NO_FIX", "not a GGA sentence")

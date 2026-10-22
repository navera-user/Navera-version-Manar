"""gps_node: the receiver's UTC from RMC (the GNSS time celestial may trust, hazard H-08)."""
import pynmea2
import pytest

pytest.importorskip("serial")
from gps_pkg.nodes.gps_node import rmc_utc_epoch, zda_utc_epoch   # noqa: E402


def _rmc(body):
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return pynmea2.parse(f"${body}*{cs:02X}", check=True)


def test_a_valid_rmc_gives_the_gnss_utc():
    msg = _rmc("GPRMC,201959.50,A,3549.73,N,01038.16,E,0.0,0.0,211026,,,A")
    assert rmc_utc_epoch(msg) == pytest.approx(1792613999.5, abs=1e-3)     # 2026-10-21 20:19:59.5 UTC


def test_no_time_from_a_void_or_dateless_rmc():
    assert rmc_utc_epoch(_rmc("GPRMC,201959.50,V,,,,,,,211026,,,N")) is None
    assert rmc_utc_epoch(_rmc("GPRMC,201959.50,A,3549.73,N,01038.16,E,0.0,0.0,,,,A")) is None


def test_zda_gives_the_date_and_time():
    assert zda_utc_epoch(_rmc("GPZDA,201959.50,21,10,2026,00,00")) == pytest.approx(1792613999.5, abs=1e-3)


def test_no_time_from_an_unset_or_empty_zda():
    assert zda_utc_epoch(_rmc("GPZDA,000012.00,06,01,1980,00,00")) is None    # receiver clock not set yet
    assert zda_utc_epoch(_rmc("GPZDA,,,,,00,00")) is None

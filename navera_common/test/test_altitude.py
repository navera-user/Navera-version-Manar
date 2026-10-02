"""Height above ground from GPS, image matches and measured sources."""
import pytest

from navera_common.altitude import AltitudeEstimator


def test_gps_minus_the_ground_at_power_on():
    a = AltitudeEstimator()
    a.add_gps(0.0, 52.0)                            # on the ground at power-on
    a.add_gps(60.0, 202.0)
    agl, sigma, src = a.estimate(60.0)
    assert (agl, src) == (150.0, "GPS - ground")
    assert sigma == pytest.approx((10.0 ** 2 + (0.25 * 150.0) ** 2) ** 0.5)   # terrain unknown
    assert a.ground_source == "first GPS fix"


def test_configured_site_elevation_wins_over_the_first_fix():
    a = AltitudeEstimator(ground_altitude_m=40.0)
    a.add_gps(0.0, 300.0)                           # powered on in flight
    assert a.estimate(0.0)[0] == 260.0


def test_image_correction_is_carried_by_the_gps():
    a = AltitudeEstimator()
    a.add_gps(0.0, 50.0)
    a.add_gps(10.0, 200.0)                          # GPS says 150 m...
    a.add_vision(10.0, 135.0, 3.0)                  # ...the image measures 135 m (higher ground)
    a.add_gps(20.0, 210.0)                          # climbs 10 m
    agl, sigma, src = a.estimate(20.0)
    assert agl == pytest.approx(145.0) and src == "image + GPS" and sigma < 4.0


def test_after_gps_loss_the_image_height_is_held_with_growing_uncertainty():
    a = AltitudeEstimator()
    a.add_gps(0.0, 50.0)
    a.add_gps(10.0, 200.0)
    a.add_vision(10.0, 150.0, 3.0)
    agl, sigma, src = a.estimate(40.0)              # GPS silent since t=10
    assert agl == 150.0 and src == "image (held)" and sigma == pytest.approx(3.0 + 0.5 * 30)
    assert a.estimate(200.0) is None                # too old: unknown


def test_a_measured_height_wins_while_fresh():
    a = AltitudeEstimator()
    a.add_gps(0.0, 50.0)
    a.add_gps(5.0, 200.0)
    a.add_measured(5.0, 142.0, 0.5)
    assert a.estimate(5.0) == (142.0, 0.5, "measured")
    a.add_gps(7.0, 201.0)
    assert a.estimate(7.0)[2] == "GPS - ground"     # rangefinder silent: next source


def test_nothing_known():
    assert AltitudeEstimator().estimate(0.0) is None

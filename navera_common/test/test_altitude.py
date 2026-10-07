"""Height above ground from GPS, image matches and measured sources."""
import pytest

from navera_common.altitude import AltitudeEstimator


def test_gps_minus_the_ground_at_power_on():
    a = AltitudeEstimator()
    a.add_gps(0.0, 52.0)                            # on the ground at power-on
    a.add_gps(60.0, 202.0)
    agl, sigma, src = a.estimate(60.0)
    assert (agl, src) == (150.0, "GPS - ground")
    assert sigma == pytest.approx(_ref(10.0, 150.0))                      # terrain unknown
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
    assert a.estimate(200.0)[2] == "GPS - ground (held)"   # image too old: the held GPS height
    assert a.estimate(400.0) is None                # everything too old: unknown


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


def test_vehicle_barometer_keeps_the_height_after_gps_loss():
    a = AltitudeEstimator()
    a.add_gps(0.0, 50.0)
    a.add_relative(0.0, 0.0)
    a.add_relative(10.0, 150.0)
    a.add_vision(10.0, 135.0, 3.0)                  # the image: higher ground than home
    a.add_relative(30.0, 160.0)                     # GPS lost since t=0, the barometer goes on
    agl, sigma, src = a.estimate(30.0)
    assert agl == pytest.approx(145.0) and src == "image + vehicle altitude" and sigma < 4.0


def test_vehicle_altitude_above_home_without_image():
    a = AltitudeEstimator()
    a.add_relative(5.0, 120.0)
    agl, sigma, src = a.estimate(5.0)
    assert agl == 120.0 and src == "vehicle altitude above home"
    assert sigma == pytest.approx(_ref(3.0, 120.0))


def test_after_gps_loss_without_image_the_last_height_is_held():
    a = AltitudeEstimator()
    a.add_gps(0.0, 50.0)
    a.add_gps(10.0, 200.0)                          # then jammed
    agl, sigma, src = a.estimate(70.0)
    assert agl == 150.0 and src == "GPS - ground (held)"
    assert sigma == pytest.approx(_ref(10.0, 150.0) + 0.5 * 60.0)
    assert a.estimate(400.0) is None                # held too long: unknown


def test_restart_in_the_air_uses_the_ground_saved_before():
    saved = []
    a = AltitudeEstimator(on_ground=saved.append)
    a.add_gps(0.0, 40.0, 35.80, 10.60)                       # power-on on the ground
    assert saved == [dict(altitude_m=40.0, lat=35.80, lon=10.60)]
    b = AltitudeEstimator(saved_ground=saved[0])             # restarted at 150 m above it
    b.add_gps(500.0, 190.0, 35.81, 10.61)
    assert b.ground == 40.0 and b.ground_source == "saved ground (restart)"
    assert b.estimate(500.0)[0] == 150.0
    c = AltitudeEstimator(saved_ground=saved[0])             # another site: not reused
    c.add_gps(500.0, 300.0, 36.50, 10.10)
    assert c.ground == 300.0 and c.ground_source == "first GPS fix"


def test_ground_from_gps_and_height_above_home_even_in_the_air():
    a = AltitudeEstimator()
    a.add_relative(10.0, 120.0)
    a.add_gps(10.0, 165.0, 35.8, 10.6)                       # NAVERA started at 120 m
    assert a.ground == 45.0 and a.ground_source == "GPS - height above home"
    a.add_gps(20.0, 175.0, 35.8, 10.6)
    a.add_relative(20.0, 130.0)
    assert a.ground == 45.0


def _ref(sigma_ref, agl, relief=30.0, frac=0.02):
    """A reference height's sigma: its own, the terrain relief (metres), a little of the height."""
    return (sigma_ref ** 2 + relief ** 2 + (frac * agl) ** 2) ** 0.5


def test_a_barometer_height_at_400_m_passes_the_night_gate():
    """Night matching needs the height within 15 %: with 25 % of the height for the terrain
    no reference could ever pass (2026-10-07, simulator: night refused every frame)."""
    a = AltitudeEstimator()
    a.add_relative(0.0, 400.0)
    agl, sigma, _ = a.estimate(0.0)
    assert sigma / agl < 0.15


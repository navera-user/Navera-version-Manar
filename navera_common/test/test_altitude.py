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
    assert agl == pytest.approx(145.0) and src == "image + GPS"
    assert sigma == pytest.approx((3.0 ** 2 + 2.0 ** 2 + (1.0 * 10.0) ** 2) ** 0.5)   # the ground may differ


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
    assert agl == pytest.approx(145.0) and src == "image + vehicle altitude"
    assert sigma == pytest.approx((3.0 ** 2 + 2.0 ** 2 + 20.0 ** 2) ** 0.5)
    assert a.estimate(10.0)[1] == pytest.approx((3.0 ** 2 + 2.0 ** 2) ** 0.5)   # at the image: its own


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
    no reference could ever pass (2026-10-07, simulator: night refused every frame).
    """
    a = AltitudeEstimator()
    a.add_relative(0.0, 400.0)
    agl, sigma, _ = a.estimate(0.0)
    assert sigma / agl < 0.15


def test_a_carried_image_height_grows_uncertain_up_to_the_terrain_relief():
    """The barometer carries the vehicle's height, not the ground's: over a valley the ground under
    the vehicle moved 100 m in 20 s of flight (MARS-LVIG AMvalley03) while the carried image height
    said +-4 m. Its sigma grows with the time since the image (terrain_rate_mps), never past the
    relief a reference height assumes.
    """
    a = AltitudeEstimator(terrain_rate_mps=1.0)
    a.add_relative(0.0, 130.0)
    a.add_vision(0.0, 130.0, 3.0)
    for t in (10.0, 20.0, 60.0, 110.0):
        a.add_relative(t, 130.0)
    s10, s20, s60, s110 = (a.estimate(t)[1] for t in (10.0, 20.0, 60.0, 110.0))
    assert s10 < s20 < s60
    cap = (30.0 ** 2 + (0.02 * 130.0) ** 2) ** 0.5
    assert s60 == pytest.approx(s110) == pytest.approx((3.0 ** 2 + 2.0 ** 2 + cap ** 2) ** 0.5)


# ── the DEM (navera_common.terrain) ─────────────────────────────────────
def _valley(sigma=4.0):
    """A DEM rising 100 m per 0.01 deg of latitude northwards (slope ~0.09), flat east-west; the
    home (35.80, 10.60) at 500 m.
    """
    import numpy as np
    from navera_common.terrain import Terrain
    rows = np.arange(301)[:, None] * 0.001                 # 0.001 deg per row, north = 36.0
    grid = np.tile(500.0 + (36.0 - rows - 35.80) * 1e4, (1, 201))
    return Terrain.from_grid(grid, 36.0, 10.5, 0.001, 0.001, sigma)


def test_dem_gives_the_height_over_relief_from_the_home_anchor():
    """Barometer 150 m above home; the ground under the vehicle is 50 m higher than home: 100 m."""
    T = _valley()
    a = AltitudeEstimator(terrain=T)
    a.set_home(35.80, 10.60)
    a.add_relative(10.0, 150.0)
    a.add_position(10.0, 35.805, 10.60, 5.0)
    agl, sigma, src = a.estimate(10.0)
    assert src == "vehicle altitude - DEM" and agl == pytest.approx(100.0, abs=0.01)
    slope = 100.0 / (0.01 * 111320.0)
    home = (4.0 ** 2 + 1.0 ** 2) ** 0.5
    assert sigma == pytest.approx((home ** 2 + 3.0 ** 2 + 4.0 ** 2 + (slope * 5.0) ** 2) ** 0.5)


def test_without_dem_or_position_or_anchor_nothing_changes():
    for kw, home, pos in (({}, True, True), ({"terrain": _valley()}, False, True),
                          ({"terrain": _valley()}, True, False)):
        a = AltitudeEstimator(**kw)
        if home:
            a.set_home(35.80, 10.60)
        a.add_relative(10.0, 150.0)
        if pos:
            a.add_position(10.0, 35.805, 10.60, 5.0)
        assert a.estimate(10.0) == (150.0, pytest.approx(_ref(3.0, 150.0)), "vehicle altitude above home")


def test_first_gps_fix_on_the_ground_is_the_home():
    a = AltitudeEstimator(terrain=_valley())
    a.add_gps(0.0, 540.0, 35.80, 10.60)             # GPS datum 40 m off the DEM's: does not matter
    a.add_gps(10.0, 690.0, 35.805, 10.60)
    a.add_position(10.0, 35.805, 10.60, 3.0)
    agl, _, src = a.estimate(10.0)
    assert src == "GPS - DEM" and agl == pytest.approx(100.0, abs=0.01)


def test_image_heights_anchor_the_dem_and_carry_it_over_the_relief():
    """No home position (NAVERA started in the air): the image height taken over one place ties
    the DEM to the barometer; 60 s later over ground 80 m lower the height is right, where the
    image carried by the barometer alone would be 80 m off.
    """
    a = AltitudeEstimator(terrain=_valley())
    a.add_relative(0.0, 150.0)
    a.add_position(0.0, 35.805, 10.60, 3.0)
    a.add_vision(0.0, 100.0, 3.0)                    # ground 550 m, home 500 m: 150 - 50
    a.add_relative(60.0, 150.0)
    a.add_position(60.0, 35.797, 10.60, 3.0)         # ground 470 m
    agl, sigma, src = a.estimate(60.0)
    assert src == "vehicle altitude - DEM" and agl == pytest.approx(180.0, abs=0.05)
    assert sigma < 12.0


def test_a_wrong_image_anchor_is_outvoted():
    a = AltitudeEstimator(terrain=_valley())
    a.add_relative(0.0, 150.0)
    for i in range(5):
        a.add_position(float(i), 35.805, 10.60, 3.0)
        a.add_relative(float(i), 150.0)
        a.add_vision(float(i), 100.0 if i != 2 else 160.0, 3.0)
    a.add_relative(10.0, 150.0)
    a.add_position(10.0, 35.805, 10.60, 3.0)
    assert a._home_ground("vehicle")[0] == pytest.approx(500.0, abs=0.05)


def test_position_is_moved_on_at_its_velocity_then_dropped():
    a = AltitudeEstimator(terrain=_valley(), position_max_age_s=5.0)
    a.add_position(0.0, 35.800, 10.60, 5.0)
    a.add_position(1.0, 35.801, 10.60, 5.0)          # 111 m/s north
    lat, lon, sig = a._position_at(3.0)
    assert lat == pytest.approx(35.803) and sig == pytest.approx(5.0 + 0.5 * 111.32 * 2.0)
    assert a._position_at(7.0) is None
    assert a._position_at(0.5)[0] == pytest.approx(35.8005)


def test_the_dem_is_used_only_when_more_certain():
    """Right after an image height its carry (sigma ~3.6 m) beats a DEM of sigma 20 m."""
    a = AltitudeEstimator(terrain=_valley(sigma=20.0))
    a.set_home(35.80, 10.60)
    a.add_relative(0.0, 150.0)
    a.add_position(0.0, 35.805, 10.60, 3.0)
    a.add_vision(0.0, 101.0, 3.0)
    assert a.estimate(0.0)[2] == "image + vehicle altitude"

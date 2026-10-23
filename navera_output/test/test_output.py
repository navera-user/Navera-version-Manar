"""Unit tests for the vehicle output: decision policy, NMEA, MAVLink GPS_INPUT."""
import json
import math
from datetime import datetime, timezone
from types import SimpleNamespace

import pynmea2
import pytest
from pymavlink.dialects.v20 import common as mavlink2

from navera_output import mavlink_out, nmea
from navera_output.policy import (KIND_ESTIMATED, KIND_FIX, KIND_NONE, STATE_DEGRADED,
                                  STATE_FIX, STATE_NO_FIX, Config, Output, bridge, decide, hold)

GPS, DAY = 1, 2
T = datetime(2026, 9, 28, 12, 34, 56, 780000, tzinfo=timezone.utc)


def pos(source=GPS, lat=35.8288, lon=10.6360, alt=43.0, var=(4.0, 4.0, 16.0), details=None):
    cov = [var[0], 0, 0, 0, var[1], 0, 0, 0, var[2]]
    return SimpleNamespace(source=source, latitude=lat, longitude=lon, altitude=alt,
                           position_covariance=[float(c) for c in cov],
                           details_json=json.dumps(details or {"num_sats": 9, "geo_sep_m": 33.0}))


# ── policy ────────────────────────────────────────────────────────────────
def test_fix_is_sent_with_real_accuracy():
    o = decide(Config(), STATE_FIX, 0.1, pos(), 0.2, GPS)
    assert o.kind == KIND_FIX and o.sigma_h_m == 2.0 and o.sigma_v_m == 4.0
    assert o.satellites == 9 and o.alt_msl_m == pytest.approx(10.0)


def test_degraded_is_withheld_by_default():
    o = decide(Config(), STATE_DEGRADED, 0.1, pos(source=DAY), 0.2, DAY)
    assert o.kind == KIND_NONE and "forward_degraded" in o.reason


def test_degraded_forwarded_only_with_a_stated_sigma():
    with pytest.raises(ValueError):
        Config(forward_degraded=True).validate()
    cfg = Config(forward_degraded=True, degraded_sigma_m=600.0)
    cfg.validate()
    o = decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY, details={}), 0.2, DAY)
    assert o.kind == KIND_ESTIMATED and o.sigma_h_m == 600.0 and o.satellites == 0


@pytest.mark.parametrize("state, st_age, p, p_age, active, reason", [
    (None, None, pos(), 0.1, GPS, "arbiter silent"),
    (STATE_FIX, 5.0, pos(), 0.1, GPS, "arbiter silent"),          # nav_status stale
    (1, 0.1, pos(), 0.1, GPS, "no fix"),                           # NO_FIX
    (STATE_FIX, 0.1, None, None, GPS, "position not current"),
    (STATE_FIX, 0.1, pos(), 6.0, GPS, "position not current"),     # stale position (> 5 s)
    (STATE_FIX, 0.1, pos(source=DAY), 0.1, GPS, "not from the active source"),
    (STATE_FIX, 0.1, pos(lat=math.nan), 0.1, GPS, "not finite"),
])
def test_everything_else_is_no_fix(state, st_age, p, p_age, active, reason):
    o = decide(Config(), state, st_age, p, p_age, active)
    assert o.kind == KIND_NONE and reason in o.reason


# ── NMEA ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lat, lon", [(35.8288, 10.636), (-33.8688, 151.2093),
                                      (40.7128, -74.006), (-0.5, -0.25)])
def test_gga_rmc_parse_back_exactly(lat, lon):
    o = decide(Config(), STATE_FIX, 0.1, pos(lat=lat, lon=lon), 0.1, GPS)
    g = pynmea2.parse(nmea.gga(o, T).strip(), check=True)      # checksum verified
    r = pynmea2.parse(nmea.rmc(o, T).strip(), check=True)
    assert g.latitude == pytest.approx(lat, abs=1e-7) and g.longitude == pytest.approx(lon, abs=1e-7)
    assert r.latitude == pytest.approx(lat, abs=1e-7) and r.longitude == pytest.approx(lon, abs=1e-7)
    assert g.gps_qual == 1 and g.num_sats == "09" and float(g.horizontal_dil) == 1.0
    assert float(g.altitude) == pytest.approx(10.0) and float(g.geo_sep) == 33.0
    assert r.status == "A" and r.mode_indicator == "A" and r.datestamp.isoformat() == "2026-09-28"
    assert g.timestamp.isoformat().startswith("12:34:56.78")


def test_estimated_is_quality_6_mode_e():
    cfg = Config(forward_degraded=True, degraded_sigma_m=600.0)
    o = decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY, details={}), 0.1, DAY)
    g = pynmea2.parse(nmea.gga(o, T).strip(), check=True)
    r = pynmea2.parse(nmea.rmc(o, T).strip(), check=True)
    assert g.gps_qual == 6 and float(g.horizontal_dil) == 99.9 and r.mode_indicator == "E"


def test_no_fix_sentences_carry_no_position():
    o = Output(KIND_NONE, "no fix")
    g = pynmea2.parse(nmea.gga(o, T).strip(), check=True)
    r = pynmea2.parse(nmea.rmc(o, T).strip(), check=True)
    assert g.gps_qual == 0 and g.lat == "" and r.status == "V" and r.lat == ""


def test_minute_rounding_carries_into_degrees():
    o = decide(Config(), STATE_FIX, 0.1, pos(lat=35.99999999999, lon=10.0), 0.1, GPS)
    g = pynmea2.parse(nmea.gga(o, T).strip(), check=True)
    assert g.lat.startswith("3600.00000") and g.latitude == pytest.approx(36.0, abs=1e-6)


# ── MAVLink GPS_INPUT ─────────────────────────────────────────────────────
def _roundtrip(fields):
    mav = mavlink2.MAVLink(None, srcSystem=1, srcComponent=191)
    buf = mav.gps_input_encode(**fields).pack(mav)
    return mavlink2.MAVLink(None).parse_char(buf)


def test_gps_input_fix_roundtrip():
    o = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS)
    m = _roundtrip(mavlink_out.gps_input_fields(o, T))
    assert m.get_type() == "GPS_INPUT" and m.fix_type == mavlink_out.FIX_3D
    assert m.lat == 358288000 and m.lon == 106360000 and m.alt == pytest.approx(10.0)
    assert m.horiz_accuracy == pytest.approx(2.0) and m.satellites_visible == 9
    assert not m.ignore_flags & mavlink_out.IGNORE_ALT
    # a GPS fix without a receiver velocity states none: an "unknown" 30 m/s accuracy would keep
    # ArduPilot from setting its origin (EKF3 "GPS speed error", SITL)
    assert m.ignore_flags & mavlink_out.IGNORE_VEL_HORIZ and m.ignore_flags & mavlink_out.IGNORE_SPEED_ACCURACY


def test_gps_input_no_fix_and_unknown_altitude():
    m = _roundtrip(mavlink_out.gps_input_fields(Output(KIND_NONE), T))
    assert m.fix_type == mavlink_out.FIX_NO_FIX and m.lat == 0
    o = decide(Config(), STATE_FIX, 0.1, pos(alt=math.nan), 0.1, GPS)
    m = _roundtrip(mavlink_out.gps_input_fields(o, T, mavlink_out.FIX_2D))
    assert m.fix_type == mavlink_out.FIX_2D and m.ignore_flags & mavlink_out.IGNORE_ALT
    # default: usable by ArduPilot / PX4 (3D, altitude flagged ignored)
    m = _roundtrip(mavlink_out.gps_input_fields(o, T))
    assert m.fix_type == mavlink_out.FIX_3D and m.ignore_flags & mavlink_out.IGNORE_ALT


def test_gps_input_never_carries_a_vision_height():
    """F7: a non-GNSS position goes out with IGNORE_ALT even when its producer attached a
    height (here day vision at FIX and forwarded as ESTIMATED, both with altitude and geoid).
    """
    day = pos(source=DAY, alt=500.0)
    for o in (decide(Config(), STATE_FIX, 0.1, day, 0.1, DAY),
              decide(Config(forward_degraded=True, degraded_sigma_m=15.0), STATE_DEGRADED, 0.1, day, 0.1, DAY)):
        assert o.kind in (KIND_FIX, KIND_ESTIMATED) and not o.gnss and math.isfinite(o.alt_msl_m)
        m = _roundtrip(mavlink_out.gps_input_fields(o, T))
        assert m.fix_type == mavlink_out.FIX_3D and m.ignore_flags & mavlink_out.IGNORE_ALT
        assert m.alt == 0.0 and m.lat == 358288000


def test_gps_week_time():
    # 2026-09-28 00:00:00 UTC is Monday of GPS week 2438 (anchor: 2022-11-27 = week 2238),
    # plus 18 leap seconds.
    week, ms = mavlink_out.gps_week_time(datetime(2026, 9, 28, tzinfo=timezone.utc))
    assert week == 2438 and ms == (1 * 86400 + 18) * 1000


# ── Velocity ──────────────────────────────────────────────────────────────
def test_gps_velocity_is_sent_with_a_gps_position():
    o = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS, (3.0, -4.0))
    assert o.has_velocity
    m = _roundtrip(mavlink_out.gps_input_fields(o, T))
    assert not m.ignore_flags & mavlink_out.IGNORE_VEL_HORIZ
    assert m.ignore_flags & mavlink_out.IGNORE_VEL_VERT
    assert (m.vn, m.ve) == (pytest.approx(3.0), pytest.approx(-4.0))
    # stated: a receiver's velocity accuracy is not in RMC; the configured one, never 0 / ignored
    assert not m.ignore_flags & mavlink_out.IGNORE_SPEED_ACCURACY and m.speed_accuracy == pytest.approx(0.5)
    r = pynmea2.parse(nmea.rmc(o, T, 5.0, 306.87).strip())
    assert float(r.spd_over_grnd) == pytest.approx(5.0 / 0.514444, abs=0.01)


def test_an_unknown_velocity_is_stated_unknown_never_left_out():
    """F28: ArduPilot keeps the last velocity it got when a GPS_INPUT flags it ignored, and EKF3
    resets its velocity to it after a timeout. An unknown velocity goes out as 0 +- top speed.
    """
    day = pos(source=2)
    o2 = decide(Config(), STATE_FIX, 0.1, day, 0.1, 2, (3.0, -4.0))   # a GPS velocity is not a vision one
    assert o2.kind == KIND_FIX and not o2.has_velocity
    est = decide(Config(forward_degraded=True, degraded_sigma_m=30.0, max_speed_mps=45.0),
                 STATE_DEGRADED, 0.1, day, 0.1, 2)
    for out in (o2, est):
        m = _roundtrip(mavlink_out.gps_input_fields(out, T))
        assert m.fix_type == mavlink_out.FIX_3D and (m.vn, m.ve, m.vd) == (0.0, 0.0, 0.0)
        assert not m.ignore_flags & (mavlink_out.IGNORE_VEL_HORIZ | mavlink_out.IGNORE_SPEED_ACCURACY)
        assert m.ignore_flags & mavlink_out.IGNORE_VEL_VERT
        assert m.speed_accuracy == pytest.approx(45.0 if out is est else 30.0)
    for vel in (None, (math.nan, 1.0)):                                 # GPS: stated none
        o = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS, vel)
        assert not o.has_velocity and math.isnan(o.vel_sigma_mps)
    # nothing stated at all (an Output built by hand): flagged ignored, as before
    m = _roundtrip(mavlink_out.gps_input_fields(Output(KIND_ESTIMATED, lat=35.8, lon=10.6, sigma_h_m=30.0), T))
    assert m.ignore_flags & mavlink_out.IGNORE_VEL_HORIZ and m.ignore_flags & mavlink_out.IGNORE_SPEED_ACCURACY
    # "no fix": everything flagged ignored (ArduPilot's EKF does not read a fix_type 1 message)
    m = _roundtrip(mavlink_out.gps_input_fields(Output(KIND_NONE), T))
    assert m.ignore_flags & mavlink_out.IGNORE_VEL_HORIZ and m.ignore_flags & mavlink_out.IGNORE_VEL_VERT


def test_a_vision_position_carries_navera_s_velocity_with_its_accuracy_and_never_a_vertical_one():
    cfg = Config(forward_degraded=True, degraded_sigma_m=30.0)
    o = decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY, alt=500.0), 0.1, DAY,
               autopilot_vel=(-22.0, 1.5, 2.4))                      # east, north, sigma
    assert o.kind == KIND_ESTIMATED and o.has_velocity and o.vel_sigma_mps == 2.4
    m = _roundtrip(mavlink_out.gps_input_fields(o, T))
    assert (m.vn, m.ve) == (pytest.approx(1.5), pytest.approx(-22.0))
    assert m.speed_accuracy == pytest.approx(2.4)
    assert m.ignore_flags & mavlink_out.IGNORE_VEL_VERT and m.vd == 0.0
    assert m.ignore_flags & mavlink_out.IGNORE_ALT                       # F7 unchanged
    assert not m.ignore_flags & (mavlink_out.IGNORE_VEL_HORIZ | mavlink_out.IGNORE_SPEED_ACCURACY)
    # NMEA: only a measured velocity gives RMC a speed (an unknown one has none)
    assert not decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY), 0.1, DAY).has_velocity


def test_after_a_gap_a_vision_position_waits_for_the_velocity_of_the_new_fixes():
    """F28: the first fix after an EKF3 timeout resets the autopilot's position AND velocity."""
    from navera_output.policy import reacquire
    cfg = Config(forward_degraded=True, degraded_sigma_m=30.0)
    day = pos(source=DAY, details={})
    unknown = decide(cfg, STATE_DEGRADED, 0.1, day, 0.1, DAY)
    rough = decide(cfg, STATE_DEGRADED, 0.1, day, 0.1, DAY, autopilot_vel=(20.0, 0.0, 9.5))
    good = decide(cfg, STATE_DEGRADED, 0.1, day, 0.1, DAY, autopilot_vel=(20.0, 0.0, 6.0))
    for out in (unknown, rough):
        for quiet in (5.0, 60.0, None):                                  # None: never sent anything
            r = reacquire(cfg, out, quiet)
            assert r.kind == KIND_NONE and "reacquiring" in r.reason and not r.soft
    assert reacquire(cfg, good, 60.0) is good
    assert reacquire(cfg, unknown, 4.9) is unknown                       # no gap: sent as it is
    assert reacquire(Config(forward_degraded=True, degraded_sigma_m=30.0, reacquire_after_s=0.0),
                     unknown, 60.0) is unknown                           # disabled
    gps = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS)
    assert reacquire(cfg, gps, 60.0) is gps                              # a GPS fix never waits
    _, held = _held_east()
    b = bridge(VISION, held, 104.0)
    assert reacquire(cfg, b, 60.0) is b                                  # nor a bridged position


def test_forwarded_accuracy_never_better_than_the_source_states():
    cfg = Config(forward_degraded=True, degraded_sigma_m=300.0)
    cn = pos(source=4, var=(55_000.0 ** 2, 55_000.0 ** 2, 0.0))
    cn.position_covariance_type = 1                         # APPROXIMATED
    o = decide(Config(forward_degraded=True, degraded_sigma_m=300.0, max_forward_sigma_m=1e6),
               STATE_DEGRADED, 0.1, cn, 0.1, 4)
    assert o.kind == KIND_ESTIMATED and o.sigma_h_m == pytest.approx(55_000.0)
    o = decide(cfg, STATE_DEGRADED, 0.1, cn, 0.1, 4)            # default limit 1 km
    assert o.kind == KIND_NONE and "too coarse" in o.reason
    day = pos(source=DAY)                                  # unknown covariance → configured
    day.position_covariance_type = 0
    assert decide(cfg, STATE_DEGRADED, 0.1, day, 0.1, DAY).sigma_h_m == 300.0


def test_old_measurements_are_withheld_and_the_rest_carry_their_age():
    cfg = Config(forward_degraded=True, degraded_sigma_m=30.0)
    o = decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY), 0.1, DAY, measured_age_s=0.8)
    assert o.kind == KIND_ESTIMATED and o.age_s == pytest.approx(0.8)
    o = decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY), 0.1, DAY, measured_age_s=5.6)
    assert o.kind == KIND_NONE and "measured 5.6 s ago" in o.reason
    o = decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY), 0.1, DAY, measured_age_s=-5.0)
    assert o.kind == KIND_NONE and "future" in o.reason
    assert decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS).age_s == 0.0      # age unknown: now


def test_a_forwarded_sigma_above_the_ceiling_is_refused_at_start():
    with pytest.raises(ValueError, match="nothing would ever be forwarded"):
        Config(forward_degraded=True, degraded_sigma_m=5000.0).validate()
    Config(forward_degraded=True, degraded_sigma_m=30.0).validate()


def test_a_vision_position_never_goes_out_over_nmea_unless_allowed():
    from navera_output.policy import for_nmea
    cfg = Config(forward_degraded=True, degraded_sigma_m=30.0)
    est = decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY), 0.1, DAY)
    assert est.kind == KIND_ESTIMATED
    assert for_nmea(est).kind == KIND_NONE and "NMEA" in for_nmea(est).reason
    assert for_nmea(est, allow_degraded=True) is est
    fix = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS)
    assert for_nmea(fix) is fix


def test_a_vision_position_is_carried_to_now_with_an_honest_accuracy():
    cfg = Config(forward_degraded=True, degraded_sigma_m=30.0, max_speed_mps=60.0)
    p = pos(source=DAY, lat=35.8, lon=10.6)
    # 1.5 s old photo, flying north at 40 m/s (speed known to +-1 m/s)
    o = decide(cfg, STATE_DEGRADED, 0.1, p, 0.1, DAY, measured_age_s=1.5, ground_vel=(0.0, 40.0, 1.0))
    north_m = (o.lat - 35.8) * 111195.0
    assert north_m == pytest.approx(60.0, abs=0.5) and o.age_s == 0.0
    assert o.sigma_h_m == pytest.approx(31.5)                     # 30 + 1 m/s x 1.5 s
    # speed unknown: not moved, stamped when measured, accuracy grown by max speed x age
    o = decide(cfg, STATE_DEGRADED, 0.1, p, 0.1, DAY, measured_age_s=1.5)
    assert o.lat == 35.8 and o.age_s == pytest.approx(1.5) and o.sigma_h_m == pytest.approx(30.0 + 90.0)
    # GPS is never carried (its latency is small and the autopilot's own)
    g = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS, measured_age_s=0.2, ground_vel=(0.0, 40.0, 1.0))
    assert g.lat == 35.8288 and g.sigma_h_m == 2.0


def test_a_degraded_position_needs_a_stated_accuracy_somewhere():
    cfg = Config(forward_degraded=True)                       # no degraded_sigma_m (the ROS case)
    unknown = pos(source=DAY)
    unknown.position_covariance_type = 0
    assert decide(cfg, STATE_DEGRADED, 0.1, unknown, 0.1, DAY).kind == KIND_NONE
    stated = pos(source=DAY, var=(900.0, 900.0, 0.0))
    stated.position_covariance_type = 1
    o = decide(cfg, STATE_DEGRADED, 0.1, stated, 0.1, DAY)
    assert o.kind == KIND_ESTIMATED and o.sigma_h_m == 30.0


def test_only_a_satellite_position_is_labelled_gnss():
    assert decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS).gnss is True
    p = pos(source=DAY, details={})
    assert decide(Config(), STATE_FIX, 0.1, p, 0.1, DAY).gnss is False        # a future vision FIX


# ── bridging a gap in the vision positions ───────────────────────────────
VISION = Config(forward_degraded=True, degraded_sigma_m=50.0)


def _held_east(speed=15.0, sigma=50.0, sig_v=1.0):
    """A forwarded estimate at t = 100, the vehicle flying east at `speed`."""
    p = pos(source=DAY, details={}, var=(sigma ** 2, sigma ** 2, 0))
    p.position_covariance_type = 2                       # the source states its accuracy
    o = decide(VISION, STATE_DEGRADED, 0.1, p, 0.1, DAY)
    return o, hold(o, 100.0, (speed, 0.0, sig_v))


def test_the_soft_no_fix_reasons_are_the_ones_a_gap_can_be_bridged_for():
    cfg = VISION
    assert decide(cfg, STATE_NO_FIX, 0.1, pos(source=DAY), 0.1, DAY).soft
    assert decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY), 6.0, DAY).soft          # position not current
    assert decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY), 0.1, DAY, None, 6.0).soft  # measured too long ago
    # the arbiter silent (crashed, restarting) or initializing (just restarted): no NEW position,
    # bridgeable (B23: a killed estimator landed the copter on the real box)
    assert decide(cfg, None, None, None, None, None).soft
    assert decide(cfg, STATE_DEGRADED, 3.0, pos(source=DAY), 0.1, DAY).soft         # nav_status stale
    init = decide(cfg, 0, 0.1, pos(source=DAY), 0.1, DAY)
    assert init.soft and init.kind == KIND_NONE and "initializing" in init.reason
    assert not decide(cfg, STATE_DEGRADED, 0.1, pos(source=DAY), 0.1, GPS).soft      # other source
    coarse = decide(Config(forward_degraded=True, degraded_sigma_m=900.0, max_speed_mps=30.0), STATE_DEGRADED, 0.1,
                    pos(source=DAY, details={}), 0.1, DAY, None, 4.0)
    assert coarse.kind == KIND_NONE and not coarse.soft and "too coarse" in coarse.reason


def test_a_bridged_position_moves_along_the_velocity_with_a_growing_accuracy():
    first, held = _held_east()
    prev = first.sigma_h_m
    lon_per_m = 1.0 / (111195.0 * math.cos(math.radians(first.lat)))
    for dt in (1.0, 3.0, 6.0, 10.0):
        b = bridge(VISION, held, 100.0 + dt)
        assert b.kind == KIND_ESTIMATED and b.bridged and b.sigma_h_m > prev and b.age_s == 0.0
        assert b.lon == pytest.approx(first.lon + 15.0 * dt * lon_per_m, abs=1e-7)
        prev = b.sigma_h_m
    # velocity error 1 m/s + heading 5 deg x 15 m/s + 1/2 a t^2 with a = 0.5, over 10 s
    assert prev == pytest.approx(first.sigma_h_m + 10.0 + math.radians(5.0) * 15.0 * 10.0 + 25.0, rel=1e-6)


def test_a_bridged_position_carries_the_velocity_sent_before_its_accuracy_growing():
    p = pos(source=DAY, details={}, var=(2500.0, 2500.0, 0))
    p.position_covariance_type = 2
    o = decide(VISION, STATE_DEGRADED, 0.1, p, 0.1, DAY, autopilot_vel=(15.0, 0.0, 2.0))
    # the plain track velocity (north here) is not what the position is carried along
    b = bridge(VISION, hold(o, 100.0, (0.0, 15.0, 1.0)), 104.0)
    assert (b.vel_n_mps, b.vel_e_mps) == (0.0, 15.0)
    assert b.vel_sigma_mps == pytest.approx(2.0 + 0.5 * 4.0)              # + unseen accel x t
    lon_per_m = 1.0 / (111195.0 * math.cos(math.radians(o.lat)))
    assert b.lat == pytest.approx(o.lat) and b.lon == pytest.approx(o.lon + 60.0 * lon_per_m, abs=1e-7)
    assert b.sigma_h_m == pytest.approx(50.0 + 2.0 * 4.0 + math.radians(5.0) * 15.0 * 4.0 + 4.0)
    _, held = _held_east()                                                # sent without one
    b = bridge(VISION, held, 104.0)
    assert not b.has_velocity and b.vel_sigma_mps == VISION.max_speed_mps


def test_a_bridge_without_a_velocity_stays_put_and_grows_by_the_top_speed():
    o = decide(VISION, STATE_DEGRADED, 0.1, pos(source=DAY, details={}, var=(2500.0, 2500.0, 0)), 0.1, DAY)
    held = hold(o, 100.0, None)
    b = bridge(VISION, held, 104.0)
    assert (b.lat, b.lon) == (o.lat, o.lon)
    assert b.sigma_h_m == pytest.approx(o.sigma_h_m + 30.0 * 4.0)


def test_a_bridge_ends_at_its_time_or_when_the_accuracy_is_too_coarse():
    _, held = _held_east()
    assert bridge(VISION, held, 100.0 + 10.0).kind == KIND_ESTIMATED
    late = bridge(VISION, held, 100.0 + 10.1)
    assert late.kind == KIND_NONE and "longer than the bridge" in late.reason
    far = Config(forward_degraded=True, degraded_sigma_m=50.0, max_forward_sigma_m=100.0)
    _, held2 = _held_east(sigma=70.0)
    coarse = bridge(far, held2, 100.0 + 8.0)                 # 70 + 8 + 0.087*15*8 + 16 = 104 > 100
    assert coarse.kind == KIND_NONE and "too coarse" in coarse.reason


def test_nothing_is_bridged_unless_forwarding_a_vision_estimate():
    gps = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS)
    assert hold(gps, 100.0, (10.0, 0.0, 1.0)) is None                # a GPS fix is never bridged
    vis = decide(VISION, STATE_FIX, 0.1, pos(source=DAY, details={}, var=(40.0, 40.0, 0)), 0.1, DAY)
    assert vis.kind == KIND_FIX and not vis.gnss
    assert hold(vis, 100.0, None) is not None                        # a vision FIX is (endur2)
    assert hold(Output(KIND_NONE, "no fix"), 100.0, None) is None
    _, held = _held_east()
    assert bridge(Config(), held, 101.0).kind == KIND_NONE           # forward_degraded off
    assert bridge(Config(forward_degraded=True, degraded_sigma_m=50.0, bridge_max_s=0.0), held, 101.0).kind == KIND_NONE
    assert bridge(VISION, None, 101.0).kind == KIND_NONE
    assert bridge(VISION, held, 99.0).kind == KIND_NONE              # a clock that went backwards


def test_velocity_settings_are_validated():
    for bad in (dict(max_speed_mps=0.0), dict(gnss_speed_sigma_mps=0.0), dict(reacquire_after_s=-1.0),
                dict(reacquire_vel_sigma_mps=0.0)):
        with pytest.raises(ValueError):
            Config(forward_degraded=True, degraded_sigma_m=50.0, **bad).validate()


def test_bridge_settings_are_validated():
    with pytest.raises(ValueError):
        Config(forward_degraded=True, degraded_sigma_m=50.0, bridge_period_s=0.0).validate()
    with pytest.raises(ValueError):
        Config(forward_degraded=True, degraded_sigma_m=50.0, bridge_max_s=-1.0).validate()


# ── MAVLink HIL_GPS (PX4) ─────────────────────────────────────────────────
def _roundtrip_hil(fields):
    mav = mavlink2.MAVLink(None, srcSystem=1, srcComponent=191)
    buf = mav.hil_gps_encode(**fields).pack(mav)
    return mavlink2.MAVLink(None).parse_char(buf)


def test_hil_gps_fix_carries_the_receiver_accuracy_and_altitude():
    o = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS, (3.0, -4.0))
    m = _roundtrip_hil(mavlink_out.hil_gps_fields(o, T))
    assert m.get_type() == "HIL_GPS" and m.fix_type == 3
    assert m.lat == 358288000 and m.lon == 106360000 and m.alt == 10000      # MSL mm
    assert m.eph == 200 and m.epv == 400 and m.satellites_visible == 9
    assert (m.vn, m.ve, m.vd) == (300, -400, 0) and m.vel == 500
    assert m.cog == pytest.approx(30687, abs=1)
    assert m.time_usec == int(T.timestamp() * 1e6)


def test_hil_gps_vision_position_has_no_vision_height_no_satellites():
    """A non-GNSS position: PX4 cannot be told to ignore the altitude — the last GNSS altitude
    (held) goes out with epv UNKNOWN, never the vision height (F7); 0 satellites; stated eph.
    """
    est = decide(Config(forward_degraded=True, degraded_sigma_m=15.0), STATE_DEGRADED, 0.1,
                 pos(source=DAY, alt=500.0), 0.1, DAY)
    assert est.kind == KIND_ESTIMATED
    m = _roundtrip_hil(mavlink_out.hil_gps_fields(est, T, held_alt_msl_m=250.4))
    assert m.fix_type == 3 and m.alt == 250400 and m.epv == mavlink_out.UINT16_UNKNOWN
    assert m.eph == 1500 and m.satellites_visible == 0
    # unknown velocity: 0 (PX4 reads it as valid: EKF2_GPS_CTRL must exclude velocity)
    assert (m.vn, m.ve) == (0, 0) and m.vel == mavlink_out.UINT16_UNKNOWN and m.cog == mavlink_out.UINT16_UNKNOWN
    m = _roundtrip_hil(mavlink_out.hil_gps_fields(est, T))            # nothing held: 0, still epv unknown
    assert m.alt == 0 and m.epv == mavlink_out.UINT16_UNKNOWN


def test_hil_gps_no_fix_and_clamping():
    m = _roundtrip_hil(mavlink_out.hil_gps_fields(Output(KIND_NONE), T))
    assert m.fix_type == mavlink_out.FIX_NO_FIX and m.lat == 0 and m.eph == mavlink_out.UINT16_UNKNOWN
    big = Output(KIND_ESTIMATED, lat=35.8, lon=10.6, sigma_h_m=900.0, vel_n_mps=400.0, vel_e_mps=-400.0)
    m = _roundtrip_hil(mavlink_out.hil_gps_fields(big, T))
    assert m.eph == 65534 and m.vn == 32767 and m.ve == -32767        # never "unknown" by overflow
    assert mavlink_out.hil_gps_fields(Output(KIND_ESTIMATED, lat=1, lon=1, sigma_h_m=0.004), T)["eph"] == 1


def test_message_for_autopilot():
    from navera_output.nodes.vehicle_output_node import message_for_autopilot
    assert message_for_autopilot(12) == "hil_gps"                     # MAV_AUTOPILOT_PX4
    assert message_for_autopilot(3) == "gps_input"                    # ArduPilot
    assert message_for_autopilot(None) == "gps_input"

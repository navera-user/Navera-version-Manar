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
                                  STATE_FIX, Config, Output, decide)

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
    assert m.ignore_flags & mavlink_out.IGNORE_VEL_HORIZ and not m.ignore_flags & mavlink_out.IGNORE_ALT


def test_gps_input_no_fix_and_unknown_altitude():
    m = _roundtrip(mavlink_out.gps_input_fields(Output(KIND_NONE), T))
    assert m.fix_type == mavlink_out.FIX_NO_FIX and m.lat == 0
    o = decide(Config(), STATE_FIX, 0.1, pos(alt=math.nan), 0.1, GPS)
    m = _roundtrip(mavlink_out.gps_input_fields(o, T, mavlink_out.FIX_2D))
    assert m.fix_type == mavlink_out.FIX_2D and m.ignore_flags & mavlink_out.IGNORE_ALT
    # default: usable by ArduPilot / PX4 (3D, altitude flagged ignored)
    m = _roundtrip(mavlink_out.gps_input_fields(o, T))
    assert m.fix_type == mavlink_out.FIX_3D and m.ignore_flags & mavlink_out.IGNORE_ALT


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
    r = pynmea2.parse(nmea.rmc(o, T, 5.0, 306.87).strip())
    assert float(r.spd_over_grnd) == pytest.approx(5.0 / 0.514444, abs=0.01)


def test_no_velocity_without_gps_velocity_or_for_other_sources():
    o = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS, None)
    assert not o.has_velocity
    assert _roundtrip(mavlink_out.gps_input_fields(o, T)).ignore_flags & mavlink_out.IGNORE_VEL_HORIZ
    day = pos(source=2)
    o = decide(Config(), STATE_FIX, 0.1, day, 0.1, 2, (3.0, -4.0))
    assert o.kind == KIND_FIX and not o.has_velocity
    o = decide(Config(), STATE_FIX, 0.1, pos(), 0.1, GPS, (math.nan, 1.0))
    assert not o.has_velocity


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

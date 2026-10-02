"""A vehicle's NavSatFix becomes NAVERA's GPS source contract."""
import math

from navera_msgs.msg import PositionEstimate
from sensor_msgs.msg import NavSatFix, NavSatStatus

from gps_pkg.nodes.ros_gps_node import estimate_from_fix


def fix(status=NavSatStatus.STATUS_FIX, lat=35.8, lon=10.6, cov_type=NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN):
    m = NavSatFix()
    m.status.status, m.latitude, m.longitude, m.altitude = status, lat, lon, 40.0
    m.position_covariance = [4.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 16.0]
    m.position_covariance_type = cov_type
    return m


def test_a_fix_with_its_accuracy():
    e = estimate_from_fix(fix())
    assert e.valid and e.source == PositionEstimate.SOURCE_GPS and e.latitude == 35.8
    assert e.position_covariance[0] == 4.0
    assert e.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_APPROXIMATED


def test_no_fix_or_null_island_is_invalid():
    for m in (fix(status=NavSatStatus.STATUS_NO_FIX), fix(lat=0.0, lon=0.0), fix(lat=math.nan)):
        e = estimate_from_fix(m)
        assert not e.valid and math.isnan(e.latitude)


def test_unknown_accuracy_stays_unknown():
    e = estimate_from_fix(fix(cov_type=NavSatFix.COVARIANCE_TYPE_UNKNOWN))
    assert e.valid and e.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_UNKNOWN

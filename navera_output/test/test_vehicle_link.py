"""vehicle_link locks onto the autopilot, not onto another MAVLink device on the link."""
from pymavlink.dialects.v20 import common as mav

from navera_output.nodes.vehicle_link_node import VehicleLink


class FakeLink:
    def __init__(self, beats):
        self.beats, self.target_system, self.target_component = list(beats), 0, 0

    def recv_match(self, type=None, blocking=True, timeout=None):
        return self.beats.pop(0) if self.beats else None


def beat(sysid, compid, vtype, autopilot):
    m = mav.MAVLink_heartbeat_message(vtype, autopilot, 0, 0, 0, 3)
    m._header = mav.MAVLink_header(0, mlen=9, seq=0, srcSystem=sysid, srcComponent=compid)
    return m


def test_ground_station_heartbeat_is_skipped():
    gcs = beat(255, 190, mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID)
    cam = beat(1, 100, mav.MAV_TYPE_CAMERA, mav.MAV_AUTOPILOT_INVALID)
    ap = beat(1, 1, mav.MAV_TYPE_QUADROTOR, mav.MAV_AUTOPILOT_ARDUPILOTMEGA)
    link = FakeLink([gcs, cam, ap])
    hb = VehicleLink._wait_autopilot(link, timeout=2.0)
    assert hb is ap and (link.target_system, link.target_component) == (1, 1)


def test_no_autopilot_gives_none():
    link = FakeLink([beat(255, 190, mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID)])
    assert VehicleLink._wait_autopilot(link, timeout=0.5) is None


def test_the_first_gps_is_read_only_when_navera_does_not_feed_it():
    from navera_output.nodes.vehicle_link_node import gps1_readable
    assert gps1_readable(None, False)[0] is False                  # not read yet: not trusted
    assert gps1_readable(0, False)[0] is False
    assert gps1_readable(14, False) == (False, "GPS1 is fed over MAVLink (type 14): NAVERA's own output")
    assert gps1_readable(5, True)[0] is False                      # NMEA while NAVERA outputs NMEA
    assert gps1_readable(5, False)[0] is True
    for real in (1, 2, 9):                                         # auto, u-blox, DroneCAN
        assert gps1_readable(real, False)[0] is True


def test_gps_raw_messages_become_a_navsatfix_with_the_receivers_accuracy():
    from navera_output.nodes.vehicle_link_node import gps_raw_navsatfix
    from builtin_interfaces.msg import Time
    from sensor_msgs.msg import NavSatFix
    m = mav.MAVLink_gps_raw_int_message(0, 3, 357340010, 105758485, 95300, 72, 110, 50, 0, 14,
                                        alt_ellipsoid=127400, h_acc=1500, v_acc=2500)
    f = gps_raw_navsatfix(m, Time(), "vehicle_gps1")
    assert (f.latitude, f.longitude, f.altitude) == (35.734001, 10.5758485, 127.4)
    assert f.position_covariance_type == NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
    assert f.position_covariance[0] == 2.25 and f.position_covariance[8] == 6.25
    warned = []
    m2 = mav.MAVLink_gps_raw_int_message(0, 3, 357340010, 105758485, 95300, 72, 110, 50, 0, 14)
    f2 = gps_raw_navsatfix(m2, Time(), "vehicle_gps1", lambda: warned.append(1))
    assert f2.altitude == 95.3 and warned == [1]                   # MSL only: said
    assert f2.position_covariance_type == NavSatFix.COVARIANCE_TYPE_UNKNOWN
    assert gps_raw_navsatfix(mav.MAVLink_gps_raw_int_message(0, 2, 1, 1, 0, 0, 0, 0, 0, 5), None, "x") is None


def test_system_time_becomes_a_time_reference_only_once_the_autopilot_has_a_time():
    from builtin_interfaces.msg import Time
    from navera_output.nodes.vehicle_link_node import system_time_reference
    assert system_time_reference(mav.MAVLink_system_time_message(0, 123456), Time()) is None
    assert system_time_reference(mav.MAVLink_system_time_message(86_400_000_000, 1), Time()) is None   # 1970
    ref = system_time_reference(mav.MAVLink_system_time_message(1_792_613_999_500_123, 1), Time(sec=5))
    assert (ref.time_ref.sec, ref.time_ref.nanosec) == (1_792_613_999, 500_123_000)
    assert ref.source == "autopilot" and ref.header.stamp.sec == 5


def test_global_position_velocity_is_published_enu():
    """open3: the autopilot's EKF velocity for the day node's carry (GLOBAL_POSITION_INT vx north, vy east,
    vz down, cm/s -> TwistStamped ENU m/s)."""
    from types import SimpleNamespace
    from builtin_interfaces.msg import Time
    from navera_output.nodes.vehicle_link_node import global_position_velocity
    v = global_position_velocity(SimpleNamespace(vx=250, vy=-120, vz=40), Time(sec=5))
    assert (v.twist.linear.x, v.twist.linear.y, v.twist.linear.z) == (-1.2, 2.5, -0.4)
    assert v.header.stamp.sec == 5
    assert global_position_velocity(SimpleNamespace(vx=float("nan"), vy=0, vz=0), Time()) is None

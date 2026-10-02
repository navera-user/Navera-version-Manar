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

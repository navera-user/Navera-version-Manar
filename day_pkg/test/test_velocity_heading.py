"""The heading the track velocity was measured at, from the frames' attitude headings.

Real flight (MARS-LVIG AMvalley03, replayed through the node): after the GPS loss the track held GPS
points and odometry steps only — no vision fix, so no heading for its velocity — and a U-turn was
carried straight on (100 m off in 20 s).
"""
import math
from collections import deque
from types import MethodType, SimpleNamespace

import pytest

from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common.track import TrackVelocity

M_LAT = 1.0 / 111195.0


def _node(gps_east_mps=12.0):
    """GPS points 12 m/s east at t = 1000..1009 (no vision fix); frames heading 90 deg until 1009."""
    tr = TrackVelocity(accel_mps2=0.25)
    lon_m = M_LAT / math.cos(math.radians(39.9))
    for i in range(10):
        tr.add(1000.0 + i, 39.9, 44.9 + gps_east_mps * i * lon_m, 2.5)
    n = SimpleNamespace(track=tr, _carry=None, _track_heading=None, _vel_epoch=None, gyro=None,
                        _frame_headings=deque(maxlen=600))
    for f in ("_heading_for_match", "_carry_heading", "_velocity_heading", "_note_frame_heading",
              "_predicted", "_set_carry", "_keep_carry_velocity"):
        setattr(n, f, MethodType(getattr(DaySubscriber, f), n))
    n._frame_time = DaySubscriber._frame_time
    for i in range(10):
        n._note_frame_heading(_meta(1000.0 + i, 90.0))
    return n


def _meta(t, heading):
    return {"image_stamp_ns": int(t * 1e9), "attitude_source": "imu", "heading_deg": heading}


def test_the_velocity_heading_is_the_frames_heading_at_the_fit_time():
    n = _node()
    assert n.track.fit_time() == pytest.approx(1004.5)
    assert n._velocity_heading(0.0) == pytest.approx(90.0)


def test_a_turned_vehicle_carries_its_velocity_turned():
    """10 s later the IMU says heading 180 (south): the carried position goes south, not east."""
    n = _node()
    lat, lon, _ = n._predicted(_meta(1019.0, 180.0))
    north = (lat - 39.9) / M_LAT
    assert north < -30.0                                    # it turned south along the way


def test_without_frame_headings_nothing_changes():
    n = _node()
    n._frame_headings.clear()
    assert n._velocity_heading(0.0) is None                 # as before: no heading known
    lat, lon, _ = n._predicted(_meta(1019.0, 180.0))
    assert (lat - 39.9) / M_LAT == pytest.approx(0.0, abs=1.0)          # straight on east


def test_frame_headings_interpolate_across_north():
    n = _node()
    n._frame_headings.clear()
    n._note_frame_heading(_meta(2000.0, 350.0))
    n._note_frame_heading(_meta(2001.0, 10.0))
    at = DaySubscriber._heading_in
    assert at(n._frame_headings, 2000.5) == pytest.approx(0.0, abs=1e-6)
    assert at(n._frame_headings, 2002.0) == pytest.approx(10.0)         # just after the last frame
    assert at(n._frame_headings, 2005.0) is None                        # too far from any frame

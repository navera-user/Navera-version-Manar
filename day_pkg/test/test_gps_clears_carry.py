"""A trusted GPS fix ends any carried (dead-reckoned) velocity: after the GPS loss the track's own
velocity is carried, not one left from an earlier dead-reckoning."""
import math
import threading
from collections import deque
from types import SimpleNamespace

from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common.prior import GpsPrior
from navera_common.sensor_history import History
from navera_common.track import TrackVelocity
from navera_common.latency_cal import LatencyCalibrator
from navera_msgs.msg import PositionEstimate


def _gps(lat, lon, t):
    m = PositionEstimate()
    m.source, m.valid, m.mode = PositionEstimate.SOURCE_GPS, True, PositionEstimate.MODE_MEASURED
    m.latitude, m.longitude = lat, lon
    m.header.stamp.sec, m.header.stamp.nanosec = int(t), int((t % 1) * 1e9)
    m.position_covariance = [2.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0]
    return m


def test_a_gps_fix_clears_a_stale_carry(monkeypatch):
    n = DaySubscriber.__new__(DaySubscriber)
    n._gps_prior, n._gps_hist, n.latency_cal = GpsPrior(), History(maxlen=50, max_gap_s=1.5), LatencyCalibrator()
    n.shadow_mode, n._remember_anchor, n.track = False, (lambda: None), TrackVelocity()
    n._anchor_lat = n._anchor_lon = None
    n._gps_pending, n._busy_lock = deque(), threading.Lock()
    n._carry, n._vel_epoch = (35.8, 10.6, 100.0, 0.0, 0.0, 0.0, 9.0), 99.0      # standing still at power-on
    n.on_gps(_gps(35.81, 10.61, 1000.0))
    assert n._carry is None and n._vel_epoch is None and len(n.track._pts) == 1
    assert math.isclose(n._anchor_lat, 35.81)

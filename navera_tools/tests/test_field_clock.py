"""Field server time safety: the Jetson has no battery clock (boots on its last saved time, steps when
NTP arrives). Star solves only on a trusted time; a clock step drops the phone offsets taken before it."""
import time
import types

from navera_tools.field import server as srv


def _bare():
    """A Field without __init__ (no camera, no tracker): only the clock fields."""
    s = srv.Field.__new__(srv.Field)
    import collections
    import threading
    s.lock = threading.Lock()
    s.offsets = collections.deque(maxlen=60)
    s._wall_minus_mono = time.time() - time.monotonic()
    s._ntp_checked, s._ntp_synced = time.monotonic(), False      # cached: "not synchronised"
    s.session = None
    return s


def test_no_phone_clock_and_no_ntp_means_no_star_time():
    s = _bare()
    assert s.star_clock_offset_s() is None


def test_ntp_synchronised_jetson_is_trusted_without_the_phone():
    s = _bare()
    s._ntp_synced = True
    assert s.star_clock_offset_s() == 0.0


def test_phone_offset_is_used_when_known():
    s = _bare()
    s.offsets.extend([3600.2, 3600.1, 3600.3])
    assert abs(s.star_clock_offset_s() - 3600.2) < 1e-9


def test_a_clock_step_drops_the_old_offsets():
    s = _bare()
    s.offsets.extend([57600.0] * 5)
    s._wall_minus_mono -= 57600.0                     # as if the wall clock just jumped 16 h forward
    with s.lock:
        assert s._clock_jumped() is True
    assert len(s.offsets) == 0 and s.star_clock_offset_s() is None
    with s.lock:
        assert s._clock_jumped() is False               # once only


def test_small_drift_is_not_a_jump():
    s = _bare()
    s.offsets.extend([0.1] * 5)
    s._wall_minus_mono -= 0.5
    with s.lock:
        assert s._clock_jumped() is False
    assert len(s.offsets) == 5

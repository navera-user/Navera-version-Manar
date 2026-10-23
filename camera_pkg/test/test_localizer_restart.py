"""live_camera after its localizer was restarted alone (B23): the frame in flight is lost with the
old localizer; the new one's "ready" releases the next frame at once instead of after ack_timeout_s.
"""
import threading
from types import MethodType, SimpleNamespace

from std_msgs.msg import Bool

from camera_pkg.nodes.live_camera import LiveCamera


class _Log:
    def __init__(self):
        self.lines = []

    def warn(self, m):
        self.lines.append(m)


def _camera():
    c = SimpleNamespace(_ready=threading.Event(), _acked=threading.Event(), _awaiting=None, _log=_Log())
    c._acked.set()
    c.get_logger = lambda: c._log
    c._on_ready = MethodType(LiveCamera._on_ready, c)
    return c


def test_the_first_ready_only_opens_the_gate():
    c = _camera()
    c._on_ready(Bool(data=False))
    assert not c._ready.is_set()
    c._on_ready(Bool(data=True))
    assert c._ready.is_set() and c._acked.is_set() and c._log.lines == []


def test_a_restarted_localizer_releases_the_frame_waiting_for_its_ack():
    c = _camera()
    c._on_ready(Bool(data=True))
    c._awaiting = 41
    c._acked.clear()                                   # frame 41 sent, the localizer dies with it
    c._on_ready(Bool(data=True))                       # the respawned localizer is ready
    assert c._acked.is_set() and "frame 41 dropped" in c._log.lines[0]


def test_ready_again_with_nothing_in_flight_changes_nothing():
    c = _camera()
    c._on_ready(Bool(data=True))
    c._awaiting = 7                                    # acked already
    c._on_ready(Bool(data=True))
    assert c._acked.is_set() and c._log.lines == []

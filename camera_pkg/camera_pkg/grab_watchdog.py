"""Camera stall watchdog: a camera input that delivers no frame for `stall_s` is stalled.

The live camera exits on a stalled device so systemd restarts the pipeline and reopens it
(unplugged and replugged, a USB reset, a stuck driver). Counting failed grabs alone is not
enough: OpenCV's V4L2 grab waits up to 10 s before failing (50 failures = minutes), and a grab
that blocks never fails at all. The watchdog judges by time since the last good grab, and is
read both by the grab thread and by the sending thread (which sees a grab that never returns).
"""
import threading
from typing import Optional


class GrabWatchdog:
    """Time since the last good grab of a camera input (monotonic seconds)."""

    def __init__(self, stall_s: float = 10.0):
        self.stall_s = float(stall_s)
        self._last_ok: Optional[float] = None
        self._lock = threading.Lock()

    def start(self, now: float) -> None:
        """The device was opened at `now`: it has stall_s to deliver its first frame."""
        with self._lock:
            self._last_ok = now

    def ok(self, now: float) -> None:
        """A frame was grabbed at `now`."""
        with self._lock:
            self._last_ok = now

    def stalled(self, now: float) -> Optional[str]:
        """Why the camera counts as stalled at `now` (None: not stalled, or not started)."""
        with self._lock:
            last = self._last_ok
        if last is None or self.stall_s <= 0 or now - last <= self.stall_s:
            return None
        return f"no frame from the camera for {now - last:.0f} s (unplugged, or the driver is stuck)"

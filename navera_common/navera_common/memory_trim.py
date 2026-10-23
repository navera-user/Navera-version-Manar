"""Give freed heap memory back to the system (glibc malloc_trim), for long-running nodes.

The day pipeline allocates large, short-lived native buffers on many threads every frame (torch
CPU tensors, OpenCV images, numpy arrays; 38 threads in day_subscriber). glibc keeps what is freed
inside its arenas, and the high-water mark ratchets up whenever a larger transient appears: the
process RSS grows in steps with no Python object growing (F40: Isaac endurance run 2026-10-22,
day_subscriber 2192 -> 2365 MiB in 43 min on the same loop; tracemalloc on the Jetson soak saw
< 70 MB of Python allocations in the same time). malloc_trim(0) returns the free pages of every
arena to the kernel (madvise), without moving live data: a few ms on a 2 GB process.
"""
import ctypes
import ctypes.util
import time
from typing import Optional

_libc = None


def _load():
    global _libc
    if _libc is None:
        try:
            _libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
            _libc.malloc_trim.argtypes = [ctypes.c_size_t]
            _libc.malloc_trim.restype = ctypes.c_int
        except (OSError, AttributeError):        # not glibc (musl, macOS): nothing to trim
            _libc = False
    return _libc


def rss_mib() -> Optional[float]:
    """This process's resident memory (MiB), or None."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return None


def trim() -> bool:
    """malloc_trim(0): True if glibc released memory, False if not (or not glibc)."""
    libc = _load()
    return bool(libc and libc.malloc_trim(0))


class Trimmer:
    """Calls trim() at most every period_s; remembers what the last trim gave back."""

    def __init__(self, period_s: float = 60.0):
        self.period_s = float(period_s)
        self._last = None
        self.last_freed_mib = None
        self.last_ms = None

    def maybe_trim(self, now: Optional[float] = None) -> bool:
        """Trim if period_s has passed since the last trim (period_s <= 0: never)."""
        now = time.monotonic() if now is None else now
        if self.period_s <= 0 or (self._last is not None and now - self._last < self.period_s):
            return False
        self._last = now
        before, t0 = rss_mib(), time.perf_counter()
        trim()
        self.last_ms = (time.perf_counter() - t0) * 1000.0
        after = rss_mib()
        self.last_freed_mib = None if before is None or after is None else before - after
        return True

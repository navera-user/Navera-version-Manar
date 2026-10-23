"""Re-acquiring the map after a gap: the carried position's uncertainty searched with small windows.

After a long gap (cloud bank, uniform ground) the dead-reckoned position's stated uncertainty grows to
hundreds of metres, while its real error is often far smaller. One matcher window that wide fails:
the learned matcher (DISK + LightGlue) against a 600 m window found 0-11 matches on frames that gave
90-170 inliers in a 150 m window around the same place (Isaac Sim frames, outage 60 s, 2026-10-22,
offline replay; the GPS check had shown the same, day_subscriber._gps_check_locate). So the
uncertainty disc is covered with small windows instead, on a hexagonal lattice, nearest the
carried position first; a frame tries a few of them (the centre always, then the next ones of the
scan), the following frames go on with the scan.

Pure geometry and bookkeeping, no ROS: day_subscriber does the matching.
"""
import math
from typing import List, Tuple


def cover_windows(radius_m: float, window_m: float, max_windows: int = 400) -> List[Tuple[float, float]]:
    """(east, north) offsets in metres of windows of radius window_m whose union covers the disc of
    radius radius_m around (0, 0): a hexagonal lattice of spacing window_m x sqrt(3) (circles of
    radius window_m on it cover the plane), the windows that reach into the disc, nearest the centre
    first (ties by angle, for a stable order). Always starts with (0, 0); at most max_windows."""
    if not (window_m > 0.0) or not (radius_m > window_m):
        return [(0.0, 0.0)]
    s = window_m * math.sqrt(3.0)
    rows = int(math.ceil((radius_m + window_m) / (s * math.sqrt(3.0) / 2.0))) + 1
    cols = int(math.ceil((radius_m + window_m) / s)) + 1
    pts = []
    for j in range(-rows, rows + 1):
        y = j * s * math.sqrt(3.0) / 2.0
        x0 = 0.5 * s if j % 2 else 0.0
        for i in range(-cols - 1, cols + 2):
            x = i * s + x0
            d = math.hypot(x, y)
            if d - window_m < radius_m:
                pts.append((d, math.atan2(y, x) % (2.0 * math.pi), x, y))
    pts.sort()
    return [(x, y) for _, _, x, y in pts[:max(1, int(max_windows))]]


class WindowScan:
    """Which windows of the cover a frame tries: the centre, then the next ones of a scan that goes on
    from frame to frame (wrapping round), so that a few windows a frame cover the whole disc in turn."""

    def __init__(self):
        self._next = 1

    def reset(self) -> None:
        self._next = 1

    def pick(self, windows: List[Tuple[float, float]], per_frame: int) -> List[Tuple[float, float]]:
        """The windows for this frame: windows[0] (the carried position) and per_frame - 1 others."""
        if not windows:
            return []
        out = [windows[0]]
        rest = len(windows) - 1
        if rest <= 0 or per_frame <= 1:
            return out
        if self._next > rest:
            self._next = 1
        n = min(per_frame - 1, rest)
        for k in range(n):
            out.append(windows[1 + (self._next - 1 + k) % rest])
        self._next = 1 + (self._next - 1 + n) % rest
        return out

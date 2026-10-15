"""Ground velocity from the vehicle's recent MEASURED positions, for dead-reckoning.

When vision cannot match (sea, uniform ground, a tilted frame) NAVERA carries the last
measured position along the velocity measured just before, turned by the heading change
the IMU measures since (a vehicle's heading follows its course in a turn; a constant
crab angle from wind is kept). The stated uncertainty grows with time: velocity error
plus a heading error, both from the fit — never a position more precise than it is.
"""
import math
from collections import deque
from typing import Optional, Tuple

from navera_common.geo import dead_reckon

EARTH_R = 6371000.0


class TrackVelocity:
    def __init__(self, window_s: float = 20.0, min_span_s: float = 4.0, min_points: int = 3,
                 heading_sigma_deg: float = 5.0, speed_sigma_floor_mps: float = 0.5,
                 accel_mps2: float = 0.5):
        self.window_s, self.min_span_s, self.min_points = window_s, min_span_s, min_points
        self.heading_sigma = math.radians(heading_sigma_deg)
        self.speed_floor = speed_sigma_floor_mps
        # speed changes NAVERA does not see (a drone speeding up / slowing, a curve): the
        # error grows like 1/2 a t^2 — measured ~0.27 m/s^2 in the simulator (F6b), 0.5 kept
        self.accel = accel_mps2
        self._pts = deque(maxlen=200)                  # (t, lat, lon, sigma_m)

    def reset(self) -> None:
        self._pts.clear()

    def add(self, t: float, lat: float, lon: float, sigma_m: float) -> None:
        if self._pts and t <= self._pts[-1][0]:
            if t < self._pts[-1][0] - 1.0:              # clock stepped back
                self._pts.clear()
            else:
                return
        self._pts.append((t, lat, lon, max(1.0, sigma_m)))

    def velocity(self, t_now: float) -> Optional[Tuple[float, float, float]]:
        """(east m/s, north m/s, 1-sigma speed error m/s) from a weighted line fit of the
        fixes of the last window_s before their latest one, or None."""
        if not self._pts:
            return None
        t_end = self._pts[-1][0]
        pts = [p for p in self._pts if t_end - p[0] <= self.window_s]
        # never across a gap of more than 5 s between fixes: a line through the fixes on
        # both sides of a gap with a turn in it is a chord, not the velocity (2026-10-07)
        for i in range(len(pts) - 1, 0, -1):
            if pts[i][0] - pts[i - 1][0] > 5.0:
                pts = pts[i:]
                break
        if len(pts) < self.min_points or pts[-1][0] - pts[0][0] < self.min_span_s:
            return None
        lat0, lon0 = pts[-1][1], pts[-1][2]
        k = math.cos(math.radians(lat0))
        xs = [(math.radians(p[2] - lon0) * EARTH_R * k, math.radians(p[1] - lat0) * EARTH_R) for p in pts]
        ts = [p[0] for p in pts]
        w = [1.0 / p[3] ** 2 for p in pts]
        sw = sum(w)
        tm = sum(wi * ti for wi, ti in zip(w, ts)) / sw
        stt = sum(wi * (ti - tm) ** 2 for wi, ti in zip(w, ts))
        if stt <= 0:
            return None
        v = []
        for axis in (0, 1):
            xm = sum(wi * x[axis] for wi, x in zip(w, xs)) / sw
            v.append(sum(wi * (ti - tm) * (x[axis] - xm) for wi, ti, x in zip(w, ts, xs)) / stt)
        # slope error from the fixes' stated accuracy (and the scatter, if larger)
        resid = [math.hypot(x[0] - (v[0] * (ti - tm) + sum(wi * xx[0] for wi, xx in zip(w, xs)) / sw),
                            x[1] - (v[1] * (ti - tm) + sum(wi * xx[1] for wi, xx in zip(w, xs)) / sw))
                 for ti, x in zip(ts, xs)]
        scatter = math.sqrt(sum(r * r for r in resid) / max(1, len(resid) - 2))
        sig_pos = max(scatter, math.sqrt(len(pts) / sw))
        sig_v = max(self.speed_floor, sig_pos / math.sqrt(sum((ti - tm) ** 2 for ti in ts)))
        return v[0], v[1], sig_v

    def propagate(self, t_now: float, heading_change_deg: float = 0.0):
        """(lat, lon, sigma_m) of the last fix carried to t_now, or None. heading_change_deg:
        how much the vehicle turned (IMU) since the last fix, applied to the velocity."""
        vel = self.velocity(t_now)
        if vel is None:
            return None
        ve, vn, sig_v = vel
        t_last, lat, lon, sig0 = self._pts[-1]
        dt = t_now - t_last
        if dt <= 0:
            return lat, lon, sig0
        speed = math.hypot(ve, vn)
        if speed <= 0.05:
            p = (lat, lon)
        else:
            # a turn of heading_change_deg since the last fix, taken at a constant rate: the
            # path is an arc (integrated in <= 5 deg steps) — rotating the whole carry by the
            # final turn put a quarter turn's position ~1/3 of its length off the track
            a = math.radians(heading_change_deg or 0.0)
            steps = max(1, int(abs(a) / math.radians(5.0)))
            de = dn = 0.0
            for i in range(steps):
                ai = a * (i + 0.5) / steps
                de += (ve * math.cos(ai) + vn * math.sin(ai)) * dt / steps
                dn += (-ve * math.sin(ai) + vn * math.cos(ai)) * dt / steps
            dist = math.hypot(de, dn)
            p = dead_reckon(lat, lon, math.degrees(math.atan2(de, dn)) % 360.0, dist / dt, dt)
            if p is None:
                return None
        return p[0], p[1], sig0 + self.sigma_growth(sig_v, speed, dt, 0.0, heading_change_deg)

    def sigma_growth(self, sig_v: float, speed: float, dt: float, since_fix_s: float = 0.0,
                     heading_change_deg: float = 0.0) -> float:
        """How much the stated uncertainty of a carried position grows over dt seconds.

        since_fix_s: the time already elapsed between the last MEASURED fix and the start of this
        step (0 = the step starts at the fix). A position carried step by step (once a second)
        must grow like one carried over the whole time: the unseen acceleration term is
        1/2 a t^2 of the time since the measurement, not 1/2 a dt^2 of each step added up —
        that sum is 1/2 a dt per second, i.e. linear, and understated the real error 5x after
        100 s (simulator, 2026-10-15: stated +-244 m, real 1205 m).
        A turn: when it started and at what rate are not known — half its sideways reach."""
        t1 = since_fix_s + dt
        return (sig_v * dt + self.heading_sigma * speed * dt
                + 0.5 * self.accel * (t1 * t1 - since_fix_s * since_fix_s)
                + 0.5 * abs(math.radians(heading_change_deg or 0.0)) * speed * dt)

    def last_time(self) -> Optional[float]:
        return self._pts[-1][0] if self._pts else None

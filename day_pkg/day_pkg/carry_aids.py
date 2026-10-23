"""What the day pipeline's carry knows of the vehicle's motion besides its own fixes (open3, 2026-10-23).

The carried position went on with the velocity the track measured last, turned at most by the frame
heading change. Three Isaac Sim closed-loop failures came from motion the track had not seen:

- the day node killed on a waypoint corner (fin_endur_2h): the restored carry went straight on while
  the copter turned ~150 deg, 745 m off at a stated +-384 m, the autopilot following it;
- a 60 s cloud bank right after a corner (outage60): the velocity fitted over the corner was 6-8 m/s
  off from the first seconds, 360-475 m and an EKF failsafe (the autopilot's own velocity was 0.5 m/s
  off at the same instant);
- the GPS lost as the copter starts its leg at 1200 m (h1200): it accelerates from the hover while
  the frames match badly, the carry kept the hover's velocity, 1-3 km off.

Two aids, each optional:

- **VelocityRef**: the autopilot's velocity (vehicle_link /navera/vehicle/velocity: its EKF, which
  integrates its own IMU — turns and speed changes included). Without GPS that EKF is corrected by
  NAVERA's own positions, so it is never taken as it is: a constant offset (its bias) is fitted on
  NAVERA's measured fixes of the last 20 s (each fix minus the path the autopilot's velocity draws
  from the reference instant; the line through the rest is the bias), refused when the fixes do not
  lie on that path within their stated accuracy (chi-square). The carry is then the integral of the
  autopilot's velocity (plus the bias only for an autopilot NAVERA does not feed: fed NAVERA's
  positions its EKF absorbs the bias the carry adds, its velocity moves by it, the carry adds it again
  — Isaac Sim outage60, 0.5 -> 7 m/s off in 45 s; then the bias's size only widens the stated
  accuracy); its uncertainty: the velocity error x t plus 1/2 drift t^2 (the autopilot's velocity
  drifting while NAVERA feeds it carried positions).
- **AttitudeYaw**: the absolute yaw of the IMU's attitude (vehicle or camera IMU). The gyro heading
  (gyro_heading.py) integrates rates inside one process; across a restart of the day process (no
  samples for the seconds it is down) the turn over the gap is the yaw now minus the yaw persisted
  with the snapshot (carry_state), interpolated across the gap (when it turned is not known: half
  the sideways reach of that turn goes into the stated accuracy).

Pure Python (no ROS).
"""
import bisect
import math
import threading
from typing import List, Optional, Tuple

from day_pkg.vision_nav import _move

EARTH_R = 6371000.0


def yaw_of_quaternion(q_xyzw) -> Optional[float]:
    """Azimuth of the body x axis (deg clockwise from north) of an ENU attitude quaternion, or None."""
    try:
        x, y, z, w = (float(c) for c in q_xyzw)
    except (TypeError, ValueError):
        return None
    n = x * x + y * y + z * z + w * w
    if not (0.9 < n < 1.1):
        return None
    r00, r10 = 1 - 2 * (y * y + z * z), 2 * (x * y + w * z)
    if math.hypot(r00, r10) < 1e-3:                      # nose straight up or down: no yaw
        return None
    return (90.0 - math.degrees(math.atan2(r10, r00))) % 360.0


class VelocityRef:
    """A measured velocity (east, north m/s) by time, integrated: the autopilot's (module doc)."""

    def __init__(self, max_gap_s: float = 1.0, history_s: float = 300.0, extrapolate_s: float = 1.0):
        self.max_gap, self.history_s, self.extrapolate_s = max_gap_s, history_s, extrapolate_s
        self._t: List[float] = []
        self._v: List[Tuple[float, float, float, float]] = []    # (ve, vn, Se, Sn): S = integral of v
        self._lock = threading.Lock()

    def add(self, t: float, ve: float, vn: float) -> None:
        if not all(math.isfinite(c) for c in (t, ve, vn)):
            return
        with self._lock:
            if self._t and t <= self._t[-1]:
                if t < self._t[-1] - 1.0:                         # clock stepped back
                    self._t.clear(); self._v.clear()
                else:
                    return
            if self._t:
                dt = t - self._t[-1]
                pe, pn, se, sn = self._v[-1]
                if dt <= self.max_gap:                            # (never integrated across a gap)
                    se, sn = se + 0.5 * (pe + ve) * dt, sn + 0.5 * (pn + vn) * dt
                self._t.append(t)
                self._v.append((ve, vn, se, sn))
            else:
                self._t.append(t)
                self._v.append((ve, vn, 0.0, 0.0))
            if len(self._t) > 64 and self._t[0] < t - 1.2 * self.history_s:
                k = bisect.bisect_left(self._t, t - self.history_s)
                del self._t[:k], self._v[:k]

    def _at(self, t: float):
        """(index of the sample at or before t, ve, vn, Se, Sn), or None."""
        if not self._t or t < self._t[0]:
            return None
        if t >= self._t[-1]:
            dt = t - self._t[-1]
            if dt > self.extrapolate_s:
                return None
            ve, vn, se, sn = self._v[-1]
            return len(self._t) - 1, ve, vn, se + ve * dt, sn + vn * dt
        i = bisect.bisect_right(self._t, t) - 1
        ta, tb = self._t[i], self._t[i + 1]
        if tb - ta > self.max_gap:
            return None
        f = (t - ta) / (tb - ta) if tb > ta else 0.0
        a, b = self._v[i], self._v[i + 1]
        return (i,) + tuple(a[k] + f * (b[k] - a[k]) for k in range(4))

    def _no_gap(self, i0: int, i1: int) -> bool:
        return all(self._t[j + 1] - self._t[j] <= self.max_gap for j in range(i0, min(i1, len(self._t) - 1)))

    def v(self, t: float) -> Optional[Tuple[float, float]]:
        with self._lock:
            a = self._at(t)
        return None if a is None else (a[1], a[2])

    def first_time(self) -> Optional[float]:
        """Start of the latest run of samples without a gap, or None."""
        with self._lock:
            if not self._t:
                return None
            i = len(self._t) - 1
            while i > 0 and self._t[i] - self._t[i - 1] <= self.max_gap:
                i -= 1
            return self._t[i]

    def disp(self, t0: float, t1: float) -> Optional[Tuple[float, float]]:
        """Displacement (east, north m) the velocity draws from t0 to t1 (either order), or None
        (outside the samples or across a gap)."""
        with self._lock:
            a, b = self._at(min(t0, t1)), self._at(max(t0, t1))
            if a is None or b is None or not self._no_gap(a[0], b[0]):
                return None
        de, dn = b[3] - a[3], b[4] - a[4]
        return (de, dn) if t1 >= t0 else (-de, -dn)

    def covers(self, t0: float, t1: float) -> bool:
        return self.disp(t0, t1) is not None

    def fit_bias(self, pts, t_ref: float, window_s: float = 20.0, min_points: int = 4, min_span_s: float = 4.0,
                 max_gap_s: float = 5.0, max_chi2: float = 4.0, floor_mps: float = 0.3):
        """(bias east, bias north, 1-sigma m/s) to add to this velocity so that it draws NAVERA's measured
        points [(t, lat, lon, sigma_m)] of the last window_s up to t_ref, or None: too few covered,
        or the points off that path beyond their stated accuracy (reduced chi-square > max_chi2)."""
        sel = [p for p in pts if t_ref - window_s <= p[0] <= t_ref + 1e-6]
        for i in range(len(sel) - 1, 0, -1):
            if sel[i][0] - sel[i - 1][0] > max_gap_s:
                sel = sel[i:]
                break
        if not sel:
            return None
        lat0, lon0 = sel[-1][1], sel[-1][2]
        k = math.cos(math.radians(lat0))
        rows = []
        for t, lat, lon, s in sel:
            d = self.disp(t_ref, t)
            if d is None:
                continue
            rows.append((t - t_ref, math.radians(lon - lon0) * EARTH_R * k - d[0],
                         math.radians(lat - lat0) * EARTH_R - d[1], 1.0 / max(1.0, s) ** 2))
        if len(rows) < min_points or rows[-1][0] - rows[0][0] < min_span_s:
            return None
        sw = sum(r[3] for r in rows)
        tm = sum(r[3] * r[0] for r in rows) / sw
        stt = sum(r[3] * (r[0] - tm) ** 2 for r in rows)
        if stt <= 0:
            return None
        b, chi2 = [], 0.0
        for ax in (1, 2):
            m = sum(r[3] * r[ax] for r in rows) / sw
            s = sum(r[3] * (r[0] - tm) * (r[ax] - m) for r in rows) / stt
            chi2 += sum(r[3] * (r[ax] - m - s * (r[0] - tm)) ** 2 for r in rows)
            b.append(s)
        chi2_dof = chi2 / max(1, 2 * (len(rows) - 2))
        if chi2_dof > max_chi2:
            return None
        return b[0], b[1], max(floor_mps, math.sqrt(max(1.0, chi2_dof) / stt))


class AttitudeYaw:
    """The IMU attitude's yaw by time (unwrapped), with seeded points across a restart (module doc)."""

    def __init__(self, max_gap_s: float = 0.5, history_s: float = 300.0, extrapolate_s: float = 0.5,
                 max_seed_gap_s: float = 60.0):
        self.max_gap, self.history_s, self.extrapolate_s = max_gap_s, history_s, extrapolate_s
        self.max_seed_gap = max_seed_gap_s
        self._t: List[float] = []
        self._y: List[float] = []
        self._lock = threading.Lock()

    def add(self, t: float, yaw_deg: Optional[float]) -> None:
        if yaw_deg is None or not (math.isfinite(t) and math.isfinite(yaw_deg)):
            return
        with self._lock:
            if self._t and t <= self._t[-1]:
                if t < self._t[-1] - 1.0:
                    self._t.clear(); self._y.clear()
                else:
                    return
            y = yaw_deg if not self._y else self._y[-1] + (yaw_deg - self._y[-1] + 180.0) % 360.0 - 180.0
            self._t.append(t)
            self._y.append(y)
            if len(self._t) > 64 and self._t[0] < t - 1.2 * self.history_s:
                k = bisect.bisect_left(self._t, t - self.history_s)
                del self._t[:k], self._y[:k]

    def seed(self, t: float, yaw_deg: Optional[float]) -> bool:
        """A persisted yaw at t (before every sample): the turn from it is interpolated across the gap."""
        if yaw_deg is None or not (math.isfinite(t) and math.isfinite(yaw_deg)):
            return False
        with self._lock:
            if self._t and t >= self._t[0]:
                return False
            if self._t:
                if self._t[0] - t > self.max_seed_gap:
                    return False
                y = self._y[0] + (yaw_deg - self._y[0] + 180.0) % 360.0 - 180.0
                self._t.insert(0, t)
                self._y.insert(0, y)
            else:
                self._t.append(t)
                self._y.append(yaw_deg)
            return True

    def _at(self, t: float):
        """(index, yaw) at t, or None. Across a gap: interpolated (the seed's gap included)."""
        if not self._t or t < self._t[0]:
            return None
        if t >= self._t[-1]:
            return (len(self._t) - 1, self._y[-1]) if t - self._t[-1] <= self.extrapolate_s else None
        i = bisect.bisect_right(self._t, t) - 1
        ta, tb = self._t[i], self._t[i + 1]
        f = (t - ta) / (tb - ta) if tb > ta else 0.0
        return i, self._y[i] + f * (self._y[i + 1] - self._y[i])

    def turn(self, t0: float, t1: float) -> Optional[Tuple[float, float, float]]:
        """(turn deg from t0 to t1, seconds inside gaps, turn deg inside those gaps), or None."""
        with self._lock:
            a, b = self._at(t0), self._at(t1)
            if a is None or b is None:
                return None
            gap_s = gap_turn = 0.0
            for j in range(a[0], min(b[0] + 1, len(self._t) - 1)):
                dt = self._t[j + 1] - self._t[j]
                if dt > self.max_gap:
                    lo, hi = max(self._t[j], t0), min(self._t[j + 1], t1)
                    if hi > lo:
                        gap_s += hi - lo
                        gap_turn += abs(self._y[j + 1] - self._y[j]) * (hi - lo) / dt
        return b[1] - a[1], gap_s, gap_turn

    def yaw(self, t: float) -> Optional[float]:
        with self._lock:
            a = self._at(t)
        return None if a is None else a[1] % 360.0


def carry_with_turns(lat: float, lon: float, t0: float, ve: float, vn: float, t: float, turn_at,
                     step_s: float = 0.5) -> Tuple[float, float, float, float]:
    """(lat, lon, ve, vn) carried from t0 to t with the velocity turned by turn_at(s) (deg turned from
    t0 to s; None: straight) in steps of at most step_s."""
    dt = max(0.0, t - t0)
    n = max(1, int(math.ceil(dt / step_s)))
    de = dn = 0.0
    for i in range(n):
        a = math.radians(turn_at(t0 + dt * (i + 0.5) / n) or 0.0)
        de += (ve * math.cos(a) + vn * math.sin(a)) * dt / n
        dn += (-ve * math.sin(a) + vn * math.cos(a)) * dt / n
    a = math.radians(turn_at(t) or 0.0) if dt > 0 else 0.0
    p = _move((lat, lon), de, dn)
    return p[0], p[1], ve * math.cos(a) + vn * math.sin(a), -ve * math.sin(a) + vn * math.cos(a)


def carry_autopilot(lat: float, lon: float, t0: float, t: float, apv: VelocityRef, bias,
                    ve0: Optional[float] = None, vn0: Optional[float] = None):
    """(lat, lon, ve, vn, gap_s, dv_gap) carried from t0 to t along the autopilot's velocity + bias, or
    None. The autopilot's samples may start after t0 (a restarted process): the first gap is bridged
    with the mean of the velocity at t0 (ve0, vn0: required then) and the autopilot's at its first
    sample (gap_s, and |dv| across it, for the stated accuracy)."""
    if bias is None or apv is None or t < t0:
        return None
    be, bn = bias[0], bias[1]
    d = apv.disp(t0, t)
    gap, dvg = 0.0, 0.0
    if d is None:
        t1 = apv.first_time()
        if t1 is None or not (t0 < t1 <= t) or ve0 is None or vn0 is None:
            return None
        d1, v1 = apv.disp(t1, t), apv.v(t1)
        if d1 is None or v1 is None:
            return None
        gap = t1 - t0
        w1 = (v1[0] + be, v1[1] + bn)
        dvg = math.hypot(w1[0] - ve0, w1[1] - vn0)
        de = 0.5 * (ve0 + w1[0]) * gap + d1[0] + be * (t - t1)
        dn = 0.5 * (vn0 + w1[1]) * gap + d1[1] + bn * (t - t1)
    else:
        de, dn = d[0] + be * (t - t0), d[1] + bn * (t - t0)
    v = apv.v(t)
    if v is None:
        return None
    p = _move((lat, lon), de, dn)
    return p[0], p[1], v[0] + be, v[1] + bn, gap, dvg


def autopilot_sigma_growth(sig_v: float, dt: float, since_v: float, drift_mps2: float,
                           gap_s: float = 0.0, dv_gap: float = 0.0, accel_mps2: float = 0.5) -> float:
    """Growth of the stated 1-sigma of a position carried dt seconds along the autopilot's velocity:
    the bias's error x dt, the autopilot's drift since the velocity was fitted (1/2 drift t^2 from
    since_v), and across a bridged gap the unseen acceleration and half the velocity change's reach."""
    t1 = max(0.0, since_v) + max(0.0, dt)
    return (sig_v * max(0.0, dt) + 0.5 * drift_mps2 * (t1 * t1 - max(0.0, since_v) ** 2)
            + (0.5 * dv_gap * gap_s + 0.5 * accel_mps2 * gap_s * gap_s if gap_s > 0 else 0.0))

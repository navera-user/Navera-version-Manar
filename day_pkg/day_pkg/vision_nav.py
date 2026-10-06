"""Day-vision navigation between map matches: where to search, what to believe, what to say.

The matchers (local_matcher, learned_matcher) locate ONE frame around a prior. This module
holds what happens between and around them — the problems a 2026-10-06 bench campaign
(Insta360 over 2-3 year older imagery, 5 terrains, turns, height changes, 30 min) found:

- gaps without a match became 0.3-1 km errors: the position stood still and the search
  went on in a straight line out of its 400 m circle. Here the position is carried along
  the velocity (turned with the heading during turns, measured by frame-to-frame visual
  odometry when it can), its stated uncertainty grows, the search circle follows it, and
  past max_sigma_m / max_dr_s the output says "no position" instead of a wrong one;
- the height froze when matches failed (it only updated on a match) and matching then kept
  failing: an independent height (GPS - ground, a barometer) is used whenever there is one,
  and after retry_after failures neighbouring heights are tried;
- fixes with few inliers carried the 20-50 m errors: each fix gets a sigma from its inlier
  count and is rejected when it disagrees with the prediction beyond gate_k sigma (unless
  it is very strong) or when its inliers cover too little of the frame;
- constant offsets between the matched map and the ground (map registration, camera
  boresight): measured while GPS is good, removed after its loss, near where measured.

Pure Python (no ROS): the day node and the bench use the same rules.
"""
import math
from collections import deque
from typing import Optional, Tuple

M_PER_DEG = 111_320.0


def _en(p: Tuple[float, float], ref: Tuple[float, float]) -> Tuple[float, float]:
    """(east, north) metres of p from ref."""
    return ((p[1] - ref[1]) * M_PER_DEG * math.cos(math.radians(ref[0])), (p[0] - ref[0]) * M_PER_DEG)


def _move(p: Tuple[float, float], de: float, dn: float) -> Tuple[float, float]:
    return (p[0] + dn / M_PER_DEG, p[1] + de / (M_PER_DEG * math.cos(math.radians(p[0]))))


def _wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


class VisionNavigator:
    """Position, velocity, height and map bias of a vehicle navigating by map matches."""

    def __init__(self, max_dr_s: float = 120.0, max_sigma_m: float = 300.0, accel_mps2: float = 0.5,
                 search_k: float = 3.0, min_search_m: float = 80.0, max_search_m: float = 1500.0,
                 gate_k: float = 3.0, strong_inliers: int = 100, min_spread: float = 0.25,
                 retry_after: int = 3, bias_radius_m: float = 3000.0):
        self.max_dr_s, self.max_sigma_m, self.accel = max_dr_s, max_sigma_m, accel_mps2
        self.search_k, self.min_search_m, self.max_search_m = search_k, min_search_m, max_search_m
        self.gate_k, self.strong_inliers, self.min_spread = gate_k, strong_inliers, min_spread
        self.retry_after, self.bias_radius_m = retry_after, bias_radius_m
        self.fix = None               # (lat, lon, t, sigma_m, heading_deg or None): last position measured
        self.vel = None               # (east, north) m/s
        self.vel_sigma = 5.0          # m/s
        self._fixes = deque(maxlen=8)  # (t, lat, lon) of recent fixes: the velocity
        self.height = None            # (m above ground, sigma_m, t, source)
        self.fails = 0                # matches failed in a row
        self._bias = deque(maxlen=30)  # (lat, lon, de, dn): GPS minus vision, while GPS is good
        self.last_reason = ""

    # ── inputs ───────────────────────────────────────────────────────────
    def gps(self, t: float, lat: float, lon: float, sigma_m: float = 5.0,
            heading_deg: Optional[float] = None) -> None:
        """A trusted GPS position: it is the position (vision only checks it and learns the bias)."""
        self._set_fix(t, lat, lon, sigma_m, heading_deg)

    def set_height(self, t: float, height_m: float, sigma_m: float, source: str) -> None:
        """An independent height above the ground (GPS - ground elevation, barometer, rangefinder)."""
        if height_m and height_m > 0:
            self.height = (float(height_m), float(sigma_m), t, source)

    def bias_sample(self, vision: Tuple[float, float], gps: Tuple[float, float]) -> None:
        """While GPS is good: where vision put the frame vs where GPS says the camera points."""
        de, dn = _en(gps, vision)
        self._bias.append((vision[0], vision[1], de, dn))

    def odometry(self, t: float, de: float, dn: float, dt: float, quality: float) -> None:
        """Frame-to-frame displacement (visual odometry, metres over dt): a measured velocity."""
        if dt <= 0 or quality <= 0:
            return
        v = (de / dt, dn / dt)
        if self.vel is None:
            self.vel = v
        else:
            w = min(0.7, quality)
            self.vel = ((1 - w) * self.vel[0] + w * v[0], (1 - w) * self.vel[1] + w * v[1])
        self.vel_sigma = min(self.vel_sigma, 2.0)

    # ── prediction and search ────────────────────────────────────────────
    def bias(self, near: Tuple[float, float]) -> Tuple[float, float]:
        """The map bias (east, north m) learned within bias_radius_m of near: median of samples."""
        pts = [(de, dn) for lat, lon, de, dn in self._bias
               if math.hypot(*_en((lat, lon), near)) <= self.bias_radius_m]
        if len(pts) < 3:
            return 0.0, 0.0
        des, dns = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
        return des[len(des) // 2], dns[len(dns) // 2]

    def predict(self, t: float, heading_deg: Optional[float] = None) -> Optional[Tuple[float, float, float]]:
        """(lat, lon, sigma_m) at t: the last fix carried along the velocity. With a heading
        (IMU) and the heading at the last fix, the velocity turns with the vehicle: in a turn
        a straight-line carry leaves the track."""
        if self.fix is None:
            return None
        lat, lon, tf, sig, hdg_fix = self.fix
        dt = max(0.0, t - tf)
        if self.vel is None or dt == 0:
            return lat, lon, sig + (0 if self.vel else 25.0 * dt)
        ve, vn = self.vel
        if heading_deg is not None and hdg_fix is not None:
            # turned at a constant rate from the fix's heading to the present one: integrate
            turn = math.radians(_wrap(heading_deg - hdg_fix))
            steps = max(1, int(abs(turn) / math.radians(5)))
            de = dn = 0.0
            for i in range(steps):
                a = turn * (i + 0.5) / steps
                c, s = math.cos(a), math.sin(a)
                de += (c * ve + s * vn) * dt / steps
                dn += (-s * ve + c * vn) * dt / steps
        else:
            de, dn = ve * dt, vn * dt
        p = _move((lat, lon), de, dn)
        return p[0], p[1], sig + self.vel_sigma * dt + 0.5 * self.accel * dt * dt

    def search(self, t: float, heading_deg: Optional[float] = None, footprint_m: float = 0.0):
        """(centre, radius_m) to search the next frame in: the prediction and k sigma of it
        (the window follows the uncertainty: a lost vehicle is searched for wider)."""
        p = self.predict(t, heading_deg)
        if p is None:
            return None, None
        r = min(max(self.search_k * p[2], self.min_search_m), self.max_search_m)
        return (p[0], p[1]), r

    def heights_to_try(self) -> Tuple[Optional[float], list, float]:
        """(height, extra heights to try, scale tolerance): after retry_after failures in a
        row, the neighbouring heights too (a stale height makes every match fail)."""
        if self.height is None:
            return None, [], 0.3
        h, sig = self.height[0], self.height[1]
        tol = min(0.35, max(0.15, 2.0 * sig / h))
        if self.fails >= self.retry_after:
            return h, [h * 0.8, h * 1.25], max(tol, 0.2)
        return h, [], tol

    # ── a match result ───────────────────────────────────────────────────
    def update(self, t: float, res: dict, height_used: Optional[float], heading_deg: Optional[float] = None,
               gps_valid: bool = False) -> bool:
        """A matcher result for the frame taken at t: True when accepted as a position."""
        if not res.get("accepted"):
            self.fails += 1
            self.last_reason = res.get("reason") or "no match"
            return False
        lat, lon = res["predicted_lat"], res["predicted_lon"]
        inl = int(res.get("inliers") or 0)
        if not gps_valid:
            de, dn = self.bias((lat, lon))
            lat, lon = _move((lat, lon), de, dn)
        sig = float(res.get("sigma_m") or 30.0)
        pred = self.predict(t, heading_deg)
        if not gps_valid and pred is not None and inl < self.strong_inliers:
            d = math.hypot(*_en((lat, lon), pred[:2]))
            lim = self.gate_k * math.hypot(pred[2], sig)
            if d > lim:
                self.fails += 1
                self.last_reason = f"{d:.0f} m from the prediction (> {lim:.0f} m, {inl} inliers): rejected"
                return False
        if inl < 50 and float(res.get("spread", 1.0)) < self.min_spread:
            self.fails += 1
            self.last_reason = f"inliers on {res.get('spread', 0):.0%} of the frame ({inl}): rejected"
            return False
        self.fails = 0
        if height_used and res.get("scale_residual"):
            hv = height_used * float(res["scale_residual"])
            sv = max(0.03 * hv, sig)                         # vision height: ~3 % (campaign median)
            if self.height is None or t - self.height[2] > 5.0 or self.height[3] == "vision":
                self.height = (hv, sv, t, "vision")
            else:                                           # an independent height is fresher: blend
                h, s = self.height[0], self.height[1]
                w = s * s / (s * s + sv * sv)
                self.height = (h + w * (hv - h), math.sqrt(1.0 / (1.0 / (s * s) + 1.0 / (sv * sv))), t, self.height[3])
        if not gps_valid:
            self._set_fix(t, lat, lon, sig, heading_deg)
        return True

    def _set_fix(self, t, lat, lon, sigma_m, heading_deg):
        if self.fix is not None and t < self.fix[2]:
            return
        self._fixes.append((t, lat, lon))
        # the velocity: from the latest fix at least 2 s older (else the oldest >= 1 s older)
        older = [f for f in self._fixes if t - f[0] >= 2.0] or [f for f in self._fixes if t - f[0] >= 1.0][:1]
        if older:
            t0, la0, lo0 = older[-1]
            de, dn = _en((lat, lon), (la0, lo0))
            v = (de / (t - t0), dn / (t - t0))
            if self.vel is None or self.fix is None or t - self.fix[2] > 10.0:
                self.vel = v
            else:
                self.vel = (0.5 * self.vel[0] + 0.5 * v[0], 0.5 * self.vel[1] + 0.5 * v[1])
            self.vel_sigma = 1.0 + sigma_m / max(t - t0, 1.0)
        self.fix = (lat, lon, t, sigma_m, heading_deg)

    # ── output ───────────────────────────────────────────────────────────
    def output(self, t: float, heading_deg: Optional[float] = None):
        """(lat, lon, sigma_m, mode) — mode 'measured' (a fix this instant), 'propagated'
        (carried, growing sigma) or 'unavailable' (too long or too uncertain: say so)."""
        p = self.predict(t, heading_deg)
        if p is None:
            return None, None, None, "unavailable"
        age = t - self.fix[2]
        if age > self.max_dr_s or p[2] > self.max_sigma_m:
            return None, None, p[2], "unavailable"
        return p[0], p[1], p[2], ("measured" if age < 0.5 else "propagated")

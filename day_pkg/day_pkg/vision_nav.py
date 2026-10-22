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
  count and is rejected when it disagrees with the prediction beyond gate_k sigma (a very
  strong one: beyond strong_gate_k sigma) or when its inliers cover too little of the frame;
  a doubted fix is believed when the next one agrees with it (re-acquisition);
- a strong match can still be in the wrong place (2026-10-19 bench: 100-150 inliers, 270-650 m
  off, forwarded as NAVERA's position): with max_speed_mps, no fix — strong, confirmed or
  not — is believed further from the last fix than the vehicle can travel (max_speed_mps x
  the time since + gate_k x the two sigmas);
- constant offsets between the matched map and the ground (map registration, camera
  boresight): measured while GPS is good, removed after its loss, near where measured.

Pure Python (no ROS): the day node and the bench use the same rules.
"""
import math
import time
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


def kinematic_margin_m(gate_k: float, sigma_last_m: float, sigma_fix_m: float, cap_m: float = float("inf")) -> float:
    """Allowance, beyond max_speed x elapsed, for a fix's distance from the last position:
    gate_k x the two positions' combined sigma, at most cap_m."""
    return min(gate_k * math.hypot(sigma_last_m, sigma_fix_m), cap_m)


class VisionNavigator:
    """Position, velocity, height and map bias of a vehicle navigating by map matches."""

    def __init__(self, max_dr_s: float = 120.0, max_sigma_m: float = 300.0, accel_mps2: float = 0.5,
                 search_k: float = 3.0, min_search_m: float = 80.0, max_search_m: float = 600.0,
                 gate_k: float = 3.0, strong_inliers: int = 100, min_spread: float = 0.25,
                 retry_after: int = 3, bias_radius_m: float = 3000.0, strong_gate_k: float = 6.0,
                 max_speed_mps: Optional[float] = None, blend_fixes: bool = False,
                 blend_below_inliers: int = 10 ** 9, consistency=None):
        self.max_dr_s, self.max_sigma_m, self.accel = max_dr_s, max_sigma_m, accel_mps2
        self.search_k, self.min_search_m, self.max_search_m = search_k, min_search_m, max_search_m
        self.gate_k, self.strong_inliers, self.min_spread = gate_k, strong_inliers, min_spread
        self.retry_after, self.bias_radius_m = retry_after, bias_radius_m
        self.strong_gate_k = strong_gate_k  # a strong fix's gate (sigmas); was unlimited
        self.max_speed_mps = max_speed_mps  # the vehicle's top speed: the kinematic gate (None: off)
        # a fix is averaged with the prediction, each weighted by its sigma (a Kalman update per
        # axis), instead of replacing it: few-inlier fixes (heavy clouds) are noisy, not biased
        self.blend_fixes = blend_fixes
        self.blend_below_inliers = blend_below_inliers   # only fixes with fewer inliers are averaged
        # day_pkg.fix_consistency.FixConsistency: the product's doubt / confirmation rules (F16, D17);
        # None: the rules below as they were before 2026-10-22 (the bench baseline)
        self.consistency = consistency
        self.kinematic_rejected = 0
        self.weak_inliers = 30        # fewer: the fix places the vehicle, not its velocity
        self.fix = None               # (lat, lon, t, sigma_m, heading_deg or None): last position measured
        self.vel = None               # (east, north) m/s
        self.vel_sigma = 5.0          # m/s
        self.vel_hdg = None           # the heading (IMU) when the velocity was measured
        self._carry = None            # (lat, lon, t, sigma, heading, velocity): carried since the last fix
        self._fixes = deque(maxlen=8)  # (t, lat, lon) of recent fixes: the velocity
        # height above ground: a Kalman filter on (height, climb rate) — process noise for
        # climbs the vehicle makes, updated by independent heights (GPS - ground, baro) and by
        # vision (the height the frame was matched at x the fitted scale)
        self._h = None                # [height, climb rate], 2x2 covariance, time
        self.height_source = None     # where the last independent height came from
        self.climb_accel = 0.5        # m/s^2: climb-rate changes the filter allows
        # a climb does not last for ever: the carried climb rate fades (time constant), and is
        # never more than max_climb — without it a climb measured before the matches stopped
        # was extrapolated without limit (camera campaign 5: the height tried reached 3-11x
        # the truth, the matching failed for good and the GPU memory ran out)
        self.climb_tau_s = 10.0
        self.climb_hold_s = 3.0
        self.max_climb_mps = 8.0
        self.height = None            # (m above ground, sigma_m, t, source): the filter's state
        self.fails = 0                # matches failed in a row
        self._bias = deque(maxlen=40)  # (lat, lon, de, dn, heading): GPS minus vision, while GPS is good
        self._bias_t = deque(maxlen=40)  # when each of them was taken (s)
        self.max_bias_m = 30.0
        self.vo_rejected = 0
        self._pending = None          # (t, lat, lon, sigma) of a fix the gate doubted
        self._out = None              # (t, lat, lon, sigma): the blended output of the last fix
        self.last_reason = ""

    # ── inputs ───────────────────────────────────────────────────────────
    def gps(self, t: float, lat: float, lon: float, sigma_m: float = 5.0,
            heading_deg: Optional[float] = None) -> None:
        """A trusted GPS position: it is the position (vision only checks it and learns the bias)."""
        self._set_fix(t, lat, lon, sigma_m, heading_deg)

    def set_height(self, t: float, height_m: float, sigma_m: float, source: str) -> None:
        """An independent height above the ground (GPS - ground elevation, barometer, rangefinder)."""
        if height_m and height_m > 0:
            self._height_update(t, float(height_m), float(sigma_m), source)
            self.height_source = source

    def _height_predict(self, t: float):
        if self._h is None:
            return None
        (h, v), P, th = self._h
        dt = max(0.0, t - th)
        q = self.climb_accel ** 2
        # the climb rate is held for climb_hold_s after the last update (frame-to-frame the
        # filter tracks a steady climb without lag), then fades over climb_tau_s: the height
        # moves by at most v (hold + tau)
        hold = min(dt, self.climb_hold_s)
        e = math.exp(-(dt - hold) / self.climb_tau_s)
        a = hold + self.climb_tau_s * (1.0 - e)
        v = max(-self.max_climb_mps, min(self.max_climb_mps, v))
        P = [[P[0][0] + a * (P[0][1] + P[1][0]) + a * a * P[1][1] + q * dt ** 4 / 4,
              e * (P[0][1] + a * P[1][1]) + q * dt ** 3 / 2],
             [e * (P[1][0] + a * P[1][1]) + q * dt ** 3 / 2, e * e * P[1][1] + q * dt * dt]]
        return (h + v * a, v * e), P, t

    def _height_update(self, t: float, z: float, sigma: float, source: str) -> None:
        pred = self._height_predict(t)
        if pred is None:
            self._h = ((z, 0.0), [[sigma * sigma, 0.0], [0.0, 4.0]], t)
        else:
            (h, v), P, _ = pred
            S = P[0][0] + sigma * sigma
            k0, k1 = P[0][0] / S, P[1][0] / S
            r = z - h
            self._h = ((h + k0 * r, v + k1 * r),
                       [[(1 - k0) * P[0][0], (1 - k0) * P[0][1]],
                        [P[1][0] - k1 * P[0][0], P[1][1] - k1 * P[0][1]]], t)
        (h, _), P, _ = self._h
        self.height = (h, math.sqrt(max(P[0][0], 1e-6)), t, source)

    def height_at(self, t: float) -> Optional[Tuple[float, float]]:
        """(height, sigma) predicted at t (the climb rate carried), or None."""
        p = self._height_predict(t)
        return None if p is None else (p[0][0], math.sqrt(max(p[1][0][0], 1e-6)))

    def bias_sample(self, vision: Tuple[float, float], gps: Tuple[float, float],
                    heading_deg: Optional[float] = None, t: Optional[float] = None) -> None:
        """While GPS is good: where vision put the frame vs where GPS (at the frame's
        instant) says the camera points."""
        de, dn = _en(gps, vision)
        self._bias.append((vision[0], vision[1], de, dn, heading_deg))
        self._bias_t.append(time.time() if t is None else float(t))

    def rollback_bias(self, since_t: float) -> int:
        """Forget the map-bias samples taken at or after since_t (a GPS trusted then may have
        been slowly spoofed: its drift would be learned as a map shift); returns how many."""
        n = 0
        while self._bias_t and self._bias_t[-1] >= since_t:
            self._bias_t.pop()
            self._bias.pop()
            n += 1
        return n

    def odometry(self, t: float, de: float, dn: float, dt: float, quality: float) -> bool:
        """Frame-to-frame displacement (visual odometry, metres over dt): a velocity
        measurement, used only when it agrees with the velocity the map fixes measured
        (phase correlation can lock on what does not move in the image and under-measure)."""
        if dt <= 0 or quality <= 0:
            return False
        v = (de / dt, dn / dt)
        if self.vel is not None:
            dv = math.hypot(v[0] - self.vel[0], v[1] - self.vel[1])
            if dv > max(3.0 * min(self.vel_sigma, 5.0), 0.3 * math.hypot(*self.vel), 3.0):
                self.vo_rejected += 1
                return False
            w = min(0.5, quality)
            self.vel = ((1 - w) * self.vel[0] + w * v[0], (1 - w) * self.vel[1] + w * v[1])
        else:
            self.vel = v
        self.vel_sigma = max(self.vel_sigma, 3.0)          # never more certain than the VO itself
        return True

    # ── prediction and search ────────────────────────────────────────────
    def bias(self, near: Tuple[float, float]) -> Tuple[float, float]:
        """The map bias (east, north m) learned within bias_radius_m of near, or (0, 0).
        Only a significant one: samples from at least two headings 60 deg apart (an offset
        from timing or camera mounting turns with the vehicle and averages out over
        headings, a map shift does not), median beyond 2 standard errors, capped."""
        pts = [p for p in self._bias if math.hypot(*_en(p[:2], near)) <= self.bias_radius_m]
        if len(pts) < 5:
            return 0.0, 0.0
        hd = [p[4] for p in pts if p[4] is not None]
        if not hd or max(abs(_wrap(a - b)) for a in hd for b in hd) < 60.0:
            return 0.0, 0.0
        # per heading sector (45 deg) a median, then the mean of the sectors: an offset that
        # turns with the vehicle cancels, a map shift stays
        sectors = {}
        for p in pts:
            if p[4] is not None:
                sectors.setdefault(int(((p[4] % 360.0) + 22.5) // 45.0) % 8, []).append(p)
        out = []
        for i in (2, 3):
            meds, resid = [], []
            for grp in sectors.values():
                xs = sorted(p[i] for p in grp)
                m = xs[len(xs) // 2]
                meds.append(m)
                resid += [x - m for x in xs]
            mean = sum(meds) / len(meds)
            sd = math.sqrt(sum(r * r for r in resid) / max(len(resid) - 1, 1))
            spread = max(meds) - min(meds)                  # sectors disagree: not a map shift
            se = 1.2533 * sd / math.sqrt(len(pts)) + 0.5 * spread
            out.append(mean if abs(mean) > 2.0 * se else 0.0)
        n = math.hypot(*out)
        if n > self.max_bias_m:
            out = [x * self.max_bias_m / n for x in out]
        return out[0], out[1]

    @staticmethod
    def _rotate(v, deg):
        """(east, north) turned clockwise by deg."""
        a = math.radians(deg)
        return (v[0] * math.cos(a) + v[1] * math.sin(a), -v[0] * math.sin(a) + v[1] * math.cos(a))

    def predict(self, t: float, heading_deg: Optional[float] = None) -> Optional[Tuple[float, float, float]]:
        """(lat, lon, sigma_m) at t: the position carried along the velocity from where it
        was last carried (advance(), once per frame) or the last fix. The velocity turns
        with the heading frame by frame: one constant-rate turn from the fix's heading to
        the present one folded a 180 deg turn or a full lap into a small one (campaign 4:
        the coast prediction 3-3.8 km off, outside the search window)."""
        base = self._carry or self._from_fix()
        if base is None:
            return None
        lat, lon, tb, sig, hdg_b, vel = base
        dt = max(0.0, t - tb)
        if vel is None or dt == 0:
            return lat, lon, sig + (0 if vel else 25.0 * dt)
        turn = _wrap(heading_deg - hdg_b) if heading_deg is not None and hdg_b is not None else 0.0
        steps = max(1, int(abs(turn) / 5.0))
        de = dn = 0.0
        for i in range(steps):                                # a constant-rate turn since the base
            v = self._rotate(vel, turn * (i + 0.5) / steps)
            de += v[0] * dt / steps
            dn += v[1] * dt / steps
        p = _move((lat, lon), de, dn)
        speed = math.hypot(*vel)
        # speed error, heading error (5 deg), unseen accelerations, and the turn (when it
        # started and its rate are not known: half its sideways reach)
        return (p[0], p[1], sig + self.vel_sigma * dt + math.radians(5.0) * speed * dt
                + 0.5 * self.accel * dt * dt + 0.5 * abs(math.radians(turn)) * speed * dt)

    def _from_fix(self):
        if self.fix is None:
            return None
        lat, lon, tf, sig, hdg_fix = self.fix
        vel, hdg = self.vel, self.vel_hdg if self.vel_hdg is not None else hdg_fix
        if vel is not None and hdg is not None and hdg_fix is not None:
            vel, hdg = self._rotate(vel, _wrap(hdg_fix - hdg)), hdg_fix   # the velocity at the fix's heading
        return lat, lon, tf, sig, hdg, vel

    def advance(self, t: float, heading_deg: Optional[float] = None) -> None:
        """Carry the position to t (once per frame without a fix): the next prediction
        starts from here, with the velocity turned to this heading."""
        p = self.predict(t, heading_deg)
        base = self._carry or self._from_fix()
        if p is None or base is None or t <= base[2]:
            return
        vel, hdg = base[5], base[4]
        if vel is not None and heading_deg is not None and hdg is not None:
            vel, hdg = self._rotate(vel, _wrap(heading_deg - hdg)), heading_deg
        self._carry = (p[0], p[1], t, p[2], hdg, vel)

    def search(self, t: float, heading_deg: Optional[float] = None, footprint_m: float = 0.0):
        """(centre, radius_m) to search the next frame in: the prediction and k sigma of it
        (the window follows the uncertainty: a lost vehicle is searched for wider)."""
        p = self.predict(t, heading_deg)
        if p is None:
            return None, None
        r = min(max(self.search_k * p[2], self.min_search_m), self.max_search_m)
        return (p[0], p[1]), r

    def heights_to_try(self, t: Optional[float] = None) -> Tuple[Optional[float], list, float]:
        """(height, extra heights to try, scale tolerance) at t: after retry_after failures
        in a row, the neighbouring heights too (a stale height makes every match fail)."""
        hs = self.height_at(t) if t is not None else (self.height[:2] if self.height else None)
        if hs is None:
            return None, [], 0.3
        h, sig = hs
        tol = min(0.35, max(0.15, 2.0 * sig / h))
        if self.fails >= self.retry_after:
            return h, [h * 0.8, h * 1.25], max(tol, 0.2)
        return h, [], tol

    # ── a match result ───────────────────────────────────────────────────
    def update(self, t: float, res: dict, height_used: Optional[float], heading_deg: Optional[float] = None,
               gps_valid: bool = False, search_m: Optional[float] = None) -> bool:
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
        spread = float(res.get("spread", 1.0))
        if inl < 100 and spread <= 0.25:
            # inliers on a quarter of the frame or less: such fixes reached p95 24-28 m
            # while stated 7.7 m (campaign 4)
            sig = max(sig, 14.5)
        pred = self.predict(t, heading_deg)
        if (inl < 30 and spread < self.min_spread) or (inl < 50 and spread <= 0.125):
            # (campaign 2: of 35 fixes refused on spread < 25 % with < 50 inliers, 27 were
            # right; campaign 3: the wrong ones that slipped through had their inliers in one
            # cell of eight)
            self.fails += 1
            self.last_reason = f"inliers on {res.get('spread', 0):.0%} of the frame ({inl}): rejected"
            return False
        if not gps_valid and self.max_speed_mps and self.fix is not None and t > self.fix[2]:
            # physically impossible from the last fix, however strong or confirmed the match
            reach = self.max_speed_mps * (t - self.fix[2]) + kinematic_margin_m(self.gate_k, self.fix[3], sig)
            jump = math.hypot(*_en((lat, lon), self.fix[:2]))
            if jump > reach:
                self.fails += 1
                self.kinematic_rejected += 1
                self.last_reason = (f"impossible jump {jump:.0f} m in {t - self.fix[2]:.1f} s from the last fix "
                                    f"(max {reach:.0f} m at {self.max_speed_mps:.0f} m/s, {inl} inliers): rejected")
                return False
        doubt, reacquired = None, False
        if self.consistency is not None:
            if not gps_valid and pred is not None:
                lost = pred[2] > self.consistency.lost_sigma_m
                doubt = self.consistency.doubt(math.hypot(*_en((lat, lon), pred[:2])), pred[2], sig, inl)
                if doubt is not None:
                    if not self.consistency.confirm(t, lat, lon, sig, self.vel, lost):
                        self.fails += 1
                        self.last_reason = doubt + ": rejected (a second agreeing fix would confirm it)"
                        return False
                    self.last_reason = doubt + ": confirmed by the previous fix — re-acquired"
                    reacquired = True
            self.consistency.clear()
        elif not gps_valid and pred is not None:
            d = math.hypot(*_en((lat, lon), pred[:2]))
            lim = self.gate_k * math.hypot(pred[2], sig)
            if inl >= self.strong_inliers:
                lim = self.strong_gate_k * math.hypot(pred[2], sig)
                if d > lim:
                    doubt = f"strong fix ({inl} inliers) {d:.0f} m from the prediction (> {lim:.0f} m)"
            elif d > lim:
                doubt = f"{d:.0f} m from the prediction (> {lim:.0f} m, {inl} inliers)"
            elif pred[2] > 50.0 and inl < 40:
                # lost enough that the gate is wide: a weak fix alone could be anywhere in it
                doubt = f"weak fix ({inl} inliers) while the position is uncertain (±{pred[2]:.0f} m)"
        if doubt is not None and not reacquired:
            # two fixes in a row that agree with each other (carried by the velocity) and not
            # with the prediction: the prediction is what is wrong — re-acquired
            pend, self._pending = self._pending, (t, lat, lon, sig)
            ok = False
            if pend is not None and 0 < t - pend[0] <= 6.0:
                ve, vn = self.vel if self.vel is not None else (0.0, 0.0)
                carried = _move(pend[1:3], ve * (t - pend[0]), vn * (t - pend[0]))
                gap = math.hypot(*_en((lat, lon), carried))
                ok = gap <= max(3.0 * math.hypot(sig, pend[3]), 15.0) + 0.3 * math.hypot(ve, vn) * (t - pend[0])
            if not ok:
                self.fails += 1
                self.last_reason = doubt + ": rejected (a second agreeing fix would confirm it)"
                return False
            self.last_reason = doubt + ": confirmed by the previous fix — re-acquired"
            reacquired = True
        self._pending = None
        self.fails = 0
        wide = (search_m or 0.0) > 300.0 or reacquired
        if height_used and res.get("scale_residual"):
            hv = height_used * float(res["scale_residual"])
            # vision height: ~3 % (campaign median), worse with few inliers; a re-acquisition
            # far from the prediction counts little (one set it 15 % low and the next frames
            # failed) but is not ignored (a stale height then stayed wrong: campaign 5)
            hs = max(0.03 * hv, 0.05 * hv if inl < 50 else 0.0)
            self._height_update(t, hv, 0.12 * hv if wide and inl < 100 else hs, "vision")
        if not gps_valid:
            out = None
            if self.blend_fixes and pred is not None and not reacquired and inl < self.blend_below_inliers:
                k = pred[2] ** 2 / (pred[2] ** 2 + sig ** 2)
                de, dn = _en((lat, lon), pred[:2])
                out = _move(pred[:2], k * de, k * dn) + (math.sqrt(k) * sig,)
            # a weak fix places the vehicle but does not measure its velocity (campaign 5: the
            # velocity of weak fixes carried the output to 68-142 m). The carry starts from the
            # MEASURED fix: fed the blended output it filtered itself (as day_subscriber, F38)
            self._set_fix(t, lat, lon, sig, heading_deg, velocity=inl >= self.weak_inliers)
            self._out = None if out is None else (t,) + out
        return True

    def _set_fix(self, t, lat, lon, sigma_m, heading_deg, velocity: bool = True):
        if self.fix is not None and t < self.fix[2]:
            return
        self._carry = None
        if self.vel is not None and self.vel_hdg is not None and heading_deg is not None:
            # the velocity follows the heading (a velocity from before a turn blended as it
            # was with the one after cancelled: 0 m/s at the GPS loss on the coast, 618 m)
            self.vel = self._rotate(self.vel, _wrap(heading_deg - self.vel_hdg))
            self.vel_hdg = heading_deg
        if not velocity:
            self.fix = (lat, lon, t, sigma_m, heading_deg)
            return
        self._fixes.append((t, lat, lon))
        # the velocity: from the latest fix at least 2 s older (else the oldest >= 1 s older),
        # never along a chord longer than 8 s (across a turn it is not a velocity)
        recent = [f for f in self._fixes if t - f[0] <= 8.0]
        older = [f for f in recent if t - f[0] >= 2.0] or [f for f in recent if t - f[0] >= 1.0][:1]
        if older:
            t0, la0, lo0 = older[-1]
            de, dn = _en((lat, lon), (la0, lo0))
            v = (de / (t - t0), dn / (t - t0))
            if self.vel is None or self.fix is None or t - self.fix[2] > 10.0:
                self.vel = v
            else:
                self.vel = (0.5 * self.vel[0] + 0.5 * v[0], 0.5 * self.vel[1] + 0.5 * v[1])
            # few fixes or a turn since: the velocity is less sure
            floor = 3.0 if len(self._fixes) < 4 else 0.0
            self.vel_sigma = max(floor, 1.0 + sigma_m / max(t - t0, 1.0))
            self.vel_hdg = heading_deg
        self.fix = (lat, lon, t, sigma_m, heading_deg)

    # ── output ───────────────────────────────────────────────────────────
    def output(self, t: float, heading_deg: Optional[float] = None):
        """(lat, lon, sigma_m, mode) — mode 'measured' (a fix this instant), 'propagated'
        (carried, growing sigma) or 'unavailable' (too long or too uncertain: say so)."""
        p = self.predict(t, heading_deg)
        if p is None:
            return None, None, None, "unavailable"
        if t - self.fix[2] >= 0.5:
            self.advance(t, heading_deg)
        age = t - self.fix[2]
        if age > self.max_dr_s or p[2] > self.max_sigma_m:
            return None, None, p[2], "unavailable"
        if age < 0.5 and self._out is not None and self._out[0] == self.fix[2]:
            return self._out[1], self._out[2], self._out[3], "measured"
        return p[0], p[1], p[2], ("measured" if age < 0.5 else "propagated")

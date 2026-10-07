"""spoof.py — catch a fake GPS, like NAVERA's arbiter does (simplified).

Positions are in METRES on a flat local map: x = east, y = north (lesson 6), so the maths
stays simple. Times are in seconds.

    python3 spoof.py            # plays the three attacks of scenarios.py through your guard

The real code: ~/navera/navera_estimator/navera_estimator/nodes/estimator_node.py
(_check_gps_plausibility, _drifting_away, _independent_reference).
"""
import math
import re

MAX_SPEED_MPS = 30.0      # the vehicle's top speed (max_speed_mps; the simulator's drone: 30 m/s)
JUMP_MARGIN_M = 50.0      # GPS noise allowance (gps_jump_margin_m)
GPS_TIMEOUT_S = 3.0       # a gap longer than this is an OUTAGE (gps_timeout_s)
STRICT_SIGMAS = 3.0       # "disagrees" = beyond 3 sigma of the vision fix
WIDE_SIGMAS = 5.0         # gps_crosscheck_sigmas: the wide tolerance is 5 sigma + 50 m
PERSIST_S = 3.0           # gps_crosscheck_persist_s
DOUBT_AFTER = 2           # distinct vision fixes in a row beyond 3 sigma -> GPS IN DOUBT
STREAK_N = 5              # ... -> GPS REFUSED (drifting away)
CONFIRM_N = 2             # distinct vision fixes agreeing within 3 sigma -> re-accepted
DOUBT_MAX_M = 500.0       # a bigger gap is more likely a wrong vision match: no "doubt"
VISION_FRESH_S = 5.0      # a vision fix older than this is not used (day_timeout_s)


def distance(x1, y1, x2, y2):
    """Straight-line distance in metres (Pythagoras)."""
    return math.hypot(x2 - x1, y2 - y1)


def reachable_m(dt_s, max_speed=MAX_SPEED_MPS, margin=JUMP_MARGIN_M):
    """How far the vehicle can have moved in dt_s seconds: max_speed x dt + margin.
    A negative dt counts as 0."""
    return None   # TODO 1


def kinematic_gate(trusted, fix, max_speed=MAX_SPEED_MPS, margin=JUMP_MARGIN_M):
    """True when `fix` is reachable from the last `trusted` fix.
    trusted and fix are (t, x, y) tuples."""
    return None   # TODO 2  (tip: t0, x0, y0 = trusted)


class GpsGuard:
    """Decides, for every GPS fix, if GPS is TRUSTED, IN_DOUBT (used, but suspicious) or REFUSED.

    guard.on_vision(t, x, y, sigma)   — a fix from an independent source (sigma None = unknown)
    guard.on_gps(t, x, y)             — a GPS fix; returns the state; guard.reason says why
    """

    def __init__(self, max_speed=MAX_SPEED_MPS):
        self.max_speed = max_speed
        self.state, self.reason = "TRUSTED", "no GPS yet"
        self.trusted = None            # (t, x, y) of the last GPS fix we accepted
        self.refused_by = None         # "jump" or "crosscheck" while REFUSED
        self.vision = None             # (t, x, y, sigma) latest independent fix
        self.streak = set()            # vision stamps disagreeing beyond 3 sigma, in a row
        self.disagree_since = None     # when GPS started disagreeing beyond 5 sigma + 50 m
        self.disagree_refs = set()     # vision stamps seen during that disagreement
        self.agree_refs = set()        # vision stamps agreeing, while waiting for confirmation

    def on_vision(self, t, x, y, sigma):
        self.vision = (t, x, y, sigma)

    def on_gps(self, t, x, y):
        if self.trusted is None:                                   # the very first fix
            self.trusted = (t, x, y)
            return self._set("TRUSTED", "GPS fix")
        outage = t - self.trusted[0] > GPS_TIMEOUT_S
        if self.state == "REFUSED" or outage:
            return self._confirm(t, x, y, outage)                  # TODO 4
        if not kinematic_gate(self.trusted, (t, x, y), self.max_speed):
            d = distance(self.trusted[1], self.trusted[2], x, y)
            dt = t - self.trusted[0]
            self.refused_by = "jump"
            return self._set("REFUSED", f"implausible jump {d:.0f} m in {dt:.1f} s "
                                        f"(max {_m(reachable_m(dt, self.max_speed))} m) — possible spoofing")
        self._cross_check(t, x, y)                                 # TODO 3
        if self.state != "REFUSED":
            self.trusted = (t, x, y)
        return self.state

    def _cross_check(self, t, x, y):
        """A trusted GPS compared with the independent source. Sets the state."""
        ref = self.vision_reference(t, x, y)
        if ref is None:                                            # nobody to compare with
            return self._set("TRUSTED", "GPS fix")
        d, sigma, vt = ref
        # TODO 3 — four small steps, in this order:
        # 1. if d > STRICT_SIGMAS * sigma: add vt to self.streak, else empty it (self.streak = set())
        # 2. if len(self.streak) >= STREAK_N: return self._refuse("GPS drifting away from vision: ...")
        # 3. if d <= WIDE_SIGMAS * sigma + JUMP_MARGIN_M: forget the disagreement
        #    (self.disagree_since, self.disagree_refs = None, set()); else remember since when
        #    (only if it is None), add vt to self.disagree_refs, and refuse ("GPS drifting away
        #    from vision: ... apart for 3 s") once t - self.disagree_since >= PERSIST_S AND
        #    there are at least 2 disagree_refs
        # 4. if len(self.streak) >= DOUBT_AFTER and d <= DOUBT_MAX_M:
        #        return self._set("IN_DOUBT", f"GPS IN DOUBT: vision disagrees by {d:.0f} m (possible slow spoofing)")
        #    otherwise return self._set("TRUSTED", "GPS fix")
        return self._set("TRUSTED", "GPS fix")

    def _confirm(self, t, x, y, outage):
        """GPS refused, or back after an outage: when may we use it again?"""
        ref = self.vision_reference(t, x, y)
        if ref is not None:
            d, sigma, vt = ref
            # TODO 4a — with an independent source of stated accuracy:
            #  - agreeing (d <= STRICT_SIGMAS * sigma): add vt to self.agree_refs, else empty it
            #  - CONFIRM_N distinct agreeing fixes: clear agree_refs, refused_by, streak and the
            #    disagreement, self.trusted = (t, x, y), and
            #    return self._set("TRUSTED", "GPS confirmed by vision (... 2 fixes) — re-accepted")
            #  - disagreeing: self.refused_by = self.refused_by or "crosscheck", and
            #    return self._set("REFUSED", f"GPS {d:.0f} m from vision (3 sigma ...) — possible spoofing")
            #  - otherwise (one agreeing fix so far): return self._set("REFUSED", "GPS waiting for a second agreeing vision fix")
            return self._set("REFUSED", "TODO 4a")
        # TODO 4b — no independent source: only the kinematic gate is left.
        #  - refused by the cross-check (self.refused_by == "crosscheck"): stay as we are (return self.state)
        #  - reachable from self.trusted: refused_by = None, trusted = (t, x, y),
        #    return self._set("TRUSTED", "GPS plausible again — re-accepted")
        #  - else: refused_by = "jump", return self._set("REFUSED", "implausible jump ... — possible spoofing")
        return self._set("REFUSED", "TODO 4b")

    # ---- you don't need to change anything below this line (but you can read it!) ----

    def vision_reference(self, t, x, y):
        """(distance GPS-vision, vision sigma, vision stamp) when a FRESH vision fix with a
        STATED sigma exists, else None. A source of unknown accuracy cannot vouch for or
        against GPS (the real _independent_reference)."""
        if self.vision is None:
            return None
        vt, vx, vy, sigma = self.vision
        if sigma is None or sigma < 0.01 or not (0.0 <= t - vt < VISION_FRESH_S):
            return None
        return distance(x, y, vx, vy), sigma, vt

    def _refuse(self, reason):
        self.refused_by = "crosscheck"
        self.streak, self.disagree_since, self.disagree_refs, self.agree_refs = set(), None, set(), set()
        return self._set("REFUSED", reason)

    def _set(self, state, reason):
        self.state, self.reason = state, reason
        return state


def _m(v):
    """A distance for a message: '80' (or '?' while reachable_m() is not written)."""
    return f"{v:.0f}" if isinstance(v, (int, float)) else "?"


def play(steps, guard=None, verbose=True):
    """Play a scenario (list of (t, kind, x, y, sigma)) through a GpsGuard.
    Returns [(t, state, reason, gps_offset_m)] for every GPS fix."""
    guard = guard or GpsGuard()
    out, last = [], None
    for t, kind, x, y, sigma, offset in steps:
        if kind == "vision":
            guard.on_vision(t, x, y, sigma)
            continue
        st = guard.on_gps(t, x, y)
        out.append((t, st, guard.reason, offset))
        key = (st, re.sub(r"[0-9.]+", "#", str(guard.reason)))
        if verbose and key != last:                    # print only the changes
            print(f"  t={t:6.1f} s  GPS {offset:6.0f} m off  ->  {str(st):9s} {guard.reason}")
            last = key
    return out


if __name__ == "__main__":
    import scenarios
    for name in scenarios.NAMES:
        print(f"\n=== {name}: {scenarios.DESCRIPTION[name]}")
        play(scenarios.build(name), GpsGuard(max_speed=scenarios.MAX_SPEED[name]))

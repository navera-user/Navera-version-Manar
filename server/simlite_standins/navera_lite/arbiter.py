"""Sim Lite stand-in judge: arbiter v0's naive rules (mission 09), self-contained. Written for the course.

Sent to the browser instead of the course's finished judge while mission 29 is not passed (and when your own
arbiter.py is not finished): priority GPS > day > night > celestial, the first fresh source wins at once (no
hold-off), a GPS fix farther than max_speed × elapsed + margin from the last stored one is refused, FIX if the
numbers give σ ≤ fix_max_sigma_m (v0 does not ask whether they are a covariance). Mission 29 replaces it."""
import math
from dataclasses import dataclass, field

from navera_lite.estimate import SOURCES, TIMEOUT_KEY, classify, horizontal


@dataclass
class Decision:
    state: str
    source: str | None
    estimate: object
    sigma_m: float | None
    reason: str
    sources: dict = field(default_factory=dict)
    switched: bool = False


def _metres(a, b):
    k = 111_320.0
    return math.hypot((b.lon - a.lon) * k * math.cos(math.radians(a.lat)), (b.lat - a.lat) * k)


class Arbiter:
    """v0 (naive on purpose). receive(est, now_s) → (stored, why); step(now_s) → Decision."""

    def __init__(self, cfg):
        self.cfg = dict(cfg)
        self.latest, self.trusted, self.current = {}, None, None

    def receive(self, est, now_s):
        if est.source not in TIMEOUT_KEY:
            return False, f"unknown source {est.source!r}"
        ok_pos = est.valid and math.isfinite(est.lat) and math.isfinite(est.lon)
        if est.source == "gps" and ok_pos:
            if self.trusted is not None:
                dt = abs(est.stamp_s - self.trusted.stamp_s)
                reach = float(self.cfg["max_speed_mps"]) * dt + float(self.cfg["gps_jump_margin_m"])
                d = _metres(self.trusted, est)
                if d > reach:
                    return False, f"jump {d:.0f} m > {reach:.0f} m"
            self.trusted = est
        est.t_recv_s = now_s
        self.latest[est.source] = est
        return True, "stored"

    def step(self, now_s):
        if not self.latest:
            return Decision("STARTING", None, None, None, "no position received yet")
        why = {}
        for name in SOURCES:
            est = self.latest.get(name)
            if est is None:
                continue
            age = now_s - est.stamp_s
            if not est.valid:
                why[name] = "no position"
            elif age > float(self.cfg[TIMEOUT_KEY[name]]):
                why[name] = f"stale ({age:.1f} s)"
            else:
                a, _, c = horizontal(est.cov)
                sigma = math.sqrt(max(a, c, 0.0))
                state, words = classify(sigma, self.cfg)
                switched, self.current = name != self.current, name
                return Decision(state, name, est, sigma, f"{name}: {words} (arbiter v0)", why, switched)
        self.current = None
        return Decision("NO_FIX", None, None, None,
                        "no usable source (" + "; ".join(f"{k}: {v}" for k, v in why.items()) + ")", why)

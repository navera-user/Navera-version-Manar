"""arbiter.py — your own NAVERA arbiter: eligibility predicates, priority selection with
hold-off (hysteresis), and the FIX / DEGRADED / NO_FIX / INITIALIZING classification.

The real one is ~/navera/navera_estimator/navera_estimator/nodes/estimator_node.py.
Yours follows the same rules, written as plain functions and one small class that you can
test without ROS.

An ESTIMATE is a Python dict with the information of a navera_msgs/PositionEstimate:

    {"source": "gps",            # "gps", "day", "night" or "cn" (celestial)
     "stamp": 12.0,              # when it was MEASURED (seconds, same clock as `now`)
     "valid": True,              # the source says: "you may use this position"
     "mode": "MEASURED",         # "MEASURED", "PROPAGATED", "HELD" or "REPLAYED"
     "lat": 35.8250, "lon": 10.6380,
     "cov": [9.0, 0, 0,  0, 9.0, 0,  0, 0, 36.0],   # 3x3 covariance, row-major, m^2 (E, N, Up)
     "cov_type": "APPROXIMATED"} # "UNKNOWN", "APPROXIMATED", "DIAGONAL_KNOWN" or "KNOWN"

Run the demo:   python3 arbiter.py
"""
import math

# The same numbers as ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
TIMEOUTS = {"gps": 3.0, "day": 5.0, "night": 5.0, "cn": 45.0}   # freshness windows T_s (s)
FUTURE_TOLERANCE_S = 0.5      # a stamp further than this in the FUTURE is refused
SWITCH_HOLDOFF_S = 2.0        # a better source must stay eligible this long before it takes over
FIX_MAX_SIGMA_M = 25.0        # largest stated sigma still reported as FIX
MIN_STATED_SIGMA_M = 0.01     # a sigma below 1 cm is "not filled in", not an accuracy

PRIORITY = ["gps", "day", "night", "cn"]          # first eligible source wins
NAMES = {"gps": "GPS", "day": "day vision", "night": "night vision", "cn": "celestial"}
USABLE_MODES = ("MEASURED", "PROPAGATED")
BOUNDED_TYPES = ("APPROXIMATED", "DIAGONAL_KNOWN", "KNOWN")


def is_fresh(est, now):
    """True when the estimate is young enough to describe the present.

    age = now - est["stamp"].  Fresh means:  -FUTURE_TOLERANCE_S <= age < TIMEOUTS[source]
    (a stamp far in the future means a clock problem: its age cannot be trusted).
    """
    # TODO 1: compute the age, then return True/False with the rule above.
    return None


def cov_ok(cov):
    """True when `cov` (9 numbers, a 3x3 matrix in row-major order) IS a covariance matrix:

      1. it has 9 elements, all finite (no nan, no inf)
      2. the variances (diagonal: indices 0, 4, 8) are >= 0
      3. it is symmetric: cov[1]==cov[3], cov[2]==cov[6], cov[5]==cov[7], within
         tol = 1e-9 * max(1, cov[0], cov[4], cov[8])
      4. the horizontal 2x2 block [[cov[0], cov[1]], [cov[3], cov[4]]] is positive
         semi-definite: with 1. and 2. true, that means its determinant >= -tol
    """
    # TODO 2: the four conditions of the docstring, one `if ...: return False` each.
    # Convert to floats first: None, or a list of the wrong length, must give False, not a crash.
    return None


def stated_sigma(est):
    """The horizontal 1-sigma (m) the source STATES, or None when it states none.

      - cov_type not in BOUNDED_TYPES             -> None (UNKNOWN or garbage)
      - sigma = sqrt(max(cov[0], cov[4]))          (the worse of East and North)
      - sigma < MIN_STATED_SIGMA_M                 -> None (zero is a missing value)
    """
    # TODO 3: None, or the stated horizontal sigma in metres.
    return None


def is_eligible(est, now):
    """True when the arbiter may use this estimate at all. ALL of these must hold:
      1. est["valid"] is True
      2. est["mode"] is MEASURED or PROPAGATED (a HELD echo or REPLAYED data never wins)
      3. it is fresh (is_fresh)
      4. position_ok(lat, lon): finite, in range, not exactly (0, 0)
      5. cov_ok(est["cov"])
    An UNKNOWN covariance type is allowed (it will be DEGRADED), but its numbers must
    still form a covariance (all zeros is fine).
    """
    # TODO 4: the 5 rules, one guard clause each. position_ok() is below the line.
    return None


def classify(est):
    """(state, reason) for the WINNING estimate. Exactly the real _classify() rules, in order:

      MEASURED, stated sigma above 25 m  -> ("DEGRADED", "GPS fix, uncertainty 40 m > 25 m")
      MEASURED, stated sigma <= 25 m     -> ("FIX",      "GPS fix")
      MEASURED, no stated sigma          -> ("DEGRADED", "day vision fix, uncertainty unknown")
      anything else (PROPAGATED)         -> ("DEGRADED", "night vision solution is propagated (dead-reckoned)")

    Use NAMES[est["source"]] for the name, stated_sigma(est), and f"{x:.0f}" for the numbers.
    """
    # TODO 5: return (state, reason) following the 4 lines above, in that order.
    return None, None


def decide(estimates, now, active=None, eligible_since=None, holdoff_s=SWITCH_HOLDOFF_S):
    """The arbiter's decision: {"state": ..., "source": ..., "reason": ...}. Pure function.

    estimates       list of the latest estimate of each source heard so far (maybe empty)
    now             the current time (s)
    active          the source that won last time (or None)
    eligible_since  {source: time since which it has been CONTINUOUSLY eligible}
    holdoff_s       the hold-off (s)

      - no estimate at all  -> "INITIALIZING", source None, reason "waiting for first source message"
      - none eligible       -> "NO_FIX", source None, reason = the why_not() clauses of the
                               sources heard, in PRIORITY order, joined with "; "
      - otherwise best = the first eligible source in PRIORITY. Hold-off: if `active` is
        eligible, best != active, and now - eligible_since[best] < holdoff_s, the winner
        stays `active`. state/reason = classify(winner).
    """
    # TODO 6: INITIALIZING / NO_FIX / priority + hold-off.
    return {"state": None, "source": None, "reason": "TODO 6"}


class Arbiter:
    """The arbiter as a STATE MACHINE: it remembers what decide() needs between two calls.

        arb = Arbiter()
        arb.receive(estimate)      # a message arrives
        d = arb.step(now)          # decide now (on every arrival AND on a 5 Hz clock)
    """

    def __init__(self, holdoff_s=SWITCH_HOLDOFF_S):
        self.holdoff_s = holdoff_s
        self.latest = {}            # source -> latest estimate received
        self.active = None          # source that won the last step (or None)
        self.eligible_since = {}    # source -> time since which it is continuously eligible
        self.switches = []          # (time, old source, new source) each time the winner changes
        self.decision = None        # the last decision dict

    def receive(self, est):
        """Store `est` as the latest of its source, EXCEPT a late GPS fix: a GPS estimate whose
        stamp is older than the GPS estimate already stored is dropped (old news from a buffer)."""
        # TODO 7: keep the newest estimate of each source; drop a late GPS fix.
        pass

    def step(self, now):
        """One decision at time `now`, in this order (the real _select() does the same):
          1. for every source in PRIORITY: if it has an estimate and it is eligible now,
             eligible_since.setdefault(source, now); otherwise eligible_since.pop(source, None)
          2. d = decide(latest estimates in PRIORITY order, now, self.active,
                        self.eligible_since, self.holdoff_s)
          3. if d["source"] != self.active: append (now, self.active, d["source"]) to
             self.switches (None counts: losing every source is a change too)
          4. self.active = d["source"]; self.decision = d; return d
        """
        # TODO 8: the four steps of the docstring.
        return None


# ---- you don't need to change anything below this line (but you can read it!) ----

def position_ok(lat, lon):
    """A real, in-range position (same rule as navera_common/geo.py is_finite_latlon)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return not (lat == 0.0 and lon == 0.0)


def why_not(est, now):
    """One clause explaining why `est` is not usable — the same words as the real
    _source_reason(). Returns "" when it is usable."""
    name = {"gps": "GPS", "day": "day", "night": "night", "cn": "cn"}[est["source"]]
    age = now - est["stamp"]
    timeout = TIMEOUTS[est["source"]]
    if age < -FUTURE_TOLERANCE_S:
        return f"{name}: timestamp {-age:.1f}s in the future (clock problem)"
    if age >= timeout:
        return f"{name}: stale ({age:.1f}s>{timeout:.1f}s)"
    if est.get("valid") is not True:
        return f"{name}: invalid"
    if est.get("mode") not in USABLE_MODES:
        return f"{name}: {str(est.get('mode')).lower()} not usable"
    if not is_eligible(est, now):
        return f"{name}: non-finite position or covariance"
    return ""


def make_est(source, stamp, sigma=None, **kw):
    """An estimate dict. sigma=None -> covariance type UNKNOWN (all zeros);
    otherwise East/North variance sigma^2 and Up variance (2 sigma)^2, type APPROXIMATED."""
    if sigma is None:
        cov, ctype = [0.0] * 9, "UNKNOWN"
    else:
        v = float(sigma) ** 2
        cov, ctype = [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4.0 * v], "APPROXIMATED"
    est = dict(source=source, stamp=stamp, valid=True, mode="MEASURED",
               lat=35.8250, lon=10.6380, cov=cov, cov_type=ctype)   # Sousse, Tunisia (example only)
    est.update(kw)
    return est


def gps(stamp, sigma=3.0, **kw):
    """A quick GPS estimate for the demo and your own tests."""
    return make_est("gps", stamp, sigma, **kw)


def day(stamp, sigma=None, **kw):
    """A quick day-vision estimate (default: uncertainty unknown)."""
    return make_est("day", stamp, sigma, **dict(dict(lat=35.8254, lon=10.6387), **kw))


if __name__ == "__main__":
    now = 100.0
    cases = [
        ("nothing received yet", []),
        ("a fresh GPS", [gps(99.5)]),
        ("GPS + day vision", [gps(99.5), day(99.0)]),
        ("GPS 4 s old, day vision fresh", [gps(96.0), day(99.0)]),
        ("GPS with HDOP 20 (sigma 40 m)", [gps(99.5, sigma=40.0)]),
        ("GPS with an all-zero covariance", [gps(99.5, sigma=0.0)]),
        ("everything old", [gps(90.0), day(90.0)]),
    ]
    for title, ests in cases:
        print(f"{title:34s} -> {decide(ests, now)}")
    print("\nThe state machine: day vision active, GPS comes back at t = 10 s")
    arb = Arbiter()
    for k in range(0, 30):
        t = 0.5 * k
        arb.receive(day(t))
        if t >= 10.0:
            arb.receive(gps(t))
        arb.step(t)
    print("switches:", arb.switches, "(expected: None->day at 0.0, day->gps at 12.0)")

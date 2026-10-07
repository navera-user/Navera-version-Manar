"""arbiter.py — your own (simplified) NAVERA arbiter.

The real one is ~/navera/navera_estimator/navera_estimator/nodes/estimator_node.py.
Yours follows the same rules, written as plain functions you can test without ROS.

An ESTIMATE is a Python dict, one per source, the latest one we received:

    {"source": "gps",          # "gps", "day", "night" or "cn" (celestial)
     "stamp": 12.0,            # when it was MEASURED (seconds, same clock as `now`)
     "valid": True,            # the source says: "you may use this position"
     "mode": "MEASURED",       # "MEASURED", "PROPAGATED", "HELD" or "REPLAYED"
     "lat": 35.83, "lon": 10.64,
     "sigma": 3.0}             # stated accuracy (1 sigma, metres), or None = unknown

Run the demo:   python3 arbiter.py
"""
import math

# The same numbers as ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
TIMEOUTS = {"gps": 3.0, "day": 5.0, "night": 5.0, "cn": 45.0}   # freshness window (s)
FUTURE_TOLERANCE_S = 0.5      # a stamp further than this in the FUTURE is refused
SWITCH_HOLDOFF_S = 2.0        # a better source must stay usable this long before it takes over
FIX_MAX_SIGMA_M = 25.0        # largest stated sigma still reported as FIX
MIN_STATED_SIGMA_M = 0.01     # a sigma below 1 cm is "not filled in", not an accuracy

PRIORITY = ["gps", "day", "night", "cn"]          # first usable source wins
NAMES = {"gps": "GPS", "day": "day vision", "night": "night vision", "cn": "celestial"}
USABLE_MODES = ("MEASURED", "PROPAGATED")


def is_fresh(est, now):
    """True when the estimate is young enough to be used.

    age = now - est["stamp"].  Fresh means:  -FUTURE_TOLERANCE_S <= age < TIMEOUTS[source]
    (a stamp far in the future means a clock problem: its age cannot be trusted).
    """
    age = now - est["stamp"]
    return -FUTURE_TOLERANCE_S <= age < TIMEOUTS[est["source"]]


def is_eligible(est, now):
    """True when the arbiter may use this estimate at all. ALL of these must hold:
      1. est["valid"] is True
      2. est["mode"] is MEASURED or PROPAGATED (a HELD echo or REPLAYED data never wins)
      3. it is fresh (is_fresh)
      4. lat and lon are finite numbers, in range, and not exactly (0, 0)
      5. sigma is None (unknown is allowed — it will just be DEGRADED) or a finite number >= 0
    """
    if est.get("valid") is not True:
        return False
    if est.get("mode") not in USABLE_MODES:
        return False
    if not is_fresh(est, now):
        return False
    if not position_ok(est.get("lat"), est.get("lon")):
        return False
    sigma = est.get("sigma")
    if sigma is not None and not (isinstance(sigma, (int, float)) and math.isfinite(sigma) and sigma >= 0):
        return False
    return True


def classify(est):
    """(state, reason) for the WINNING estimate. Exactly the real _classify() rules:

      MEASURED, stated sigma (>= 1 cm) above 25 m -> ("DEGRADED", "GPS fix, uncertainty 40 m > 25 m")
      MEASURED, stated sigma (>= 1 cm) <= 25 m    -> ("FIX",      "GPS fix")
      MEASURED, sigma unknown (None or < 1 cm)    -> ("DEGRADED", "day vision fix, uncertainty unknown")
      anything else (PROPAGATED)                  -> ("DEGRADED", "night vision solution is propagated (dead-reckoned)")

    Use NAMES[est["source"]] for the name, and f"{sigma:.0f}" for the numbers.
    """
    name = NAMES[est["source"]]
    sigma = est.get("sigma")
    bounded = sigma is not None and sigma >= MIN_STATED_SIGMA_M
    if est["mode"] == "MEASURED" and bounded and sigma > FIX_MAX_SIGMA_M:
        return "DEGRADED", f"{name} fix, uncertainty {sigma:.0f} m > {FIX_MAX_SIGMA_M:.0f} m"
    if est["mode"] == "MEASURED" and bounded:
        return "FIX", f"{name} fix"
    if est["mode"] == "MEASURED":
        return "DEGRADED", f"{name} fix, uncertainty unknown"
    return "DEGRADED", f"{name} solution is propagated (dead-reckoned)"


def decide(estimates, now, active=None, eligible_since=None):
    """The arbiter's decision: {"state": ..., "source": ..., "reason": ...}.

    estimates       list of the latest estimate of each source heard so far (maybe empty)
    now             the current time (s)
    active          the source that won last time (or None)
    eligible_since  {source: time it became continuously eligible}

      - no estimate at all            -> state "INITIALIZING", source None, reason "waiting for first source message"
      - none eligible                 -> state "NO_FIX", source None,
                                         reason = the why_not() clauses of each source in PRIORITY order
                                         (only the sources heard), joined with "; "
      - otherwise the first eligible source in PRIORITY wins, EXCEPT (hold-off): if the active
        source is still eligible and the best one has been eligible for less than
        SWITCH_HOLDOFF_S, keep the active one.  state/reason come from classify(winner).
    """
    eligible_since = eligible_since or {}
    if not estimates:
        return {"state": "INITIALIZING", "source": None, "reason": "waiting for first source message"}
    by_source = {e["source"]: e for e in estimates}
    usable = [s for s in PRIORITY if s in by_source and is_eligible(by_source[s], now)]
    if not usable:
        clauses = [why_not(by_source[s], now) for s in PRIORITY if s in by_source]
        return {"state": "NO_FIX", "source": None,
                "reason": "; ".join(c for c in clauses if c) or "no usable source"}
    best = usable[0]
    winner = best
    if active in usable and best != active:
        dwell = now - eligible_since.get(best, now)
        if dwell < SWITCH_HOLDOFF_S:
            winner = active
    state, reason = classify(by_source[winner])
    return {"state": state, "source": winner, "reason": reason}


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


def gps(stamp, sigma=3.0, **kw):
    """A quick GPS estimate for the demo and your own tests."""
    return dict(dict(source="gps", stamp=stamp, valid=True, mode="MEASURED", lat=35.8256, lon=10.6385,
                     sigma=sigma), **kw)


def day(stamp, sigma=None, **kw):
    return dict(dict(source="day", stamp=stamp, valid=True, mode="MEASURED", lat=35.8259, lon=10.6390,
                     sigma=sigma), **kw)


if __name__ == "__main__":
    now = 100.0
    cases = [
        ("nothing received yet", []),
        ("a fresh GPS", [gps(99.5)]),
        ("GPS + day vision", [gps(99.5), day(99.0)]),
        ("GPS 4 s old, day vision fresh", [gps(96.0), day(99.0)]),
        ("GPS with HDOP 20 (sigma 40 m)", [gps(99.5, sigma=40.0)]),
        ("everything old", [gps(90.0), day(90.0)]),
    ]
    for title, ests in cases:
        d = decide(ests, now)
        print(f"{title:32s} -> {d}")

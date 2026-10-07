# Lab 12 — what did the jury say? For each run of your source, copy the arbiter's verdict:
#   STATE:  the `state` number of /navera/nav_status  (0 INITIALIZING, 1 NO_FIX, 2 FIX, 3 DEGRADED)
#   REASON: its `reason`, the part about day vision — e.g. "day: stale (10.0s>3.0s)" or "day vision fix"
# Commands (lab, steps 4–6):
#   ros2 topic echo /navera/nav_status --field reason
#   ros2 topic echo --once /navera/nav_status --field state

VERDICTS = {
    #  fault          (STATE, "REASON")
    "none":        (None, ""),
    "nan":         (None, ""),
    "not_psd":     (None, ""),
    "stale":       (None, ""),
    "latency":     (None, ""),
    "future":      (None, ""),
    "invalid":     (None, ""),
    "replayed":    (None, ""),
    "held":        (None, ""),
    "propagated":  (None, ""),
    "unknown_cov": (None, ""),
    "big_sigma":   (None, ""),
    "tilted":      (None, ""),
}

# Quiz — "a", "b" or "c".
# Q1. "nan" and "not_psd" give the same reason. Why is that acceptable?
#   a) because the arbiter cannot see the difference between them
#   b) because both mean "this message holds no usable position or covariance": the decision is the
#      same; the source's own log or details_json tell an engineer more
#   c) it is a bug of NAVERA
Q1 = ""
# Q2. Your source states sigma = 15 m and gets a green FIX. What does that prove about its accuracy?
#   a) that it is really accurate to 15 m
#   b) nothing: the arbiter believes the stated sigma; only a measurement (validation) can prove it
#   c) that it is more accurate than the GPS
Q2 = ""

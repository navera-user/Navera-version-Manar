# Lab 12 — what did the arbiter say? For each run of your source, copy the arbiter's verdict:
#   STATE:  the `state` number of /navera/nav_status  (0 INITIALIZING, 1 NO_FIX, 2 FIX, 3 DEGRADED)
#   REASON: its `reason`.
#     - state NO_FIX (1): the reason lists every source; copy only the "day: ..." part,
#       e.g. "day: stale (10.0s>3.0s)".
#     - state FIX (2) or DEGRADED (3): the reason is one sentence; copy all of it,
#       e.g. "day vision fix" or "day vision fix, uncertainty unknown".
#     Numbers may differ a little from the lab (10.4 s instead of 10.0 s): copy what YOU see.
# Commands (lab, steps 4 and 5):
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

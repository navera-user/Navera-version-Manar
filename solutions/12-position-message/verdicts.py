# Lab 12 — what did the jury say? (teacher solution)

VERDICTS = {
    "none":        (2, "day vision fix"),
    "nan":         (1, "day: non-finite position or covariance"),
    "not_psd":     (1, "day: non-finite position or covariance"),
    "stale":       (1, "day: stale (10.0s>3.0s)"),
    "latency":     (2, "day vision fix"),
    "future":      (1, "day: timestamp 5.0s in the future (clock problem)"),
    "invalid":     (1, "day: invalid (lens covered)"),
    "replayed":    (1, "day: replayed not usable"),
    "held":        (1, "day: held not usable"),
    "propagated":  (3, "day vision solution is propagated (dead-reckoned)"),
    "unknown_cov": (3, "day vision fix, uncertainty unknown"),
    "big_sigma":   (3, "day vision fix, uncertainty 30 m > 25 m"),
    "tilted":      (2, "day vision fix"),
}

Q1 = "b"
Q2 = "b"

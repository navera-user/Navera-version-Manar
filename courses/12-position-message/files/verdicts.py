# Lab 12 — what did the jury say? Copy the arbiter's `reason` for each run of your source
# (from `ros2 topic echo /navera/nav_status --field reason`), between the quotes.
# Copy the part about day vision — for example "day: stale (11.4s>3.0s)" or "day vision fix".

REASON_GOOD = ""          # python3 my_source.py
REASON_NAN = ""           # python3 my_source.py nan
REASON_BAD_COV = ""       # python3 my_source.py bad_cov
REASON_STALE = ""         # python3 my_source.py stale
REASON_INVALID = ""       # python3 my_source.py invalid
REASON_REPLAYED = ""      # python3 my_source.py replayed
REASON_UNKNOWN_COV = ""   # python3 my_source.py unknown_cov
REASON_SIGMA_40 = ""      # python3 my_source.py   with SIGMA_M = 40.0 (then put it back to 15.0!)

# Quiz — "a", "b" or "c".
# Q1. Faults "nan" and "bad_cov" give the same reason. Why is that acceptable?
#   a) because the arbiter cannot see the difference between them
#   b) because both mean "this message does not hold a usable position or covariance": the arbiter's
#      decision is the same; the source's own log or details tell an engineer more
#   c) it is a bug of NAVERA
Q1 = ""

# Q2. Your source says sigma = 15 m and gets a green FIX. What does that prove about its accuracy?
#   a) that it is really accurate to 15 m
#   b) nothing: the arbiter believes the stated sigma; only a measurement (validation) can prove it
#   c) that it is more accurate than the GPS
Q2 = ""

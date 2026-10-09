# Lab 1 — your answers. Numbers without quotes (MARGIN_M = 12.5). Text and sentences IN QUOTES:
# ARCH = "aarch64", EXPLAIN_TWO = "Because …". Without quotes, Python stops with a NameError.
# Save with Ctrl+S, then press ✔ Check my work.
#
# PREDICT_… : write your guess BEFORE you run the step. A wrong guess is fine — it is not graded
#             right or wrong. Guessing first is how you notice what surprised you.
# EXPLAIN_… : after the run, explain in your own words (one or two sentences).

# ---- Step 1: the computer ----------------------------------------------------------
ARCH = ""            # what `uname -m` prints
CPU_CORES = 0        # what `nproc` prints

# ---- Step 3: NAVERA's rules, read in your copy (estimator_params.yaml) -------------
V_MAX_MPS = 0.0      # max_speed_mps
MARGIN_M = 0.0       # gps_jump_margin_m
GPS_TIMEOUT_S = 0.0  # gps_timeout_s

# ---- Step 6: a clock 1 µs fast -------------------------------------------------------
PREDICT_CLOCK = ""   # before running: where will find_position land with the wrong clock? why?
CLOCK_ERROR_M = 0    # after running: "distance from the true position" of find_position (metres)
EXPLAIN_CLOCK = ""   # why did find_position_and_bias find the right place when find_position did not?

# ---- Step 7: two beacons -------------------------------------------------------------
PREDICT_TWO = ""     # before running: with only A and B and an unknown clock, how many answers?
EXPLAIN_TWO = ""     # after running: why so many? (count the unknowns and the measurements)

# ---- Step 8: the spoofer -------------------------------------------------------------
PREDICT_SPOOF = ""   # before running: will your receiver notice the spoof? how?
EXPLAIN_SPOOF = ""   # after running: why is the mismatch 0 at the fake position?

# ---- Step 9: the jump gate -----------------------------------------------------------
PREDICT_GATE = ""    # before running: how many fixes refused in attack A (300 m jump)? in attack B (drag)?
JUMP_REFUSED = -1    # after running: count_refused for attack A
DRIFT_REFUSED = -1   # after running: count_refused for attack B
EXPLAIN_GATE = ""    # why can't the gate alone stop these attacks? what does NAVERA add?

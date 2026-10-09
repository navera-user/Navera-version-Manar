# Lab 1 — your answers. Numbers without quotes (MARGIN_M = 12.5). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ---- Step 1: NAVERA's rules (estimator_params.yaml) -------------------------------------
V_MAX_MPS = 0.0      # max_speed_mps
MARGIN_M = 0.0       # gps_jump_margin_m
GPS_TIMEOUT_S = 0.0  # gps_timeout_s

# ---- Step 4: a clock 1 µs ahead ------------------------------------------------------------
PREDICT_CLOCK = ""   # where does find_position land, with what minimum mismatch?
CLOCK_ERROR_M = 0    # part 1 of `clock`: distance from the true position (m)
EXPLAIN_CLOCK = ""   # why does adding the bias as an unknown repair the solution?

# ---- Step 5: two beacons -------------------------------------------------------------------
PREDICT_TWO = ""     # with only A and B, how many (x, y, bias) fit?
EXPLAIN_TWO = ""     # count unknowns vs measurements; how many satellites does real GPS need?
CURVE = ""           # which curve do the fitting positions draw? (one word)

# ---- Step 6: Gauss–Newton ---------------------------------------------------------------------
GN_STEPS = 0         # how many steps until the mismatch is below 1e-6 (from `gn`)
EXPLAIN_GN = ""      # why is it so much faster than brute force, and what could make it fail?

# ---- Step 7: spoofing --------------------------------------------------------------------------
PREDICT_SPOOF = ""   # full spoof: what will your solver find, with what mismatch?
EXPLAIN_SPOOF = ""   # why is the mismatch 0 at the fake position? what does it mean for a receiver?
PREDICT_PARTIAL = "" # only A, B, C spoofed, D real: what changes?
EXPLAIN_PARTIAL = "" # why can a receiver with a spare measurement notice a partial spoof?

# ---- Step 8: the jump gate --------------------------------------------------------------------
PREDICT_GATE = ""    # how many fixes refused in attack A (300 m jump)? in attack B (drag)?
JUMP_REFUSED = -1    # count_refused for attack A
DRIFT_REFUSED = -1   # count_refused for attack B

# ---- Step 9: be the arbiter ------------------------------------------------------------------
ARBITER_SOURCE = ""  # "gps", "day", "night", "celestial" or "none"
ARBITER_STATE = ""   # "FIX", "DEGRADED" or "NO_FIX"

# ---- Step 10: the detective ------------------------------------------------------------------
PREDICT_FLIGHT = ""  # will the jump gate catch the spoof? will the cross-check? when?
FLIGHT_REFUSED = -1  # jump gate alone on the whole flight: fixes refused
CAUGHT_AT_S = -1     # first disagreement (s)
EXPLAIN_FLIGHT = ""  # when did the spoof really start (look at out/flight.png), and why was it caught so late?

# ---- Step 11: attacker vs defender ----------------------------------------------------------
STEALTH_SPEED_MPS = 0      # NAVERA defaults: highest drag speed (m/s) never refused
REFUSED_ONE_FASTER = -1    # how many of the 60 fixes are refused at 1 m/s more
DEFENDER_MARGIN_M = 0      # v_max = 15 m/s: smallest whole-metre margin with zero refusals on the honest GPS
DEFENDER_STEALTH_MPS = 0   # the attacker's best drag speed against your defender setting
EXPLAIN_TRADEOFF = ""      # what does a tighter gate cost, and what does it still not stop?

# Lab 10 — your answers. Numbers without quotes (RATE = 1.02). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Build ========

# ---- Step 0: the bug -------------------------------------------------------------------------
BUG_SPEED_10HZ_MPS = 0.0   # the forwarder re-sends at 10 Hz: the largest speed the listener computes (m/s)

# ---- Step 3: real dt or nominal dt? -----------------------------------------------------------
PREDICT_DRIVE = ""       # after the busy second, how far from the truth is the NOMINAL-dt receiver? and yours?
NOMINAL_ERROR_M = 0.0    # NOMINAL dt: distance from the truth at the last stamp (m, one decimal)
NOMINAL_SPEED_MAX_MPS = 0.0   # NOMINAL dt: the largest speed a listener computes (m/s, one decimal)
EXPLAIN_DRIVE = ""       # why is the nominal receiver wrong, and why does the error not shrink again after the stall?

# ---- Step 4: make_fix vs convert.to_navsatfix ------------------------------------------------
EXPLAIN_FIX = ""
#   one field that to_navsatfix fills differently from your make_fix, and why

# ---- Step 6: your node, live ------------------------------------------------------------------
MEASURED_RATE_HZ = 0.0   # `ros2 topic hz`: the last "average rate" (default node, 1 Hz)
MEASURED_STD_S = -1.0    # `ros2 topic hz`: the last "std dev" (s)

# ---- Step 7: jitter ----------------------------------------------------------------------------
PREDICT_JITTER = ""      # your node on a computer that is late at random: what speeds will a listener compute?
EXPLAIN_JITTER = ""      # why do YOUR fixes stay right although the intervals vary? what would a nominal node show?

# ======== Session 2 — Sabotage ========

# ---- Step 9: the saboteur (run A, B, C, D in this order) ---------------------------------
PREDICT_SABOTAGE = ""    # your four guesses (A, B, C, D) BEFORE you run them
V0_OLD = ""              # A: stamp_offset_s -5.0 → "FIX", "DEGRADED" or "NO_FIX"
V0_COARSE = ""           # B: sigma_m 40.0
V0_COARSE_REASON = ""    # B: the `message` of the status, copied exactly
V0_NO_SIGMA = ""         # C: sigma_m 0.0 (your receiver states no accuracy)
V0_FUTURE = ""           # D: stamp_offset_s 30.0
AGE_FUTURE_S = 0.0       # D: the age_s value v0 reports (s, one decimal)
FROZEN_S = 0             # D: after you stop the receiver, about how many seconds does v0 still say FIX?
EXPLAIN_JUMP = ""
#   in A, why is the elapsed time of the jump gate negative, and what does the gate assume about stamps?
EXPLAIN_HOLES = ""       # which of v0's verdicts are wrong, and why does v0 make each mistake?

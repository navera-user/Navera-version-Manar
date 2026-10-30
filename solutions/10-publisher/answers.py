# Lab 10 — your answers. Numbers without quotes (RATE = 1.02). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Build ========

# ---- Step 0: the bug -------------------------------------------------------------------------
BUG_SPEED_10HZ_MPS = 100.0   # the forwarder re-sends at 10 Hz: the largest speed the listener computes (m/s)

# ---- Step 3: real dt or nominal dt? -----------------------------------------------------------
PREDICT_DRIVE = "The nominal one loses the busy second, so maybe 10 m behind; mine stays on the truth."       # after the busy second, how far from the truth is the NOMINAL-dt receiver? and yours?
NOMINAL_ERROR_M = 12.5    # NOMINAL dt: distance from the truth at the last stamp (m, one decimal)
NOMINAL_SPEED_MAX_MPS = 14.3   # NOMINAL dt: the largest speed a listener computes (m/s, one decimal)
EXPLAIN_DRIVE = "The nominal receiver adds 0.5 s of motion per tick, but the busy computer lost two ticks, so one second of motion is never added and the error stays at about 12 m; between ticks its speeds also swing because the real intervals are not 0.5 s."       # why is the nominal receiver wrong, and why does the error not shrink again after the stall?

# ---- Step 4: make_fix vs convert.to_navsatfix ------------------------------------------------
EXPLAIN_FIX = "to_navsatfix takes frame_id from the Estimate's source (day, night...) and sets service 0 for a source that is not GPS; mine always writes gps and SERVICE_GPS."
#   one field that to_navsatfix fills differently from your make_fix, and why

# ---- Step 6: your node, live ------------------------------------------------------------------
MEASURED_RATE_HZ = 1.000   # `ros2 topic hz`: the last "average rate" (default node, 1 Hz)
MEASURED_STD_S = 0.0004    # `ros2 topic hz`: the last "std dev" (s)

# ---- Step 7: jitter ----------------------------------------------------------------------------
PREDICT_JITTER = "Always 10 m/s, because my dt is the real time between ticks."      # your node on a computer that is late at random: what speeds will a listener compute?
EXPLAIN_JITTER = "My node moves the vehicle by speed times the real dt measured on the same clock as the stamp, so each fix is where the vehicle was at its stamp; a nominal-dt node would show speeds from about 3 to 60 m/s at the same instants."      # why do YOUR fixes stay right although the intervals vary? what would a nominal node show?

# ======== Session 2 — Sabotage ========

# ---- Step 9: the saboteur (run A, B, C, D in this order) ---------------------------------
PREDICT_SABOTAGE = "A NO_FIX (old), B DEGRADED, C DEGRADED (unknown), D NO_FIX (future is wrong)."    # your four guesses (A, B, C, D) BEFORE you run them
V0_OLD = "NO_FIX"              # A: stamp_offset_s -5.0 → "FIX", "DEGRADED" or "NO_FIX"
V0_COARSE = "DEGRADED"
V0_COARSE_REASON = "gps: σ 40.0 m > 25.0 m"
V0_NO_SIGMA = "FIX"         # C: sigma_m 0.0 (your receiver states no accuracy)
V0_FUTURE = "FIX"           # D: stamp_offset_s 30.0
AGE_FUTURE_S = -29.4       # D: the age_s value v0 reports (s, one decimal)
FROZEN_S = 33             # D: after you stop the receiver, about how many seconds does v0 still say FIX?
EXPLAIN_JUMP = "The new receiver stamps its fixes 5 s behind the clock, so its first fix is stamped before the last trusted fix of the previous receiver: the elapsed time is negative. The gate assumes that stamps only move forward, so it refuses fixes that are really reachable."
#   in A, why is the elapsed time of the jump gate negative, and what does the gate assume about stamps?
EXPLAIN_HOLES = "C and D are wrong. With no accuracy stated v0 still reads sigma 0.0 from the nine zeros and calls it a perfect FIX, because it never looks at the covariance type. With a stamp 30 s in the future the age is negative, so v0 thinks the fix is fresh and keeps it for 33 s after the receiver is dead."       # which of v0's verdicts are wrong, and why does v0 make each mistake?

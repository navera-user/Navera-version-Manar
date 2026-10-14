# Lab 24 — your answers. Numbers without quotes (DRIFT_BARO = 4.2). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Odometer ========

# ---- Step 0: the flight, by hand ---------------------------------------------------------------
SLIDE_PX = 0.0           # how many pixels the ground slides between two frames (20 m apart), from frame 1's
                         # barometer height in flight.csv, HFOV 70°, 320 px — computed by hand, before any code
PREDICT_SEA = ""         # over open water, what will phase correlation say? (the shift, the response)

# ---- Steps 1–2: your FFT against OpenCV ----------------------------------------------------------
MEAN_DIFF_PX = 0.0       # `compare`: the mean |your shift − OpenCV's shift|, px (three decimals)
EXPLAIN_SUBPIXEL = ""    # where does that small difference come from, and what do both methods agree on?

# ---- Steps 3–4: dead reckoning along the first leg ----------------------------------------------
DRIFT_BARO = 0.0         # `leg`: drift, m per 100 m flown (two decimals)
SCALE_RATIO = 0.0        # `leg`: "the truth is k × your step length" — k (three decimals)
HEADING_ERROR_DEG = 0.0  # `leg`: how many degrees your steps point away from the true ones (two decimals)
TRUE_ALT_M = 0.0         # the height that makes the scale right (from SCALE_RATIO and the barometer), metres
DRIFT_TRUE_ALT = 0.0     # `leg --altitude TRUE_ALT_M`: drift, m per 100 m
DRIFT_BOTH = 0.0         # `leg` with both corrections: drift, m per 100 m
EXPLAIN_BIAS = ""        # what were the two causes, and why do they make the error grow with every step?

# ---- Step 5: six odometers ---------------------------------------------------------------------
PREDICT_RACE = ""        # on straight pairs, which odometer will be the most precise, and how many times slower than
                         # your phase correlation will the learned descriptor be?
OK_PHASE_TURN4 = 0       # `odometers`: row turn4, column "phase" — pairs right (of 8)
OK_ORB_FIT_TURN30 = 0    # `odometers`: row turn30, column "ORB fit" — pairs right (of 8)
EXPLAIN_ODOMETERS = ""   # why does phase correlation need the IMU; what do keypoints (and your learned descriptor)
                         # cost; what can no method do?

# ======== Session 2 — Navigator ========

# ---- Step 6: drift, simulated ------------------------------------------------------------------
PREDICT_GROWTH = ""      # on the log-log plot, what will the "both" curve (σ = 0.5 m and bias 0.1 m) look like?
EXPONENT_RANDOM = 0.0    # `python3 drift_sim.py`: the exponent p of "random only" (two decimals)
EXPONENT_BIAS = 0.0      # the exponent p of "bias only"
N_CROSS = 0              # σ = 0.5 m, bias = 0.1 m: after how many steps is the bias part as large as the random part?

# ---- Step 7: when to trust a step ----------------------------------------------------------------
SEA_MAX_RESPONSE = 0.0   # `responses`: the highest response of a wrong step over the water (three decimals)
MIN_RESPONSE = 0.0       # YOUR threshold: steps with a lower response are refused (the runner's `fuse` reads it)
EXPLAIN_THRESHOLD = ""   # why are the steps over the water weak, and what kind of wrong step does a threshold miss?

# ---- Steps 8–9: the gate and the map fixes -------------------------------------------------------
PREDICT_GATE = ""        # before `fuse`: which stage (A–D) will have the largest worst error, and will stage D's 2σ
                         # cover the true error more or less than 86 % of the time?
GATE_REFUSED = 0         # `fuse`: how many steps your gate refused (stage D)
WORST_NO_FIX = 0.0       # `fuse`: stage C, worst error, m
WORST_FUSED = 0.0        # `fuse`: stage D, worst error, m
COVERAGE = 0.0           # `fuse`: stage D, "within 2σ" (0.78 or 78)
EXPLAIN_FUSION = ""      # what does a fix do to the error, where is the worst error, and is the stated σ honest?

# ---- Look back (not graded) ----
LOOK_BACK = ""

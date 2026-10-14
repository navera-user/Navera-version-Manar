# Lab 24 — your answers. Numbers without quotes (DRIFT_BARO = 4.2). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Odometer ========

# ---- Step 0: the flight, by hand ---------------------------------------------------------------
SLIDE_PX = 39.3
PREDICT_SEA = "Over the water nothing stays in place, so I expect a random shift and a very low response."

# ---- Steps 1–2: your FFT against OpenCV ----------------------------------------------------------
MEAN_DIFF_PX = 0.061
EXPLAIN_SUBPIXEL = "Both find the same integer peak; the small difference comes from the sub-pixel refinement: I fit a parabola, OpenCV takes a weighted centroid around the peak."

# ---- Steps 3–4: dead reckoning along the first leg ----------------------------------------------
DRIFT_BARO = 4.63
SCALE_RATIO = 1.032
HEADING_ERROR_DEG = 2.01
TRUE_ALT_M = 120.1
DRIFT_TRUE_ALT = 3.51
DRIFT_BOTH = 0.07
EXPLAIN_BIAS = "The barometer height is 3 % too low, so every step is 3 % too short (a scale error), and the IMU heading is 2 degrees too large, so every step is turned. Both are biases: the same error at every step, so they never cancel and add up linearly."

# ---- Step 5: six odometers ---------------------------------------------------------------------
PREDICT_RACE = "I think the learned descriptor will be the most precise and about 10 times slower than phase correlation."
OK_PHASE_TURN4 = 1
OK_ORB_FIT_TURN30 = 8
EXPLAIN_ODOMETERS = "Phase correlation fails after a turn of only 4 degrees, so the IMU heading change must derotate the frame first; then it is precise and fast. Keypoints survive turns, but they are slower, and my learned descriptor costs much more time for the same precision. Over the sea every method fails."

# ======== Session 2 — Navigator ========

# ---- Step 6: drift, simulated ------------------------------------------------------------------
PREDICT_GROWTH = "It will follow the random line at first and the bias line later, bending from slope one half to slope one."
EXPONENT_RANDOM = 0.5
EXPONENT_BIAS = 1.0
N_CROSS = 25

# ---- Step 7: when to trust a step ----------------------------------------------------------------
SEA_MAX_RESPONSE = 0.03
MIN_RESPONSE = 0.035
EXPLAIN_THRESHOLD = "Over the water the waves move, nothing fixed moves together, so the peak is as low as noise. The threshold cannot catch the overlay steps: the static text box gives a strong peak at zero shift."

# ---- Steps 8–9: the gate and the map fixes -------------------------------------------------------
PREDICT_GATE = "Stage A will be the worst; I think stage D will cover the error less than 86 % of the time."
GATE_REFUSED = 7
WORST_NO_FIX = 52.6
WORST_FUSED = 18.9
COVERAGE = 0.78
EXPLAIN_FUSION = "Each map fix pulls the position back, so the error is a saw-tooth. The worst error is at the end of the long gap over the sea with no fix. Only 78 % within 2 sigma instead of about 86 %, so the stated sigma is a little optimistic: the bias per step is larger than 0.7 m."

# ---- Look back (not graded) ----
LOOK_BACK = ""

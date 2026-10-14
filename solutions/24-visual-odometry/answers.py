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
TURN_LIMIT_DEG = 0.36
PREDICT_RACE = "On the coast ORB will find few corners and fail; phase correlation should still work. My PatchNet was trained within 20 degrees, so I expect fewer matches at 30 degrees."
OK_PHASE_TURN4 = 1
OK_ORB_COAST = 4
LEARNED_IMU_TURN30 = 198
LEARNED_MATCHES_TURN30 = 107
EXPLAIN_ODOMETERS = "Phase correlation breaks after a turn of a few tenths of a degree, so the IMU heading change must derotate the frame first. On the coast it still works because it uses every pixel, while ORB finds only a few corners and its median is noise. My PatchNet is precise but about ten times slower, and without the IMU, past its 20 degree training range, it kept only 107 matches at 30 degrees against 198 on the same frames derotated, about half."

# ======== Session 2 — Navigator ========

# ---- Step 6: drift, simulated ------------------------------------------------------------------
PREDICT_GROWTH = "About 2 % away; with 200 flights about 3 times farther, because the Monte Carlo error goes like one over the square root of the number of flights."
EXPONENT_RANDOM = 0.5
EXPONENT_BIAS = 1.0
N_CROSS = 25

# ---- Step 7: when to trust a step ----------------------------------------------------------------
SEA_MAX_RESPONSE = 0.03
MIN_RESPONSE = 0.035
EXPLAIN_THRESHOLD = "Over the water the waves move, nothing fixed moves together, so the peak is as low as noise. The threshold cannot catch the overlay steps: the static text box gives a strong peak at zero shift. The margin is narrow, only 0.01 between 0.030 and 0.040, so it is not safe alone."

# ---- Steps 8–9: the gate and the map fixes -------------------------------------------------------
PREDICT_GATE = "Stage A will be the worst; I think stage D will cover the error less than 86 % of the time."
GATE_REFUSED = 7
WORST_NO_FIX = 52.6
WORST_FUSED = 18.9
COVERAGE = 0.78
EXPLAIN_FUSION = "Each map fix pulls the position back, so the error is a saw-tooth. The worst error is at the end of the long gap over the sea with no fix. The error leaves the 2 sigma band only at frames 20 to 39, right after the fixes at 20 and 30, which were 7.0 and 6.5 m off with a stated 4 m: unlucky fixes. A larger bias removes only some misses. The frames are correlated, so 78 % on one flight is a hint, not a proof."

# ---- Look back (not graded) ----
LOOK_BACK = ""

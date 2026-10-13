# Lab 8 — your answers. Numbers without quotes (BEST_HEADING_DEG = 12.5). Text in quotes ("…").
# Lists in square brackets: HAND_BLUR = [1.0, 2.0, 3.0]. Tuples in round brackets: LIKE_TRACE = (1.0, 2, 3.0, 4.0).
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Darkroom (pixels, dtypes, filters) ========

# ---- Step 0: the thermal frame ------------------------------------------------------------------
PREDICT_CAST = ""           # before running: thermal16.png holds 16-bit counts from about 7 150 to 8 430.
                            # After t.astype(np.uint8), what will the picture look like? (one or two sentences)

# ---- Step 2: the cast, done right ---------------------------------------------------------------
NAIVE_COLDEST = 0           # the coldest pixel of thermal16.png after .astype(np.uint8)
NAIVE_HOTTEST = 0           # the hottest pixel of thermal16.png after .astype(np.uint8)
EXPLAIN_CAST = ""           # why do these two come out like this, and why does your normalise() not have the problem?

# ---- Steps 3-4: convolution ------------------------------------------------------------------------
HAND_BLUR = []              # by hand: [2, 2, 2, 8, 8, 8] convolved with [1, 2, 1] / 4, border "reflect 101" (6 numbers)
HAND_DERIV = []             # by hand: [2, 2, 2, 8, 8, 8] convolved (true convolution) with [1, 0, -1] (6 numbers)
PREDICT_SPEED = ""          # before `run_images.py filters`: how many times slower than OpenCV will your convolve2d be?
EXPLAIN_FLIP = ""           # what would a correlation (no flip) give with [1, 0, -1] here, and why does the flip
                            # change nothing for the Gaussian?

# ======== Session 2 — Map matcher (geometry, photo to map) ========

# ---- Step 5: the affine matrix by hand -------------------------------------------------------------
CORNER_UV = None            # where does the pixel (0, 0) go with affine_matrix(-90.0, 0.5, (40.0, 30.0))? (u, v)

# ---- Step 7: the photo made like the map -----------------------------------------------------------
LIKE_TRACE = None           # by hand, BEFORE coding: (s, side, dx, dy) for the lab photo; s to 3 decimals,
                            # (dx, dy) = c_out − c_in, the column you add to M
PREDICT_NCC = ""            # before `like`: roughly what NCC for the raw photo, and for like_map at the compass heading?
NCC_COMPASS = 0.0           # NCC of your like_map with the compass heading of info.json

# ---- Step 8: the heading sweep ---------------------------------------------------------------------
PREDICT_SWEEP = ""          # before the sweep: at which heading will the NCC peak, and how fast will it fall?
BEST_HEADING_DEG = 0.0      # the heading with the highest NCC, to 0.1° (refine with sweep FROM TO STEP)
COMPASS_ERROR_DEG = 0.0     # true heading − compass heading (degrees, with its sign)
HEADING_TOL_DEG = 0.0       # how far (±, degrees) from the best heading does the NCC stay at 0.9 or more?
EXPLAIN_SWEEP = ""          # what does the sweep say about the heading accuracy a pixel comparison needs?
                            # what could a system do when its compass is not that good?

# ---- Step 8b: heading or scale? ------------------------------------------------------------------------
SCALE_TOL_PCT = 0.0         # at your best heading: how many % either side of 0.60 m/px does the NCC stay ≥ 0.9?
EXPLAIN_SCALE = ""          # which costs more here, a 5 % scale error or a 5° heading error? which sensor sets each?

# ---- Look back (not graded) -------------------------------------------------------------------------
LOOK_BACK = ""

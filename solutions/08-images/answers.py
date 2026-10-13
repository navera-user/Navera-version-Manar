# Lab 8 — your answers. Numbers without quotes (BEST_HEADING_DEG = 12.5). Text in quotes ("…").
# Lists in square brackets: HAND_BLUR = [1.0, 2.0, 3.0]. Tuples in round brackets: LIKE_TRACE = (1.0, 2, 3.0, 4.0).
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Darkroom (pixels, dtypes, filters) ========

# ---- Step 0: the thermal frame ------------------------------------------------------------------
PREDICT_CAST = "I think it will be very dark or noisy, because 7000 does not fit in a byte."           # before running: thermal16.png holds 16-bit counts from about 7 150 to 8 430.
                            # After t.astype(np.uint8), what will the picture look like? (one or two sentences)

# ---- Step 2: the cast, done right ---------------------------------------------------------------
NAIVE_COLDEST = 238           # the coldest pixel of thermal16.png after .astype(np.uint8)
NAIVE_HOTTEST = 238           # the hottest pixel of thermal16.png after .astype(np.uint8)
EXPLAIN_CAST = "astype keeps only the value modulo 256: 7150 and 8430 differ by 1280 = 5 x 256, so both wrap to 238 and the picture shows 5 bands of contours. normalise maps the min to 0 and the max to 255 in float first, so nothing wraps."           # why do these two come out like this, and why does your normalise() not have the problem?

# ---- Steps 3-4: convolution ------------------------------------------------------------------------
HAND_BLUR = [2.0, 2.0, 3.5, 6.5, 8.0, 8.0]              # by hand: [2, 2, 2, 8, 8, 8] convolved with [1, 2, 1] / 4, border "reflect 101" (6 numbers)
HAND_DERIV = [0.0, 0.0, 6.0, 6.0, 0.0, 0.0]             # by hand: [2, 2, 2, 8, 8, 8] convolved (true convolution) with [1, 0, -1] (6 numbers)
PREDICT_SPEED = "about 10 times slower"          # before `run_images.py filters`: how many times slower than OpenCV will your convolve2d be?
EXPLAIN_FLIP = "A correlation reads img(x - 1) - img(x + 1), so every sign is reversed: [0, 0, -6, -6, 0, 0]. The Gaussian kernel is symmetric, so flipping it gives the same kernel and the same result."           # what would a correlation (no flip) give with [1, 0, -1] here, and why does the flip
                            # change nothing for the Gaussian?

# ======== Session 2 — Map matcher (geometry, photo to map) ========

# ---- Step 5: the affine matrix by hand -------------------------------------------------------------
CORNER_UV = (55.0, 10.0)      # where does the pixel (0, 0) go with affine_matrix(-90.0, 0.5, (40.0, 30.0))? (u, v)

# ---- Step 7: the photo made like the map -----------------------------------------------------------
LIKE_TRACE = (0.620, 496, -72.0, 8.0)   # by hand, BEFORE coding: (s, side, dx, dy) for the lab photo; s to 3 decimals,
                            # (dx, dy) = c_out − c_in, the column you add to M
PREDICT_NCC = "raw photo near 0, like_map at the compass heading maybe 0.8"      # before `like`: roughly what NCC for the raw photo, and for like_map at the compass heading?
NCC_COMPASS = 0.746           # NCC of your like_map with the compass heading of info.json

# ---- Step 8: the heading sweep ---------------------------------------------------------------------
PREDICT_SWEEP = "near 31 degrees, falling slowly over about 10 degrees"          # before the sweep: at which heading will the NCC peak, and how fast will it fall?
BEST_HEADING_DEG = 35.0      # the heading with the highest NCC, to 0.1° (refine with sweep FROM TO STEP)
COMPASS_ERROR_DEG = 4.0     # true heading − compass heading (degrees, with its sign)
HEADING_TOL_DEG = 1.5       # how far (±, degrees) from the best heading does the NCC stay at 0.9 or more?
EXPLAIN_SWEEP = "The NCC falls from 0.965 to 0.746 with only 4 degrees of heading error and stays above 0.9 only within about 1.5 degrees, so a pixel comparison needs the heading to about a degree. With a worse compass, a system can search over headings (a sweep like this one) or use a matching method that estimates the rotation itself, such as features."          # what does the sweep say about the heading accuracy a pixel comparison needs?
                            # what could a system do when its compass is not that good?

# ---- Step 8b: heading or scale? ------------------------------------------------------------------------
SCALE_TOL_PCT = 2.3         # at your best heading: how many % either side of 0.60 m/px does the NCC stay ≥ 0.9?
EXPLAIN_SCALE = "A 5 % scale error (0.57 or 0.63 m/px) still gives NCC 0.80-0.82, but a 5 degree heading error gives only 0.69, so here the heading matters more. The scale comes from the height above ground and the lens, the heading from the compass or IMU."          # which costs more here, a 5 % scale error or a 5° heading error? which sensor sets each?

# ---- Look back (not graded) -------------------------------------------------------------------------
LOOK_BACK = ""

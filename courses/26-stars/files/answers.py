# Lab 26 — your answers. Numbers without quotes (N_VOTE_STARS = 12). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Stargazer (the clock and the sky) ========

# ---- Step 0: before reading anything --------------------------------------------------------------------
PREDICT_SIDEREAL = ""       # a star is due south at 21:00 tonight. Tomorrow: 21:00, a little earlier or later? why?

# ---- Step 1: the catalogue ---------------------------------------------------------------------------------
N_VOTE_STARS = 0            # how many catalogue stars have vmag ≤ 4.5?

# ---- Step 2: the clock of the sky (python3 run_stars.py clock) ----------------------------------------------
TRANSIT_SHIFT_S = 0.0       # by how many seconds does Vega's transit come earlier the next night?
VEGA_SHIFT_ARCMIN = 0.0     # how far precession moved Vega since J2000 (arcminutes, ′)
VEGA_SHIFT_KM = 0.0         # that angle as a distance on the Earth (km)
EXPLAIN_SIDEREAL = ""       # why does the sky's clock gain on yours, and why does it matter for a star fix?

# ---- Step 3: the sky over Cape Town (python3 run_stars.py sky capetown) --------------------------------------
ACHERNAR_ALT_DEG = 0.0      # Achernar's altitude (degrees)
ACHERNAR_AZ_DEG = 0.0       # Achernar's azimuth (degrees)
POLARIS_CAPE_ALT_DEG = 0.0  # Polaris' altitude seen from Cape Town (degrees, with its sign)

# ---- Step 4: latitude from Polaris (python3 run_stars.py polaris) -------------------------------------------
PREDICT_POLARIS = ""        # before running: with the correction, which place keeps the largest error? why?
NAIVE_MAX_ERR_KM = 0.0      # the largest error of "latitude = altitude of Polaris" (km, all places)
CORRECTED_MAX_ERR_KM = 0.0  # the largest error with the hour-angle correction (km, all places)
EXPLAIN_POLARIS = ""        # why is the naive error about that size? what does the correction remove? why is the
                            # corrected error largest where it is?

# ======== Session 2 — Star navigator (a fix from a photo) ========

# ---- Step 5: find the stars (python3 run_stars.py detect, detect 2) -----------------------------------------
PREDICT_DETECT = ""         # before running: how many of the 125 stars brighter than 5.0 will you find, and how
                            # many of the 40 hot pixels will you report as stars? why?
N_STARS_01 = 0              # how many stars your detector finds in photo 1
CENTROID_RMS_PX = 0.0       # the RMS centre error against the truth (pixels)
EXPLAIN_CENTROID = ""       # why weight the centre by brightness? why do the size limits and the local background
                            # matter (photo 2)?

# ---- Step 6: which stars are these? (python3 run_stars.py solve) --------------------------------------------
SOLVE_RMS_ARCSEC = 0.0      # the plate solve's fit residual (″)
PIXEL_ARCMIN = 0.0          # one pixel at the image centre, on the sky (′)
PIXEL_KM = 0.0              # that angle as a distance on the Earth (km)

# ---- Step 8: two roots, one prior (python3 run_stars.py fix / fix truth / fix magnetic / fix oneroot) -------
TRACE_PSI_DEG = 0.0         # by hand, before coding TODO 7: ψ for the docstring example (degrees)
MEDIAN_FIX_KM = 0.0         # fix: the median error with the IMU (km)
NO_FIX_PHOTO = 0            # fix: the photo number that gives no position
PERFECT_MAX_KM = 0.0        # fix truth: the largest error with a perfect attitude (km)
PREDICT_MAGNETIC = ""       # before "fix magnetic": how many km does forgetting the declination (≈ +3.3°) move photo 1's fix?
MAGNETIC_ERR_01_KM = 0.0    # fix magnetic: photo 1's error (km)
ONE_ROOT_ERR_03_KM = 0.0    # fix oneroot: photo 3's error (km)
EXPLAIN_ROOTS = ""          # why can one direction give two places? why is the asin root wrong for photo 3? why does
                            # photo 6 give no position?
EXPLAIN_NORTH = ""          # why does forgetting the declination move photo 1 so far? why do photos 3–5 then give
                            # no position at all?

# ---- Step 9: the error budget (python3 run_stars.py budget) -------------------------------------------------
PREDICT_BUDGET = ""         # before running: measured RMS close to your formula, above, or below? and the median?
FORMULA_KM = 0.0            # your error_km for photo 1 (km)
MC_RMS_KM = 0.0             # the measured RMS error (km)
MC_MEDIAN_KM = 0.0          # the measured median error (km)
MOUNT_BIAS_MAX_DEG = 0.0    # the largest fixed tilt (perfect IMU) that keeps the fix within 55 km (degrees)
EXPLAIN_BUDGET = ""         # which term dominates for photo 1? why is the median smaller than the RMS? why do the
                            # formula and the simulation differ?

# ---- Step 11: look back (not graded; for you and your teacher) ---------------------------------------------
LOOK_BACK = ""

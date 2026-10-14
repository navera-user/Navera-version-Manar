# Lab 28 — your answers. Numbers without quotes (SIGMA_40S_M = 12.3). Text in quotes ("…"). True / False without quotes.
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Height keeper ========

# ---- Step 0: before reading anything ---------------------------------------------------------------------
PREDICT_GROW = "Clearly more: the velocity error alone makes 40 m, and the random accelerations add more on top."           # σ 3 m and 1 m/s, then 40 s without a fix: σ of the position about 43 m, clearly less,
                            # or clearly more? why?

# ---- Step 1: the prediction (python3 run_kalman.py grow) -----------------------------------------------------
SIGMA_40S_M = 89.49           # σ of the position after 40 s (m)
EXPLAIN_GROW = "The velocity error multiplies time (1 m/s × 40 s = 40 m), and the random accelerations of q make the velocity error itself grow, so the position variance grows like t cubed: 89 m instead of 43 m."           # why does σ grow faster than a straight line? which two things add up?

# ---- Step 2: the update, by hand first (then python3 run_kalman.py step) -------------------------------------
TRACE_HEIGHT_M = 124.8        # the height after the update (m)
TRACE_CLIMB_MPS = 1.2       # the climb rate after the update (m/s)
TRACE_SIGMA_M = 1.789         # σ of the height after the update (m)

# ---- Step 3: the race (python3 run_kalman.py race) ------------------------------------------------------------
RACE_RMSE_RAW_M = 2.789       # RMS error of the raw heights against the truth (m)
RACE_RMSE_FILTER_M = 1.832    # RMS error of your filter against the truth (m)

# ---- Step 4: what q means (python3 run_kalman.py heights 0.05 / 5 / 0.5) --------------------------------------
PREDICT_Q = "0.05 will be worse: it cannot follow the climb, maybe even worse than the raw heights."              # before running: 0.05 or 5, which has the larger RMS error? will one do worse than the
                            # raw heights? why?
RMSE_CA_005_M = 3.098         # RMS error, whole flight, climb_accel 0.05 (m)
RMSE_CA_5_M = 2.510           # RMS error, whole flight, climb_accel 5 (m)
EXPLAIN_Q = "With 0.05 the model allows almost no climb acceleration, so in the climb the filter lags several metres behind (worse than the raw heights) while it states a small sigma because it trusts its model: overconfident. With 5 it believes every measurement and follows the noise in level flight."              # what goes wrong with each, where in the flight, and why does the smallest value state
                            # the smallest σ while being the most wrong?

# ======== Session 2 — Tracker ========

# ---- Step 5: honesty (python3 band_sim.py) --------------------------------------------------------------------
PREDICT_BAND = "Maybe 1.5 to 2.5."           # before running: the mean NEES of an honest 2-D filter over 361 s: between which two
                            # numbers in 95 % of flights?
BAND_LOW = 1.80              # the band for n = 2, N = 361, p = 0.95 (two decimals)
BAND_HIGH = 2.21

# ---- Step 6: the tracker (python3 run_kalman.py track 0.3) ------------------------------------------------------
NEES_NO_GATE = 16.48          # the mean NEES without a gate
SIGMA_END_JAM_M = 91.7       # σ east at the end of the jam (m)
ERR_END_JAM_M = 103.2         # the true error at the end of the jam (m)

# ---- Step 7: the gate (python3 run_kalman.py track 0.3 0.99) -----------------------------------------------------
PREDICT_GATE = "All 6 wrong ones, about 3 good ones (1 %), and the NEES comes close to 2."           # before running: wrong fixes refused (of 6)? good fixes refused (of 315)? the NEES?
NEES_GATE = 2.07             # the mean NEES with the 99 % gate
WRONG_REFUSED = 6           # wrong fixes refused
GOOD_REFUSED = 5            # good fixes refused
D2_AFTER_JAM = 1.40          # d² of the first fix after the jam
EXPLAIN_GATE = "A 99 % gate refuses 1 % of honest fixes by definition: about 3 of 315, we got 5, which is chance. Without the gate each wrong fix 80 to 200 m away is believed, pulls the estimate far off while P stays small, so err transpose P inverse err is huge for several seconds."           # why were a few good fixes refused (about what a 99 % gate should refuse?), and why did
                            # the wrong fixes raise the NEES so much without the gate?
JUDGE_D2 = 2.67              # by hand: a fix 150 m north of the prediction at the end of the jam (σ 5 m): its d²
JUDGE_ACCEPT = True         # True or False: does the 99 % gate accept it?

# ---- Step 8: the tuner (python3 run_kalman.py sweep) ---------------------------------------------------------------
Q_BEST = 0.3                # the q you would fly (m²/s⁴)
EXPLAIN_TUNE = "With q 0.01 and 0.03 the sigma stayed small during the jam while the true error grew, so the first fix after the jam was too far for the gate and refused, then the next ones even farther: the filter locked out and lost the track. q 0.1 has a mean NEES of 3.2, above the band: overconfident, so it is not honest even if its error is small; 0.3 is inside the band with the smallest error."           # what happened to q = 0.01 and 0.03 after the jam, step by step? why not q = 0.1?

# ---- Step 10: look back (not graded) ---------------------------------------------------------------------------------
LOOK_BACK = ""

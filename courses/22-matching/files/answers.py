# Lab 22 — your answers. Numbers without quotes (KEPT_08 = 312). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.
# DECISIONS (session 2): your choices for NAVERA Lite's matcher. The check measures them on scenes you never saw.

# ======== Session 1 — Geometer ========

# ---- Step 0: look before you match (no code) ------------------------------------------------------
PREDICT_HARDEST = ""     # which of the eight pairs will be the hardest to match correctly, and why?

# ---- Step 1: the ratio test ------------------------------------------------------------------------------
PRECISION_NONE = 0.0     # from `ratio city`: the precision with no ratio test (three decimals)
KEPT_08 = 0              # pairs kept by your ratio test at 0.8
PRECISION_08 = 0.0       # and their precision (three decimals)
EXPLAIN_RATIO = ""       # why does comparing with the SECOND-nearest throw out wrong pairs?

# ---- Steps 2–3: similarity and homography -------------------------------------------------------------
RESID_SIM_TILT = 0.0     # from `fit`: median residual (px) of YOUR similarity on city_tilt (two decimals)
RESID_H_TILT = 0.0       # median residual (px) of YOUR homography on city_tilt
EXPLAIN_DOF = ""         # why can the similarity not fit the tilted photo, and what does the homography cost?

# ---- Step 4: how many samples? ---------------------------------------------------------------------------
ITERS_SIM_W02 = 0        # from `iters`: w = 0.2, s = 2
ITERS_H_W02 = 0          # w = 0.2, s = 4

# ---- Step 5: RANSAC ----------------------------------------------------------------------------------------
PREDICT_RANSAC_MIN = ""     # before `ransac`: with only the samples ransac_iterations asks for (w = 0.91: 4 for a
                            # homography), will your homography RANSAC put the photo's centre within 5 m of the truth?
CENTRE_ERR_SIM_TILT = 0.0   # from `ransac city_tilt`: centre error (m) of YOUR similarity RANSAC (one decimal)
CENTRE_ERR_H_TILT = 0.0     # and of YOUR homography RANSAC

# ---- Step 6: the gates ---------------------------------------------------------------------------------------
PREDICT_GATES = ""       # before you run `gates`: which pairs will your gates refuse, and why?
REASON_WRONG_PLACE = ""  # your gates' reason for wrong_place (the exact words, e.g. "too few inliers")
REASON_HILLS = ""        # your gates' reason for hills
PROTOTYPE_WRONG = ""     # the pair that the prototype rule (≥ 12 inliers, no scale check) accepts at another place
EXPLAIN_GATES = ""       # what does the scale gate cost (look at hills), and why does NAVERA keep it anyway?

# ======== Session 2 — Learned matcher ========

# ---- Step 8: your network as a matcher ----------------------------------------------------------------------
PAIRS_SIFT_SHAKEN = 0       # from `learned olives_shaken`: the pairs SIFT finds (the 'pairs' column)
PAIRS_LEARNED_SHAKEN = 0    # the pairs your network finds

# ---- Step 9: DECISION — your network's threshold -------------------------------------------------------------
LEARNED_RATIO = None     # DECISION (Step 9): your network's ratio (0 < r ≤ 1), from YOUR curve tables
LEARNED_MAX_DIST = None  # DECISION: None (no distance cut), or a descriptor distance d: keep a pair only if dist < d
EXPLAIN_THRESHOLD = ""   # justify it with numbers of `curve` (precision, right pairs kept), against SIFT's 0.8

# ---- Step 10: DECISION — where your network can be trusted -------------------------------------------------------
PREDICT_ENVELOPE = ""    # before `envelope`: up to what heading error will your network work, and why?
NETWORK_MAX_ERR_DEG = None  # from `envelope`: the heading ERROR printed under table A (degrees)
HEADING_LIMIT_DEG = None    # DECISION (Step 10): the network is used only when the heading prior's σ is ≤ this (degrees)
EXPLAIN_ENVELOPE = ""    # where does your network beat SIFT, where does it fail, and what in its training explains both?

# ---- Step 11: your matcher's policy ----------------------------------------------------------------------------------
EXPLAIN_POLICY = ""      # your match_photo: which matcher first, when the other, and what makes it refuse

# ---- Look back (not graded) ----
LOOK_BACK = ""

# Lab 22 — your answers. Numbers without quotes (KEPT_08 = 312). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.
# DECISIONS (session 2): your choices for NAVERA Lite's matcher. The check measures them on scenes you never saw.

# ======== Session 1 — Geometer ========

# ---- Step 0: look before you match (no code) ------------------------------------------------------
PREDICT_HARDEST = "The sea: there is nothing to match. Then the shaken olives: every tree looks the same."     # which of the eight pairs will be the hardest to match correctly, and why?

# ---- Step 1: the ratio test ------------------------------------------------------------------------------
PRECISION_NONE = 0.365     # from `ratio city`: the precision with no ratio test (three decimals)
KEPT_08 = 571              # pairs kept by your ratio test at 0.8
PRECISION_08 = 0.935       # and their precision (three decimals)
EXPLAIN_RATIO = "When the second-nearest descriptor is almost as close as the nearest, the point looks like two places of the photo: the pair is ambiguous and is often wrong. A clear gap means a distinct point; the ratio test keeps only those and precision goes from 0.365 to 0.935."       # why does comparing with the SECOND-nearest throw out wrong pairs?

# ---- Steps 2–3: similarity and homography -------------------------------------------------------------
RESID_SIM_TILT = 7.74     # from `fit`: median residual (px) of YOUR similarity on city_tilt (two decimals)
RESID_H_TILT = 0.19       # median residual (px) of YOUR homography on city_tilt
EXPLAIN_DOF = "The tilted camera sees the ground in perspective: the far side is smaller than the near side, a trapezoid that no similarity (one scale, one turn) can make. The homography has 8 degrees of freedom and fits it, but it needs samples of 4 points, so many more RANSAC iterations (567 instead of 49 at w = 0.3)."         # why can the similarity not fit the tilted photo, and what does the homography cost?

# ---- Step 4: how many samples? ---------------------------------------------------------------------------
PREDICT_ITERS = "about 1000"       # before you run `iters`: with w = 0.2, how many samples for a homography? (a guess)
ITERS_SIM_W02 = 113        # from `iters`: w = 0.2, s = 2
ITERS_H_W02 = 2876          # w = 0.2, s = 4

# ---- Step 5: RANSAC ----------------------------------------------------------------------------------------
CENTRE_ERR_SIM_TILT = 1.91   # from `ransac city_tilt`: centre error (m) of YOUR similarity RANSAC (one decimal)
CENTRE_ERR_H_TILT = 0.21     # and of YOUR homography RANSAC

# ---- Step 6: the gates ---------------------------------------------------------------------------------------
PREDICT_GATES = "The sea (no features) and the wrong place; maybe the shaken olives."       # before you run `gates`: which pairs will your gates refuse, and why?
REASON_WRONG_PLACE = "scale off"  # your gates' reason for wrong_place (the exact words, e.g. "too few inliers")
REASON_HILLS = "scale off"        # your gates' reason for hills
PROTOTYPE_WRONG = "wrong_place"     # the pair that the prototype rule (≥ 12 inliers, no scale check) accepts at another place
EXPLAIN_GATES = "On hills the altitude is wrong, so the scale gate refuses a right match: we lose availability. NAVERA keeps the gate because a wrong place almost never matches at the right scale: a refused right match costs one frame, an accepted wrong one (1 097 m in the prototype) can send the drone away."       # what does the scale gate cost (look at hills), and why does NAVERA keep it anyway?

# ======== Session 2 — Learned matcher ========

# ---- Step 8: your network as a matcher ----------------------------------------------------------------------
PAIRS_SIFT_SHAKEN = 2       # from `learned olives_shaken`: the pairs SIFT finds (the 'pairs' column)
PAIRS_LEARNED_SHAKEN = 47    # the pairs your network finds

# ---- Step 9: DECISION — your network's threshold -------------------------------------------------------------
LEARNED_RATIO = 0.7      # DECISION: the ratio test of your network (a number, 0 < r ≤ 1)
LEARNED_MAX_DIST = None  # DECISION: None (no distance cut), or a descriptor distance d: keep a pair only if dist < d
EXPLAIN_THRESHOLD = "On the curve table my network at 0.8 keeps 1672 pairs with precision 0.843, worse than SIFT at 0.8 (0.867). At 0.7 the precision is 0.946 and it still keeps 1361 right pairs, only 3.5 % fewer than at 0.8, so I chose 0.7: fewer wrong pairs for RANSAC for almost no loss."   # justify it with numbers of `curve` (precision, right pairs kept), against SIFT's 0.8

# ---- Step 10: DECISION — where your network can be trusted -------------------------------------------------------
PREDICT_ENVELOPE = "It was trained with turns up to ±20°, so it should fail beyond about 20–30°."    # before `envelope`: up to what heading error will your network work, and why?
HEADING_LIMIT_DEG = 20   # DECISION: your matcher uses the network only when the heading prior's σ is ≤ this (degrees)
EXPLAIN_ENVELOPE = "My network works up to a 20° heading error on both places, at 30° only on the city (11 inliers) and never beyond, because it was trained only on pairs turned by ±20° and has no orientation of its own. It beats SIFT on shaken olives (31 against 3 inliers at shake13) because its training data had blur and noise. A zoom error above 15 % is refused by the scale gate for both."    # where does your network beat SIFT, where does it fail, and what in its training explains both?

# ---- Step 11: your matcher's policy ----------------------------------------------------------------------------------
EXPLAIN_POLICY = "SIFT first, because it needs no prior and gives the most inliers on sharp photos. If the gates refuse it and the heading prior is known with sigma at most 20°, my network on the upright photo. Each attempt must pass my gates with the prior zoom, otherwise the matcher refuses."      # your match_photo: which matcher first, when the other, and what makes it refuse

# ---- Look back (not graded) ----
LOOK_BACK = ""

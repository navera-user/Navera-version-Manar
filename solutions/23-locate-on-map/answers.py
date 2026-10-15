# Lab 23 — your answers. Numbers without quotes (MED_DINO = 187.0). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Finder ========

# ---- Step 0: look (no code) ---------------------------------------------------------------------
PREDICT_LOOK = ("It covers parts of about four tiles; comparing with whole tiles can find the one holding the centre, "
                "but its centre can be up to about 175 m from the truth.")

# ---- Step 2: DINOv2's input ---------------------------------------------------------------------
N_PATCHES = 256

# ---- Step 4: retrieval against the baselines (σ 200 m priors) -------------------------------------
PREDICT_DINO = "Better than NAVERA's, because the photos are drawn in the map's own style: maybe 100 m better than the prior."
MED_DINO = 181.0
MED_PRIOR = 246.0
MED_RANDOM = 457.0
MED_BEST = 103.0
P90_DINO = 559.0
P90_PRIOR = 442.0
EXPLAIN_BASELINE = ("DINOv2 beat staying at the prior by about 65 m on the median and the random tile by about 275 m, but "
                    "its p90 is worse than the prior's (559 vs 442 m): when it is wrong it is far wrong. Even the best tile is about 100 m away "
                    "because a tile is 248 m wide and its centre is not the photo's centre: a tile-level answer has a "
                    "resolution limit.")

# ---- Step 5: a worse prior --------------------------------------------------------------------------
MED_DINO_800 = 559.0
MED_PRIOR_800 = 816.0
EXPLAIN_SIGMA = ("With σ 800 m the prior is about 800 m off but retrieval still picks a tile near the truth, so it is "
                 "worth running when σ is large; with σ 200 m the prior is already almost as good as the best guess "
                 "retrieval can make.")

# ---- Step 6: failures ------------------------------------------------------------------------------
WORST_TERRAIN = "sea"
EXPLAIN_SCORE = ("No: the similarity of a wrong top tile is often as high as that of a right one, the two ranges "
                 "overlap. A drone must not trust the score; an independent check like the fine step's gates must "
                 "accept or refuse the candidate.")

# ---- Steps 7–9: your own network ------------------------------------------------------------------
EXPLAIN_PAIRS = ("A real photo is taken anywhere inside a tile, so the view is offset from the tile's centre; the black "
                 "corners, blur, clouds and light changes are what real photos have, so the network learns to ignore "
                 "them (augmentation).")
N_PARAMS = 257344
MED_MINE_400 = 215.0
MED_DINO_400 = 240.0

# ---- Step 10: one experiment -----------------------------------------------------------------------
PREDICT_EXPERIMENT = ("no-augment > shift 0 > n-train 2000 > tau 0.5: without augmentation the real photos have effects "
                      "it never saw; tau only changes how hard impostors count. I train --no-augment.")
EXP_MEDIAN = 813.0
EXPLAIN_EXPERIMENT = ("Without augmentation the median went from 215.0 m to 813.0 m, because the network "
                      "never saw black corners, blur or light changes in training, so it did not learn to ignore them "
                      "and real photos looked unlike every tile. The class table: n-train 2000 555 m, shift 0 483 m, "
                      "tau 0.5 473 m — fewer pairs hurt more than I guessed.")

# ---- Step 11: speed ----------------------------------------------------------------------------------
MS_DINO = 1319.0
MS_MINE = 7.5
EXPLAIN_CHOICE = ("TileNet: on these drawn maps it was more accurate (lower median) than DINOv2 and it is about a "
                  "hundred times faster on the CPU with far fewer parameters, which matters on a Jetson shared with "
                  "the camera and the rest of the stack.")

# ======== Session 2 — Locator ========

# ---- Step 13: the fine step ---------------------------------------------------------------------------
LOCAL_ERR_P02 = 3.0

# ---- Step 14: your decision -------------------------------------------------------------------------------
PREDICT_SWEEP = "Up to about 300 m the fine step alone should be fine."
DIRECT_MAX_R_M = 300.0
EXPLAIN_DECISION = ("Up to 150-300 m the fine step alone gave about as many positions (11/20 and 9/20 against 10/20 and 11/20) with 0 wrong and less time; at 600 m it gave only 7/20 against 13/20 for retrieval and took 1.9 s per photo, and at 1 200 m the patch is too large (0/20). So 300 m.")

# ---- Step 15: the error budget ------------------------------------------------------------------------------
BUDGET_TOTAL = 5.16

# ---- Step 16: the whole chain ---------------------------------------------------------------------------------
FINAL_AVAIL = 0.61
FINAL_MEDIAN = 3.6
FINAL_P90 = 7.6
FINAL_WRONG = 0
EXPLAIN_REFUSED = ("p01 is open sea: 0 inliers (min 6), gate 1 refused it. Refusing was right: every piece of sea looks "
                   "the same, so any position would be a guess, and a wrong position is worse than no fix.")

# ---- Look back (not graded) ----
LOOK_BACK = ""

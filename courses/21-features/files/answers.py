# Lab 21 — your answers. Numbers without quotes (REP_SIFT_ZOOM4 = 0.71). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Scout & detector ========

# ---- Step 0: the scout (no code) ---------------------------------------------------------------
PREDICT_RANK = ""        # the six terrains, from the MOST keypoints to the fewest, and the one you would trust most
                         # to be found on a map (look at out/… only after you wrote this: see the lab)

# ---- Steps 2–3: the house ---------------------------------------------------------------------
KIND_1 = ""              # "flat", "edge" or "corner" (from YOUR eigen2 and harris on the printed Sxx, Syy, Sxy)
KIND_2 = ""
KIND_3 = ""
R_POINT_3 = 0.0          # the Harris response R (k = 0.04) of point 3, computed from its Sxx, Syy, Sxy (no decimals)
EXPLAIN_EIGEN = ""       # what do the two eigenvalues say about a window, and why does Harris not compute them?

# ---- Step 4: repeatability ----------------------------------------------------------------------
PREDICT_ZOOM = ""        # which detector will suffer most when the photo is 4 times closer, and why?
REP_HARRIS_ROT35 = 0.0   # from `repeat`, two decimals
REP_HARRIS_ZOOM4 = 0.0
REP_SIFT_ZOOM4 = 0.0
CHANCE = 0.0             # the chance level of the table (all rows show the same)
WORST_ZOOM4 = ""         # "harris", "orb" or "sift": the worst detector on city_zoom4
EXPLAIN_SCALE = ""       # why does Harris survive the turn but not the 4× zoom, while SIFT survives both?

# ---- Step 5: terrains ----------------------------------------------------------------------------
MOST_KEYPOINTS = ""      # the terrain with the most SIFT keypoints (OpenCV's default contrast)
SIFT_FIELDS = 0          # SIFT keypoints of terrain_fields.png (default contrast)
DARK_SIFT_BEFORE = 0     # drone_city_dark.jpg: SIFT keypoints before CLAHE
DARK_SIFT_AFTER = 0      #                      and after CLAHE
EXPLAIN_TERRAIN = ""     # which terrain fooled your Step 0 ranking, and why many keypoints do not mean easy matching

# ======== Session 2 — Learner ========

# ---- Step 6: binary descriptors -----------------------------------------------------------------
HAMMING_SAME = 0         # median Hamming distance, same ground point (from `hamming`)
HAMMING_RANDOM = 0       # median Hamming distance, random pairs
EXPLAIN_HAMMING = ""     # why is the random median close to 128, and what does the gap allow?

# ---- Step 7: the training data ------------------------------------------------------------------
PREDICT_HARD = ""        # in out/patches.png: which pairs will be hardest for a descriptor, and why?

# ---- Step 8: the network ----------------------------------------------------------------------------
PREDICT_PARAMS = ""      # BEFORE you work it out: how many numbers will PatchNet learn? (a guess)
N_PARAMS = 0             # the parameters of the whole PatchNet, worked out by hand from the rule (weights + biases)

# ---- Steps 10–11: training, filters, overfitting ------------------------------------------------------
VAL_SCORE_FULL = 0.0     # the matching score printed after your full training of my_desc.pt (three decimals)
EXPLAIN_FILTERS = ""     # out/filters.png: what pattern do many trained filters show that random ones do not, and why
                         # would it help to recognise a ground point?
PREDICT_OVERFIT = ""     # with only 300 training pairs and 30 epochs: what will the two loss curves do?
EXPLAIN_OVERFIT = ""     # what happened to the train and validation losses with 300 pairs, and why?

# ---- Step 12: learned vs OpenCV --------------------------------------------------------------------
SCORE_ORB = 0.0          # from `compare`, three decimals
SCORE_SIFT = 0.0
SCORE_UNTRAINED = 0.0
SCORE_LEARNED = 0.0
EXPLAIN_BASELINES = ""   # raw pixels score almost as well as ORB, and the untrained network worse than raw pixels: why?
EXPLAIN_LEARNED = ""     # why does your network win here, what do its failures (out/failures.png) have in common, and
                         # what would you need before trusting it on a real drone?

# ---- Step 13: your experiment (ONE change) -----------------------------------------------------------
EXPERIMENT = ""          # "margin", "batch", "pairs" or "negatives"
PREDICT_EXPERIMENT = ""  # BEFORE you run it: will the score go up, down or stay, and why?
EXP_SCORE = 0.0          # the matching score of exp.pt (three decimals, from the end of its training)
EXPLAIN_EXPERIMENT = ""  # what happened compared with my_desc.pt, and what it tells you about that setting

# ---- Look back (not graded) ----
LOOK_BACK = ""

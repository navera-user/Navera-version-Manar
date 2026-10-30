# Lab 23 — your answers. Numbers without quotes (MED_DINO = 187.0). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Finder ========

# ---- Step 0: look (no code) ---------------------------------------------------------------------
PREDICT_LOOK = ""        # the photo covers how many of the 9 tiles? Will "compare the view with whole tiles" find
                         # the right one, and how far from the truth can a tile's centre be?

# ---- Step 2: DINOv2's input ---------------------------------------------------------------------
N_PATCHES = 0            # how many 14 × 14 patches does DINOv2 cut from one 224 × 224 picture?

# ---- Step 4: retrieval against the baselines (σ 200 m priors) -------------------------------------
PREDICT_DINO = ""        # before `retrieve`: will DINOv2's top tile beat "stay at the prior"? By how much?
MED_DINO = 0.0           # median errors from `retrieve` (metres, no decimals)
MED_PRIOR = 0.0
MED_RANDOM = 0.0
MED_BEST = 0.0
P90_DINO = 0.0           # the p90 column: DINOv2's and the prior's
P90_PRIOR = 0.0
EXPLAIN_BASELINE = ""    # did DINOv2 beat the prior on the median? and on the p90? Why is the BEST tile not 0 m away?

# ---- Step 5: a worse prior --------------------------------------------------------------------------
MED_DINO_800 = 0.0       # `retrieve --sigma 800`: DINOv2's median, and the prior's
MED_PRIOR_800 = 0.0
EXPLAIN_SIGMA = ""       # when is retrieval worth running, and when is the prior already as good?

# ---- Step 6: failures ------------------------------------------------------------------------------
WORST_TERRAIN = ""       # "textured", "sparse" or "sea": where retrieval fails most
EXPLAIN_SCORE = ""       # can the similarity of the top tile tell you that it is the wrong tile? What does that mean
                         # for a drone that must not trust a wrong position?

# ---- Steps 7–9: your own network ------------------------------------------------------------------
EXPLAIN_PAIRS = ""       # look at out/pairs.png: why is a view NOT centred on its tile, and why are the black corners,
                         # blur and clouds there?
N_PARAMS = 0             # TileNet's parameters, counted by hand from the rule (weights + biases)
MED_MINE_400 = 0.0       # your my_tiles.pt: retrieval median at σ 400 m (printed at the end of `train`)
MED_DINO_400 = 0.0       # `retrieve --sigma 400`: DINOv2's median at σ 400 m

# ---- Step 10: one experiment -----------------------------------------------------------------------
PREDICT_EXPERIMENT = ""  # rank the FOUR flags (most harmful first) with your reasons, BEFORE you train exp.pt
EXP_MEDIAN = 0.0         # exp.pt's retrieval median at σ 400 m (printed at the end of its training)
EXPLAIN_EXPERIMENT = ""  # what changed, by how much, why — and where the class table proved your ranking wrong

# ---- Step 11: speed ----------------------------------------------------------------------------------
MS_DINO = 0.0            # `speed`: milliseconds per photo on the CPU
MS_MINE = 0.0
EXPLAIN_CHOICE = ""      # which finder would you fly on the drone's Jetson, and why? (accuracy AND cost)

# ======== Session 2 — Locator ========

# ---- Step 13: the fine step ---------------------------------------------------------------------------
LOCAL_ERR_P02 = 0.0      # `local p02`: the error of the position (metres, one decimal)

# ---- Step 14: your decision -------------------------------------------------------------------------------
PREDICT_SWEEP = ""       # before `sweep`: below which search radius is "fine only" good enough?
DIRECT_MAX_R_M = 0.0     # YOUR rule: up to this radius (m) the fine step searches alone; above it, retrieval first
EXPLAIN_DECISION = ""    # why this value? Quote the sweep: availability, wrong positions, time

# ---- Step 15: the error budget ------------------------------------------------------------------------------
BUDGET_TOTAL = 0.0       # `budget`: the total (metres, two decimals)

# ---- Step 16: the whole chain ---------------------------------------------------------------------------------
FINAL_AVAIL = 0.0        # `run` with your rule (σ 200 m priors): availability (0 to 1, two decimals)
FINAL_MEDIAN = 0.0       # median error (m, one decimal)
FINAL_P90 = 0.0          # p90 (m, one decimal)
FINAL_WRONG = 0          # wrong positions accepted
EXPLAIN_REFUSED = ""     # pick one refused photo: which gate refused it, and why was refusing right?

# ---- Look back (not graded) ----
LOOK_BACK = ""

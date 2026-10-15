# Lab 25 — your answers. Numbers without quotes (AUDIT_BEST_NCC = 0.73). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Night watch ========

# ---- Step 0: look (no code) ---------------------------------------------------------------------
PREDICT_LOOK = ""        # which of B, C, D will be easiest to match with A, which hardest, and why?

# ---- Step 2: the data auditor -------------------------------------------------------------------
PREDICT_AUDIT = ""       # if the replay set's night frames are real thermal, about what NCC do you expect between a
                         # night frame and the day frame of the same place? (before you run `audit`)
TWIN_OF_NIGHT_01 = 0     # the day frame (its number) with the best NCC for night frame 1
AUDIT_BEST_NCC = 0.0     # the median of the best NCC (two decimals, from `audit`)
EXPLAIN_AUDIT = ""       # what are the replay set's "night" frames really, and give two clues

# ---- Steps 3–4: footprint and coverage ------------------------------------------------------------
PREDICT_FIRST_CAM = ""   # the simulator's first thermal camera (56.7° × 48°), drone ceiling 400 m: can it ever give a
                         # night fix (85 % coverage)? (before you run `coverage`)
COV_350_0 = 0.0          # BY HAND, before `coverage`: lesson camera 84° × 68°, 350 m, heading 0°, square 495.8 m
                         # (three decimals)
MIN_ALT_FIRST_0 = 0      # minimum height of the first simulator camera, heading 0° (whole metres)
MIN_ALT_FIRST_45 = 0     #                                                heading 45°
EXPLAIN_COVERAGE = ""    # why does a heading of 45° need more height than 0°, and what does that mean for that camera?

# ---- Step 5: preparing the flight's frames ---------------------------------------------------------
REFUSED_FRAME = 0        # the number of the frame that `prepare` refused

# ---- Step 6: NCC ------------------------------------------------------------------------------------
PREDICT_NCC = ""         # in which of the five conditions will NCC find the right place, and in which not? Why?
NCC_GOOD_SAME = 0.0      # from `ncc`: share of "good" for day vs day (a share 0–1: 87 % → 0.87)
NCC_GOOD_NIGHT = 0.0     #                                   night
NCC_GOOD_INVERTED = 0.0  #                                   night inverted
EXPLAIN_NCC = ""         # why does NCC work day vs day but not at night, and why does inverting the night not fix it?

# ---- Step 7: the motion gate ----------------------------------------------------------------------
GATE_REFUSED = []        # the times (s) of the refused fixes, e.g. [2.0, 6.0]
EXPLAIN_GATE = ""        # why was the fix at 8 s refused, why was the one at 32 s accepted, and what happened after it?

# ======== Session 2 — Night navigator ========

# ---- Step 8: making pairs ----------------------------------------------------------------------------
EXPLAIN_CORNERS = ""     # what do the 8 numbers of a label mean, and why predict corners rather than the 9 entries of H?

# ---- Step 9: the input -------------------------------------------------------------------------------
EXPLAIN_NORM = ""        # why is each channel of each pair normalised on its own, and what does the "+ 1.0" protect?

# ---- Step 10: the network ----------------------------------------------------------------------------
PREDICT_PARAMS = ""      # BEFORE you work it out: which layer holds most of the 192 600 parameters? (a guess)
N_PARAMS_FC1 = 0         # the parameters of fc1, worked out by hand (weights + biases)

# ---- Steps 11–12: training and overfitting -----------------------------------------------------------
VAL_CENTRE_PX = 0.0      # the median centre error printed after your full training (two decimals)
PREDICT_OVERFIT = ""     # pairs from only 3 places, 30 epochs: what will the two loss curves do?
EXPLAIN_OVERFIT = ""     # what did the two losses do with 3 places, and why? At which epoch would you have stopped?

# ---- Step 13: your design decision (an ablation) ----------------------------------------------------------
PREDICT_ABLATION = ""    # which choice you turn off (a, b or c) and how much worse or better you expect it to be
ABLATION = ""            # "a" (no normalisation), "b" (no augmentation) or "c" (no ρ scaling)
ABLATION_PX = 0.0        # the median centre error of that run's last line (two decimals)
EXPLAIN_ABLATION = ""    # compared with your own error: was the author's choice worth it? Why? How sure are you?

# ---- Step 14: learned vs NCC ---------------------------------------------------------------------------
NET_NIGHT_PX = 0.0       # from `compare`: your network's median error at night (px, one decimal)
NCC_NIGHT_PX = 0.0       #                 NCC's median error at night
NET_NOON_PX = 0.0        #                 your network's median error at noon
EXPLAIN_LEARNED = ""     # why does your network win at night but not at noon or at dawn? What would you need before
                         # trusting it on a real drone?

# ---- Step 15: sabotage ------------------------------------------------------------------------------
PREDICT_STRICT = ""      # the renamed checkpoint loaded with strict=False: its median error at night — near yours, near
                         # the prior's, or much worse? Why?
MISSING_KEYS = 0         # how many keys were missing (from `sabotage`)
EXPLAIN_STRICT = ""      # why is strict=False dangerous, and what did NAVERA change after LOC-6?

# ---- Step 16: the night flight --------------------------------------------------------------------------
FLY_MEDIAN_M = 0.0       # the network's median error over the flight's prepared frames (metres, from `fly`)

# ---- Look back (not graded) ------------------------------------------------------------------------------
LOOK_BACK = ""

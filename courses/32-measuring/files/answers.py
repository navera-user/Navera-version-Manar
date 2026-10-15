# Lab 32 — your answers. Numbers without quotes (RETR_JAM_MEDIAN_M = 123.4). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — The numbers ========

# ---- Step 0: before any code ----------------------------------------------------------------------------
PREDICT_BEAT = ""          # during the 60 s jam, will the retrieval-like vision of flight_retrieval beat the
                           # baseline "repeat the last GPS position"? By how much (median)? (before Step 3)

# ---- Step 3: the flights (python3 measure_lab.py flights) -----------------------------------------------
RETR_JAM_MEDIAN_M = -1     # flight_retrieval, jam, the judge: the median error (m)
BASE_JAM_MEDIAN_M = -1     # the baseline during the same jam: the median error (m)
TARGET_LONGEST_GAP_S = -1  # flight_target: the longest gap (s)
EXPLAIN_MAX = ""           # flight_target's largest error during the jam (about 70 m) is far above its p90:
                           # when did it happen, and why? (look at out/errors_target.png and the lake)
SELECTIVE_JAM_MEDIAN_M = -1    # flight_selective, jam, the judge: the median error (m)
SELECTIVE_JAM_AVAIL_PCT = -1   # flight_selective, jam: the availability in % (e.g. 12.5)
EXPLAIN_SELECTIVE = ""     # flight_selective's median during the jam is much smaller than flight_retrieval's.
                           # Is its navigation better? Why does the median look better?

# ---- Step 4: two percentile rules (python3 measure_lab.py rules) -----------------------------------------
EXPLAIN_RULE = ""          # flight_target, jam (51 errors): the two rules give the same median but p95 values
                           # about 7 m apart. Why exactly the same for one, and so different for the other?

# ======== Session 2 — Error bars ========

# ---- Step 6: intervals (python3 measure_lab.py ci) --------------------------------------------------------
PREDICT_BLOCK = ""         # for which flight will the block interval of the jam median differ most from the
                           # iid one, and why?
EXPLAIN_PAIRED = ""        # flight_retrieval: what may you write about "vision vs baseline"? Quote the interval.
EXPLAIN_SELECTIVE_CI = ""  # flight_selective: its paired interval is entirely below 0. Has it proved that it
                           # beats the baseline? Why not?

# ---- Step 7: success rates (python3 measure_lab.py wilson) -----------------------------------------------
WILSON_LO_PCT = -1         # the lower end of the Wilson interval of 32 of 33, in % (one decimal)
ZERO_UPPER_PCT = -1        # the upper end of the Wilson interval of 0 of 33, in % (one decimal)

# ---- Step 8: coverage (python3 measure_lab.py coverage) --------------------------------------------------
PREDICT_COVERAGE = ""      # correlated errors (ρ 0.9) + the iid bootstrap: how often will a "95 %" interval of
                           # the median contain the true median? (before you run it)
EXPLAIN_COVERAGE = ""      # after: why does the iid bootstrap fail on correlated errors, and why do blocks help
                           # only partly?

# ---- Step 9: is the stated σ honest? (evaluate_bag) ------------------------------------------------------
HONEST_SIGMA_DAY_M = -1    # the "honest σ" of the day source, with the truth file (m, one decimal)
DAY_WITHIN_2SIGMA_PCT = -1 # the share of day errors within 2 × the stated σ (%)
EXPLAIN_GPS_STATED = ""    # the GPS states 2.0 m; its honest σ is smaller. Is that a problem? Why is it the
                           # better mistake for a judge?

# ---- Look back (not graded) ------------------------------------------------------------------------------
LOOK_BACK = ""             # one number from a product sheet you will now read differently, and what you would ask

# Lab 12 — your answers. Numbers without quotes (LAG_PLANE_MEDIAN_M = 12.3). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.
import math

from navera_lite.estimate import (COV_APPROXIMATED, COV_DIAGONAL_KNOWN, COV_KNOWN, COV_UNKNOWN,  # noqa: F401
                                  Estimate)

# ======== Session 1 — The contract ========

# ---- Step 0: a dead GPS ------------------------------------------------------------------------
PREDICT_DEAD = ""    # you stop the fake GPS: what will the judge say 10 s later? (before you run it)
EXPLAIN_DEAD = ""    # after lesson §4: why did arbiter v0 keep a dead GPS at FIX for so long?

# ---- Step 1: fill the contract -----------------------------------------------------------------
MY_ESTIMATE = None   # the Estimate(...) of the night-vision fix described in the lab, Step 1

# ---- Step 4: the lag study (python3 contract_lab.py lag) ---------------------------------------
PREDICT_LAG = ""            # drone at 15 m/s, fixes ≈1.6 s old, σ 30 m stated: what % will be within 30 m?
LAG_PLANE_MEDIAN_M = 0.0    # median error at 40 m/s (two decimals)
LAG_PLANE_WITHIN_PCT = -1.0 # % of fixes within the stated 30 m at 40 m/s
LAG_DRONE_WITHIN_PCT = -1.0 # the same at 15 m/s
LAG_OLD_WINDOW_REFUSED = -1 # how many of these fixes a 3.0 s day-vision timeout would refuse as stale
LAG_SPEED_MAX_MPS = 0.0     # the fastest speed (m/s, one decimal) that keeps 90 % of the fixes within 30 m
EXPLAIN_LAG = ""            # the matcher is good to 1 m; why are its positions wrong by tens of metres?

# ======== Session 2 — Attack, then defend ========

# ---- Steps 6 and 8: what the LIVE judges said (copy the line of `python3 contract_lab.py status`) ------
VERDICTS_V0 = {              # arbiter v0, naive (live, Step 6), e.g. "FIX | gps: σ 0.0 m"
    "zero": "",
    "unknown": "",
    "not_psd": "",
    "future": "",
}
VERDICTS_MINE = {            # arbiter v0 with -p use_eligible:=true: YOUR eligible() (live, Step 8)
    "zero": "",
    "unknown": "",
    "not_psd": "",
    "future": "",
}

# ---- Step 8: the future attack, watched long ------------------------------------------------------
PREDICT_REVIVE = ""  # your judge refused the future fix; the source is dead: what will it say about 60 s later?
EXPLAIN_REVIVE = ""  # what did you see, and why? (what does the judge keep, what changes when the clock reaches the stamp)

# ---- Step 9: the limit of any checklist ------------------------------------------------------------
EXPLAIN_HONEST = ""  # a source states σ 3 m but is 500 m off; why can no eligible() refuse it, and what can?

# ---- Look back (not graded) -----------------------------------------------------------------------
LOOK_BACK = ""

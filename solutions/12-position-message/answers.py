# Lab 12 — your answers. Numbers without quotes (LAG_PLANE_MEDIAN_M = 12.3). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.
import math

from navera_lite.estimate import (COV_APPROXIMATED, COV_DIAGONAL_KNOWN, COV_KNOWN, COV_UNKNOWN,  # noqa: F401
                                  Estimate)

# ======== Session 1 — The contract ========

# ---- Step 0: a dead GPS ------------------------------------------------------------------------
PREDICT_DEAD = "NO_FIX after 3 s, gps stale, as in mission 11"
EXPLAIN_DEAD = ("The fake GPS stamped its fixes 30 s in the future, so their age was negative (about -30 s) and "
                "never above the 3 s timeout: v0 believed the last fix was fresh for 30 + 3 s after the GPS died.")

# ---- Step 1: fill the contract -----------------------------------------------------------------
MY_ESTIMATE = Estimate("night", 35.7712, 10.8265, 812.4,
                       cov=(324.0, 0.0, 0.0, 0.0, 576.0, 0.0, 0.0, 0.0, 900.0),
                       cov_type=COV_DIAGONAL_KNOWN, alt_m=math.nan, valid=True)

# ---- Step 4: the lag study (python3 contract_lab.py lag) ---------------------------------------
PREDICT_LAG = "maybe half of them"
LAG_PLANE_MEDIAN_M = 64.30
LAG_PLANE_WITHIN_PCT = 0.0
LAG_DRONE_WITHIN_PCT = 76.88
LAG_OLD_WINDOW_REFUSED = 6
LAG_SPEED_MAX_MPS = 13.1   # 30 / 2.284 = 13.13; confirmed: 13.0 → 90.00 %, 13.1 → 89.38 %
EXPLAIN_LAG = ("Each position describes where the camera was when the photo was taken, 1 to 2.5 s before the "
               "judge uses it; the plane kept flying at 40 m/s during that age, so it is 40 to 100 m further on.")

# ======== Session 2 — Attack, then defend ========

# ---- Steps 6 and 8: what the LIVE judges said (copy the line of `python3 contract_lab.py status`) ------
VERDICTS_V0 = {
    "zero": "FIX | gps: σ 0.0 m",
    "unknown": "FIX | gps: σ 2.0 m",
    "not_psd": "FIX | gps: σ 9.0 m",
    "future": "FIX | gps: σ 3.0 m",
}
VERDICTS_MINE = {
    "zero": "DEGRADED | gps: σ unknown",
    "unknown": "DEGRADED | gps: σ unknown",
    "not_psd": "NO_FIX | no usable source (gps: not a covariance)",
    "future": "NO_FIX | no usable source (gps: from the future)",
}

# ---- Step 8: the dead source that comes back ------------------------------------------------------
PREDICT_REVIVE = "NO_FIX from the future all the time"
EXPLAIN_REVIVE = ("At about 60 s the dead GPS became FIX again for 3-4 s, then stale: the judge keeps the refused fix "
                  "as the newest one of its source and tests it again at every tick; when the clock reaches its stamp "
                  "it is no longer in the future and looks fresh.")

# ---- Step 9: the limit of any checklist ------------------------------------------------------------
EXPLAIN_HONEST = ("A covariance that says 3 m is a perfectly valid covariance: eligible() can only check that the "
                  "claim is well formed and fresh, it must believe what the source states about itself. Only an "
                  "independent source (a cross-check with vision, the jump gate) or a validation measurement can "
                  "show that the source is 500 m off.")

# ---- Look back (not graded) -----------------------------------------------------------------------
LOOK_BACK = ""

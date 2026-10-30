# Lab 32 — your answers. Numbers without quotes (RETR_JAM_MEDIAN_M = 123.4). Text in quotes ("…").
# (teacher's solution — see TEACHER.md for the rubric)

PREDICT_BEAT = "I think vision wins easily, maybe 200 m better than the frozen position."
RETR_JAM_MEDIAN_M = 420.6
BASE_JAM_MEDIAN_M = 450.0
TARGET_LONGEST_GAP_S = 9
EXPLAIN_MAX = ("Around t = 120 s, over the lake: vision found no match for 14 s, so the judge kept giving the last "
               "stored fix while it was up to 5 s old (the day timeout); at 15 m/s an old position is about 70 m "
               "behind. Then the fix went stale and the judge said NO_FIX for 9 s.")
SELECTIVE_JAM_MEDIAN_M = 236.0
SELECTIVE_JAM_AVAIL_PCT = 31.7
EXPLAIN_SELECTIVE = ("No, it is the same method with the bad positions withheld: the median is computed only on the "
                     "19 easy seconds it chose to answer, so it looks better, while the availability during the jam "
                     "falls to 32 % and the autopilot has no position for gaps up to 13 s.")
EXPLAIN_RULE = ("With 51 values the median sits exactly on one sample (position 25), so both rules give it. The p95 "
                "falls at position 47.5, between two errors of the tail that are far apart: the linear rule "
                "interpolates halfway between them, the nearest rule takes one of the samples (index 48).")
PREDICT_BLOCK = "wider"
EXPLAIN_PAIRED = ("The paired interval of median(vision) - median(baseline) is about [-282, 190] m with blocks: it "
                  "contains 0, so I may only write that on this flight vision is not shown to be better or worse "
                  "than repeating the last GPS position; the 29 m is within the noise.")
EXPLAIN_SELECTIVE_CI = ("No. The pairs are only the 19 seconds the method chose to answer, the seconds where it was "
                        "good; the other 41 seconds are missing, so the comparison is conditional on its own "
                        "selection and ignores the availability loss.")
WILSON_LO_PCT = 84.7
ZERO_UPPER_PCT = 10.4
PREDICT_COVERAGE = "about 80 %"
EXPLAIN_COVERAGE = ("Consecutive errors are correlated, so 60 seconds carry the information of only a few independent "
                    "values; the iid bootstrap treats them as 60 independent ones and its interval is too narrow. "
                    "Blocks keep the correlation inside each block, but with only 6 blocks of 10 s the interval is "
                    "still too narrow, so the coverage stays below 95 %.")
HONEST_SIGMA_DAY_M = 23.4
DAY_WITHIN_2SIGMA_PCT = 58
EXPLAIN_GPS_STATED = ("It is pessimistic: the GPS is more accurate than it says (98 % within 2 sigma instead of 86 %). "
                      "A judge that believes a too large sigma is only cautious, while a too small sigma, like the day "
                      "source's 15 m, makes it trust a bad position.")
LOOK_BACK = ""

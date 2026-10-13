# Lab 5 — your answers. Numbers without quotes (KENJI_GATE_1S_M = 12.5). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the step, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Reviewer ========

# ---- Step 3: two dots and three dots ----------------------------------------------------------
TWO_DOT_FILES = 0       # how many files `git diff --stat main..kenji/fewer-refusals` lists
THREE_DOT_FILES = 0     # how many files `git diff --stat main...kenji/fewer-refusals` lists
EXPLAIN_DOTS = ""       # why are they different? which one does a reviewer want, and why?

# ---- Step 4: what Kenji's patch would do --------------------------------------------------------
KENJI_GATE_1S_M = 0     # with Kenji's settings: the largest jump accepted 1 s after the last trusted fix (m)
SPOOF_ACCEPTED_AT_S = 0 # with Kenji's code: trusted fix at t = 0 s, then a fake fix 50 km away at
                        # t = 1, 2, 3 … s (one per second). At which t is the fake fix accepted?

# ======== Session 2 — Detective ========

# ---- Step 6: the bug report ---------------------------------------------------------------------
PREDICT_PROBE = ""      # what will probe_gate.py print on your branch? (5 would be right)
PROBE_BRANCH = -1       # what it prints on your branch my-first-change
PROBE_V01 = -1          # what it prints at the tag v0.1
PREDICT_TESTS = ""      # how many commits will git bisect have to test between v0.1 and main? why?

# ---- Step 7: git bisect -------------------------------------------------------------------------
FIRST_BAD = ""          # the hash of the first bad commit (at least 7 characters)
TESTS_RUN = 0           # how many commits your bisect_test.sh was run on (count them in bisect.log)
EXPLAIN_BISECT = ""     # why so few tests for 30 commits? and why must a broken commit give exit code 125?
EXPLAIN_CAUSE = ""      # which line of the bad commit breaks the gate, why GPS is then locked out,
                        # and what that says about Kenji's patch

# ---- Step 8: test, then revert ---------------------------------------------------------------
EXPLAIN_REVERT_COST = ""  # what else did the revert remove, and how would one-concern commits
                          # (or a fix forward) have avoided it?

# ---- Step 9: rescue -----------------------------------------------------------------------------
EXPLAIN_RESCUE = ""     # where were your two "lost" commits, how did you find them, and what could git
                        # NOT have given back?

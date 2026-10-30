# Lab 29 — your answers. Numbers without quotes (V0_FLAP_SWITCHES = 12). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — The judge ========

# ---- Step 0: arbiter v0 and a GPS that comes and goes (flapping.csv) ---------------------------------
PREDICT_FLAP = ""      # in 30 s, how many times will arbiter v0 change its winner? (before you run it)
V0_FLAP_SWITCHES = -1  # the number judge_lab.py printed after "changes of winner:" for v0 (--v0)

# ---- Step 4: your judge on the same GPS (flapping.csv) -----------------------------------------------
MINE_FLAP_SWITCHES = -1  # the number after "changes of winner:" for YOUR judge
EXPLAIN_FLAP = ""       # 2.5 s to 24.5 s: GPS usable several times, your judge stayed on day vision: why?
                       # which run of GPS fixes finally took over, and why that one?

# ---- Step 5: the door left open (lockout.csv) ---------------------------------------------------------
PREDICT_LOCKOUT = ""   # a judge whose door lets a fix stamped 20 s ahead in: what happens to the HONEST GPS
                       # fixes that arrive after it, and what does the judge say between 10 s and 40 s?
EXPLAIN_LOCKOUT = ""   # after the run: what happened to the honest fixes, and why, and why did an old
                       # position come back as FIX around t = 32 s?

# ======== Session 2 — Live, and what it costs ========

# ---- Step 6: the race ---------------------------------------------------------------------------------
EXPLAIN_WAIT = ""      # at t = 15.0 s the GPS is back, eligible and first in priority: why does your judge
                       # still use day vision?

# ---- Step 7: the price of the hold-off (python3 experiment.py) ----------------------------------------
PREDICT_HOLDOFF = ""   # changes of winner per minute with no hold-off, and with 2 s? (before you run it)
EXPLAIN_HOLDOFF = ""   # after: what does a longer hold-off buy, and what does it cost? Quote your numbers.

# ---- Look back (not graded) ---------------------------------------------------------------------------
LOOK_BACK = ""         # one rule of your judge you would defend in front of a pilot, and why

# Lab 29 — your answers. Numbers without quotes (V0_FLAP_SWITCHES = 12). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — The judge ========

# ---- Step 0: arbiter v0 and a GPS that comes and goes (flapping.csv) ---------------------------------
PREDICT_FLAP = "about 10 changes"
V0_FLAP_SWITCHES = 29

# ---- Step 5: the door left open (lockout.csv) ---------------------------------------------------------
PREDICT_LOCKOUT = "the judge refuses the future fix and the honest ones keep it at FIX"
EXPLAIN_LOCKOUT = ("Once the fix stamped 30.5 s was stored, every honest fix had an older stamp, so the door dropped "
                   "them as old news for 20 s and the judge fell back to day vision. When the clock reached that "
                   "stamp the stored fix became eligible, waited the hold-off and won as FIX at 32 s with a position "
                   "about 430 m behind, and the jump gate, which trusted it, refused the honest fixes as jumps.")

# ======== Session 2 — Live, and what it costs ========

# ---- Step 6: the race ---------------------------------------------------------------------------------
EXPLAIN_WAIT = ("The hold-off: GPS came back at 14.0 s, so at 15.0 s it has been eligible for 1 s only, less than "
                "the 2 s it must wait before it may replace day vision; it takes over at 16.0 s.")

# ---- Step 7: the price of the hold-off (python3 experiment.py) ----------------------------------------
PREDICT_HOLDOFF = "30 per minute without, 10 with 2 s"
EXPLAIN_HOLDOFF = ("A 2 s hold-off cuts the changes of winner from 31.1 to 12.1 per minute, so the output is much "
                   "steadier, but the GPS was eligible and not used for 228.8 s of the 600 s, and its share falls "
                   "from 62 % to 24 %: stability costs good GPS time.")

# ---- Look back (not graded) ---------------------------------------------------------------------------
LOOK_BACK = "a refused fix is never stored, so it can never come back"

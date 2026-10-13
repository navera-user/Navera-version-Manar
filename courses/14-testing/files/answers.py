# Lab 14 — your answers. Numbers without quotes (N_TESTS = 12), text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Pin the bugs ========

# ---- Step 0: the stack's own suite -------------------------------------------------------------
PREDICT_SUITE = ""        # how many tests does navera_lite/tests hold, and how long will they take?
N_TESTS = 0               # how many tests pytest ran (the number before "passed")
SLOWEST_TEST = ""         # the slowest test as --durations prints it, e.g. "navera_lite/tests/test_x.py::test_y"

# ---- Step 1: break the stack, then restore it with git ---------------------------------------------
PREDICT_FAILS = ""        # how many of the suite's tests will fail after the "small change"?
N_FAILED = -1             # how many really failed
EXPLAIN_ONE_TEST = ""     # why that many? which other parts use is_finite_latlon, and did their tests notice?

# ---- Step 2: example tests ------------------------------------------------------------------------
PREDICT_TRAINING = ""     # before your first `python3 hunt.py`: how many of the 7 training mutants will die?

# ---- Step 3: properties ----------------------------------------------------------------------------
PREDICT_COUNTEREXAMPLE = ""   # before you run d) on the whole Earth: where will hypothesis find a failure?
COUNTEREXAMPLE = ()       # the Falsifying example of d), as 4 numbers: (lat0, lon0, e_m, n_m)
EXPLAIN_COUNTEREXAMPLE = ""   # what happens physically, and is it a bug of offset or a limit of its domain?

# ======== Session 2 — Hunt and launch ========

# ---- Step 4: the mutation score ----------------------------------------------------------------------
EQUIVALENT_MUTANT = 0     # the number of the training mutant that NO test can kill
EXPLAIN_EQUIVALENT = ""   # why can no input show a difference?

# ---- Step 6: the launch test ------------------------------------------------------------------------
PREDICT_REPUBLISH = ""    # the judge re-publishes at 5 Hz: which test fails, and how many positions will it count?
REPUBLISH_FAILED = ""     # the name of the test that really failed (from launch_test's output)
REPUBLISH_COUNT = 0       # how many positions it counted instead of 1 (the number before "!= 1")

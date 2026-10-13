# Lab 14 — answers (solution). Values measured in the sandbox, 2026-10-13.

# ---- Step 0
PREDICT_SUITE = "About 50 tests, a few seconds."
N_TESTS = 89
SLOWEST_TEST = "navera_lite/tests/test_ros_smoke.py::test_arbiter_v0_judges_the_replayed_demo"

# ---- Step 1
PREDICT_FAILS = "Maybe five: every test that uses positions."
N_FAILED = 1
EXPLAIN_ONE_TEST = ("Only one test of the 89 checks Null Island through is_finite_latlon. The judge arbiter_v0 and "
                    "the trip node also call it, and estimate.eligible has its own (0, 0) rule, but no test of the "
                    "judge sends (0, 0): v0 would now take it as usable and say FIX, and no test would notice.")

# ---- Step 2
PREDICT_TRAINING = "Four of six."

# ---- Step 3
PREDICT_COUNTEREXAMPLE = "Near the poles or at the date line."
COUNTEREXAMPLE = (89.55257463757103, 0.0, 0.0, 49751.430354205564)
EXPLAIN_COUNTEREXAMPLE = ("49 751 m north of 89.55° is a latitude just above 90°: the flat-Earth offset adds "
                          "degrees and does not know that a move over the pole comes down the other side. It "
                          "is a limit of its domain (small moves, far from the poles), so I restricted the "
                          "start latitude to ±80° and documented it.")

# ---- Step 4
EQUIVALENT_MUTANT = 3
EXPLAIN_EQUIVALENT = ("A NaN or infinite longitude is still refused by the range test abs(lo) <= 180.0, because "
                      "every comparison with NaN is False and infinity is above 180. So for every input the "
                      "mutant returns the same result: no test can show a difference.")

# ---- Step 6
PREDICT_REPUBLISH = "test_1, about 10 positions: 5 per second for 2 s."
REPUBLISH_FAILED = "test_1_a_5_km_jump_is_refused"
REPUBLISH_COUNT = 12

"""answers.py — teacher's example answers for lab 33."""
PREDICT_SUITE = "about 160 tests, maybe 15 seconds"
EXPLAIN_RED = ("It must fail on the old code: a test that already passes before the change does not see the problem, "
               "so it would prove nothing about my change; failing first shows that it checks the missing behaviour.")
EXPLAIN_SEEDS = ("If I could choose the seeds after seeing the results I could pick the lucky ones that favour my "
                 "change; a block fixed in advance in project.json removes that choice.")
PREDICT_EFFECT = "D around -0.1, an interval below 0, fix_share a bit lower"
EXPLAIN_PAIRED = ("Both campaigns fly the same seeds, so the same noise and the same faults: the difference between "
                  "the two runs of a pair is only my change, and the shared noise cancels, so the interval is narrow.")
EXPLAIN_RULER = ("world.py is the ruler of the comparison, the simulated world that measures both versions; if it "
                 "changed between before and after I could not tell my change from a change of the measurement.")
LOOK_BACK = "Write the rule first, then measure."

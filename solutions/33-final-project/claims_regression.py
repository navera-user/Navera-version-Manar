"""claims_regression.py — teacher/builder only: the regression set of check 10's claim filter (like mission 32's).
It takes NEGATION, CLAIM, MISSING and claims() out of courses/33-final-project/check.py (without running the check)
and classifies every sentence below. Run: python3 solutions/33-final-project/claims_regression.py
The filter runs only when the decision is INCONCLUSIVE, or REJECT with D on the bad side (a reject that comes from
the guard-rail may report the gain).
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(os.path.join(HERE, "..", "..", "courses", "33-final-project", "check.py"), encoding="utf-8").read()
ns = {"re": re}
for node in ast.parse(SRC).body:
    if (isinstance(node, ast.Assign) and any(getattr(t, "id", "") in ("NEGATION", "CLAIM", "MISSING", "CASE_B",
                                                                       "CASE_B_HEDGE", "CLAUSES")
                                             for t in node.targets)) or \
            (isinstance(node, ast.FunctionDef) and node.name == "claims"):
        exec(compile(ast.Module([node], []), "check.py", "exec"), ns)

CLAIMS = [   # must be caught (a gain claimed that an inconclusive interval does not support)
    "Inconclusive. Our change improves the median error by 1.4 m, but more runs are needed.",
    "The change reduces the error by 2 m.",
    "It lowers the p95 to 40 m.",
    "The guard is faster now.",
    "Detection comes sooner with the new rule.",
    "This is an improvement of 1.4 m.",
    "The new σ is better: the mean honest2 went from 0.717 to 0.892.",
    "It still beats the old rule, although the interval contains 0.",
    "The change improves honest2: the mean went from 0.717 to 0.892.",
    "Only the p95 decreased, by 3 m.",
    "The detector shortens the detection delay.",
    # round-2 reviewer's realistic weak sentences (all must be caught)
    "Inconclusive. Our change improves detection by 2.55 s, but more runs are needed.",
    "The change makes the guard detect the drift 2.55 s earlier.",
    "Detection is quicker with the change.",
    "The new patience catches the drift sooner, but the guard-rail is unclear.",
    "The guard now detects spoofing 2.55 s earlier on average.",
    "The change helps: detection went from 18.25 to 15.70 s.",
    "Our change gives a gain of 2.55 s.",
    "This change works well and should be merged.",
    "The detection time dropped by 2.55 s.",
    "The detect time is shorter after the change.",
    "Detection got 14 % faster.",
    "The change does improve detection but not by 2 s for sure.",
    "There is a clear improvement in detection time.",
    "It reduces detect_s by 2.55 s, if the guard-rail allows.",
    "The interval contains no 0, so detection is faster.",
    "We expected a gain and we got it: 2.55 s.",
    "The change is effective.",
    "The change was successful.",
    "The mean error after the change is smaller than the mean before, so the change works.",
    "The p95 is less than the old one: the change improves the guard.",
    "The change reduces the error by less than the 3 m we hoped, but it reduces it.",
    "The error after is lower than before.",
    "The change makes the error drop by 1.4 m.",
    "The change clearly brings the error down.",
    "Honest2 got closer to 0.86, which is what we wanted.",
]
HONEST = [   # must pass
    "The change is not shown to lower the error on these 30 runs.",
    "D = −1.4 m, 95 % interval [−3.1, 0.4] m: it contains 0.",
    "The error fell (D = −7.7 m [−10.0, −5.6]) but availability lost 0.049 of the jam, beyond the 0.02 limit: rejected.",
    "I would fly a longer campaign to see whether the gain is real.",
    "Our hypothesis was that a shorter window lowers the error.",
    "We hoped the change would reduce the p95.",
    "No improvement is shown on these runs.",
    "A gain may exist but these 30 runs cannot show it.",
    "Inconclusive: the interval of D contains 0, so a gain is not shown.",
    "The guard-rail did not get worse: 0 false alarms in 30 runs, which shows only a rate below 0.114.",
    # lesson §5 case (b): a gain over 0, but perhaps smaller than the minimum effect (honest; the check applies the
    # filter only when the interval contains 0, and these must pass even if it did)
    "Detection is faster by 2.55 s (95 % interval 1.70 to 3.45 s), but perhaps by less than the 2 s minimum effect.",
    "The change lowers the error, but the interval crosses the minimum effect, so a gain that matters is not shown.",
    "A gain over 0 is shown, but not one larger than the minimum effect of 0.02.",
    "D lies below 0, perhaps only by less than the minimum effect.",
]
bad = [s for s in CLAIMS if ns["claims"](s) is None] + [s for s in HONEST if ns["claims"](s) is not None]
for s in CLAIMS:
    print(("✔ caught  " if ns["claims"](s) else "✘ MISSED  ") + s)
for s in HONEST:
    print(("✔ passes  " if ns["claims"](s) is None else "✘ FLAGGED ") + s)
print(f"\n{len(CLAIMS) + len(HONEST) - len(bad)} of {len(CLAIMS) + len(HONEST)} classified right")
sys.exit(1 if bad else 0)

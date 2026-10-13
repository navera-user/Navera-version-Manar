# Lab 5 — reference answers (teacher only). Values recomputed with solutions/05-git/make_repo.py.

# ======== Session 1 — Reviewer ========
TWO_DOT_FILES = 6
THREE_DOT_FILES = 5
EXPLAIN_DOTS = ("Two dots compare the two snapshots, main's tip against Kenji's tip, so main's two newer commits "
                "(README review rule and the geo test) show up reversed as if Kenji had deleted them. Three dots "
                "start from the merge base, where Kenji's branch left main, so they show only what his branch did: "
                "that is what a reviewer wants to read.")
KENJI_GATE_1S_M = 600
SPOOF_ACCEPTED_AT_S = 12

# ======== Session 2 — Detective ========
PREDICT_PROBE = "5 if the gate still works; maybe 7 if it never widens"
PROBE_BRANCH = 7
PROBE_V01 = 5
PREDICT_TESTS = "About 5: 30 suspects, each test halves them, log2(30) is about 4.9."
FIRST_BAD = "bd4a667"
TESTS_RUN = 7
EXPLAIN_BISECT = ("Each test halves the suspects, so 30 commits need about log2(30) = 5 tests instead of 30. "
                  "The wip commit has a syntax error: it cannot be imported, so it is neither good nor bad; with exit "
                  "125 bisect skips it, while exit 1 would wrongly call it the first bad commit.")
EXPLAIN_CAUSE = ("The commit measures elapsed_s from prev_t_s, the previous fix even when it was refused, instead of "
                 "the last trusted fix. So elapsed is always 1 s, the gate never widens beyond 150 m and after a real "
                 "500 m jump the true GPS is locked out for ever. Kenji's 10 s timer treats that symptom and opens "
                 "the door to a patient spoofer; the cause was this one line.")
EXPLAIN_REVERT_COST = ("The revert removed the whole commit: also refused_for_s() and its test, the operator-display feature, while the CHANGELOG still announces it. If the feature and the elapsed change had been two commits, reverting the bad one would keep the feature; a fix forward that only changes the elapsed_s line keeps it too.")
EXPLAIN_RESCUE = ("git reset --hard only moved the branch label back; the two commits still existed in .git and the "
                  "reflog listed where the branch pointed before, so git reset --hard HEAD@{1} put it back. Git could "
                  "not have given back edits that were never committed.")

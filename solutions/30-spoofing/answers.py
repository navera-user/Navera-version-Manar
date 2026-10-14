# Lab 30 — your answers. Numbers without quotes (PATIENT_FLOWN_T_S = 96.0). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Statistician ========

# ---- Step 0: the judge alone against a slow drift (python3 spoof_run.py drift --no-guard) ----------------------
PREDICT_NOGUARD = "All the way, about 280 m: each 4 m step is far below the jump gate (30 m/s + 50 m), so the judge follows the GPS."        # BEFORE running: the spoofer pulls the GPS east at 4 m/s for 70 s (up to 280 m). Mission 29's
                            # judge has the jump gate. How far from the truth will the judge's position get? why?
NOGUARD_MAX_ERROR_M = 278.0   # the run's "largest error of the judge's position" (m)

# ---- Step 2: does your test keep its promise? (python3 spoof_run.py stats) -------------------------------------
PREDICT_STATS = "A little less than 1 %: S also holds the gap term (30 m/s x 0.1 s = 3 m) although the pairs did not move, so S is a bit too big."          # BEFORE running: with p_fa = 0.01, will the share of honest pairs beyond γ be exactly 1 %,
                            # a little more, or a little less? why? (look at what innovation() puts into S)
STATS_SHARE_1PC = 0.00915       # the measured share for p_fa 0.01 (a number like 0.0123)
MEAN_D2 = 1.925               # the measured mean d²
EXPLAIN_STATS = "S adds the time-gap term g² = 9 m² as if the vehicle flew at top speed during the 0.1 s gap, but these pairs measured the same point, so S (243) is larger than the real variance (234): d² is smaller by 234/243, the mean is 2 x 234/243 = 1.93 and the share beyond γ is a bit below p_fa. The test is conservative."          # why is the measured share not exactly p_fa, and why is the mean d² not exactly 2?

# ---- Step 3: the jump gate's hole (python3 spoof_run.py patient --no-guard, then with --vmax 100.0) ------------
PREDICT_PATIENT = "About 75 s after the last trusted fix, so near t = 95 s; then the true GPS at 120 s is 2 km from the trusted spoof and is refused as a jump."        # BEFORE running: the judge alone, a 2 km spoof from t = 20 s that waits. When will the judge
                            # fly on the spoof? what happens when the true GPS comes back at t = 120 s?
PATIENT_THEORY_DT_S = 74.77   # your patient_accept_time for the lab's case (2000 m, 15 m/s, 30 m/s, 50 m), in s
PATIENT_FLOWN_T_S = 96.0     # the run: the time at which the judge starts flying on the spoofed GPS (s)
VMAX100_FLOWN_T_S = 41.0     # the same with --vmax 100.0 (s)
EXPLAIN_PATIENT = "The last trusted fix is at t = 19 s, so theory says 19 + 74.8 = 93.8 s: the gate accepts the next whole-second fix at 94 s and the judge switches back from vision after its 2 s hold-off, at 96 s. At 120 s the true GPS is 2 km from the trusted spoof and is refused as a jump: locked out. With a top speed of 100 m/s the circle grows more than three times faster and the spoof gets in at 41 s: the top speed must be the vehicle's own."        # theory vs run (which t was the last trusted fix? why a few seconds more?), what happened at
                            # t = 120 s, and what a generous top speed does to the hole

# ---- Step 4: when is a drift caught? -----------------------------------------------------------------------------
DRIFT_THEORY_S = 20.0        # drift_alarm_time for the lab's drift: 4 m/s, σ_s = √243 m, γ for p_fa 0.01, n = 5, every 2 s

# ---- Steps 5–6: the ROC (python3 detection.py; your operating point is TODO 9 in detection.py) -------------------
NAVERA_RULE_PD = 0.17        # P_D of the rule closest to NAVERA's (p_fa 0.01 per test, n = 5) in your table
CORRELATED_PFA = 0.2815        # results.json "correlated": P_FA of the rule (0.05, 3) when vision errors have ρ = 0.9
EXPLAIN_ROC = "I chose p 0.05, n 3: P_FA 0.005 and P_D 0.91, the highest detection that meets 1 % (p 0.01, n 2 is a tie within the Monte-Carlo noise). NAVERA's rule detects only 17 % of this drift within 40 s, but over a one-hour flight with 1 800 tests the false alarms per flight grow roughly 30 times, so a stricter rule keeps them rare."            # which rule did you choose and why? why is it not NAVERA's (0.01, 5)? what changes for a
                            # one-hour flight (1 800 tests instead of 60)?
EXPLAIN_CORRELATED = "With rho 0.9 the same vision error lasts several tests, so one bad error makes the whole streak: the streak is almost one event, not independent tests, and P_FA^n no longer holds (0.005 becomes 0.28). I would ask for distinct, decorrelated fixes (more time between them) or a longer n."     # why does ρ = 0.9 raise the false-alarm rate so much? what would you change in the rule?

# ======== Session 2 — Guardian ========

# ---- Step 8: your guard against the drift (python3 spoof_run.py drift) -------------------------------------------
PREDICT_GUARD_DRIFT = "20 s after the drift starts: about t = 30 s, offset 80 m."    # BEFORE running: from DRIFT_THEORY_S (the drift starts at t = 10 s, tests at 10.1, 12.1 …),
                            # at what time and offset will your guard refuse the GPS?
DRIFT_DOUBT_OFFSET_M = 60.0  # the run: the offset of the first spoofed GPS fix judged IN_DOUBT (m)
DRIFT_REFUSED_OFFSET_M = 84.0  # the run: the offset of the first spoofed GPS fix judged REFUSED (m)
EXPLAIN_DRIFT = "Predicted 20 s after the start (t = 30.1 s, 80 m); the guard refused at the vision fix of 30.1 s and the runner shows it at the next GPS fix, t = 31 s, 84 m; noise moves the first disagreeing test. After the refusal the judge flies on day vision."          # compare with your prediction: why a little later / larger? who flies after the refusal?

# ---- Step 9: every attack (python3 spoof_run.py all) -------------------------------------------------------------
EXPLAIN_LIMITS = "drift_novision, patient, jamspoof_novision and creep still win: without a reference of stated accuracy only the jump gate is left, and the creep stays inside the test radius."         # which attacks still win against your guard, and what do they have in common?

# ---- Step 10: live over ROS 2 (guard_node.py + python3 spoof_run.py drift --ros) ----------------------------------
ROS_REFUSED_T_S = 30.6       # ros_drift.json: the time t of the first change with gps_guard REFUSED (s)

# ---- Step 11: red team (python3 spoof_run.py creep --creep X) ----------------------------------------------------
CREEP_MAX_M = 50.0           # the largest creep offset (m) your guard never REFUSES (find it to the nearest metre or two)
EXPLAIN_CREEP = "The test only refuses gaps beyond its radius sqrt(9.21 x 243) = 47 m (plus noise), so an offset that stays inside the radius is never refused: the guard bounds the error, it does not remove it. A smaller vision sigma or averaging many tests would shrink the bound."          # why is there such an offset, how does it compare with the test's radius, and what would
                            # make it smaller?

# ---- Step 12: look back (not graded; for you and your teacher) ---------------------------------------------------
LOOK_BACK = ""

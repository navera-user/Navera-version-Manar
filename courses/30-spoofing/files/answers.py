# Lab 30 — your answers. Numbers without quotes (PATIENT_FLOWN_T_S = 96.0). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Statistician ========

# ---- Step 0: the judge alone against a slow drift (python3 spoof_run.py drift --no-guard) ----------------------
PREDICT_NOGUARD = ""        # BEFORE running: the spoofer pulls the GPS east at 4 m/s for 70 s (up to 280 m). Mission 29's
                            # judge has the jump gate. How far from the truth will the judge's position get? why?
NOGUARD_MAX_ERROR_M = 0.0   # the run's "largest error of the judge's position" (m)

# ---- Step 2: does your test keep its promise? (python3 spoof_run.py stats) -------------------------------------
PREDICT_STATS = ""          # BEFORE running: with p_fa = 0.01, will the share of honest pairs beyond γ be exactly 1 %,
                            # a little more, or a little less? why? (look at what innovation() puts into S)
STATS_SHARE_1PC = 0.0       # the measured share for p_fa 0.01 (a number like 0.0123)
MEAN_D2 = 0.0               # the measured mean d²
EXPLAIN_STATS = ""          # why is the measured share not exactly p_fa, and why is the mean d² not exactly 2?

# ---- Step 3: the jump gate's hole (python3 spoof_run.py patient --no-guard, then with --vmax 100.0) ------------
PREDICT_PATIENT = ""        # BEFORE running: the judge alone, a 2 km spoof from t = 20 s that waits. When will the judge
                            # fly on the spoof? what happens when the true GPS comes back at t = 120 s?
PATIENT_THEORY_DT_S = 0.0   # your patient_accept_time for the lab's case (2000 m, 15 m/s, 30 m/s, 50 m), in s
PATIENT_FLOWN_T_S = 0.0     # the run: the time at which the judge starts flying on the spoofed GPS (s)
VMAX100_FLOWN_T_S = 0.0     # the same with --vmax 100.0 (s)
EXPLAIN_PATIENT = ""        # theory vs run (which t was the last trusted fix? why a few seconds more?), what happened at
                            # t = 120 s, and what a generous top speed does to the hole

# ---- Step 4: when is a drift caught? -----------------------------------------------------------------------------
DRIFT_THEORY_S = 0.0        # drift_alarm_time for the lab's drift: 4 m/s, σ_s = √243 m, γ for p_fa 0.01, n = 5, every 2 s

# ---- Steps 5–6: the ROC (python3 detection.py; your operating point is TODO 9 in detection.py) -------------------
NAVERA_RULE_PD = 0.0        # P_D of the rule closest to NAVERA's (p_fa 0.01 per test, n = 5) in your table
CORRELATED_PFA = 0.0        # results.json "correlated": P_FA of the rule (0.05, 3) when vision errors have ρ = 0.9
EXPLAIN_ROC = ""            # which rule did you choose and why? why is it not NAVERA's (0.01, 5)? what changes for a
                            # one-hour flight (1 800 tests instead of 60)?
EXPLAIN_CORRELATED = ""     # why does ρ = 0.9 raise the false-alarm rate so much? what would you change in the rule?

# ======== Session 2 — Guardian ========

# ---- Step 8: your guard against the drift (python3 spoof_run.py drift) -------------------------------------------
PREDICT_GUARD_DRIFT = ""    # BEFORE running: from DRIFT_THEORY_S (the drift starts at t = 10 s, tests at 10.1, 12.1 …),
                            # at what time and offset will your guard refuse the GPS?
DRIFT_DOUBT_OFFSET_M = 0.0  # the run: the offset of the first spoofed GPS fix judged IN_DOUBT (m)
DRIFT_REFUSED_OFFSET_M = 0.0  # the run: the offset of the first spoofed GPS fix judged REFUSED (m)
EXPLAIN_DRIFT = ""          # compare with your prediction: why a little later / larger? who flies after the refusal?

# ---- Step 9: every attack (python3 spoof_run.py all) -------------------------------------------------------------
EXPLAIN_LIMITS = ""         # which attacks still win against your guard, and what do they have in common?

# ---- Step 10: live over ROS 2 (guard_node.py + python3 spoof_run.py drift --ros) ----------------------------------
ROS_REFUSED_T_S = 0.0       # ros_drift.json: the time t of the first change with gps_guard REFUSED (s)

# ---- Step 11: red team (python3 spoof_run.py creep --creep X) ----------------------------------------------------
CREEP_MAX_M = 0.0           # the largest creep offset (m) your guard never REFUSES (find it to the nearest metre or two)
EXPLAIN_CREEP = ""          # why is there such an offset, how does it compare with the test's radius, and what would
                            # make it smaller?

# ---- Step 12: look back (not graded; for you and your teacher) ---------------------------------------------------
LOOK_BACK = ""

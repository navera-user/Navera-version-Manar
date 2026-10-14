# Lab 27 — your answers. Numbers without quotes (N_ACCEPT_99 = 2). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Ellipse maker ========

# ---- Step 0: before reading anything ------------------------------------------------------------------------
PREDICT_INSIDE = ""         # a GPS states σ = 3 m (east and north, independent): how many fixes in 100 are within
                            # 3 m of the truth? one number and one reason

# ---- Step 1: the data (python3 run_uncertainty.py look) ----------------------------------------------------
PREDICT_CLOUD = ""          # from the ranges look prints: which axis is worse? correlated errors? sign of ρ?

# ---- Step 2: the cloud (python3 run_uncertainty.py cloud) ----------------------------------------------------
ELLIPSE_A_M = 0.0           # the long semi-axis of the 1-sigma ellipse (m)
ELLIPSE_B_M = 0.0           # the short semi-axis (m)
ELLIPSE_ANGLE_DEG = 0.0     # the angle of the long axis, from east towards north (degrees)
LONG_AXIS_BEARING_DEG = 0.0 # the same axis as a compass bearing, clockwise from north, in [0, 180) (by hand)
JUDGE_SIGMA_M = 0.0         # the judge's one σ, √max(a, c) (m)

# ---- Step 3: distances in sigmas (cloud again, then python3 chi2_sim.py) --------------------------------------
PREDICT_CIRCLE = ""         # before running: at k = 1 the judge's circle is bigger than the 1-sigma ellipse. At k = 3
                            # (circle of radius 3 × JUDGE_SIGMA_M against the 3-sigma ellipse), which holds more? why?
INSIDE_1SIGMA_PCT = 0.0     # the share of the 600 fixes inside the 1-sigma ellipse (%)
INSIDE_3SIGMA_PCT = 0.0     # the share inside the 3-sigma ellipse (%)
CIRCLE_3_PCT = 0.0          # the share inside the judge's circle, k = 3 (%)
SIM_P95 = 0.0               # chi2_sim.py: the d² that 95 % of your simulated errors stay below
EXPLAIN_CHI2 = ""           # why ~39 % inside the 1-sigma ellipse on a map, when ±1σ holds 68 % on one axis?
                            # and why is the 95 % threshold near 6, not 4? and why does the circle lose at k = 3?

# ---- Step 4: J P Jᵀ (python3 run_uncertainty.py radar, then radar wide) --------------------------------------
PREDICT_RADAR = ""          # by hand, before running: the long semi-axis a of the J P Jᵀ ellipse at 3 000 m, σβ 1° (m)
RADAR_A_M = 0.0             # a of J P Jᵀ (your polar_to_en) (m)
MC_A_M = 0.0                # a of the 20 000 draws (your sample_cov) (m)
PREDICT_WIDE = ""           # before "radar wide": with σβ = 10°, what share of the draws falls inside the 95 % ellipse?
WIDE_INSIDE_PCT = 0.0       # radar wide: the share of draws inside the 95 % ellipse of J P Jᵀ (%)
EXPLAIN_RADAR = ""          # why is the ellipse long ACROSS the line of sight? why does J P Jᵀ fail with 10°?

# ======== Session 2 — Gatekeeper ========

# ---- Step 5: the judge (python3 run_uncertainty.py judge) -----------------------------------------------------
PREDICT_JUDGE = ""          # before running, from judge.json only: which of A–F will a 99 % gate accept?
D2_A = 0.0                  # fix A's d²
N_ACCEPT_99 = 0             # how many of the six fixes your 99 % gate accepts
EXPLAIN_JUDGE = ""          # why is E refused although nearer than A? what would the never-grown predictor and the
                            # 160 m circle do, and what happens to the never-grown predictor next?

# ---- Step 6: the attacker (python3 run_uncertainty.py attack) -------------------------------------------------
PREDICT_ATTACK = ""         # by hand, before running: the longest and shortest offsets your 99 % gate accepts, and
                            # their bearings (lesson §5 and your ellipse)
ATTACK_MAX_M = 0.0          # the longest offset your gate accepts (m)
ATTACK_MIN_M = 0.0          # the shortest (m)
EXPLAIN_ATTACK = ""         # which direction does the attacker choose, why, which formula gives the two numbers?
                            # what would shrink the attacker's room, and at what cost?

# ---- Step 7: fusion (python3 run_uncertainty.py fuse) ---------------------------------------------------------
PREDICT_FUSE = ""           # before running: "fuse every pair" — smaller or larger RMS than GPS alone? why?
RMS_GPS_M = 0.0             # RMS error of GPS alone (m)
RMS_ALL_M = 0.0             # RMS error of "fuse every pair" (m)
RMS_GATED_M = 0.0           # RMS error of "gate, then fuse" (m)
COVER_GATED_PCT = 0.0       # coverage of "gate, then fuse" (%)
COVER_LIAR_PCT = 0.0        # coverage of "gate, then fuse — vision states 5 m" (%)
LIAR_REFUSED = 0            # good vision fixes refused by the gate when vision states 5 m
EXPLAIN_FUSE = ""           # why can fusing everything be worse than GPS alone although its p95 is better? what does
                            # the liar do to the coverage and to the gate?

# ---- Step 8: publishing (python3 run_uncertainty.py publish) --------------------------------------------------
STATED_SIGMA_M = 0.0        # the judge's σ for GPS alone at the canyon second (m)
WORST_SIGMA_M = 0.0         # the long semi-axis of that GPS ellipse (m)
FALSE_FIX_S = 0             # seconds where GPS alone is FIX while its long axis is longer than 25 m
EXPLAIN_PUBLISH = ""        # why do the two σ differ, how large can the difference get, what would you change?

# ---- Step 10: look back (not graded; for you and your teacher) ------------------------------------------------
LOOK_BACK = ""

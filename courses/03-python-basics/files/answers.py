# Lab 3 — your answers. Numbers without quotes (TRIP_MIN = 12.34). Text in quotes ("…"). Lists: [1, 2].
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Flight planner ========

# ---- Step 3: the wind triangle (your heading_for_track; plan_mission.py wind draws it) -------
PREDICT_WIND = ""       # heading to fly on the way out: left or right of 030°, by about how much?
OUT_HEADING_DEG = 0.0   # heading to fly, outbound (2 decimals)
OUT_GS_MPS = 0.0        # ground speed, outbound (m/s, 2 decimals)
BACK_GS_MPS = 0.0       # ground speed, back (m/s, 2 decimals)

# ---- Step 4: go / no-go (plan_mission.py gonogo gives the legs; you add them up) -----------
PREDICT_TRIP = ""       # with this wind, is the round trip longer, shorter or as long as in still air? why?
TRIP_MIN = 0.0          # round trip WITH the wind (min, 2 decimals)
ENDURANCE_MIN = 0.0     # the quad's endurance with its 20 % reserve (min, 2 decimals)
DECISION = ""           # "GO" or "NO-GO"
EXPLAIN_TRIP = ""       # why does the wind cost time on a round trip, although it helps on the way back?

# ---- Step 5: the wind limit (your own script my_limit.py) -----------------------------------
MAX_WIND_MPS = 0.0      # strongest wind from 020°, in 0.5 m/s steps, for which the quad is still GO
ANALYTIC_WIND_MPS = 0.0   # the same limit for a pure head/tailwind, solved by algebra (m/s, 2 decimals)

# ======== Session 2 — Fleet and track detective ========

# ---- Step 7: inheritance (python3 plan_mission.py fleet) -----------------------------------
WHERE_ENDURANCE_FROM = ""   # wing.endurance_s() runs the code of which class? (a class name)
SUPER_ERROR = ""            # the exception name when FixedWing's super().__init__(...) line is missing
EXPLAIN_SUPER = ""          # why that error? what did super().__init__(...) do?
WING_TRIP_MIN = 0.0         # the wing's round trip (min, 2 decimals)
PRINT_WING = ""     # what print(wing) shows
WHERE_REPR_FROM = ""     # whose __repr__ runs for print(wing)? (a class name)

# ---- Step 9: the harbour survey (python3 plan_mission.py track) ----------------------------
TRACK_POINTS = 0
TRACK_LENGTH_M = 0.0        # 1 decimal
MEDIAN_SPEED_MPS = 0.0      # 2 decimals
MAX_SPEED_MPS = 0.0         # 2 decimals
EXPLAIN_MEDIAN = ""         # why does the median describe this flight better than the mean or the max?

# ---- Step 10: the glitch hunt (python3 plan_mission.py glitch) -----------------------------
PREDICT_GLITCH = ""         # ONE wrong fix in the file: how many positions will glitches() list?
GLITCHES = []               # what glitches() returns at the quad's max speed (a list)
BAD_FIX_T_S = 0             # the time (s) of the WRONG fix
EXPLAIN_GLITCH = ""         # why does one wrong fix give that many entries?
FLAGGED_AT_15 = 0           # len(glitches(15)) on the harbour track
FLAGGED_AT_100 = None     # what tr.glitches(100) returns (the plane's limit)
EXPLAIN_THRESHOLD = ""      # why is the vehicle's max speed a better threshold than 15 m/s?
GLITCH_EXTRA_M = 0.0        # how many metres the wrong fix adds to the track length (1 decimal)

# ---- Step 11: a loop against NumPy (python3 plan_mission.py speed) -------------------------
PREDICT_SPEEDUP = ""        # how many times faster will speeds_mps() be than a Python loop?
SPEEDUP_X = 0.0             # the first "times faster" number printed

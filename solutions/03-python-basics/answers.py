# Lab 3 — your answers. Numbers without quotes (TRIP_MIN = 12.34). Text in quotes ("…"). Lists: [1, 2].
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Flight planner ========

# ---- Step 3: the wind triangle (your heading_for_track; plan_mission.py wind draws it) -------
PREDICT_WIND = "A little to the right of 030, maybe 5 degrees, because the wind comes from the left front."   # heading to fly on the way out: left or right of 030°, by about how much?
OUT_HEADING_DEG = 25.02   # heading to fly, outbound (2 decimals)
OUT_GS_MPS = 6.05   # ground speed, outbound (m/s, 2 decimals)
BACK_GS_MPS = 17.86   # ground speed, back (m/s, 2 decimals)

# ---- Step 4: go / no-go (plan_mission.py gonogo gives the legs; you add them up) -----------
PREDICT_TRIP = "About the same: the tailwind gives back what the headwind takes."   # with this wind, is the round trip longer, shorter or as long as in still air? why?
TRIP_MIN = 27.67   # round trip WITH the wind (min, 2 decimals)
ENDURANCE_MIN = 21.94   # the quad's endurance with its 20 % reserve (min, 2 decimals)
DECISION = "NO-GO"   # "GO" or "NO-GO"
EXPLAIN_TRIP = "The outbound leg is flown slowly against the headwind, so it lasts much longer; the tailwind leg back is fast but short in time, so the time lost out is bigger than the time gained back."   # why does the wind cost time on a round trip, although it helps on the way back?

# ---- Step 5: the wind limit (your own script my_limit.py) -----------------------------------
MAX_WIND_MPS = 2.5   # strongest wind from 020°, in 0.5 m/s steps, for which the quad is still GO
ANALYTIC_WIND_MPS = 2.70   # the same limit for a pure head/tailwind, solved by algebra (m/s, 2 decimals)

# ======== Session 2 — Fleet and track detective ========

# ---- Step 7: inheritance (python3 plan_mission.py fleet, then print(wing)) ------------------
WING_TRIP_MIN = 13.72   # the wing's round trip, with YOUR heading_for_track at 20 m/s (min, 2 decimals)
WING_DECISION = "GO"   # "GO" or "NO-GO" for the wing
WHERE_ENDURANCE_FROM = "Vehicle"   # wing.endurance_s() runs the code of which class? (ONE class name)
PRINT_WING = "FixedWing('wing', cruise 20 m/s)"   # the line print(wing) shows
WHERE_REPR_FROM = "Vehicle"   # whose __repr__ runs for print(wing)? (ONE class name)
EXPLAIN_REPR = "Vehicle's __repr__ writes type(self).__name__, and type(self) is the class of the object, FixedWing, not the class where the code is written."   # why does print(wing) say FixedWing, although that __repr__ ran?
SUPER_ERROR = "AttributeError"   # the exception name when FixedWing's super().__init__(...) line is missing
EXPLAIN_SUPER = "Without super().__init__ the Vehicle constructor never runs, so the object has no battery_wh or power_w attribute and endurance_s cannot read them."   # why that error? what did super().__init__(...) do?

# ---- Step 9: the harbour survey (python3 plan_mission.py track) ----------------------------
TRACK_POINTS = 263
TRACK_LENGTH_M = 3270.1   # 1 decimal
MEDIAN_SPEED_MPS = 12.05   # 2 decimals
MAX_SPEED_MPS = 54.34   # 2 decimals
EXPLAIN_MEDIAN = "One glitch at 54 m/s pulls the mean up and sets the max, but the median is the middle value and stays at the cruise speed of about 12 m/s."   # why does the median describe this flight better than the mean or the max?

# ---- Step 10: the glitch hunt (python3 plan_mission.py glitch) -----------------------------
PREDICT_GLITCH = "One position."   # ONE wrong fix in the file: how many positions will glitches() list?
GLITCHES = [150, 151]   # what glitches() returns at the quad's max speed (a list)
BAD_FIX_T_S = 150   # the time (s) of the WRONG fix
EXPLAIN_GLITCH = "The wrong fix makes two fast segments: the segment into it and the segment out of it back to the true track, so both positions 150 and 151 are reached too fast."   # why does one wrong fix give that many entries?
FLAGGED_AT_15 = 33   # len(glitches(15)) on the harbour track
FLAGGED_AT_100 = []     # what tr.glitches(100) returns (the plane's limit)
EXPLAIN_THRESHOLD = "At 15 m/s the honest noise of the GPS gives many false alarms; the quad physically cannot fly faster than its max speed of 20 m/s, so only real glitches pass that limit."   # what 15 m/s costs, what 100 m/s misses, why the vehicle's max speed
GLITCH_EXTRA_M = 90.9   # how many metres the wrong fix adds to the track length (1 decimal)

# ---- Step 11: a loop against NumPy (python3 plan_mission.py speed) -------------------------
PREDICT_SPEEDUP = "Ten times."   # how many times faster will speeds_mps() be than a Python loop?
SPEEDUP_X = 4.0   # the first "times faster" number printed

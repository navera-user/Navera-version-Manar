# Lab 13 — your answers. Numbers without quotes (SPEED_FILE = 12.5), True / False without quotes,
# text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Guard the knobs ========

# ---- Step 0: two traps, no code ------------------------------------------------------------
PREDICT_INT = ""          # what will `-p max_speed_mps:=30` do to the judge?
PREDICT_SET = ""          # after `ros2 param set /arbiter fix_max_sigma_m 2.0`, what will the verdict be?
SET_REPORTED_OK = None    # did `ros2 param set /arbiter fix_max_sigma_m 2.0` say it succeeded? True / False
STATE_AFTER_SET = ""      # the judge's state AFTER that set: "FIX", "DEGRADED" or "NO_FIX"
EXPLAIN_SILENT = ""       # why did the state not follow the new value?

# ---- Step 2: descriptors at work -------------------------------------------------------------
PREDICT_GUARDS = ""       # which of the three commands of Step 2 will be refused, and by which guard?
RATE_SET_OK = None        # ros2 param set ... rate_hz 5.0 accepted?            True / False
SPEED_500_OK = None       # ros2 param set ... speed_mps 500.0 accepted?        True / False
START_150_RUNS = None     # does the node start with -p speed_mps:=150.0?       True / False

# ---- Step 3: the callback, and the attacker ------------------------------------------------
BOAT_25_OK = None         # boat, then ros2 param set ... speed_mps 25.0 accepted?   True / False
ATTACK_SPEED = 0.0        # the speed_mps that `ros2 param get` shows after the attacker's start command
EXPLAIN_GUARDS = ""       # why did the callback not stop the attacker? which guard acts at start?

# ---- Step 4: an integrator's settings file -------------------------------------------------
N_INTEGRATOR_PROBLEMS = -1   # how many problems check_settings() finds in integrator.yaml

# ======== Session 2 — One command ========

# ---- Step 6: who wins? (speed_mps of /drone/fake_gps, from `ros2 param get`) ------------------
PREDICT_PRECEDENCE = ""   # your six predictions, before you run anything
SPEED_DEFAULT = 0.0       # command (a): no file
SPEED_FILE = 0.0          # command (b): --params-file my_gps.yaml
SPEED_FILE_THEN_P = 0.0   # command (c): --params-file my_gps.yaml -p speed_mps:=25.0
SPEED_P_THEN_FILE = 0.0   # command (d): -p speed_mps:=25.0 --params-file my_gps.yaml
SPEED_TWO_FILES = 0.0     # command (e): --params-file my_gps.yaml --params-file fast.yaml
SPEED_F = 0.0             # command (f): fast.yaml, then my_gps.yaml, then -p speed_mps:=30.0
EXPLAIN_PRECEDENCE = ""   # explain (c), (e) and (f) with the rows of lesson §3

# ---- Step 7: your launch file ----------------------------------------------------------------
PREDICT_NO_BOAT = ""      # use_boat:=false gps_source:=boat — what will the judge say?
NO_BOAT_STATE = ""        # the state it really shows: "STARTING", "FIX", "DEGRADED" or "NO_FIX"
EXPLAIN_REMAP = ""        # why that state, and why is it dangerous that nothing crashed?

# ---- Step 8: one speed for every vehicle (R-1) -------------------------------------------------
PREDICT_PLANE = ""        # a plane at 85 m/s, judged with the drone's 30 m/s: what happens?
PLANE_STATE_30 = ""       # the judge's state after 10 s, max_speed_mps 30.0
PLANE_STATE_100 = ""      # the same with max_speed_mps 100.0
EXPLAIN_R1 = ""           # what refused the plane's real GPS, and what would have caught the mistake earlier?

# ---- Step 9: change one setting --------------------------------------------------------------
PREDICT_SIGMA = ""        # fix_max_sigma_m 2.0, receivers stating σ 3 m: what state and message?
SIGMA_STATE = ""          # the judge's state with fix_max_sigma_m: 2.0
SIGMA_MESSAGE = ""        # its message, copied from `ros2 topic echo`

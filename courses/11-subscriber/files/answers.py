# Lab 11 — your answers. Numbers without quotes (GAP_SINGLE_MS = 250). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Memory ========

# ---- Step 0: a messenger that polls (python3 polling.py) ---------------------------------------
PREDICT_POLL = ""      # positions at 5 Hz, a 5 Hz timer forwards the latest one: will any be lost or sent twice?
DROPPED_5HZ = -1       # DROPPED with the defaults
DOUBLED_5HZ = -1       # DOUBLED with the defaults
DOUBLED_10HZ = -1      # DOUBLED with --poll-hz 10
EXPLAIN_POLLING = ""   # why does it happen (what does jitter do?), and why does forwarding on arrival fix it?

# ---- Step 4: a noisy drive (python3 run_trip.py drive) -----------------------------------------
PREDICT_NOISE = ""     # σ 3 m, one fix per second: the std of the speed over a 1 s window? over a 10 s window?
INSTANT_STD_MPS = 0.0  # cruising, window 1 s: std (m/s)
WINDOW_STD_MPS = 0.0   # cruising, window 10 s: std (m/s)
PARKED_INSTANT_MPS = 0.0   # parked, window 1 s: mean (m/s)
LAG_S = 0.0            # window 10 s: seconds after the stop until it reads below 1 m/s
EXPLAIN_WINDOW = ""    # what does the long window buy, and what does it cost? which one would you show a driver?

# ======== Session 2 — On the wire ========

# ---- Step 6: bad fixes on the wire (bad_fixes.csv through your trip node) ---------------------
PREDICT_TRIP = ""      # read bad_fixes.csv: how many fixes accepted, how many refused, and the last reason?
TRIP_FIXES = -1        # "fixes" in /navera_lite/trip at the end
TRIP_REFUSED = -1      # "refused"
TRIP_LAST_REFUSAL = "" # "last_refusal"
TRIP_DISTANCE_M = 0.0  # "distance_m"

# ---- Step 7: a blocking callback (python3 blocking_demo.py …) ----------------------------------
PREDICT_BLOCKING = ""  # fixes at 5 Hz, 0.3 s of work each, a 10 Hz timer, one thread: longest timer gap? fix age?
GAP_SINGLE_MS = 0      # mode single: longest timer gap (ms)
GAP_MULTI_MS = 0       # mode multi: longest timer gap (ms)
AGE_MULTI_S = 0.0      # mode multi: the max age of a fix when its callback started (s)
EXPLAIN_BLOCKING = ""  # why does multi rescue the timer but not the fixes? and what did shared show?

# ---- Step 8: the judge notices a silent GPS (status_listener.py) -------------------------------
PREDICT_SILENCE = ""   # arbiter v0 (gps_timeout_s 3.0, tick_hz 5.0): how long after the last fix's stamp is NO_FIX?
SILENCE_S = []         # the "GPS silent for … s" values you saw, e.g. [7.25, 7.31] (at least 2)
EXPLAIN_SILENCE = ""   # where do the numbers come from, which one spoke first each time (the judge or your trip node), and why?

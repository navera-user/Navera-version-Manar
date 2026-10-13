# Lab 9 — your answers. Fill each value, save (Ctrl+S), then press ✔ Check my work.
# Text between quotes "like this"; numbers without quotes (25.0); True / False with a capital letter, no quotes;
# lists in brackets: ["/a", "/b"].
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Map the graph ========

# ---- Step 0: the silent listener ---------------------------------------------------------------
PREDICT_SILENT = ""          # why could a listener hear nothing on a topic that exists and that echo can read?

# ---- Step 1: run a node from a package --------------------------------------------------------
MODULE_ERROR = ""            # the error NAME printed when you run arbiter_v0.py by its path (one word)

# ---- Step 2: read the code, then map the node --------------------------------------------------
PREDICT_SUBSCRIBES = ""      # from the code only, BEFORE `ros2 node info`: which topics will /arbiter subscribe to?
ARBITER_SUBSCRIBES = []      # its subscriptions, from `ros2 node info /arbiter` (leave out /parameter_events)
ARBITER_PUBLISHES = []       # its publications (leave out /parameter_events and /rosout)
EXTRA_PARAMS = []            # parameters of `ros2 param list /arbiter` that are NOT keys of navera_lite.yaml
EXPLAIN_LAG = ""             # a listing was empty/incomplete right after a start: why, and what do you do?

# ---- Step 3: message types ---------------------------------------------------------------------
STATUS_NO_FIX = None            # the value of NavSatStatus's constant STATUS_NO_FIX
NO_FIX_LEVEL = None            # the level NUMBER the arbiter puts in its status when the state is NO_FIX

# ---- Step 4: watch the judge -------------------------------------------------------------------
PREDICT_HZ = ""              # how many status messages per second? (tick_hz is 5.0)
STATUS_HZ = 0.0              # the average rate printed by `ros2 topic hz /navera_lite/status`
EXPLAIN_HZ = ""              # why that rate and not exactly tick_hz?
GATE_ALLOWED_M = 0           # arbiter.log, FIRST refused GPS fix: the distance the gate allowed (m)
EXPLAIN_GATE = ""            # why does the gate allow that much, and not 150 m?

# ---- Step 5: two judges ------------------------------------------------------------------------
STATUS_PUBLISHERS = 0        # "Publisher count" of /navera_lite/status with the second arbiter running
EXPLAIN_TWO_JUDGES = ""      # why does ROS allow it, and why is it dangerous for a subscriber?

# ---- Step 6: domains ---------------------------------------------------------------------------
OTHER_DOMAIN_SEES_STATUS = None   # True or False
EXPLAIN_ISOLATION = ""       # NAVERA's WEB-12: what could go wrong, and which two settings prevent it?

# ======== Session 2 — The silent listener ========

# ---- Step 7: offered vs requested, by hand (True = messages arrived, False = nothing arrived) -----
PREDICT_QOS = ""                     # your five guesses, BEFORE the experiments (e.g. "yes no ...")
BE_PUB_RELIABLE_SUB_RECEIVED = None  # A1: BEST_EFFORT publisher, RELIABLE subscriber
BE_PUB_BE_SUB_RECEIVED = None        # A2: BEST_EFFORT publisher, BEST_EFFORT subscriber
LATE_TL_RELIABLE_RECEIVED = None     # B1: late subscriber, TRANSIENT_LOCAL + RELIABLE
LATE_VOLATILE_RECEIVED = None        # B2: late subscriber, VOLATILE + RELIABLE
LATE_TL_BEST_EFFORT_RECEIVED = None  # B3: late subscriber, TRANSIENT_LOCAL + BEST_EFFORT
INCOMPATIBLE_POLICY = ""             # the policy named at the end of the WARN line in A1 (one word, as printed)

# ---- Step 9: the doctor on the live graph -------------------------------------------------------
LISTENER_REQUESTS = ""       # the reliability imu_listener requests (one word, as printed)
EXPLAIN_TEN = ""             # imu_listener never wrote "RELIABLE": where does it come from?

# ---- Step 10: the repair ------------------------------------------------------------------------
EXPLAIN_REPAIR = ""          # what you changed, and why in the SUBSCRIBER and not in the publisher

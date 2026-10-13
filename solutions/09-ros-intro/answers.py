# Lab 9 — your answers. Fill each value, save (Ctrl+S), then press ✔ Check my work.
# Text between quotes "like this"; numbers without quotes (25.0); True / False with a capital letter, no quotes;
# lists in brackets: ["/a", "/b"].
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Map the graph ========

# ---- Step 0: the silent listener ---------------------------------------------------------------
PREDICT_SILENT = "Maybe the listener uses another topic name or another message type, or it asks for a different QoS."   # why could a listener hear nothing on a topic that exists and that echo can read?

# ---- Step 1: run a node from a package --------------------------------------------------------
MODULE_ERROR = "ModuleNotFoundError"   # the error NAME printed when you run arbiter_v0.py by its path (one word)

# ---- Step 2: read the code, then map the node --------------------------------------------------
PREDICT_SUBSCRIBES = "The four fix topics navera_lite/fix/gps, day, night, celestial and the imu topic."   # from the code only, BEFORE `ros2 node info`: which topics will /arbiter subscribe to?
ARBITER_SUBSCRIBES = ["/navera_lite/fix/celestial", "/navera_lite/fix/day", "/navera_lite/fix/gps", "/navera_lite/fix/night", "/navera_lite/imu"]   # its subscriptions, from `ros2 node info /arbiter` (leave out /parameter_events)
ARBITER_PUBLISHES = ["/navera_lite/position", "/navera_lite/status"]   # its publications (leave out /parameter_events and /rosout)
EXTRA_PARAMS = ["use_eligible", "use_sim_time"]   # in `ros2 param list /arbiter`, not in navera_lite.yaml
EXPLAIN_LAG = "The first ros2 node list was empty because discovery takes a moment and the daemon had not seen the new node yet; I waited until its log said started and ran the listing again."   # why was a listing empty right after a start, and what did you do?

# ---- Step 3: message types ---------------------------------------------------------------------
STATUS_NO_FIX = -1   # the value of NavSatStatus's constant STATUS_NO_FIX
NO_FIX_LEVEL = 2   # the level NUMBER the arbiter puts in its status when the state is NO_FIX

# ---- Step 4: watch the judge -------------------------------------------------------------------
PREDICT_HZ = "5 per second, the tick rate."   # how many status messages per second? (tick_hz is 5.0)
STATUS_HZ = 5.6   # the average rate printed by `ros2 topic hz /navera_lite/status`
EXPLAIN_HZ = "The timer decides 5 times per second, and the arbiter also decides and publishes once more each time a fix arrives (on_fix calls step), so the rate is a bit above 5 Hz."   # why that rate and not exactly tick_hz?
GATE_ALLOWED_M = 950   # arbiter.log, FIRST refused GPS fix: the distance the gate allowed (m)
EXPLAIN_GATE = "The last trusted GPS fix was 9 s earlier because GPS was silent from 12 to 19 s, so the gate is 100 m/s times 9 s plus the 50 m margin = 950 m, not the 150 m of a 1 s gap."   # why does the gate allow that much, and not 150 m?

# ---- Step 5: two judges ------------------------------------------------------------------------
STATUS_PUBLISHERS = 2   # "Publisher count" of /navera_lite/status with the second arbiter running
EXPLAIN_TWO_JUDGES = "Topics are decoupled: a publisher does not need permission and nobody checks how many nodes publish on a name. A subscriber of the status then receives two answers mixed together and cannot tell which judge it is reading."   # why does ROS allow it, and why is it dangerous for a subscriber?

# ---- Step 6: domains ---------------------------------------------------------------------------
OTHER_DOMAIN_SEES_STATUS = False   # True or False
EXPLAIN_ISOLATION = "A simulator on the same network with the same domain could publish fake fixes that the estimator would take as real. A private ROS_DOMAIN_ID and ROS_LOCALHOST_ONLY=1 (loopback only) keep discovery inside the box."   # NAVERA's WEB-12: what could go wrong, and which two settings prevent it?

# ======== Session 2 — The silent listener ========

# ---- Step 7: offered vs requested, by hand (True = messages arrived, False = nothing arrived) -----
PREDICT_QOS = "A1 no, A2 yes, B1 yes, B2 yes, B3 yes"   # your five guesses, BEFORE the experiments (e.g. "yes no ...")
BE_PUB_RELIABLE_SUB_RECEIVED = False   # A1: BEST_EFFORT publisher, RELIABLE subscriber
BE_PUB_BE_SUB_RECEIVED = True   # A2: BEST_EFFORT publisher, BEST_EFFORT subscriber
LATE_TL_RELIABLE_RECEIVED = True   # B1: late subscriber, TRANSIENT_LOCAL + RELIABLE
LATE_VOLATILE_RECEIVED = False   # B2: late subscriber, VOLATILE + RELIABLE
LATE_TL_BEST_EFFORT_RECEIVED = False   # B3: late subscriber, TRANSIENT_LOCAL + BEST_EFFORT
INCOMPATIBLE_POLICY = "RELIABILITY"   # the policy named at the end of the WARN line in A1 (one word, as printed)

# ---- Step 9: the doctor on the live graph -------------------------------------------------------
LISTENER_REQUESTS = "RELIABLE"   # the reliability imu_listener requests (one word, as printed)
EXPLAIN_TEN = "A plain number in create_subscription is only the depth (KEEP_LAST 10); everything else comes from the default profile, which is RELIABLE and VOLATILE."   # imu_listener never wrote "RELIABLE": where does it come from?

# ---- Step 10: the repair ------------------------------------------------------------------------
EXPLAIN_REPAIR = "I passed SENSOR_QOS, a BEST_EFFORT request, to create_subscription. The IMU driver belongs to somebody else and a BEST_EFFORT request accepts both BEST_EFFORT and RELIABLE publishers, so the subscriber is the right place."   # what you changed, and why in the SUBSCRIBER and not in the publisher

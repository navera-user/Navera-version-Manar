# Lab 9 — answers. Fill each value, save (Ctrl+S), then press "Check my work".
# Every answer comes from a command you run in the lab (the step number is given).
# Text between quotes "like this"; numbers without quotes (3 or 1.5); True / False with a capital;
# lists in brackets: [1, 2] or ["/a", "/b"].

# ---- Step 1 — your domain
MY_DOMAIN_ID = None          # echo $ROS_DOMAIN_ID
DISCOVERY_PORT = None        # 7400 + 250 * domain

# ---- Step 2 — the talker, measured
CHATTER_TYPE = ""            # the `Type:` of /chatter, e.g. "package/msg/Name"
CHATTER_RELIABILITY = ""     # publisher's Reliability in `ros2 topic info -v /chatter`
CHATTER_DURABILITY = ""      # publisher's Durability
TALKER_HZ = None             # average rate from `ros2 topic hz /chatter`
CHATTER_MSG_BYTES = None     # "Message size mean" from `ros2 topic bw /chatter`, in bytes
DDS_PORTS = []               # the UDP ports printed by the `ss ... awk` command

# ---- Step 3 — one listener
CHATTER_SUBSCRIBERS = None   # subscription count with exactly one listener running (no echo)

# ---- Step 4 — domain isolation
OTHER_DOMAIN_SEES_CHATTER = None     # True or False

# ---- Step 5 — QoS experiments (True = messages arrived, False = nothing arrived)
BE_PUB_RELIABLE_SUB_RECEIVED = None  # BEST_EFFORT publisher, RELIABLE subscriber
BE_PUB_BE_SUB_RECEIVED = None        # BEST_EFFORT publisher, BEST_EFFORT subscriber
LATCHED_TRANSIENT_RECEIVED = None    # late TRANSIENT_LOCAL subscriber of /mission_start
LATCHED_VOLATILE_RECEIVED = None     # late VOLATILE subscriber of /mission_start

# ---- Step 6 — a service and an action
SERVICE_SUM = None           # the `sum` returned for a = your domain, b = 1000
FIBONACCI_8 = []             # the final `sequence` of the Fibonacci action with order 8

# ---- Step 7 — NAVERA's message constants
MODE_REPLAYED = None         # in navera_msgs/msg/PositionEstimate
STATE_FIX = None             # in navera_msgs/msg/NavStatus

# ---- Step 8 — NAVERA's arbiter
ESTIMATOR_SUBSCRIBES = []    # its 5 subscriptions (leave out /parameter_events and /rosout)
ESTIMATOR_PUBLISHES = []     # its 2 /navera/... publications
FIRST_STATE = None           # `state` in /navera/nav_status with no source running: the NUMBER
                             # printed after `state:` (0 = STATE_INITIALIZING, 1 = STATE_NO_FIX…)
NAV_STATUS_HZ = None         # average rate of /navera/nav_status
FIX_MAX_SIGMA_M = None       # double_value returned by the get_parameters service call

# ---- Quiz — write "a", "b" or "c"
# Q1. A GPS driver publishes BEST_EFFORT. Which subscription receives its messages?
#   a) only a RELIABLE one        b) only a BEST_EFFORT one        c) both kinds
Q1 = ""
# Q2. In domain 42, what is the discovery multicast port?
#   a) 7442        b) 17900        c) 10900
Q2 = ""
# Q3. A node restarts in flight and must learn that the mission has already started. Which QoS
#     makes the "mission started" message reach it without anybody sending it again?
#   a) BEST_EFFORT, depth 10
#   b) TRANSIENT_LOCAL durability on both sides, depth >= 1
#   c) RELIABLE, VOLATILE, depth 100
Q3 = ""

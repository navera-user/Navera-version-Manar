# Lab 9 — answers. Fill each value, save (Ctrl+S), then press "Check my work".
# Every answer comes from a command you run in the lab (the step number is given).
# Text goes between quotes "like this"; numbers are written without quotes, like 3 or 1.5.

# Step 1 — your ROS_DOMAIN_ID (a whole number, e.g. 123 — without quotes).
MY_DOMAIN_ID = None

# Step 3 — the message type of the topic /chatter, exactly as `ros2 topic info /chatter` writes it.
CHATTER_TYPE = ""

# Step 3 — how many messages per second the talker publishes (a number, from `ros2 topic hz`).
TALKER_HZ = None

# Step 4 — while the talker AND the listener run: how many subscribers does /chatter have?
CHATTER_SUBSCRIBERS = None

# Step 6 — in navera_msgs/msg/PositionEstimate, which number means MODE_REPLAYED?
MODE_REPLAYED = None

# Step 6 — in navera_msgs/msg/NavStatus, which number means STATE_FIX?
STATE_FIX = None

# Step 7 — the topics the NAVERA estimator SUBSCRIBES to (from `ros2 node info /estimator_node`).
# Write them in a Python list, e.g. ["/a", "/b"]. Leave out /parameter_events and /rosout.
ESTIMATOR_SUBSCRIBES = []

# Step 7 — the two NAVERA topics the estimator PUBLISHES (leave out /parameter_events and /rosout).
ESTIMATOR_PUBLISHES = []

# Step 7 — the `state` number in the first /navera/nav_status message, when no source is running.
FIRST_STATE = None

# Quiz — write the letter "a", "b" or "c".
# Q1. The talker publishes on /chatter. You start 3 listeners. What happens?
#   a) the talker must be changed to send its messages to 3 nodes
#   b) all 3 listeners receive every message; the talker does not even know they exist
#   c) only the first listener receives the messages
Q1 = ""

# Q2. Two students run the talker at the same time on this computer. Why don't they see each
#     other's messages?
#   a) because they have different ROS_DOMAIN_ID numbers
#   b) because topics are private to each terminal
#   c) because two talkers cannot run at the same time
Q2 = ""

# Q3. Which sentence is true about a ROS message type such as navera_msgs/msg/PositionEstimate?
#   a) it is free text: each node writes what it wants
#   b) it is a fixed list of named, typed fields: every node that uses it agrees on the format
#   c) it can only carry numbers
Q3 = ""

# Lab 13 — measured answers. Fill each value from the command given in the lab, save (Ctrl+S).
# Numbers without quotes (2.0), True / False with a capital letter.

# ---- Step 2 — runtime changes
RATE_SET_ACCEPTED = None      # `ros2 param set /fake_gps rate_hz 5.0`: accepted? (True / False)
SPEED_500_ACCEPTED = None     # `ros2 param set /fake_gps speed_mps 500.0`: accepted?
BOAT_FAST_ACCEPTED = None     # step 4: the boat, `ros2 param set /boat/fake_gps speed_mps 20.0`: accepted?

# ---- Step 5 — who wins? `ros2 param get /car/fake_gps rate_hz` in each experiment
RATE_CODE_DEFAULT = None      # no params file, no -p
RATE_FROM_FILE = None         # --params-file my_gps.yaml
RATE_FILE_THEN_P = None       # --params-file my_gps.yaml -p rate_hz:=4.0
RATE_P_THEN_FILE = None       # -p rate_hz:=4.0 --params-file my_gps.yaml

# ---- Step 7 — NAVERA's order trap: `ros2 param get /estimator_node gps_timeout_s`
GPS_TIMEOUT_YAML_1_PLAIN_LAUNCH = None   # YAML says 1.0, `ros2 launch navera_estimator estimator.launch.py`
GPS_TIMEOUT_YAML_1_RUN = None            # YAML says 1.0, `ros2 run navera_estimator estimator_node.py --ros-args --params-file <yaml>`
GPS_TIMEOUT_MY_LAUNCH = None             # YAML back to 3.0, your my_navera.launch.py

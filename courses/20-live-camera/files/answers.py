# Lab 20 — your answers. Numbers without quotes (FPS_LOG = 28.5). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Timekeeper ========

# ---- Step 0: a guess (no code) --------------------------------------------------------------------
PREDICT_ERROR = ""          # A plane 120 m above flat ground rolls at 40 °/s. Its program straightens each picture
                            # with the attitude it has when the picture ARRIVES, 0.10 s after the picture was taken.
                            # How far (metres) from the truth does it place the ground seen at the image centre?

# ---- Step 1: NAVERA's camera on the bench (python3 run_timing.py bench) ------------------------------
DECODE_MS = 0.0             # the decode time of one 1920 × 1080 frame on YOUR computer (ms, as printed)
CORES_ALL_FRAMES = 0.0      # how many CPU cores would decoding EVERY frame at 28.8 frames/s keep busy? (two decimals)
EXPLAIN_DECODE = ""         # why does a live camera program grab every frame but decode only the one it sends?

# ---- Step 2: frame statistics (TODO 1, python3 run_timing.py stats) ---------------------------------
FPS_LOG = 0.0               # the whole 60 s: mean frame rate (two decimals)
DROPPED_LOG = 0             # the whole 60 s: dropped frames
JITTER_40S_MS = 0.0         # jitter of the first 40 s (ms, two decimals)
JITTER_60S_MS = 0.0         # jitter of the whole 60 s (ms, two decimals)
EXPLAIN_JITTER = ""         # why does 20 more seconds almost double the jitter? Which number describes the camera's
                            # NORMAL rhythm, and which one the RISK?

# ---- Step 3: the flash bench (TODO 2, python3 run_timing.py flashes) --------------------------------
PREDICT_DELAY = ""          # before running: will the 20 delays be (almost) equal? If not, how far apart?
DELAY_MEDIAN_MS = 0.0       # the median delay (ms, one decimal)
DELAY_MIN_MS = 0.0          # the smallest delay (ms, one decimal)
DELAY_MEAN_MS = 0.0         # the mean delay (ms, one decimal)
UNSEEN_FLASH = -1           # the number of the flash the camera did not see
OUTLIER_FLASH = -1          # the number of the flash whose delay is far from all the others
EXPLAIN_SPREAD = ""         # why do the normal delays spread over about one frame period (≈ 35 ms), even on a
                            # perfect clock?

# ---- Step 4: choose the delay setting (no new code) -----------------------------------------------
LATENCY_SETTING_S = 0.0     # YOUR camera's delay setting (seconds, three decimals). Write the SAME value in
                            # camera.yaml (latency_s), and save both files.
EXPLAIN_LATENCY = ""        # how did you get it from the bench's numbers, and why not the median as it is?

# ---- Step 5: what a time error costs (TODO 3, python3 run_timing.py budget) -------------------------
BUDGET_300_M = 0.0          # 300 m above the ground, rotating at 30 °/s, a stamp wrong by ONE frame period
                            # (1/28.8 s): the ground error (m, two decimals)
DT_FOR_30M_S = 0.0          # 150 m, 25 °/s: how large a time error moves the image centre by 30 m (s, two decimals)
EXPLAIN_BUDGET = ""         # why does the same time error cost more at 300 m than at 150 m, and more in a turn than
                            # in straight, level flight?

# ======== Session 2 — The attitude at the exposure ========

# ---- Step 7: the plane's turn (TODO 4, python3 run_timing.py turn --latency 0.138, then turn) --------
PREDICT_METHODS = ""        # before running: rank the three attitudes (held at the grab, nearest sample to the
                            # exposure, slerp at the exposure) from the worst to the best
GRAB_MEDIAN_M = 0.0         # "held at the grab": median ground error (m, two decimals)
GRAB_MAX_M = 0.0            # "held at the grab": largest ground error (m, two decimals)
COPIED_MEDIAN_M = 0.0       # YOUR attitude_at with NAVERA's 0.138 s (turn --latency 0.138): median (m, two decimals)
MINE_MEDIAN_M = 0.0         # YOUR attitude_at with YOUR setting (python3 run_timing.py turn): median (m)
STRAIGHT_GRAB_M = 0.0       # python3 run_timing.py straighten: "held at the grab" — how far the centre lands (m)
EXPLAIN_TURN = ""           # when in the flight is "held at the grab" most wrong, and why then?

# ---- Step 8: refuse the frames you cannot trust (TODO 5, TODO 6, python3 run_timing.py turn) ---------
N_TURNING = 0               # frames refused with "turning …"
N_TILTED = 0                # frames refused with "tilted …"
N_NO_ATTITUDE = 0           # frames refused with "no attitude at the exposure"
EXPLAIN_REFUSE = ""         # the attitude is interpolated at the right instant: why still refuse a frame taken while
                            # the plane turns at 60 °/s?

# ---- Step 9: check the bench against the flight (python3 run_timing.py scan) -------------------------
BEST_LATENCY_S = 0.0        # the delay setting with the smallest median error (s, three decimals)
EXPLAIN_SCAN = ""           # compare it with your bench setting. Why can a real plane not do this scan?

# ---- Step 10: live, over ROS (python3 -m navera_lite.ros.camera_node …) ------------------------------
QUEUE_WAITED_S = 0.0        # with -p queue:=4: a typical "waited … s in the queue" value (s, two decimals)
EXPLAIN_QUEUE = ""          # the node subtracts the right delay: why is the attitude still wrong with a queue?

# ---- Look back (not graded) -------------------------------------------------------------------------
LOOK_BACK = ""

# Lab 16 — your answers. Numbers without quotes (PITCH_UP_DEG = -3.5). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Attitude reader (matrices and Euler angles) ========

# ---- Step 0: before reading anything ---------------------------------------------------------------
PREDICT_PITCH = ""          # a ROS message says pitch = +10°. Is the nose above or below the horizon? why?

# ---- Step 1: rot_y, rot_z (python3 run_rotations.py pitch) -----------------------------------------
PITCH_UP_DEG = 0.0          # ROS pitch = +0.12 rad: the pitch a pilot reads (positive nose UP), in degrees
EXPLAIN_PITCH = ""          # why does a positive ROS pitch move the nose that way? (axis, right-hand rule)

# ---- Step 2: the order of rotations (python3 run_rotations.py order) -------------------------------
PREDICT_ORDER = ""          # before running: A = rot_z(90°) @ rot_x(90°), B = rot_x(90°) @ rot_z(90°).
                            # where does the LEFT WING point in A? in B?
EXPLAIN_ORDER = ""          # are A and B the same attitude? which of them is "yaw 90° first, then roll 90°
                            # about the drone's NEW nose"? why? (write "A is …" or "B is …")

# ---- Step 3: gimbal lock (python3 run_rotations.py gimbal) -----------------------------------------
PREDICT_LOCK = ""           # before running: what will your matrix_to_euler_zyx return for the four attitudes?
LOCK_UP_YAW_DEG = 0.0       # your matrix_to_euler_zyx on (roll 30°, ROS pitch −90°, yaw 50°): the yaw, in degrees
NEAR_LOCK_YAW_JUMP_DEG = 0.0  # how much the yaw changed for a 1° turn near the lock (degrees)
EXPLAIN_LOCK = ""           # why do roll and yaw become one angle at pitch ±90°, and what did Apollo do about it?

# ======== Session 2 — Quaternion detective ========

# ---- Step 5: a real ROS orientation (python3 run_rotations.py pose …) ------------------------------
POSE_PITCH_UP_DEG = 0.0     # pitch_up of the orientation given in the lab (degrees, positive nose up)
POSE_HEADING_DEG = 0.0      # its heading (degrees clockwise from north)
Q360_W = 0.0                # the w of your q_from_axis_angle((0, 0, 1), 2π) — a full turn

# ---- Step 6: slerp (python3 run_rotations.py slerp) -------------------------------------------------
PREDICT_LERP = ""           # before running: at t = 0.2 of a 160° turn, how many degrees will the "linear"
                            # heading lag behind slerp's (0.1°, 1°, 5° or 20°)? why?
LERP_ERR_DEG = 0.0          # at t = 0.2: slerp heading − linear heading (degrees, with its sign)
EXPLAIN_SLERP = ""          # why does linear interpolation not turn at a constant rate?

# ---- Step 7: the oracle (python3 compare_oracle.py) -------------------------------------------------
EXPLAIN_ORACLE = ""         # why is agreement with SciPy stronger evidence than your own examples? and which
                            # convention did the comparison have to translate?

# ---- Step 8: the detective (python3 detective.py) ---------------------------------------------------
PREDICT_SUSPECT = ""        # before coding: what would each suspect (a), (b), (c) show on the pad row? which fits?
PAD_HEADING_DEG = 0.0       # the TRUE heading on the pad (t < 9 s), read correctly as (x, y, z, w)
COLLEAGUE_PAD_ROLL_DEG = 0.0  # the roll the colleague's table shows on the pad
COLLEAGUE_MAX_TILT_DEG = 0.0  # the largest tilt in the misread attitude
FLIP_T_S = 0.0              # the time (s) at which the four numbers of the log change sign (line 5)
EXPLAIN_DETECTIVE = ""      # the cause; what looks wrong; what does NOT look wrong, and why; and why the sign
                            # change at FLIP_T_S is not a bug

# ---- Step 10: look back (not graded; for you and your teacher) ---------------------------------------
LOOK_BACK = ""

# Lab 17 — your answers. Numbers without quotes (BEST_TAU_S = 3.0). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Drift hunter (gyroscope and gravity) ========

# ---- Step 0: before reading anything ---------------------------------------------------------------
PREDICT_REST = ""           # a drone sits still on a table. Its accelerometer's z reading: 0, +9.81 or −9.81 m/s²? why?

# ---- Step 1: the bias, measured on the pad -----------------------------------------------------------
GYRO_BIAS_DEG_S = (0.0, 0.0, 0.0)   # mean of gx, gy, gz while the drone sits on the pad (t_s < 10), in °/s, 4 decimals

# ---- Step 2: the gyroscope alone (python3 run_imu.py gyro) -------------------------------------------
DRIFT_FORECAST_DEG = 0.0    # before running: your z bias × 300 s = the size of the heading error you expect (degrees)
PREDICT_DRIFT_SIGN = ""     # before running: will the heading error be positive or negative? why?
GYRO_HEADING_ERR_DEG = 0.0  # run_imu.py gyro: the heading error at 300 s (degrees, with its sign)
CORRECTED_HEADING_ERR_DEG = 0.0   # run_imu.py gyro BX BY BZ (your bias): the heading error at 300 s
EXPLAIN_DRIFT = ""          # why is the sign what it is? what is left after you subtract the bias, and why?

# ---- Step 3: tilt from gravity (python3 run_imu.py tilt) ---------------------------------------------
PREDICT_SPEEDUP = ""        # before running: while the drone speeds up (10–20 s), will the accelerometer's pitch_up be
                            # the same as the truth, more nose-down, or less nose-down? why?
TURN_TRUE_BANK_DEG = 0.0    # the turn at t ≈ 99.8 s: the true roll (degrees)
TURN_ACCEL_ROLL_DEG = 0.0   # the same instant: the accelerometer's roll (1 s average, degrees)
EXPLAIN_TURN = ""           # why does the accelerometer report that?

# ======== Session 2 — Attitude engineer (fusion, compass, trust) ========

# ---- Step 4: choosing τ (python3 run_imu.py tau) -------------------------------------------------------
PREDICT_TAU = ""            # before running: which τ of 0.3, 1, 3, 10, 30, 100, 300 s will give the smallest tilt error? why?
BEST_TAU_S = 0.0            # the τ of the sweep with the smallest tilt RMS (seconds)
BEST_TILT_RMS_DEG = 0.0     # its tilt RMS (degrees)
EXPLAIN_TAU = ""            # what goes wrong with a small τ, and with a large τ?

# ---- Steps 5–6: compass and true north (python3 run_imu.py compass) -----------------------------------
DECLINATION_DEG = 0.0       # the declination at the log's place (degrees, east positive)
COMPASS_NO_TILT_RMS_DEG = 0.0   # true-heading RMS without tilt compensation (degrees)
COMPASS_TILT_RMS_DEG = 0.0  # true-heading RMS compensated with the TRUE roll and pitch (degrees)
EXPLAIN_COMPASS = ""        # why does the compass need the tilt?
CAPE_TOWN_SIDE_M = 0.0      # Cape Town, 15 Oct 2026: 5 km flown on the magnetic heading: how far to the side (m)?
CHIP_MEAN_ERR_DEG = 0.0     # the chip's attitude as delivered: mean of (its heading − true heading), degrees
EXPLAIN_NORTH = ""          # why is the chip's error about that number? why does q_true_north multiply on the LEFT,
                            # and what would multiplying on the right do?

# ---- Step 7: a frozen IMU (python3 run_imu.py stale) ---------------------------------------------------
PREDICT_STALE = ""          # before running "stale 5": what will a detector with max_repeat = 5 do on this file?
FROZEN_T_S = 0.0            # max_repeat = 50: the first time your detector says "frozen" (s)
SMALL_N_T_S = 0.0           # max_repeat = 5: the first time it says "frozen" (s)
EXPLAIN_STALE = ""          # why does a live sensor never repeat a sample exactly? why are fresh timestamps no proof?
                            # why 50 and not 5?

# ---- Step 9: look back (not graded; for you and your teacher) -------------------------------------------
LOOK_BACK = ""

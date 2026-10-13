# Lab 17 — your answers. Numbers without quotes (BEST_TAU_S = 3.0). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Drift hunter (gyroscope and gravity) ========

# ---- Step 0: before reading anything ---------------------------------------------------------------
PREDICT_REST = "Zero, because nothing moves."           # a drone sits still on a table. Its accelerometer's z reading: 0, +9.81 or −9.81 m/s²? why?

# ---- Step 1: the bias, measured on the pad -----------------------------------------------------------
GYRO_BIAS_DEG_S = (0.0636, -0.0321, 0.0946)   # mean of gx, gy, gz while the drone sits on the pad (t_s < 10), in °/s, 4 decimals

# ---- Step 2: the gyroscope alone (python3 run_imu.py gyro) -------------------------------------------
DRIFT_FORECAST_DEG = 28.4    # before running: your z bias × 300 s = the size of the heading error you expect (degrees)
PREDICT_DRIFT_SIGN = "Positive, the bias is positive."     # before running: will the heading error be positive or negative? why?
GYRO_HEADING_ERR_DEG = -28.42  # run_imu.py gyro: the heading error at 300 s (degrees, with its sign)
CORRECTED_HEADING_ERR_DEG = -1.75   # run_imu.py gyro BX BY BZ (your bias): the heading error at 300 s
EXPLAIN_DRIFT = "A positive z bias adds a turn to the left, so the yaw grows too fast and the heading (90° − yaw) becomes too small: negative. After subtracting the pad bias, what is left is the error of my estimate of the bias (500 noisy samples) times the time, plus the random walk of the noise."          # why is the sign what it is? what is left after you subtract the bias, and why?

# ---- Step 3: tilt from gravity (python3 run_imu.py tilt) ---------------------------------------------
PREDICT_SPEEDUP = "The same, gravity gives the tilt."        # before running: while the drone speeds up (10–20 s), will the accelerometer's pitch_up be
                            # the same as the truth, more nose-down, or less nose-down? why?
TURN_TRUE_BANK_DEG = 15.1    # the turn at t ≈ 99.8 s: the true roll (degrees)
TURN_ACCEL_ROLL_DEG = 0.9   # the same instant: the accelerometer's roll (1 s average, degrees)
EXPLAIN_TURN = "In a coordinated turn the thrust provides the centripetal acceleration, and the accelerometer only feels the thrust, which stays along the body z axis. So the specific force looks like gravity on a level drone and the roll reads almost zero."           # why does the accelerometer report that?

# ======== Session 2 — Attitude engineer (fusion, compass, trust) ========

# ---- Step 4: choosing τ (python3 run_imu.py tau) -------------------------------------------------------
TRACE_FIRST_ROLL_DEG = 7.5   # by hand, before coding TODO 3: the roll after the first step of its docstring example (degrees)
PREDICT_TAU = "3 s, because the turns last about 10 s."            # before running: which τ of 0.3, 1, 3, 10, 30, 100, 300 s will give the smallest tilt error? why?
BEST_TAU_S = 30.0            # the τ of the sweep with the smallest tilt RMS (seconds)
BEST_TILT_RMS_DEG = 1.85     # its tilt RMS (degrees)
EXPLAIN_TAU = "A small tau follows the accelerometer, which is noisy and fooled in turns and speed changes (tilt RMS 4.8° at 0.3 s). A large tau trusts the gyro longer, so its bias pushes the estimate away (up to b times tau) and the filter forgets errors slowly (2.7° at 300 s). The best tau is in between, where the sum of the two errors is smallest: 30 s on this flight."            # what goes wrong with a small τ, and with a large τ? why is the best τ in between?

# ---- Steps 5–6: compass and true north (python3 run_imu.py compass) -----------------------------------
DECLINATION_DEG = 3.35       # the declination at the log's place (degrees, east positive)
COMPASS_NO_TILT_RMS_DEG = 4.98   # true-heading RMS without tilt compensation (degrees)
COMPASS_TILT_RMS_DEG = 0.81  # true-heading RMS compensated with the TRUE roll and pitch (degrees)
EXPLAIN_COMPASS = "The field dips about 50 degrees, so it has a large vertical part. When the drone is tilted, roll and pitch mix that vertical part into the body x and y axes, and the horizontal direction moves although the drone does not turn."        # why does the compass need the tilt?
CAPE_TOWN_SIDE_M = 2254.5      # Cape Town, 15 Oct 2026: 5 km flown on the magnetic heading: how far to the side (m)?
CHIP_MEAN_ERR_DEG = -3.35     # the chip's attitude as delivered: mean of (its heading − true heading), degrees
EXPLAIN_NORTH = "The chip measures its heading from magnetic north, which is 3.35° east of true north here, so its heading is too small by D. The correction turns the world frame (the map) about the vertical, so it multiplies on the left; on the right it would turn about the drone's own up axis, which is the same only when the drone is level."          # why is the chip's error about that number? why does q_true_north multiply on the LEFT,
                            # and what would multiplying on the right do?

# ---- Step 7: a frozen IMU (python3 run_imu.py stale) ---------------------------------------------------
PREDICT_STALE = "It will find the freeze faster."          # before running "stale 5": what will a detector with max_repeat = 5 do on this file?
FROZEN_T_S = 13.34            # max_repeat = 50: the first time your detector says "frozen" (s)
SMALL_N_T_S = 5.08           # max_repeat = 5: the first time it says "frozen" (s)
EXPLAIN_STALE = "A live sensor has noise, so at least one of the nine numbers changes in its last digit at every sample. The timestamps kept coming every 0.02 s although the data was frozen, so fresh stamps prove nothing. With 5 the short read hiccup at 5 s already looks frozen (a false alarm); 50 waits one second, which is slower but does not trip on a hiccup."          # why does a live sensor never repeat a sample exactly? why are fresh timestamps no proof?
                            # why 50 and not 5?

# ---- Step 9: look back (not graded; for you and your teacher) -------------------------------------------
LOOK_BACK = ""

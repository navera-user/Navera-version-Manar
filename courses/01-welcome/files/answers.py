# Lab 1 — answers. Numbers without quotes (GATE_M = 123.4), text and letters in quotes (Q1 = "b").
# Save with Ctrl+S, then press ✔ Check my work.

# ---- Step 1: the computer ----------------------------------------------------------
ARCH = ""            # what `uname -m` prints (the processor architecture)
CPU_CORES = 0        # what `nproc` prints

# ---- Step 3: your NAVERA copy ------------------------------------------------------
GPS_TIMEOUT_S = 0.0      # gps_timeout_s in navera_estimator/.../config/estimator_params.yaml
FIX_MAX_SIGMA_M = 0.0    # fix_max_sigma_m in the same file
SOURCE_DAY_VISION = -1   # the number of SOURCE_DAY_VISION in navera_msgs/msg/PositionEstimate.msg

# ---- Step 4: the GNSS solver (gnss_fix.py) — 1 decimal is enough ------------------
BIAS_FOUND_M = 0.0       # "clock bias found" with the DEFAULT settings (8 satellites, 0.5 µs)
H_ERR_4_SATS_M = 0.0     # "horizontal error" with USE_SATELLITES = 4
RESID_4_SATS_M = -1.0    # "residual RMS" with USE_SATELLITES = 4
SPOOF_H_ERR_M = 0.0      # "horizontal error" with 8 satellites and SPOOF_EAST_M = 500.0
SPOOF_RESID_M = 0.0      # "residual RMS" in that same spoofed case

# ---- Step 5: the arbiter's GPS jump gate --------------------------------------------
# v_max = 100 m/s, margin = 50 m, the new GPS fix comes 2.0 s after the last trusted one.
# Beyond what distance (m) is the new fix refused?
GATE_M = 0.0

# ---- Step 7: quiz — write the letter --------------------------------------------------
# Q1. Why does a receiver need at least 4 satellites for a 3-D fix?
#   a) one per axis, plus one spare in case a satellite fails
#   b) the unknowns are x, y, z and the receiver clock bias
#   c) the 4th satellite gives the local time zone
Q1 = ""

# Q2. With exactly 4 satellites the residual RMS is 0.0 m. What does that tell you?
#   a) the fix is perfect
#   b) nothing: 4 equations for 4 unknowns always fit, so an error cannot be detected
#   c) the receiver is being spoofed
Q2 = ""

# Q3. A spoofer moved the fix 500 m east and the residual RMS stayed normal. Conclusion?
#   a) a consistent spoof looks like a normal fix: an independent source is needed to see it
#   b) the clock bias always reveals spoofing
#   c) spoofing is impossible with 8 satellites
Q3 = ""

# Q4. Real GNSS signals are recorded and re-broadcast with a delay. This attack is called:
#   a) jamming     b) multipath     c) meaconing
Q4 = ""

# Q5. Which NAVERA node decides which source's position is published?
#   a) gps_node     b) estimator_node (the arbiter)     c) vehicle_output_node
Q5 = ""

# Q6. How does NAVERA give its position to an ArduPilot autopilot?
#   a) like a GPS receiver would: NMEA sentences or the MAVLink message GPS_INPUT
#   b) it replaces the autopilot's firmware
#   c) through the operator web page
Q6 = ""

# Q7. GPS is jammed and day vision has a fresh match. Which state does NAVERA report today?
#   a) FIX     b) DEGRADED     c) NO_FIX
Q7 = ""

# Lesson 28 — short answers (graded by the check).

# Q1. GPS-off flight (campaign/off_target_events.log): the fault is injected at 12:53:26 and NAVERA
#     reports DAY VISION at 12:53:29. What is the switch latency in seconds (a number)?
#     (Compare with what campaign.py measured from the 1 Hz CSV — the report asks you to explain.)
Q1 = 0

# Q2. NAVERA keeps using the last GPS fix until it is stale (gps_timeout_s = 3 s). At the cruise speed
#     of 15 m/s, how far (m) behind the drone is a position that is 3 s old?
Q2 = 0

# Q3. The kinematic gate of the arbiter for the simulated drone (max_speed_mps = 30) between two
#     GPS fixes 0.2 s apart: the largest jump (m) that is still accepted?
Q3 = 0

# Q4. A GPS_INPUT with no altitude, no velocity (horizontal or vertical), no speed accuracy and no
#     vertical accuracy (so no VDOP either), but with a horizontal accuracy and an HDOP.
#     Value of ignore_flags (a number)?
Q4 = 0

# Q5. In the flight jam_camfail_target the GPS is used again 0 s after it comes back, not 2 s.
#   a) the GPS receiver was faster that time
#   b) there was no active source (NO FIX), and the hold-off only protects an active source
#   c) the recorder missed two rows
Q5 = ""

# Q6. Why can the simulator NOT measure the accuracy of NAVERA's day vision?
#   a) the vision errors are drawn by a profile, or the synthetic images are cut from the very map
#      vision matches against
#   b) ArduPilot SITL does not support cameras
#   c) the recording is only 1 Hz
Q6 = ""

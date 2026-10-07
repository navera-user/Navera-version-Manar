# Lesson 28 — answers.

# Set this to True ONLY if the teacher says the simulator cannot be used today:
# the checks about your own flight are then skipped, and you work on the recorded sample.
NO_SIMULATOR = False

# Q1. In the simulator, where does the ArduPilot autopilot get its position from?
#   a) from its own simulated GPS      b) only from NAVERA's output      c) from the simulator's truth
Q1 = ""

# Q2. On which port does NAVERA's operator view listen? (a number)
Q2 = 0

# Q3. Which file of ~/.navera_sim/ contains the arbiter's own "GPS refused: ..." lines? (a file name)
Q3 = ""

# Q4-Q6: the recorded SAMPLE flight (python3 flight_log.py --sample, and your functions).
# Q4. After the 60 s jam, the GPS receiver is OK again. How many seconds later does NAVERA use GPS
#     again? (use first_time() with `after=`)  — and which rule of lesson 25 explains the wait?
Q4 = 0

# Q5. The spoof was refused with "implausible jump 1994 m in 0.2 s (max 56 m at 30 m/s)".
#     What margin (m) did the arbiter add to 30 m/s x 0.2 s? (a number)
Q5 = 0

# Q6. The median NAVERA error while DAY VISION was used in the sample (m, one decimal), from median_error().
Q6 = 0

# Write the letter of your answer between the quotes, e.g.  Q1 = "b"
# Q4 to Q6: run the three attacks of spoof_real.py first and read real_*.txt / real_*_estimator.log.

# Q1. The GPS receiver says "no fix" for 30 s. Is it jamming or spoofing?
#   a) jamming: the receiver KNOWS it has nothing      b) spoofing: the receiver gives a wrong position
Q1 = "a"

# Q2. Top speed 30 m/s, margin 50 m. The last trusted fix was 2 s ago. What is the farthest
#     plausible new fix?   a) 60 m      b) 110 m      c) 2000 m
Q2 = "b"

# Q3. Why can the kinematic gate ALONE never catch a GPS pulled away at 4 m/s?
#   a) because 4 m/s is slower than the vehicle's top speed: every fix is "reachable"
#   b) because the gate only works at night
#   c) because the margin is too small
Q3 = "a"

# Q4. In real_jump.txt (vision of UNKNOWN accuracy), which words does the reason use when GPS is refused?
#   a) "GPS IN DOUBT"      b) "implausible jump"      c) "drifting away from day vision"
Q4 = "b"

# Q5. In real_drift.txt, what does the operator see FIRST, before GPS is refused?
#   a) NO_FIX      b) "GPS IN DOUBT" (GPS still used, DEGRADED)      c) nothing changes until the refusal
Q5 = "b"

# Q6. In real_jamspoof.txt, the spoofed GPS came back 2 km away after a 20 s outage, at a top speed of
#     100 m/s (so 2 km was "reachable"). What kept it out?
#   a) the kinematic gate      b) day vision, with a stated accuracy, disagreed      c) the hold-off
Q6 = "b"

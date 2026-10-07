# Write the letter of your answer between the quotes, e.g.  Q1 = "b"

# Q1. A GGA sentence has the fix quality 6. What does NAVERA's gps_node do with it?
#   a) it uses it: 6 is the best quality (RTK)
#   b) it publishes it as NOT valid: 6 is the receiver's own guess (dead reckoning), not satellites
#   c) it crashes
Q1 = "b"

# Q2. Fix A has HDOP 0.7, fix B has HDOP 4.0. Which sentence is true?
#   a) B is better: a bigger number is more precise
#   b) A is better: the satellites are well spread around the sky, the position is more precise
#   c) HDOP is the height of the receiver, it says nothing about precision
Q2 = "b"

# Q3. NAVERA's gps_node turns HDOP into an uncertainty (1 sigma) of:
#   a) HDOP x 2 m      b) HDOP x 100 m      c) nothing: it ignores HDOP
Q3 = "a"

# Q4. Why does NAVERA refuse every sentence whose checksum is missing or wrong?
#   a) to save electricity
#   b) a line damaged on the wire could become a wrong position, and the vehicle would believe it
#   c) because the checksum contains the time
Q4 = "b"

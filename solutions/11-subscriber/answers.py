# Lab 11 — your answers. Numbers without quotes (GAP_SINGLE_MS = 250). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Memory ========

# ---- Step 0: a messenger that polls (python3 polling.py) ---------------------------------------
PREDICT_POLL = "Same rate on both sides, so I guess nothing is lost; maybe a few doubles."
DROPPED_5HZ = 30
DOUBLED_5HZ = 30
DOUBLED_10HZ = 301
EXPLAIN_POLLING = ("The arrival times jitter, so sometimes no new position arrives between two ticks and the "
                   "timer sends the old one again (a double), and the next tick finds two and sends only the "
                   "newest (a drop). Forwarding in the callback, on arrival, sends each position exactly once.")

# ---- Step 4: a noisy drive (python3 run_trip.py drive) -----------------------------------------
PREDICT_NOISE = "About 4.2 m/s over 1 s and 0.42 m/s over 10 s (sqrt(2) x 3 / dt)."
INSTANT_STD_MPS = 4.11
WINDOW_STD_MPS = 0.40
PARKED_INSTANT_MPS = 5.51
LAG_S = 9.0
EXPLAIN_WINDOW = ("The 10 s window divides the same noise by a 10 times longer time, so the speed is about ten "
                  "times less noisy, but it describes the last 10 s: after the stop it needs about 9 s to show "
                  "zero, a delay. A driver wants the window speed; a parked car must not show 20 km/h.")

# ======== Session 2 — On the wire ========

# ---- Step 6: bad fixes on the wire (bad_fixes.csv through your trip node) ---------------------
PREDICT_TRIP = "Rows 5, 8, 11 and 14 look bad: 16 accepted, 4 refused, last one old fix."
TRIP_FIXES = 16
TRIP_REFUSED = 4
TRIP_LAST_REFUSAL = "old fix"
TRIP_DISTANCE_M = 190.0

# ---- Step 7: a blocking callback (python3 blocking_demo.py …) ----------------------------------
PREDICT_BLOCKING = "The timer waits for the 0.3 s callback, so gaps of about 300 ms; fixes pile up in the queue."
GAP_SINGLE_MS = 302
GAP_MULTI_MS = 101
AGE_MULTI_S = 1.97
EXPLAIN_BLOCKING = ("With two threads and two callback groups the timer runs on the free thread, so its gaps "
                    "stay near 100 ms. The fix callback is still alone in its mutually exclusive group and needs "
                    "0.3 s for fixes that come every 0.2 s, so the queue fills and the fixes are 2 s old. With "
                    "one shared group the second thread could not help: the timer waited again.")

# ---- Step 8: the judge notices a silent GPS (status_listener.py) -------------------------------
PREDICT_SILENCE = "Between 3.0 and 3.2 s: the timeout plus at most one 0.2 s tick."
SILENCE_S = [3.12, 3.04, 3.01]
EXPLAIN_SILENCE = ("No message arrives when the GPS stops, so only the arbiter's 5 Hz timer can notice: the "
                   "fix becomes stale after 3.0 s and the next tick, at most 0.2 s later, says NO_FIX. My "
                   "trip node checks its watchdog only once a second, so it says silent up to 1 s later.")

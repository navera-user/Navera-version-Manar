# Write the letter of your answer between the quotes, or a number where asked.

# Q1. In flight_measured (former day vision, ~440 m), during the 60 s jam, compare NAVERA with the
#     baseline (your results_flight_measured.json: median, p90 AND max). What is true?
#   a) NAVERA is far better than the baseline: at least two times smaller errors
#   b) NAVERA's median is only slightly better than the baseline's, and its max is worse: on this
#      jam, the method barely beats "doing nothing"
#   c) the baseline is better on every number
Q1 = "b"

# Q2. Why must the availability be reported next to the error statistics?
#   a) because it makes the numbers look better
#   b) because a system that gives a position only when it is easy can show a small error while being
#      unusable most of the time
#   c) because the autopilot needs it to fly
Q2 = "b"

# Q3. evaluate_session.py on shadow_bag: the day-vision source states sigma = 15 m. Is that honest?
#   a) no: far fewer than 86 % of its errors are within 2 sigma — it is too optimistic
#   b) yes: its errors match the stated sigma
Q3 = "a"

# Q4. In that table, the share (in %) of day-vision errors within 2 x the stated sigma. (a number)
Q4 = 59

# Q5. In that table, the "honest sigma" (in m) the tool suggests for this source. (a number)
Q5 = 21

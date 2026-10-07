# Reading the real code.  Open ~/navera/navera_estimator/navera_estimator/nodes/estimator_node.py
# and find the method (function) that does each job. Write its name between the quotes,
# exactly as it is written after `def`, for example:   Q0 = "_on_gps"

# Q1. Which method decides if a source is fresh ("alive") and eligible, with ONE rule for every source?
Q1 = ""

# Q2. Which method checks that the position is finite and the covariance is a real covariance
#     (finite, non-negative variances, symmetric, positive semi-definite)?
Q2 = ""

# Q3. Which method applies the priority list AND the switch hold-off?
Q3 = ""

# Q4. Which method turns the winner into FIX or DEGRADED (with the reason text)?
Q4 = ""

# Q5. Which method builds the one-clause explanation for ONE source that is not usable
#     ("GPS: stale (4.0s>3.0s)")?
Q5 = ""

# Q6. In estimator_params.yaml, how many seconds is the hold-off (switch_holdoff_s)? Write a number.
Q6 = 0

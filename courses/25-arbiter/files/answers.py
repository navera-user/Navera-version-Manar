# Reading the real code.  Open ~/navera/navera_estimator/navera_estimator/nodes/estimator_node.py
# (and its settings file config/estimator_params.yaml). Method names: write them exactly as
# after `def`, without `self.` and without parentheses, for example:   Q0 = "_on_gps"

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

# Q6. Which method is called at the END of _on_gps, _on_day, _on_night and _on_cn
#     (it is also called by the 5 Hz timer)?
Q6 = ""

# Q7. In estimator_params.yaml, how many seconds is the hold-off (switch_holdoff_s)? A number.
Q7 = 0

# Q8. In estimator_node.py itself (the declare_float lines), what is the DEFAULT day_timeout_s?
#     (The product runs with the yaml file, which overrides it. A number.)
Q8 = 0

# Q9. The GPS goes silent (no more messages). With the yaml settings, what is the LONGEST time
#     (s) from its last measurement until the arbiter has certainly stopped using it?
#     Think: freshness window + the longest wait for the next tick of the 5 Hz clock. A number.
Q9 = 0

# Write the letter of your answer between the quotes, or a number where asked.
# Base every answer on YOUR results (results_*.json, coverage.json) and on the tools' output.

# Q1. flight_measured (former day-vision error profile), 60 s jam. Your paired 95 % CI of
#     "CEP50 of NAVERA minus CEP50 of the baseline" (results_flight_measured.json, ci.diff_cep50_block).
#     What may you write?
#   a) NAVERA beats the baseline: its CEP50 is smaller (430 m against 452 m)
#   b) the interval contains 0: on this data we cannot claim that NAVERA beats "repeat the last
#      position" — the difference is within the sampling noise
#   c) the baseline is significantly better than NAVERA
Q1 = ""

# Q2. flight_selective is flight_measured with every vision position more than 300 m off removed.
#     Its jam CEP50 is much smaller. What is the honest reading?
#   a) withholding bad positions made the navigation better: report the smaller CEP50
#   b) the two flights cannot be compared at all
#   c) the error is computed on only the seconds that were kept; availability while jammed fell to
#      about a quarter and the longest gap is 13 s — accuracy and availability must be reported together
Q2 = ""

# Q3. Whole flight_measured: CEP50 about 5 m but RMSE about 390 m. What does this tell you?
#   a) the errors are a mixture (many GPS seconds at a few metres + a jam with errors of hundreds of
#      metres); one number for the whole flight hides it — report per phase
#   b) the RMSE is wrong: it should be close to 1.2 x CEP50
#   c) the CEP50 is wrong because of the outliers
Q3 = ""

# Q4. coverage.json: with correlated errors (rho = 0.9), the ordinary (iid) bootstrap CI contains the
#     true median far less often than 95 %. Why?
#   a) because B is too small: with B = 10 000 the coverage would be 95 %
#   b) because the median is not a good statistic
#   c) 60 correlated errors carry less information than 60 independent ones; the iid bootstrap
#      treats them as independent, so its interval is too narrow
Q4 = ""

# Q5. evaluate_session.py on shadow_bag: the day-vision source states sigma = 15 m. Is that honest?
#   a) no: far fewer than 86 % of its errors are within 2 sigma — it is too optimistic
#   b) yes: its errors match the stated sigma
Q5 = ""

# Q6. In that table, the share (in %) of day-vision errors within 2 x the stated sigma. (a number)
Q6 = 0

# Q7. In that table, the "honest sigma" (in m) the tool suggests for this source. (a number)
Q7 = 0

# Q8. The local feature matcher: "32/33 frames within 9 m". The LOWER end (in %) of the Wilson 95 %
#     interval of 32/33 (your wilson(), one decimal). (a number)
Q8 = 0

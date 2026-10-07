# Results — NAVERA during a 60 s GPS jam (simulated flights)

Replace every "(fill in …)" paragraph and every cell in parentheses or brackets with YOUR numbers
(from results_flight_*.json, rounded to the metre: "20 m", not "20.45 m"; CIs as "[18, 23]").

## What was measured

(fill in: which flights, where they come from and where they were flown, how long the GPS was
jammed, how many seconds of data — the sample size — and what is the truth.)

## Method

(fill in: the metrics you report and how they are computed — horizontal error, CEP50 / CEP95 by the
nearest-rank rule, RMSE, availability, longest gap — the baseline, and how the 95 % confidence
intervals were obtained: bootstrap, block length, paired or not, B, seed.)

## Results

| Flight | n (jam, s) | NAVERA CEP50 [95 % CI] | CEP95 | RMSE | max | Baseline CEP50 | CEP50 NAVERA − baseline [95 % CI] | Availability (jam) | Longest gap |
|---|---|---|---|---|---|---|---|---|---|
| target (15 m profile, not measured) | (s) | (m) [lo, hi] | (m) | (m) | (m) | (m) | [lo, hi] | (%) | (s) |
| measured (former day vision) | (s) | (m) [lo, hi] | (m) | (m) | (m) | (m) | [lo, hi] | (%) | (s) |
| selective (synthetic) | (s) | (m) [lo, hi] | (m) | (m) | (m) | (m) | [lo, hi] | (%) | (s) |

## Is the difference real?

(fill in: for each flight, does the CI of the difference exclude 0? What does that allow you to
write? Why a paired, block bootstrap? What does the coverage experiment say about trusting it?)

## Validity: simulation vs field

(fill in, 60 words or more: what these flights can and cannot show; where they were flown; what is
simulated; what a field test would need.)

## Conclusion

(fill in, 100 words or more: what is better, by how much, compared with what, on how much data,
measured where — and what it does NOT prove.)

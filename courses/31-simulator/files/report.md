# Lab 31 report — fault-injection campaign on NAVERA's mission simulator

Author: (your name)

<!-- Fill every section. Write in your own words, with the numbers from results.json.
     The check looks for the five headings below, about 350 words or more, and a few key numbers. -->

## 1. Set-up

(What was simulated: vehicle, route, vision profile(s), faults and their timing; which parts were
real software and which were simulated; where the data comes from.)

## 2. Results

(A table: one line per injected fault — flight, fault, switch latency, recovery latency,
availability, median / 95 % error, verdicts. Then the total: how many requirements PASS / FAIL.)

| Flight | Fault | Switch (s) | Recovery (s) | Availability | p50 / p95 (m) | Verdicts |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

## 3. Observations

(At least these three, each with numbers:
 a) GPS off: the switch latency measured from the CSV and from the events log — which is right, and why
    do they differ? Why is NAVERA's error larger in the first seconds of the outage?
 b) Spoof drift: how far did the drift drag NAVERA (gps_err_max_m) and the autopilot (ap_err_max_m)
    before the refusal? Compare with VALIDATION_STATUS.md ("refused at ~160–200 m").
 c) Target vision: the median error you measured during the jam vs the Rayleigh prediction
    (target_median_m) and the lagged Monte Carlo (lagged_median_m). Explain the difference.)

## 4. Fidelity

(What this campaign proves about NAVERA, and what it cannot prove. Be precise.)

## 5. Next campaign

(Two or three scenarios you would add, and why.)

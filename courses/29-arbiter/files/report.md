# Lab 29 report — the arbiter

<!-- Write in your own words, in full sentences. Quote the numbers you MEASURED
     (results.json, the tables printed by experiment.py and compare_real.py).
     Keep the five "## " headings. Each section: at least 40 words. Whole report: at least 350.
     These grey comments are ignored by the check; delete them if you like. -->

## 1. Hold-off

<!-- How many source switches per minute did the flapping GPS cause with h = 0 s and h = 2 s?
     How many seconds of eligible GPS were not used with h = 2 s? Which hold-off would you
     choose for a drone, and why? What does a hold-off cost when GPS is the better source? -->

TODO

## 2. Freshness

<!-- Day-vision availability with a window of 3 s and of 5 s (in %), and the number of dropouts.
     What is the largest error of using a stale fix at 40 m/s with T = 5 s? Is NAVERA's 5 s a
     good compromise in this model? What does NAVERA do so that the age of a vision fix does not
     become a 200 m error (hint: lesson text, "carried to the present")? -->

TODO

## 3. Selection or fusion

<!-- The fused sigma claimed by inverse-variance fusion, the TRUE sigma when the errors are
     correlated (rho = 0.8), and the fused position when GPS is spoofed 2000 m away.
     Give two reasons why NAVERA selects one source instead of fusing them today. -->

TODO

## 4. My arbiter against the real one

<!-- How many of the 11 decisions and how many of the source switches were identical?
     The largest difference between a real and your switch instant (s), and where it comes from
     (think: the 5 Hz clock, scheduling). One thing the real node does that your arbiter does not. -->

TODO

## 5. Limits

<!-- What do these experiments NOT show? (synthetic inputs, one seed, a model of flapping,
     no autopilot in the loop, ...) What would you measure next, and how? -->

TODO

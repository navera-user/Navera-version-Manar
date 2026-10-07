# Lab 4 — Flight-test campaign report

Write 2–5 sentences under each heading, in your own words, with numbers and units from
results.json and from what flight_analysis.py prints. Replace every "(write here)".

## Data cleaning

(write here) How many rows did the raw log have, how many duplicates and glitch rows did you
remove, and why must the NO_FIX rows with an empty position be kept?

## Flights

(write here) Compare the four flights: duration, distance, maximum altitude, logged mean speed.
Which numbers would you NOT trust, and why (look at tracks.png)?

## Outages

(write here) Number, longest and total outage per flight; which flight had the longest outage,
how long, and what share of its rows were DEGRADED or NO_FIX? Look at altitude.png.

## Speed check

(write here) Median and 95th-percentile difference between the logged speed and the speed
computed from positions, for gps and for day_vision. What does it tell you about the noise of
each source?

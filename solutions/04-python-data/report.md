# Lab 4 — Flight-test campaign report

## Data cleaning

The raw log had 1556 rows. I removed 3 exact duplicates written twice by the logger and 2
glitch rows: one fix at latitude and longitude 0 (Null Island) on the Monastir coast flight and
one altitude of 9999 m on the Sahel hills flight. 1551 rows are left. The NO_FIX rows have an empty
position but they are real moments of the flight: removing them would make the outages look
shorter than they were.

## Flights

The grid survey was the longest in distance (13.03 km in 720 s, mean logged speed
18.05 m/s, at 150 m). The Monastir coast flight covered 7.81 km, the Sousse port flight 8.79 km
and the Sahel hills flight 9.05 km at up to 251.5 m. The Sahel hills distance is too large: during
its long day-vision outage the positions are noisier, and the noise adds length. The Sousse port
distance is too small because the
steps across the NO_FIX gap are missing.

## Outages

The grid survey had one outage of 16 s and the Monastir coast flight one of 60 s. Sousse port had
2 outages, 160 s in total, the longest 100 s. The longest outage was on the Sahel hills flight
(sahel_hills): 416 s, from the
middle of the flight until landing; 40.5 % of its rows were DEGRADED and 2.3 % NO_FIX. Day
vision carried the drone home, but at the end even vision had no position.

## Speed check

For GPS rows, the median difference between the logged speed and the speed from positions is
0.77 m/s and the 95th percentile 2.28 m/s. For day vision it is 3.26 m/s and 7.80 m/s, about
four times more: vision positions are noisier, and a speed computed from two noisy positions
2 s apart amplifies that noise. Speeds from vision should be smoothed before they are used.

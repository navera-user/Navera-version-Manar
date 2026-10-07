# Lab 15 report — the synthetic Sousse drive

Name:

<!-- Replace every TODO line by your own sentences (at least 250 words in total).
     Quote the numbers from results.json and gps_node_counts.json. -->

## 1. Data quality

TODO: How many lines did is_valid() reject, and what kind of damage was each one (cut, flipped
character, missing checksum, garbage, glued, non-ASCII byte)? Which two lines passed the checksum
but were wrong (UTC times), and why could the checksum not see them?

## 2. Geometry and DOP

TODO: On how many seconds did you recompute the DOPs, and what was the largest difference with the
receiver? Give the median and the maximum HDOP. Where on the drive does HDOP spike, and why
(use dop_timeline.png and the sky plot idea of the course)?

## 3. Accuracy

TODO: Your UERE estimate, the fraction of fixes inside 2DRMS, and the median / 95 % horizontal
error. Compare your UERE with the 2 m that gps_node assumes. Is NAVERA's per-axis sigma
(2 m x HDOP) optimistic or conservative here, and by how much?

## 4. Outage and NAVERA's behaviour

TODO: The longest gap without an accepted fix (from, to, length) and what the receiver wrote during
it. What did NAVERA's real gps_node publish (valid / invalid counts and reasons)? Which line did
gps_node accept that your parser refused? Would the estimator's jump gate
(100 m/s x dt + 50 m) catch the two swapped-digit lines?

## 5. Recommendation

TODO: One or two changes you would propose for gps_node (or its configuration), with a reason
based on your measurements.

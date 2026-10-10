# Lab 28 — report

Write in your own words, in English, short sentences. Keep the four headings exactly as they are.
Each section: at least 40 words, and the numbers asked for, copied from YOUR `results.json` /
the output of `python3 analyse.py` (2 decimals is fine). Delete every TODO line when you are done.

## 1. The error ellipse

TODO: give the semi-major axis a, the semi-minor axis b and the direction of the major axis of the
1-sigma ellipse of the harbour receiver. Give the share of fixes inside the 1-sigma ellipse (%) and
compare it with the theory (39.3 %). Why would a CIRCLE describe this receiver badly?

## 2. Fusion and gating

TODO: give the d² of the good and of the bad vision fix and say what the gate did. On the coastal
track, give the RMSE with the gate and the RMSE without the gate (m), how many outliers were caught,
and how many good fixes were refused (false alarms). Is that number of false alarms what you
expect from a 99 % gate on about 320 fixes? Explain.

## 3. Consistency (NEES)

TODO: give the mean NEES of the gated filter and its 95 % band. Is the filter consistent? Use the
q sweep: what happens to the NEES and to the RMSE when q is too small, and when it is too large?
Why does a too-small q make the gate dangerous after the 40 s gap?

## 4. NAVERA

TODO: (a) result of race_navera.py: is your filter the same as NAVERA's height filter? RMSE of the
raw heights and of the filter. (b) NAVERA's vision gate refuses a fix when the distance is more
than 3 x hypot(sigma_pred, sigma_fix): with a round error, this is a chi-square test with 2 dof and
threshold 9. Give its probability in % (P(chi2_2 <= 9) = 1 - exp(-9/2)). (c) Give the sigma that
NAVERA's _stated_sigma() reads for the harbour covariance (sqrt of the larger diagonal term) and
compare it with a. What does that mean for a tilted ellipse?

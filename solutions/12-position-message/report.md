# Lab 12 — analysis

## Covariance

My default source states an ellipse of 15 m along and 6 m across a heading of 30°. Rotated into ENU
it gives [83.25, 81.84, 0, 81.84, 177.75, 0, 0, 0, 36] m². The determinant of the horizontal block is
8100 = (15 × 6)², and the eigenvalues 225 and 36 give back semi-axes of 15 m and 6 m at 30°. A
non-PSD matrix, like the not_psd fault with a correlation of 2, claims that the variance in some
direction is negative, which is impossible; the arbiter refused it as "non-finite position or
covariance" and the state became NO_FIX.

## Probability

With 100 000 samples, 0.394 of the errors were inside the 1-sigma ellipse (theory 0.393), 0.865
inside 2 sigma (0.865) and 0.950 inside 2.448 sigma (0.950). In one dimension, 0.682 of the east errors
were within one sigma_E. So "sigma = 15 m" for a 2-D position does not mean "usually within 15 m":
only about 39 % of the fixes are inside the 1-sigma ellipse, and the 95 % region is about 2.45 times
larger in every direction.

## Stated sigma

For tilted (30 m × 5 m at 45°) NAVERA's stated sigma is sqrt(462.5) = 21.5 m, below 25 m, so the
arbiter said "day vision fix" (FIX), while the ellipse's largest sigma is 30 m. big_sigma, a 30 m
circle, was DEGRADED ("uncertainty 30 m > 25 m"). The axis rule can under-state the worst direction by
up to a factor √2. I would use the largest eigenvalue for the FIX threshold: it is just as cheap to
compute, it does not depend on how the ellipse is oriented relative to north, and a green FIX should
promise the stated accuracy in every direction.

# Lab 28 — report

## 1. The error ellipse

The sample covariance of the 400 fixes in Sousse harbour gives a 1-sigma ellipse with a semi-major axis
a = 4.17 m and a semi-minor axis b = 1.52 m. The major axis points 29.8 degrees north of east. The
share of fixes inside the 1-sigma ellipse is 39.75 %, very close to the theory for a 2-D Gaussian
(39.3 %), and 95.5 % fall inside the 95 % ellipse. A circle describes this receiver badly because
the error is almost three times larger along one direction than across it: a circle large enough
for the long axis is far too pessimistic across it, and a smaller circle misses fixes along it.

## 2. Fusion and gating

The good vision fix has d² = 0.64, far below 9.21, so the gate accepts it and the fused ellipse
shrinks to 3.70 m by 1.50 m. The bad vision fix has d² = 27.35, so the gate refuses it and the GPS
estimate is kept. On the coastal track the RMSE with the gate is 4.48 m and the RMSE without the gate
is 11.31 m. The gate caught 6 of 6 outliers and refused 3 good fixes. With a 99 % gate we expect
about 1 % false alarms, so about 3 of 321 fixes: the result matches the theory. The price of fewer
false alarms would be a wider gate that lets more outliers in.

## 3. Consistency (NEES)

The mean NEES of the gated filter is 1.93, inside the 95 % band 1.80 to 2.21 for 361 steps, so the
filter is consistent: its covariance describes its real error. Without the gate the mean NEES is
12.31 because outliers pull the state while the covariance stays small. With q too small (0.003 or
0.03) the filter believes the drone flies straight, its covariance is too small, the NEES explodes
(536 and 55) and after the 40 s gap the gate refuses every true fix: the filter is lost for good.
With q too large (3 or 30) the NEES falls below 2 (pessimistic) and the RMSE grows a little
(4.91 m and 5.91 m) because the filter follows the noise.

## 4. NAVERA

My 1-D filter gives the same heights as NAVERA's VisionNavigator height filter: the largest
difference is about 3e-14 m, so it is the same filter. The raw heights have an RMSE of 2.94 m and the
filter 1.65 m. NAVERA's vision gate with 3 x hypot(sigma_pred, sigma_fix) is a chi-square test with
threshold 9 for 2 dof when the error is round: its probability is 98.89 %, close to our 99 % gate.
For the harbour covariance, _stated_sigma() reads sqrt(13.67) = 3.70 m, while the true semi-major axis
is a = 4.17 m. For a tilted ellipse the largest diagonal term underestimates the worst direction, so
the stated sigma is slightly optimistic; the eigenvalue would be the cautious choice.

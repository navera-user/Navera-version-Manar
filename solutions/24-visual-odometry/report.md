# Lab 24 — report

## 1. The odometer

My phase_shift windows both frames, divides the cross-power spectrum by its magnitude and finds the peak of its inverse
FFT, refined with a parabola. On the first leg it agrees with cv2.phaseCorrelate within 0.061 px on average
(MEAN_DIFF_PX), at most 0.15 px: the integer peak is the same, only the sub-pixel refinement differs. OpenCV is about
twice as fast (8 ms against 17 ms per step).

## 2. The drift

Along the first leg (1 020 m) the error grew to 47 m, a drift of 4.63 m per 100 m (DRIFT_BARO). The fit said the truth
is 1.032 times my step length and my steps point 2.01° clockwise: the barometer reads 3 % low (true height about
120 m) and the IMU heading is 2° too large. With the true height the drift fell to 3.51, with both corrections to
0.07 m per 100 m. Both are biases: they add up at every step and no better pixel measurement removes them.

## 3. The odometer race

A turn breaks phase correlation: by hand its limit is about 0.36°, and after 4° it found 1 pair of 8 (OK_PHASE_TURN4
= 1). Turned by the IMU heading change first, it found 8 of 8 at every turn. On the coast, phase correlation with the IMU
found 6 of 8 because it uses every pixel, while ORB found only about 6 matches per pair and 4 of 8 right. My PatchNet
was as precise as phase correlation on the city, but about ten times slower, and without the IMU its matches at 30° fell to 107 against 198 on the same frames derotated, past its
training range. Over the sea every method failed.

## 4. The navigator

Over the water the responses stayed below 0.030, while the right steps had at least 0.040, so I chose 0.035, a narrow
margin. The overlay steps had strong peaks at zero shift: the threshold cannot see them, but my gate refused all 7.
Without fixes the worst error was 52.6 m. With the map fixes the error became a saw-tooth and the worst was 18.9 m
(WORST_FUSED), at the end of the gap over the sea. The true error stayed within 2σ on 78 % of the frames (COVERAGE).
The misses are all at frames 20–39, right after two fixes that were 7.0 and 6.5 m off: unlucky fixes, not only a small
bias. One correlated flight is a hint, not a proof.

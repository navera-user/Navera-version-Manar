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

## 3. Six odometers

A turn breaks phase correlation: after only 4° it found 1 pair of 8 (OK_PHASE_TURN4 = 1), after 12° none. Turned by the
IMU heading change first, it found 8 of 8 at every turn, with a median error below 0.1 px. ORB keypoints with my
median_shift, or OpenCV's fit of a turn and a shift, also work, and my learned descriptor was as precise as phase
correlation, but it took about 100 ms per pair on the GPU against 13 ms. Over the sea every method failed.

## 4. The navigator

Over the water the responses stayed below 0.030, while the right steps had at least 0.040, so I chose 0.035. The
overlay steps had strong peaks (up to 0.46) at zero shift: the threshold cannot see them, but my gate refused all 7.
Without fixes the worst error was 52.6 m. With the map fixes the error became a saw-tooth and the worst was 18.9 m
(WORST_FUSED), at the end of the long gap over the sea. The true error stayed within 2σ on 78 % of the frames
(COVERAGE) instead of about 86 %: my stated σ was a little optimistic.

# Lab 24 — Report: visual odometry over NAVERA's Sousse map

## 1. FFT vs OpenCV

Mean and max difference between my phase correlation and `cv2.phaseCorrelate` on the 79 pairs: 0.171 px, 0.626 px.
OpenCV is faster (about 9 ms against about 24 ms per pair): it uses an optimised real-valued DFT in C++,
while my version uses complex FFTs in numpy. The integer peak is the same; only the sub-pixel part
differs, because I fit a parabola through 3 points and OpenCV takes a weighted centroid around the
peak. Both are approximations of a sinc-shaped peak, so a few tenths of a pixel of disagreement is expected.

## 2. Drift of the odometry

Drift with the barometer height: 3.43 m per 100 m. With the true height 114.25 m: 2.59 m per 100 m.
The barometer is 3 % low, so every step is 3 % short: a scale error that grows linearly with distance.
The rest comes mostly from the 2 degree heading bias of the north-up photos (sin 2 deg = 0.035,
so about 3.5 m sideways per 100 m on a straight line, partly cancelled along the curve), plus small
random pixel errors.

## 3. Random walk

Growth exponent with random errors only: 0.5; with a bias only: 1.0.
Random per-step errors grow like the square root of the number of steps, a bias grows linearly.
On a long flight the systematic errors (height, heading, scale) dominate; with sigma 0.5 m and a bias
of 0.1 m per step the bias wins after 2 sigma^2 / b^2 = 50 steps. Calibrating the bias is worth more
than measuring each shift more precisely.

## 4. Fusion with map fixes

Worst error with a fix every 10 frames: 10.3 m (odometry alone: 54.3 m).
The stated sigma grows like NAVERA's (10 % of each step + 1 m) and the 2-sigma band contains the
true error on 98.7 % of the frames, so it is honest (rather pessimistic between fixes).
At a fix the Kalman gain is close to 1 because the odometry sigma (about 30 m) is much larger than
the fix sigma (4 m): this is almost a reset.

## 5. NAVERA

FrameOdometry's drift on the same flight: 3.57 m per 100 m, with 0 steps refused — very close to mine.
In scenario B, VisionNavigator says "unavailable" from frame 29, when its stated sigma passes
max_sigma_m = 300 m. That is the right behaviour: a position with an unknown error must not be sent.
Its error (up to 149 m) is larger than my integrated odometry because it uses visual odometry only as a
velocity and carries the last fix in a straight line (no heading given here), while the path is a curve.

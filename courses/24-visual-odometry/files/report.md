# Lab 24 — Report: visual odometry over NAVERA's Sousse map

Write 2–5 sentences under each heading. Copy the numbers from the program outputs or from
`results.json` (the check compares them). Replace every placeholder (three dots) by your own
numbers and words.

## 1. FFT vs OpenCV

Mean and max difference between your phase correlation and `cv2.phaseCorrelate` on the 79 pairs: ... px, ... px.
Which one is faster, and why might the sub-pixel parts differ?

...

## 2. Drift of the odometry

Drift with the barometer height: ... m per 100 m. With the true height 114.25 m: ... m per 100 m.
Explain the difference with the scale error, and what causes the rest.

...

## 3. Random walk

Growth exponent with random errors only: ... ; with a bias only: ... .
What does this tell you about which errors matter on a long flight?

...

## 4. Fusion with map fixes

Worst error with a fix every 10 frames: ... m (odometry alone: ... m).
Is the stated 2-sigma honest (share of frames inside)? 

...

## 5. NAVERA

FrameOdometry's drift on the same flight: ... m per 100 m. In scenario B, VisionNavigator says
"unavailable" from frame ... . Is that the right behaviour? Why is its error larger than your integrated odometry?

...

# Lab 18 — Calibration report: Insta360 ONE R top lens

## 1. My calibration

All 36 views were detected (9x6 corners). OpenCV refused 2 views as ill-conditioned (f0023 and
f0208), so the fisheye calibration used 34 views. Result: fx = 670.3 px, fy = 732.4 px,
cx = 936.3 px, cy = 321.3 px, RMS = 0.506 px. My own reprojection_rms() gives exactly the same
RMS as OpenCV. NAVERA's calibrate_camera.py on the same folder gives the same numbers, because it
uses the same detector, flags and view order. The bench file says 660.5 px and 0.525 px from 38
views: fx differs by about 1.5 %, which is inside the spread measured in section 2.

## 2. Stability and hold-out

With random subsets of 8 views the standard deviation of fx was 18.9 px; with 30 views it was only
2.1 px. A calibration from a handful of views is therefore not reliable even when its RMS looks
good. In the hold-out test the train RMS was 0.474 px on 28 views and the test RMS 0.567 px on 8
views the calibration never saw. The train RMS is optimistic; the test RMS is the honest figure
for how well the model predicts new corners, and it is still well under 1 px.

## 3. Fisheye or Brown–Conrady

The Brown–Conrady fit gives RMS 0.545 px and a hold-out RMS of 0.570 px, almost the same as the
fisheye model. Both fit because the corners used lie within about 43 degrees of the optical axis,
where both polynomials can bend enough. Their parameters are very different (fx 738 px against
670 px) because focal length, distortion and board distance are correlated. In lens_curve.png the
two curves agree up to about 45 degrees and then separate completely: the Brown–Conrady curve
explodes towards 90 degrees, because it starts from tan(theta). For a 166 degree lens NAVERA must
use the fisheye model, which starts from r = f theta and can describe rays beyond 90 degrees.

## 4. The 111° crop

For a 1920 px wide straight picture, f = 960 / tan(hfov/2). At 111 degrees f = 659.8 px, which
keeps 99.9 % of the lens' centre resolution (fx = 660.5 px). At 150 degrees f = 257.2 px, only 39 %
of it, and the edges are stretched 14.9 times. At 166 degrees f = 117.9 px, only 18 %, with a
stretch of 67. At 150 m above ground the 111 degree view has a ground sampling distance of about
0.23 m per pixel. 111 degrees is the widest view that loses no centre detail, and it stays inside
the angles where the calibration is measured.

## 5. Recommendation

For a new unit calibrated in a partner's workshop in Singapore: (1) use a rigid flat board or a
screen, measure the square size with a ruler and give it in mm; (2) collect 30 or more sharp views, with the board
near every edge and corner of the picture and tilted up to about 45 degrees; (3) accept the result
only if the RMS is below 0.5 px and a hold-out test stays below 1 px; (4) calibrate at the exact
resolution and crop that NAVERA uses (--crop top for the Insta360), and (5) recalibrate after any
change of lens, resolution, crop or mounting that could move the sensor.

# Memo — the Insta360 lens, and how to calibrate a NAVERA unit

## Lens model

The bench calibration is measured only where its corners were: up to about 52° from the optical axis. Its
polynomial rises until 67.4° (825 px) and then turns back, so the outer pixels of the 1920 × 540 picture cannot be
described at all. For map matching NAVERA turns the fisheye picture into a pinhole view. The widest straight view
that keeps the lens' centre detail (f_new ≥ fx) is 110.94°, the 111° of the bench file: the centre keeps 99.9 % of
the detail and the edges are stretched 2.51 times. A 150° view would keep only 38.9 % of the centre detail, and its
edges would lie beyond the valid model.

## My calibration

From the 36 course views OpenCV refused f0023 and f0208, the two views that reach farthest to the right, so my
calibration used 34 views: fx 670.28 px, RMS 0.506 px, no corner beyond 43.0°. On 8 unseen views the error is
0.567 px against 0.474 px in training, which is honest and small. But fx moved by 38.9 px (std) between 8-view
subsets and still 3.4 px with 30 views, and it differs from the bench's 660.5 px by 1.5 %, because the views are not
the same and fx trades against the board distance. I trust it within about 45° of the axis; the edges of the 111°
view (55.5°) are not tested.

## Recommendation

1. Use a rigid, flat board (printed and glued, not a screen) and measure its squares.
2. Take at least 40 views, tilted in different directions, with corners near the left and right edges of the
   picture, up to 60° from the axis, and check that the calibration keeps them.
3. Accept the result only if the RMS is below 0.6 px, the hold-out RMS is close to it, and fx changes by less than
   1 % between two halves of the views.
4. Calibrate again after any change of resolution, crop, lens or camera, and record the crop and the camera's
   identity in the file.

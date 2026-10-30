# Filter memo — NAVERA Lite's Kalman part

<!-- 150 to 350 words, your own words. Keep the three headings. Quote your numbers with their units. -->

## Predict and update

The filter keeps a state and its covariance. The prediction moves the state with the constant-velocity model
and makes P grow by F P Fᵀ + Q: after 40 s without a fix the position σ grew from 3 m to 89.5 m. The update
blends the prediction with a measurement, weighted by their variances; through the covariance a height also
corrects the climb rate. My Height1D gave the same numbers as the reference to 10⁻⁹ m, and on the 131 heights
its RMS error was 1.832 m against 2.789 m for the raw heights.

## Choosing q and R

R is the variance each sensor states (σ²). q is the variance of the random acceleration: with climb_accel
0.05 m/s² the filter was late in the climb and worse than the raw data (3.098 m) while stating a small σ; with
5 m/s² it followed the noise (2.510 m). For the tracker I swept q and chose q = 0.3 m²/s⁴: the only value whose
mean NEES was inside the band, with the smallest error (4.69 m).

## Gate and honesty

The 99 % gate refused the 6 wrong fixes and 5 good ones; the mean NEES fell from 16.48 without the gate to 2.07,
inside my simulated band 1.80 – 2.21 for 361 steps. After the 40 s jam the filter stated 91.7 m and was really
103 m off: honest, so the first fix after the jam (d² = 1.40) was accepted. With q = 0.03 the filter was
overconfident, refused every fix after the jam and lost the track. A filter must be honest first, because its
gate and every user downstream trust its σ.

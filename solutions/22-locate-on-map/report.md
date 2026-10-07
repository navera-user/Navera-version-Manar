# Lab 22 report — locating drone photos on the map

## 1. Results

My pipeline accepted 10/13 photos (availability 77 %). The median error of the accepted photos is
0.26 m, the p90 is 0.71 m and the worst is 1.16 m. No wrong position was accepted (0 fixes beyond
50 m). Three photos were refused. p11 (2017 imagery) gave only 3 inliers: the town changed too much
in nine years, so refusing it is correct behaviour, although a better matcher could perhaps find it.
p12 is open sea: there is not a single keypoint, and "no fix" is the only honest answer. p13 has a
prior 1.2 km from the truth, so the true place is not inside the searched map: RANSAC fitted 2
inliers at a scale of 2.2, and both gates refused it. All three refusals are right.

## 2. Error budget

(a) With the true height of 200 m, assumed heights of 180, 200 and 220 m were accepted; 140, 160,
240 and 260 m were refused by the scale gate. The fitted scale was equal to h_true / h_assumed to
three decimals (for example 1.25 for 160 m). The position error stayed under 0.5 m whenever the photo
was accepted, because RANSAC fits the scale and the centre still lands on the right map pixel. A
wrong height therefore removes fixes (availability) but does not move them; the fitted scale even
measures the true height: 160 m x 1.25 = 200 m.

(b) A camera tilted by 5° and treated as straight down gave an error of 18.4 m, and h·tan(5°) =
17.5 m. At 2° it was 7.5 m (predicted 7.0 m), at 10° 36.3 m (predicted 35.3 m). The error grows
by about 3.5 m per degree at 200 m, so the attitude from the IMU must be good to a fraction of a
degree, and the frame must be straightened before matching.

(c) Worked case near Bangkok at 300 m: tilt 1.6 m, matcher 9.3 m, lag 2.0 m, map registration 5.0 m,
total 10.8 m (root sum of squares). The matcher term dominates. More inliers (a learned matcher, a sharper
map, zoom 18) would reduce it; the map term could be learned while GPS is still good, as
vision_nav.py does with its bias estimate.

## 3. My pipeline vs NAVERA's LocalMatcher

LocalMatcher accepted 8/13 photos with a median of 0.23 m, against 10/13 and 0.26 m for my
pipeline; neither accepted a wrong fix. LocalMatcher refuses p09 and p10 (2 and 5 inliers) because
it keeps at most 300 SIFT keypoints per 256 x 256 map tile, while my pipeline keeps every keypoint of
the patch. On 2022 imagery only a few keypoints survive, and the strongest 300 per tile are often not
them. Both took 2-5 s per photo on the sandbox CPU; LocalMatcher computes each tile once and caches
it, so on a real flight over the same area it becomes much faster (0.42 s per frame on the Jetson
CPU in VALIDATION_STATUS.md). On a drone I would use NAVERA's design (cached tiles, bounded memory)
with a learned matcher for cross-date photos, because my full-patch SIFT does not scale to bigger
search circles.

## 4. What these numbers do not tell

Photos p01-p08 are cut from the same imagery as the map, so matching is far too easy and the 0.2 m
medians say nothing about a real camera. VALIDATION_STATUS.md reports, for 33 real aerial frames from
another source and date, 32/33 within 9 m with a median of 4 m, and positions are stated at 30 m
until NAVERA's own camera is measured. My test also has no lens distortion, no haze and no motion
blur. Finally, 0 wrong out of 10 accepted photos does not prove the wrong-fix rate is zero: with the
rule of three, the 95 % upper bound is about 3/10 = 30 %. Hundreds of real frames are needed before
claiming a low rate.

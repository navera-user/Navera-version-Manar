# Lab 22 — analysis

## 1. Ratio test

On the `otherdate` pair (2022 photo against today's map) the ratio test decides almost everything.
At ratio 0.6 only 2 matches survive: no homography is possible (fewer than 4 pairs). At 0.8 there
are 37 good matches and 19 RANSAC inliers, so the inlier ratio w is about 0.51, and the centre is
1.0 px from the truth. At 1.0 (no ratio test) all 2000 nearest neighbours are kept, only 11 agree
on one model (w = 0.005), and the position is 364 px wrong: the outliers are so many that a
random group of them agrees better than the true matches.

## 2. Normalisation

In patch pixels (0 to 800) the DLT matrix A has a condition number of about 1e8 without
normalisation and 571 with it; the median error from 8 noisy pairs is 1.36 px against 1.35 px,
so it barely matters. In global zoom-18 tile pixels (about 3.55e7, the coordinates NAVERA's map
points use) the condition number grows to 8.5e17 and the raw DLT error becomes 25.3 px, while the
normalised DLT still gives 1.35 px. The columns of A mix numbers near 1 with products near 1e10,
so the smallest singular vector is lost in rounding errors; normalisation makes all columns of
similar size.

## 3. RANSAC iterations

With p = 0.99 and w = 0.5, a homography sample (s = 4) needs N = 72 samples, a similarity sample
(s = 2) only N = 17. With w = 0.3 the homography needs 567. The Monte Carlo test drew 72 samples
of 4 points 20 000 times and found an all-inlier sample in 98.99 % of the runs, which matches the
predicted 0.99. NAVERA fits a similarity on straightened frames: fewer points per sample means far
fewer samples for the same confidence, and a model with fewer degrees of freedom is harder to fit
to a group of wrong matches.

## 4. OpenCV vs mine

On the city both find 241 inliers, rotation 29.96 deg, scale 0.800 and a centre error of 0.19 px.
On the olives mine finds 341 inliers against 327, both within 0.4 px. On `otherdate` mine finds 22
inliers against 19, with a centre error of 1.34 px against 1.01 px. On the sea both refuse. Mine
is slower (about 0.8 s against 0.5 s including SIFT) because Python loops build A, and OpenCV
refines the final H with a non-linear least-squares step on the reprojection error, while my
refit only minimises the algebraic DLT error.

## 5. Trust gates

The ratio-1.0 match of `otherdate` had 11 inliers, so the inlier gate (8) alone would accept it.
It was refused by the rotation gate: 173 deg fitted against 120 deg expected. The scale gate is the
one NAVERA relies on most: in the benchmark of VALIDATION_STATUS.md, without the scale check a
match 1097 m off was accepted, with it no wrong match was accepted. A similarity score cannot be a
gate because NAVERA measured 0.95 to 0.98 for right and wrong places alike: it does not separate
them, while a geometric fit at the predicted scale and heading almost never happens by chance.

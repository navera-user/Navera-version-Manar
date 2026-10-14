# Lab 22 — report

## 1. Pairs and models

On the city pair SIFT gives 1500 nearest-neighbour pairs, but only 36.5 % of them are right. Lowe's ratio test at 0.8
keeps KEPT_08 = 571 pairs with a precision of 0.935: a point whose second-nearest descriptor is almost as close is
ambiguous and usually wrong. My similarity fits the sharp city pair to 0.11 px, but on the photo tilted by 15° its
median residual is 7.74 px: a perspective view is a trapezoid, which one scale and one turn cannot describe. The
homography fits it to RESID_H_TILT = 0.19 px, the same as OpenCV. It costs samples of four points instead of two.

## 2. RANSAC and the gates

With p = 0.99 and an inlier share of 0.2, a similarity needs 113 samples and a homography 2876. On the tilted pair the
formula with the measured share (w = 0.91) asked for only 4 homography samples, and one bad sample gave 5 inliers and
82 m of error: the formula assumes that every clean sample is good, so a margin is wise. With 500 samples my
homography placed the photo within 0.21 m. My gates refused the sea (no fit), the shaken olives (too few inliers),
the wrong place (scale off: 14 inliers at scale 0.00, which the prototype rule of 12 inliers would accept) and the
hills (scale off, although the match was right). Losing a right match costs one frame; accepting a wrong place cost
the prototype 1097 m.

## 3. Your network as a matcher

My network sees only upright patches at the map's scale, so the photo is turned with the prior heading first. On the
shaken olives SIFT finds 2 pairs, my network 47. My curve table showed that SIFT's 0.8 is not right for my network:
precision 0.843 against 0.946 at 0.7, for only 3.5 % fewer right pairs, so LEARNED_RATIO = 0.7, no distance cut. The
envelope shows it works up to a 20° heading error, only just at 30° on the city, and fails beyond: it was trained on turns of ±20°. It beats SIFT
on shaken olive groves (31 against 3 inliers), because its training pairs were blurred and noisy.

## 4. Your matcher's policy

SIFT first, because it needs no prior. When the gates refuse it and the heading σ is at most HEADING_LIMIT_DEG = 20,
my network tries. On the ten mission scenes it gave 5 right, 5 refused and no wrong position; the network rescued one
shaken olive grove. Everything here is drawn from a map: before trusting it on a drone I would measure it on real
frames from NAVERA's camera, with real blur, shadows and seasons.

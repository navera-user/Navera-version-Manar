# Memo — what NAVERA Lite's σ means, and what we do with it

<!-- 150 to 350 words, your own words. Keep the three headings. Quote YOUR numbers with their units. -->

## What our σ means

Our position comes with a covariance in m², east and north. It is an ellipse, not a circle: on our harbour
receiver it was 3.36 m by 1.53 m, tilted −57°. One sigma on a map is a weak promise: only 39 % of honest fixes
fall inside the 1-sigma ellipse (38.5 % measured), 95 % inside 2.45 sigma. Our judge prints one σ, the largest
diagonal term, which can be up to √2 shorter than the long axis: in the street canyon it said 22.8 m (FIX) while
the long axis was 29.3 m, for 64 seconds of the drive.

## When we refuse a position

We compare each position with what we expected, in sigmas: d² with S = our predicted covariance plus the
position's own. Above 9.21 (99 %) it is refused. This refuses 1 % of honest positions by design, and a
spoofer can still hide inside the ellipse, up to 182 m along our track after a 40 s outage but only 76 m
across. If our own covariance is too small we refuse the truth and stay locked out, so it must grow honestly
when nothing is measured.

## When we fuse, and when we must not

We fuse GPS and vision only after the gate. On a 400 s drive, fusing every pair gave an RMS of 33.3 m, worse
than GPS alone (19.0 m), because 24 wrong matches pulled it away; gate then fuse gave 12.1 m with a coverage of
93 %, close to the honest 95 %. When vision stated 5 m instead of 15 m the coverage fell to 75.5 % and the gate
refused 159 good fixes. So we fuse only honest, independent and gated sources.

# Star-fix memo — NAVERA Lite's star part

## The sky's clock and a star's place

The sky turns once in 23 h 56 min, so a star crosses the meridian 236 s earlier every night. From a UTC time I
compute the Julian date and the Greenwich sidereal time, then each star's hour angle, altitude and azimuth with
the navigational triangle. Catalogue positions are J2000: precession moved Vega by 10.6′ (about 20 km) by October
2026, so they are turned to the date first. Polaris alone gives the latitude within 70 km; with its hour angle,
within 0.8 km.

## From a photo to a position

My detector subtracts a local median background, keeps groups of 3 to 150 pixels above 5 robust σ and measures
brightness-weighted centres: 134 stars in photo 1, 0.17 px RMS from the truth. The plate solver identifies them
and gives the image centre on the sky. The IMU, turned to true north, gives the same direction in the local
frame. The altitude equation then has two roots; a prior within 5° keeps one, or none. Photo 3's asin root was
7 834 km away, and photo 6 gave no position because the prior could not choose.

## How good is it?

With a perfect attitude every fix was within 0.2 km. With the IMU's errors the median error was 116.9 km. One
degree of attitude costs 111 km; forgetting the 3.3° declination moved photo 1 to 314 km. For photo 1 my rule of
thumb says 82.6 km, the simulation 103.1 km RMS and 74.8 km median: the heading error dominates. A star fix is a
coarse check of the region, not a position to fly on.

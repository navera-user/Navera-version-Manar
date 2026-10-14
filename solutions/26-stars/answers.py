# Lab 26 — answer key (teacher). Values from python3 run_stars.py with the reference (make_expected.py).

PREDICT_SIDEREAL = "A little earlier: the sky turns once in 23 h 56 min, so the star comes back about 4 minutes before."
N_VOTE_STARS = 925
TRANSIT_SHIFT_S = 235.9
VEGA_SHIFT_ARCMIN = 10.62
VEGA_SHIFT_KM = 19.67
EXPLAIN_SIDEREAL = ("The Earth also moves about 1° along its orbit each day, so it turns about 361° relative to the "
                    "stars: the sky comes back 3 min 56 s earlier. For a fix the time sets the sky's rotation, so a "
                    "clock error moves the longitude east or west (15 arcseconds per second). Polaris is 0.6° from the "
                    "pole: one degree of ra there is only cos(89.3°) = 0.012° on the sky, so 8.8° of ra is a few "
                    "arcminutes.")
PREDICT_ACHERNAR = "90 - |-33.92 + 57.1| = 66.8 degrees at transit; 56 in the table, azimuth 144 (south-east): before its transit."
ACHERNAR_ALT_DEG = 55.96
ACHERNAR_AZ_DEG = 144.30
PREDICT_POLARIS = "Reykjavik, the highest latitude: what is left grows with tan of the latitude."
NAIVE_MAX_ERR_KM = 69.52
CORRECTED_MAX_ERR_KM = 0.782
EXPLAIN_POLARIS = ("Polaris is p = 0.63° from the pole, so its altitude is up to 0.63° x 111 km = 70 km from the "
                   "latitude. The correction p cos H puts it back on its circle around the pole. What is left are the "
                   "p squared terms, which grow with tan of the latitude: largest at Reykjavik.")
PREDICT_DETECT = "About 120 of the 121, the faintest may be lost; no hot pixels because they are only one pixel."
N_STARS_01 = 132
CENTROID_RMS_PX = 0.173
EXPLAIN_CENTROID = ("Weighting by the brightness above the background puts the centre where the light is, to a "
                    "fraction of a pixel; a plain mean of the lit pixels is pulled by the threshold. The size limits "
                    "refuse hot pixels (one pixel) and the aircraft trail (hundreds of pixels), and the local median "
                    "background keeps the stars of the glowing corner of photo 2.")
PREDICT_PIXEL = "More: at the centre one pixel is atan(1/f) = 1/1108.5 rad = 3.10 arcmin; pixels near the edge cover less sky."
SOLVE_RMS_ARCSEC = 30.0
PIXEL_ARCMIN = 3.10
TRACE_PSI_DEG = 29.19
MEDIAN_FIX_KM = 116.9
NO_FIX_PHOTO = 6
PERFECT_MAX_KM = 0.2
PREDICT_MAGNETIC = "3.3 x cos 66 x 111 = about 150 km."
MAGNETIC_ERR_01_KM = 313.7
MAGNETIC_MOVE_01_KM = 197.4
ONE_ROOT_ERR_03_KM = 7834.4
EXPLAIN_ROOTS = ("The altitude equation is R sin(phi + psi) = sin dec, and a sine takes each value twice, x and "
                 "180 - x: two places fit the same measurement. asin only returns x in [-90, 90]; for photo 3, looking "
                 "north, phi + psi is beyond 90 so the true root is the other one. In photo 6 the roots are too close "
                 "(or vanish with the IMU errors): both are within 5 degrees of the prior, so it cannot tell them apart.")
EXPLAIN_NORTH = ("Forgetting the declination turns the heading by about 3.3 degrees; the rule says 3.3 x cos 66 x "
                 "111 km = 150 km, the fix moved 197 km (heading errors are stretched, lesson 7). The error to the "
                 "truth is larger still because the IMU's own heading error adds in the same direction. At Tromso, "
                 "Cape Town and Quito the declination is larger (11, -27, -5 degrees), the roots fall beyond 5 "
                 "degrees of the prior and choose refuses them.")
PREDICT_BUDGET = "Close to the formula; the median a bit below the RMS."
FORMULA_KM = 82.6
MC_RMS_KM = 103.1
MC_MEDIAN_KM = 74.9
MOUNT_BIAS_MAX_DEG = 0.495
EXPLAIN_BUDGET = ("The 1.5 degree heading error dominates, even times cos 66. The median is below the RMS: an "
                  "error distance is never negative and the RMS squares the big ones (about 0.83 x RMS for round "
                  "Gaussian errors), and the spread is elongated (the stretched sideways part is about three times "
                  "the up-down part), which widens the gap. The formula assumes 1:1, but every sideways error is "
                  "stretched by cos lat / (cos dec * |cos H|) = 1.3 for photo 1, so the simulation is larger.")
LOOK_BACK = ""

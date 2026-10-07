# Lab 8 report — making a drone photo comparable with the map

## Convolution

My convolve2d() with a 7 x 7 Gaussian differs from cv2.filter2D by less than 0.0001 grey level,
which is float32 rounding, and my sobel() is identical to cv2.Sobel. A true convolution flips the
kernel; OpenCV's filter2D and Sobel compute a correlation, so I had to give my function the
flipped Sobel kernel, otherwise gx has the wrong sign: a road edge that gets brighter to the right
would give a negative gradient. My warp_affine() differs from cv2.warpAffine by 0.05 grey level on
average and at most 4 levels, because OpenCV rounds the source coordinates to 1/32 pixel. My
convolution is about ten times slower than OpenCV, which is acceptable for a lab but not on a drone.

## Preprocessing

The raw photo has a similarity of 0.063 with the map: nothing in common for a computer. After
make_like_map with normalise the similarity is 0.975 and the mean difference 18.4 grey levels.
Equalise gives 0.964 and 29.1, CLAHE 0.970 and 24.0. Equalisation changes the shape of the
histogram, so the pattern of light and dark stays (high correlation) but the grey values no longer
match the map, so the difference grows. Each image step must return uint8; warp_affine returns
float32, and forgetting to_uint8 gives float64 or float32 pictures that OpenCV refuses (CLAHE asserts
CV_8UC1) or saves with a warning.

## Geometry

The heading sweep finds the best similarity at 35 degrees and the scale sweep at 0.60 m per pixel,
exactly the true values in info.json. The similarity stays above 0.5 only between 25 and 45 degrees:
a heading error of about 10 degrees already destroys a pixel-by-pixel comparison. NAVERA therefore
needs the heading from its IMU and the height above ground before it prepares a frame, or it must
use a matching method that estimates rotation and scale itself, like the feature matching of later
lessons.

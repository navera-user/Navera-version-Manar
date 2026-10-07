# Lab 8 report — making a drone photo comparable with the map

<!-- Write 150-400 words in your own words. Keep the three headings exactly as they are.
     Quote numbers from results.json (python3 analysis.py). -->

## Convolution

<!-- How close are your convolve2d(), sobel() and warp_affine() to OpenCV's (max / mean
     differences)? Why does a TRUE convolution flip the kernel, and why does it matter for Sobel?
     How much slower is your version, and why is that acceptable here? -->

## Preprocessing

<!-- Similarity and difference with the map: raw photo, normalise, equalise, CLAHE. Which method
     gives the smallest difference, and why can equalise give a high similarity but a larger
     difference? Which dtype must each step return, and what happens if it does not? -->

## Geometry

<!-- The best heading and the best photo m/px found by the sweeps, compared with the true values in
     info.json. For which headings is the similarity above 0.5? What does that tell you about the
     accuracy NAVERA needs from its heading (IMU) and altitude before a match? -->

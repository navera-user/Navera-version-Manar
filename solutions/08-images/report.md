# Engineering note — making a drone photo comparable with the map

## Pixels and dtypes

The thermal frame holds 16-bit counts from 7150 to 8430. Cast directly with astype(np.uint8), every value
keeps only its remainder modulo 256, so the coldest pixel (7150) and the hottest (8430) both become 238:
they differ by 1280 = 5 × 256. The picture shows five bands of false contours and no real temperature
order. My normalise() works in float, maps the darkest count to 0 and the brightest to 255, and only then
rounds and converts, so nothing wraps. Rule: compute in float, then round, clip and convert to uint8, and
say in every function which dtype it returns.

## Filters

My convolve2d with a 7 × 7 Gaussian (σ 1.5) matches cv2.GaussianBlur to 0.00005 grey levels on the real
frame, and my Sobel (÷ 8) matches cv2.Sobel exactly, but my code takes about 230 ms where OpenCV takes
about 5 ms, roughly 45 times slower. A true convolution flips the kernel; OpenCV's filters correlate. For
the symmetric Gaussian this changes nothing, but for a derivative kernel a missing flip reverses every
sign: an edge that gets brighter to the right would come out negative.

## Photo to map

Compared with the map as it is, the photo scores an NCC of only 0.027. After like_map with the compass
heading (31°) it scores 0.746, and the heading sweep peaks at 35.0° with NCC 0.965, so the compass was 4°
off. The NCC stays at 0.9 or more only within about ±1.5° of the best heading, and within about ±2.3 % of the
best scale (0.60 m/px): a 5° heading error costs more than a 5 % scale error. A pixel comparison therefore
needs the heading to about a degree. With a worse compass a system must search over headings, or use a method
that estimates the rotation itself, such as feature matching. These NCC values are optimistic: the map and
the photo were drawn by the same renderer.

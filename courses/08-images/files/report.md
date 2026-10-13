# Engineering note — making a drone photo comparable with the map

<!-- Write 150–400 words in your own words, for an engineer of the NAVERA team. Keep the three headings
     exactly as they are. Quote your numbers with their units. Delete these comment lines if you want. -->

## Pixels and dtypes

<!-- What did the naive 16-bit → 8-bit cast do to the thermal frame (your two pixel values), and why?
     What does your normalise() do instead? One rule for every image function you write. -->

## Filters

<!-- How close are your blur and your Sobel to OpenCV's (largest difference), and how much slower?
     Why does a true convolution flip the kernel, and what would a missing flip do to an edge detector? -->

## Photo to map

<!-- The NCC of like_map with the compass heading, then at the best heading of your sweep. How wrong was
     the compass, and how close must the heading (and the scale) be for NCC ≥ 0.9? What does that mean for a
     system that compares pixels with a map, and why are these NCC values optimistic? -->

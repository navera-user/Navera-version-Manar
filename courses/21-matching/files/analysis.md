# Lab 21 — analysis

Write each section in your own words (at least 40 words each), with the numbers from your
`results.json`. Delete the lines that start with `>` when you have answered them.

## 1. Ratio test

> On the `otherdate` pair (ratio_sweep): how many good matches and inliers at ratio 0.6, 0.8 and 1.0?
> What is the inlier ratio w at each? At which ratio is the position wrong, and why?

## 2. Normalisation

> Condition number of A and median error of the DLT, with and without normalisation, in patch
> pixels and in global tile pixels. Explain why the raw DLT fails in global coordinates.

## 3. RANSAC iterations

> Give N for p = 0.99, w = 0.5 with s = 4 (homography) and s = 2 (similarity). What did the
> Monte Carlo test measure? Why does NAVERA's choice of a similarity help?

## 4. OpenCV vs mine

> Compare your RANSAC with cv2.findHomography on the four pairs: inliers, rotation, scale, centre
> error, time. Explain one difference you see.

## 5. Trust gates

> Which gates would have refused the ratio-1.0 match of `otherdate`? Which gate does NAVERA rely on
> most (see the benchmark table of the course), and why does a similarity score not work as a gate?

# Lab 20 — report

Write 40 words or more in each section, in your own words. Quote the numbers from YOUR results.json.
Replace every TODO.

## 1. Scale: Harris versus SIFT

TODO: compare the repeatability of Harris and SIFT on city_zoom4 (scale x3.9) and on city_rot35.
Why does Harris fall at x3.9? Even where Harris repeats well, why can't it be matched between a
map and a much closer photo? Compare with the chance level.

## 2. Descriptors: Hamming distances

TODO: give the median ORB Hamming distance for the same ground point and for random pairs. Explain
the value for random pairs (why near 128?). Would a threshold separate them?

## 3. Terrain and matchability

TODO: which terrains of the dataset are easy, which are hopeless (numbers)? Why can the olive grove be
hard even with thousands of keypoints? What did CLAHE do on the coast water?

## 4. World: where would day vision struggle?

TODO: a drone must fly across several continents by camera only. Discuss at least two real places (for
example Paris or Singapore, the Sahara or Namib dunes, the Alps or Andes, the open ocean, the Wadden Sea,
the Salar de Uyuni, Greenland): what texture would the camera see, and what would you expect from SIFT and from the matchability score?

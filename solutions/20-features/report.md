# Lab 20 — report

## 1. Scale: Harris versus SIFT

On city_zoom4 (the photo is 3.9 times closer than the map) Harris finds only 0.32 of its points again,
while SIFT keeps 0.79 (785 of every 1000). The chance level is 0.10, so Harris is still above chance but
weak. With its fixed window (sigma 1.5 px) Harris picks the small details of the close-up photo — windows,
parapets, cars — that do not exist at the map's 0.97 m per pixel. SIFT chooses a scale for each point, so
it detects the same structures at both resolutions. On city_rot35 (rotation only) Harris scores 0.64 and
SIFT 0.53: Harris is rotation invariant, and a sharp roof corner stays a corner. But Harris gives no
scale and no orientation, so it has no invariant descriptor: even repeatable corners could not be matched
between a 0.97 m/px map and a 0.25 m/px photo.

## 2. Descriptors: Hamming distances

For ORB descriptors of the same ground point (map patch and the photo turned by 35 degrees, 1126 pairs) the
median Hamming distance is 73 bits out of 256. For random pairs it is 127 bits. Unrelated descriptors
differ in each bit with probability about one half, so the expected distance is 256 / 2 = 128. The two
distributions are well apart, so a threshold around 90–100 bits removes most wrong pairs, but some true
pairs are above it and some random ones below it: a fixed threshold alone is not enough, which is why the
ratio test of lesson 21 compares the best and second-best candidates.

## 3. Terrain and matchability

SIFT finds 6628 keypoints on the medina, 5855 in the olive grove, 3993 on the farms and 2567 on the
dry hills, but only 4 on the coast water and 0 on the open sea. Matchability is 0.94 for the city, 1.00 for
the olives and 0.00 for both water patches; the blurry dark drone photo also scores 0.00. The olive grove
is hard despite its thousands of keypoints because the trees all look alike and stand in rows: repetitive
texture gives descriptors with near twins. CLAHE raised the keypoints on the coast water a lot, but they
sit on ripples and seagrass shadows that move and are not on the map.

## 4. Oman: where would day vision struggle?

Over Muscat, Sohar and the farms and palm groves of the Batinah coast the camera sees roofs, walls, roads
and field borders, like the Sousse medina: thousands of SIFT keypoints and a matchability near 1. The date
palms are a risk of repetitive texture, as the olives were. Over Wahiba Sands the dune ridges are low
contrast, repetitive and moving, and the map may be years old: few distinct keypoints, and the ones found
may not match. Over the sea off Masirah the score would be 0, like terrain_sea, and the coastline alone
gives an edge, not corners. In the Hajar mountains there is strong texture but the height above ground
changes quickly, so the scale is uncertain. Barr Al Hikman's mudflats are flat and change with the tide.

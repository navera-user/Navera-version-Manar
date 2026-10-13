# Lab 21 — report

## 1. The scout

I ranked the city first, then the olives, the coast, the fields, the salt pans and the sea. The measurement disagreed:
the olive grove has 13 504 SIFT keypoints, three times the city's 4 032, and the fields only 71, although they looked
textured to me. The sea gave 0 and the score said "too few features". The olives are a trap: thousands of trees that
look alike. The city had the best matchability, 1.00, against 0.81 for the olives.

## 2. The detector

After the 35° turn my Harris kept 0.85 of its points and SIFT 0.73, far above the chance level of 0.08. In the photo 4
times closer Harris fell to 0.39 while SIFT kept 0.78: the Harris window is fixed, so it finds small details that the
map does not show, while SIFT chooses a scale for each point.

## 3. Descriptors

For ORB descriptors of the same ground point the median Hamming distance was 61 bits, for random pairs 127. Unrelated
descriptors differ in about half of their 256 bits, 128. The gap lets a matcher keep the nearest descriptor and refuse
pairs whose distance is close to the random level.

## 4. The learner

I trained PatchNet on 12 288 pairs for 8 epochs on the GPU in about 14 s: both losses fell, the validation loss to
0.15. With 300 pairs the training loss fell to almost 0 but the validation loss stayed near 0.35 and rose after epoch
12: overfitting. On the 2 048 validation pairs the matching score was 0.756 for ORB, 0.875 for SIFT, 0.530 for the
untrained network and 0.957 for mine. It wins because it was trained on this kind of drawn views; before trusting it on
a real drone I would measure it on real camera frames against the map.

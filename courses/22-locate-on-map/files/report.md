# Lab 22 report — locating drone photos on the map

Write in your own words, in English, with the numbers from `results.json` and `budget.json`.
Replace every placeholder line by your own sentences (the check fails while one is left). Keep the
four headings exactly as they are.

## 1. Results

TODO: For YOUR pipeline: accepted photos written as "a/13", availability in %, median, p90 and
worst error in metres, and the number of wrong positions accepted (error > 50 m). Name the photos
that were refused and say, for each one, whether refusing it was the right answer and why.

## 2. Error budget

TODO: (a) Height sweep: which assumed heights were accepted? Compare the fitted and the expected
scale. Explain why a wrong height costs availability, not accuracy.
(b) Tilt sweep: the measured error at 5° next to h·tan(5°). What does this tell you about the IMU?
(c) The worked case (Bangkok): each term in metres and the total. Which term dominates, and what would you
change to make it smaller?

## 3. My pipeline vs NAVERA's LocalMatcher

TODO: Both results as "a/13" with their medians. Why does NAVERA refuse p09 and p10 when your code
accepts them? Compare the time per photo. Which design would you put on a drone, and why?

## 4. What these numbers do not tell

TODO: Why are the sub-metre medians optimistic? What does docs/VALIDATION_STATUS.md report for
real aerial frames? With 0 wrong fixes out of the accepted photos, what can you honestly claim
about the rate of wrong fixes (use the "rule of three" from the course)?

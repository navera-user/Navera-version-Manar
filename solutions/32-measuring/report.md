# Validation note — day vision during a GPS jam (lab 32)

Write this note as you would attach it to a validation document: numbers with their conditions, the
interval of every comparison, and what the note does NOT prove. Replace every "(fill in …)" paragraph and
every "…" cell with your own text and numbers (metres rounded to the metre, shares to the per cent).
The check reads the sections by their titles: keep the "## …" lines as they are.

## 1. What was measured

Three versions of one synthetic 240 s drone flight over the Sousse test area at 15 m/s, one row per second,
with the decisions of NAVERA Lite's judge (the course reference). GPS is jammed for 60 s (90–149 s). The truth
is the simulated true track. During the jam the judge uses day vision: a target profile, a retrieval-like
profile, and the retrieval flight with every position more than 300 m off withheld (selective).

## 2. Results

| During the jam | median (m) | 95 % CI of the median (m) | p90 (m) | availability (%) | longest gap (s) |
|---|---|---|---|---|---|
| flight_target, the judge | 12 | 10 to 17 (block) | 22 | 85 | 9 |
| flight_retrieval, the judge | 421 | 291 to 536 (block) | 758 | 100 | 0 |
| flight_selective, the judge | 236 | 218 to 260 (iid only) | 289 | 32 | 13 |
| baseline: last GPS position | 450 | — | 771 | 100 | 0 |

Paired difference median(judge) − median(baseline), blocks of 10 s, 95 % CI: target -674 to -170, retrieval -282 to 190

## 3. Is the difference real?

For the target flight the interval of the paired difference, -674 to -170 m, is entirely below 0: on these
seconds its vision is better than repeating the last GPS position, by at least 170 m. For the retrieval flight
the interval, -282 to 190 m, contains 0: the 29 m advantage is within the noise, so I cannot claim it beats the
baseline. The selective flight's interval excludes 0 only because it is computed on the 19 seconds it chose.

## 4. Is the stated accuracy honest?

The day source of the bag states a sigma of 15 m, but with the truth file its honest sigma is 23 m and only 58 %
of its errors are within 2 sigma instead of 86 %. The stated accuracy is too optimistic: the judge should state
at least 23 m for it, while GPS (honest 1.4 m against a stated 2 m) is cautious.

## 5. Validity and limits

All numbers are synthetic: simulated flights over Sousse with simulated vision error profiles, not measured with a
real camera or in the field. The errors are correlated from second to second, so 60 seconds carry far fewer
independent values; the block bootstrap helps but my coverage experiment shows it is still too narrow with 6
blocks. A confidence interval covers only the sampling noise of this one flight, not the difference between
simulation and real terrain, light, haze or another camera, and one route says nothing about other places.

## 6. Conclusion

On one synthetic 60 s jam over Sousse, the target vision profile kept a median error of 12 m (95 % confidence
interval 10 to 17 m) with an availability of 85 % and a 9 s gap over the lake, and it beat the baseline of
repeating the last GPS position by 170 m or more. The retrieval-like profile, median 421 m, is not shown to be
better than the baseline: the interval of the difference contains 0. Withholding its bad positions gives a
nicer median (236 m) but only 32 % availability and a 13 s gap, so it is not a better navigation. These are
simulation results on one flight; nothing here is measured on a real camera or in the field.

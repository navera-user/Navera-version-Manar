# Mission 29 — what the judge's choices cost

Write in full sentences, with YOUR numbers from `python3 experiment.py` (results.json). At least 40 words
in each section, 250 in all. Keep the four `## ` headings. The comments between `<!--` and `-->` do not count.

## 1. The hold-off
With no hold-off my judge changed its winner 31.10 times per minute on the flapping GPS: the output jumped
between GPS and day vision every two seconds. A 2 s hold-off cut that to 12.10 per minute, and 8 s to 0.80,
but the price grows fast: the GPS was eligible and unused for 228.8 s of the 600 s at 2 s, and its share fell
from 0.624 to 0.243. For a drone I would keep 2 s: it removes most zig-zags while a real GPS return is still
used after two seconds.

## 2. The freshness window
A 3 s window kept day vision usable 75.1 % of the time with 82 dropouts; 5 s gave 89.5 % and 24 dropouts.
The cost is age: with a 5 s window the oldest position used was 5 s old, a staleness of 200 m at 40 m/s,
against 120 m at 3 s. On a fast plane a long window needs the position carried forward to the present, or
its stated σ grown with its age.

## 3. Selection or fusion
Fusing GPS (2.5 m) with vision (20 m) claims a σ of 2.481 m, barely better than GPS alone. If the errors are
correlated with ρ = 0.6 the real σ is 2.658 m, worse than GPS alone while the output claims better. A GPS
spoofed 1500 m east drags the fused position 1476.9 m with it. Selecting one source keeps the output honest
and explainable; fusion becomes worth it only when each σ is measured and the correlations are known.

## 4. The door, the race and your design
My judge matched the reference live: 11 of 11 decisions and every switch within 0.35 s. The fix stamped in
the future is refused at the door and never stored, so it cannot block the honest fixes nor come back as
FIX. For a plane at 40 m/s I would keep a 2 s hold-off and a short window (3 s) with forward carrying,
because every second of age costs 40 m; for a harbour boat at 5 m/s a 3 s hold-off and a 6 s window are
fine, since 6 s of age is only 30 m. These experiments are synthetic: real gaps, real correlations and real
jammers may differ, and they say nothing about the accuracy of each source.

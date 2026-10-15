# Validation note — day vision during a GPS jam (lab 32)

Write this note as you would attach it to a validation document: numbers with their conditions, the
interval of every comparison, and what the note does NOT prove. Replace every "(fill in …)" paragraph and
every "…" cell with your own text and numbers (metres rounded to the metre, shares to the per cent).
The check reads the sections by their titles: keep the "## …" lines as they are.

## 1. What was measured

(fill in: which flights, how long, where, made how, how many seconds of jam, what the truth is)

## 2. Results

| During the jam | median (m) | 95 % CI of the median (m) | p90 (m) | availability (%) | longest gap (s) |
|---|---|---|---|---|---|
| flight_target, the judge | … | … | … | … | … |
| flight_retrieval, the judge | … | … | … | … | … |
| flight_selective, the judge | … | … | … | … | … |
| baseline: last GPS position | … | — | … | 100 | 0 |

Paired difference median(judge) − median(baseline), blocks of 10 s, 95 % CI: target …, retrieval …

## 3. Is the difference real?

(fill in: for each flight, does the interval of the difference contain 0, and what may you claim?)

## 4. Is the stated accuracy honest?

(fill in: the day source's stated σ, its honest σ, the share within 2 σ, and what the judge should do)

## 5. Validity and limits

(fill in: synthetic or real, simulation or field, correlated seconds, what a confidence interval does not cover)

## 6. Conclusion

(fill in: what is better, by how much, compared with what, on how much data, measured where — and what is not proved)

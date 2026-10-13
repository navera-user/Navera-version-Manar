# Flight-test campaign of 15 September 2026 — test report

Write 2–5 sentences under each heading, in your own words, with numbers and units from results.json
(`python3 run_logbook.py report`) and from what the runner prints. Replace every "(write here)" and keep
the five `##` headings. A reader who never saw the data must understand what was done and what to trust.

## Data and cleaning

(write here) How many rows did the raw log have? Which rules did you apply, how many rows did each one
remove, and how many rows are left? Why were the NO_FIX rows with an empty position kept?

## Corrections

(write here) Which labels of the data did not mean what they said? For each: the evidence (what you
compared, with numbers) and the correction applied. Say that the raw file was not edited.

## Outages

(write here) The outages per flight; the longest one (flight and duration, in seconds); which outages the
jamming plan explains and which one it does not (flight and UTC time). What did the judge report during
the outages (share of DEGRADED and NO_FIX rows)?

## Noise of the sources

(write here) For gps and for day vision: the robust σ of the speed error (m/s, two decimals), compared with
what the lesson's formula predicts (is the gap larger than the sampling scatter?); σ (std) and p95 too, and
why std and the robust σ differ so much for day vision.

## Limits

(write here) What can this campaign NOT tell you? (Synthetic data, sample sizes, one drone, the noise of
the logged speed itself, anything else you noticed.)

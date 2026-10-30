# Flight-test campaign of 15 September 2026 — test report

## Data and cleaning

The raw log had 1402 rows for four flights of the drone LITE-2. I applied three written rules in this
order: exact duplicates (3 rows, written twice by the logger), positions at latitude and longitude 0
("Null Island", 1 row on monastir_coast) and impossible altitudes outside −100 to 5000 m (1 row of 9999 m on
sahel_hills). 1397 rows are left. The 31 NO_FIX rows with an empty position were kept: they are real moments
when no source had a position, and dropping them would shorten the outages. dropna() would have lost 119 rows.

## Corrections

The sahel_hills log starts at 10:10:00 while the sheet gives its take-off at 09:10:00 UTC: exactly 3600 s,
so the logger kept local time (Tunisia, UTC+1); it also overlapped grid_survey, flown by the same drone. I
applied a clock correction of −3600 s to sahel_hills. On grid_survey the logged speed had a median of 71.9
while the positions gave 20.0 m/s, a ratio of 3.6, and 72 is above the drone's 30 m/s limit: the column
speed_mps was in km/h, so I multiplied it by 1/3.6 (0.2778). The raw files were not edited: the corrections
are written in answers.py and applied in code.

## Outages

monastir_coast had one outage of 60 s, grid_survey one of 16 s, sousse_port two (60 s and 100 s, 160 s in
total). The longest outage was on sahel_hills: 292 s, from 09:19:20 UTC until the landing, during the planned
long jamming. Every outage matches a jamming window except one: sousse_port from 08:27:00 to 08:28:40 UTC,
near the port, which the plan does not explain and must be investigated. During the outages the judge
reported DEGRADED (day vision) and, when even vision had nothing, NO_FIX: on sahel_hills 31.8 % of the rows
were DEGRADED and 2.6 % NO_FIX; on sousse_port 18.1 % and 6.0 %.

## Noise of the sources

With the corrections, the robust σ (1.4826 × MAD) of the speed error is 1.19 m/s for gps (1095 errors) and
3.75 m/s for day vision (224 errors). The lesson's formula predicts 1.10 and 4.25 m/s for position errors of
1.5 m and 6 m with 2 s between rows and 0.3 m/s of logged-speed noise: the right size. The gaps are +8 % for gps and −12 % for day vision. Forty
campaigns made the same way give 1.11 ± 0.03 and 4.1 ± 0.3 m/s: day vision's gap is ordinary sampling with
224 errors (the formula is also a little high when a 6 m noise is compared with a 20 m step), while gps's is
2 to 3 spreads, an unlucky campaign rather than a wrong formula, to check on the next one. For gps std is 1.19 m/s and p95 of |error| 2.17 m/s. For day vision std is
35.69 m/s and p95 9.19 m/s: four matches jumped 300 to 520 m, and their speed errors of up to 265 m/s
dominate std. The robust σ describes the typical noise; the jumps are real failures of the source and are
reported as the tail.

## Limits

The data is synthetic, made for the course, so the numbers describe the method, not NAVERA. The samples are
small (224 vision errors, five outages), with one drone on one day. The logged speed is not the
truth: its own noise is part of each error, and a speed computed from noisy positions is biased upward
(about +0.9 m/s for day vision at 10 m/s), so the day median error of +1.08 m/s is expected. The unplanned outage near the port has no explanation yet.

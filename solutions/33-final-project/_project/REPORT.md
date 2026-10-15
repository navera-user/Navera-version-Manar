# Project report — A held fix states a sigma that grows with its age

Teacher's example solution (idea 1 of the lesson's menu), flown with the course's NAVERA Lite.

## 1. The problem

During a GPS jam NAVERA Lite flies on day vision. A day fix is measured once per second and reaches the judge 0.3 s
later; the judge then keeps using it until the next one, or for up to 5 s when the camera sees nothing (the lake of
mission 32). All that time the fix states the σ of the instant it was measured, 15 m, although the drone has moved on
at 15 m/s. In my first exploring runs only about 70 % of the errors during the jam were within 2 × the stated σ,
where an honest round Gaussian gives 86 %: the judge says FIX with a σ that is too optimistic, the trap of mission 29
(stale fixes) and of NAVERA's held positions, which NAVERA reports as held or dead-reckoned with a growing accuracy.

## 2. Pre-registration

Hypothesis (project.json): if the sigma the judge states grows with the age of the fix, the share of errors within
2 sigma during a jam gets closer to the honest 0.86. Rule (committed with the red test and tagged before on
{BEFORE_DATE}): metric honest2 over the fault window, closer to the target 0.86 is better, statistic |mean − 0.86|
over the runs, minimum effect 0.02; guard-rail fix_share over the fault window, higher is better, may lose at most
0.10. Accept if the whole 95 % interval of D is below −0.02 and the guard-rail cannot lose more than 0.10.

## 3. The change

In navera_lite/arbiter.py a new function aged_sigma(sigma_m, age_s, speed_mps) returns √(σ² + (speed × age)²), and
Arbiter.step() states that σ instead of the source's own; the speed is a new setting age_speed_mps in
navera_lite/settings.py and navera_lite.yaml, 15 m/s, the drone's cruise speed (the top speed, 30 m/s, would be
too cautious). The old test test_step_states_and_switches pins the old σ of a 0.5 s old fix: it now runs with
age_speed_mps 0.0, because it tests the states and the switches, not the ageing. Commit {CHANGE_SHA}.

## 4. The red test

navera_lite/tests/test_ageing.py asks four things: a 2 s old fix with σ 15 m states 25 m at 10 m/s; a 1.5 s old fix
at 15 m/s states 27.0 m and is DEGRADED; speed 0 keeps the old σ; the setting exists in DEFAULTS and in the yaml. At
the tag before, 3 tests failed (the σ stayed 15.0, and KeyError 'age_speed_mps') and the speed-0 test passed, as it
should; after the change all 4 pass and the whole suite passes.

## 5. The campaign

Two scenarios of the course's simulator, campaign/jam.json (GPS jammed from 30 to 70 s) and campaign/lake.json (jam
from 30 to 75 s, camera blind from 45 to 48 s), each flown with seeds 1001 to 1020, never flown while exploring: 40
paired runs, flown once from the commit tagged before and once from the change, with the same seeds. The truth, the
GPS noise and the vision errors (the target profile, σ 15 m) are simulated.

## 6. Results

| | before | after | D = after − before | 95 % interval of D |
|---|---|---|---|---|
| metric: honest2, \|mean − 0.86\| | 0.0898 | 0.0582 | −0.0316 | [−0.0589, −0.0054] |
| guard-rail: fix_share (mean) | 1.000 | 0.969 | −0.031 | [−0.040, −0.022] |

The mean honest2 went from 0.770 to 0.918: from too optimistic to too cautious. The interval of D lies below 0 but
crosses −0.02, the minimum effect: a gain that matters is not shown. The guard-rail's interval lies entirely inside
the allowed loss of 0.10.

## 7. Decision

Inconclusive, by the rule written before the baseline: the distance to 0.86 moved by −0.0316 (95 % interval −0.0589
to −0.0054), and the interval crosses the minimum effect of 0.02, so these 40 runs cannot show the gain I asked for.

## 8. Limits

This is a simulation: one corridor near Sousse, a drone at 15 m/s, day vision drawn from the target profile, not a
real camera or matcher, no wind and no terrain. The after-share 0.918 overshoots 0.86: 15 m/s makes the σ of a
fresh day fix too large, because the drone does not always fly at cruise speed and the fix's own σ already holds part
of the lag. A next pre-registration, with a new block of seeds, could test a smaller speed or the speed measured from
the last two GPS fixes; a plane would need its own speed. The field would need recorded flights with a truth.

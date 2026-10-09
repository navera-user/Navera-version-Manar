# Mission 01 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Trilateration; the clock makes it a 4-unknown problem | §2, §3 (ship, atomic clock) | Steps 3–5 (TODO 3–4) | 4, 5, 11, 12 |
| 2. Least squares by brute force and Gauss–Newton | §2 check, §3 worked GN step | Steps 2, 6 (TODO 1, 2, 5) | 2, 3, 6, 13 |
| 3. Jamming noticed; full spoof not; partial spoof can be | §4 (jammer FSPL) | Step 7 (TODO 6) | 7, 14 |
| 4. Arbiter: priority, states, gate, cross-check and their failures | §5 (two checks) | Steps 1, 8–11 (TODO 7–9) | 1, 8, 9, 10, 15, 16, 17, 18 |

## Answer key

- Step 1: `V_MAX_MPS = 100.0`, `MARGIN_M = 50.0`, `GPS_TIMEOUT_S = 3.0`.
- Step 4: `CLOCK_ERROR_M` = 141 (grid answer (3.1, 4.1), minimum mismatch 0.256). The continuous
  least-squares optimum without bias is (3.071, 4.090), about 115 m. The check accepts 100–150.
- Step 5: 1 guess fits with A, B, C; 36 with A and B only. `CURVE = "hyperbola"`: for every fitting point,
  dA − dB = ρA − ρB (the common bias cancels), the definition of a hyperbola with foci A and B. This is
  the principle of TDOA / LORAN navigation.
- Step 6: from (5, 5, 0), mismatch 0.316 → 3.4e-5 → 8.4e-13: `GN_STEPS = 3` (2–4 accepted). Brute force
  ≈ 0.7 s, Gauss–Newton ≈ 1 ms on the Jetson. The result (3.0002, 4.0001, 0.2998) is not exactly (3, 4, 0.3)
  because the ranges are rounded to 1 m.
- Step 7: full spoof → (7, 2), b 0.3, mismatch 0, 4 472 m from the truth. Partial (A, B, C faked, D real)
  → (6.82, 1.67), b 0.41, mismatch 0.129: detectable by redundancy (RAIM idea), yet still 4.5 km wrong.
- Step 8: attack A (300 m jump) → 2 refused; attack B (20 m/s drag) → 0.
- Step 9: `gps` / `DEGRADED`: GPS is 2 s old (fresh), first in priority, σ 35 m > 25 m. Day vision is also
  DEGRADED (σ 30 m), which is not the point: priority decides the source.
- Step 10: `FLIGHT_REFUSED = 0`, `CAUGHT_AT_S = 450` (GPS and vision 391 m apart). The spoof starts at
  t = 250 s over the sea, dragging 2 m/s north; vision has no match from 200 to 449 s.
- Step 11: `STEALTH_SPEED_MPS = 150`; `REFUSED_ONE_FASTER = 60` (a too-fast drag is locked out entirely:
  every fix stays out of reach of the last trusted one). Defender with v_max 15 on the honest GPS (t < 250):
  margin 50 → 1 refusal, 56 → 0, so `DEFENDER_MARGIN_M = 56` (the 70 m multipath spike at t = 60 needs it),
  and `DEFENDER_STEALTH_MPS = 71` (4.3 km per minute instead of 9 km). On a real vehicle the GPS period
  jitters (σ 0.15 s in `estimator_params.yaml`), so a real attacker would stay a little below these values.
- The flight is simulated: `make_flight.py` in this folder regenerates `flight.csv`.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_CLOCK | b adds the **same** amount to **every** range; solved as an unknown, the residuals vanish | "the bias is found", without "common to all ranges" | repeats the numbers |
| EXPLAIN_TWO + CURVE | 3 unknowns, 2 measurements → a curve; GPS: x, y, z, b → 4; hyperbola because the range **difference** is fixed | counting right, curve not justified | "not enough beacons" |
| EXPLAIN_GN | linearisation (Jacobian) → one small least-squares solve per step, quadratic convergence; fails from a bad guess, near-singular geometry (beacons on a line), or the mirror solution | one of the two parts | "it is faster" |
| EXPLAIN_SPOOF | fake ranges are **consistent** (one point explains them) → zero residual; nothing internal to a simple receiver flags it | "mismatch 0 so no alarm" without why | "the spoofer is clever" |
| EXPLAIN_PARTIAL | a spare real range cannot be explained by the same point → non-zero residual (RAIM); a full spoof fakes all and stays consistent | notices the residual but not why | restates the output |
| EXPLAIN_FLIGHT | start ≈ 250 s, ≈ 2 m/s drag; no vision match over the sea → no independent source → caught only at the coast (450 s), ~400 m off; the gate never fires | timing right, cause vague | "the gate failed" |
| EXPLAIN_TRADEOFF | tighter v_max lowers the stealth speed (150 → 71 m/s) but needs a margin for multipath (false refusals otherwise); any drag below the gate is never refused: only a cross-check closes it | one side of the trade-off | restates numbers |

Predictions (`PREDICT_…`) are never marked. In class, ask who was surprised, and why.

## Difficulties seen in testing (simulated strong, average and weak students)

- `return` inside the loop in `mismatch` (0.431 = beacon A alone) or `total` reset inside it (0.253 = C).
- `best = None` inside the outer loop; `range(10)` instead of `range(101)`.
- TODO 4: returning `((x, y), b)`; forgetting to pass the bias to `mismatch`; a bias step of 0.1.
- TODO 5: sign errors (subtracting Δ, or residual = predicted − measured) make Gauss–Newton diverge; the
  lesson's worked first step is the fastest check. Some students forget to use all beacons (4-beacon test).
- TODO 8: not restarting the time after an accept, or starting it at `dt` (both give 4 instead of 5).
- `-6²` on a phone calculator gives −36 (weak students, lesson §2 check).
- Strong students finish in about 2 h and found the earlier version too easy: Steps 6, 7 (partial),
  10 and 11 are where they work; push them to "Going further".

## Suggested class plan (reading at home + 2 sessions of 2 h)

0. **Before session 1:** read the lesson (about 60 min) with the ✏️ checks.
1. **Session 1 — hook (10 min):** the Black Sea 2017 case. "How could twenty ships agree on a wrong
   position with no alarm?" Collect hypotheses; come back to them at the end.
2. **Board (15 min):** the least-squares valley and one Gauss–Newton step by hand (§3 table).
3. **Lab (95 min):** Steps 1–6.
4. **Session 2 — retrieval (10 min):** Check-yourself 1–3 on paper.
5. **Lab (80 min):** Steps 7–11. When most reach Step 11, a 10-minute class "attacker vs defender" round:
   who found the lowest stealth speed for a defensible margin?
6. **Debrief (30 min):** back to the Black Sea hypotheses; read 2–3 EXPLAIN answers (anonymously) and
   mark them together with the rubric; discuss what NAVERA would and would not have done there.

**Differentiation.** Fast students: "Going further" (3-D receiver, geometry and `(HᵀH)⁻¹`, a bad start).
Students who struggle with Python: pairs; TODO 5 with the lesson's worked step on the board.

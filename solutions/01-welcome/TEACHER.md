# Mission 01 — teacher notes

Not visible to students. Answer key, marking rubrics, known difficulties and a suggested class plan.

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py |
|---|---|---|---|
| (workspace, prerequisite for all) | intro | Steps 1–3 | tests 1–3 |
| 1. Trilateration; the clock makes it a 4-unknown problem | §2, §3 | Steps 5–7 (TODO 3–4) | tests 6, 7, 11, 12 |
| 2. Position as least squares, by hand and in Python | §2 (worked + check) | Step 4 (TODO 1–2) | tests 4, 5 |
| 3. Jamming detectable, a good spoof not | §4 | Step 8 (TODO 5), Step 12 | tests 8, 13, 17 |
| 4. Reason like the arbiter: priority, states, gate and its blind spot | §5 (two checks) | Steps 9–11 (TODO 6–7) | tests 9, 10, 14, 15, 16 |

## Answer key

- Step 1: `ARCH = "aarch64"`, `CPU_CORES` = output of `nproc` on the box (a number).
- Step 3: `V_MAX_MPS = 100.0`, `MARGIN_M = 50.0`, `GPS_TIMEOUT_S = 3.0`.
- Step 6: `CLOCK_ERROR_M` = 141: the grid answer (3.1, 4.1). The continuous least-squares optimum is
  (3.071, 4.090), about 115 m. The check accepts 100–150 (a student may refine the grid).
- Step 7: 1 guess fits with A, B, C; 36 with A and B only (mismatch < 0.005).
- Step 8: the solver finds (7.0, 2.0), bias 0.3 km, mismatch 0.0000, 4 472 m from the truth.
- Step 9: attack A (300 m jump) → 2 refused; attack B (20 m/s drag) → 0 refused.
- Step 10: `STEALTH_SPEED_MPS = 150` (gate per fix = 100 × 1 + 50 = 150 m, accepted when ≤),
  `STEALTH_DISTANCE_M = 9000` in 60 s. 151 m/s is refused at the first fix.
- Step 11: `ARBITER_SOURCE = "gps"`, `ARBITER_STATE = "DEGRADED"`: the GPS fix is 2 s old (fresh, < 3 s), GPS
  has priority even though day vision is more precise, and 35 m > 25 m.
- Code: see `beacons.py` in this folder.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_CLOCK | The bias adds the **same** amount to **every** range; as an unknown it is solved with the position, so the residuals vanish | Says "the bias is found" without saying it is common to all ranges | Repeats the numbers |
| EXPLAIN_TWO | 3 unknowns (x, y, b), 2 measurements → a curve of solutions; real GPS: x, y, z, b → 4 satellites | Counts correctly but no link to GPS, or the reverse | "Not enough beacons" without counting |
| EXPLAIN_SPOOF | Fake pseudoranges are **consistent** (computed for one point) → mismatch 0 there; nothing inside a simple receiver flags it; an independent, non-radio check is needed | "mismatch 0, so no alarm" without why | "The spoofer is clever" |
| EXPLAIN_GATE | The gate widens with the time since the **last trusted** fix (jumps delayed); small steps are always "possible"; a cross-check with a source of **stated uncertainty** is needed — not active today | One of the two attacks explained | Restates the formula |
| threats.md (per threat) | Receiver's view + GPS-only autopilot behaviour + NAVERA's answer **and its limit**, with a lab number | Two of the three | Generic text |

Predictions (`PREDICT_…`) are never marked. In class, ask who was surprised, and why.

## Difficulties seen in testing (simulated B2 and B1 students)

- `-6²` on a phone calculator gives −36: weak students fall into it in the ✏️ checks of §2.
- `return` inside the loop in `mismatch` (gives 0.431 = beacon A alone) and `find_position` (x always 0.0).
- `best = None` inside the outer loop (result `(10.0, …)`).
- Returning `((3.0, 4.0), 0.3)` instead of `(3.0, 4.0, 0.3)` in TODO 4.
- Forgetting `+ bias`, or writing `- bias` ("remove the bias").
- Building a list without `append` (TODO 5).
- TODO 7: not restarting the time after an accept, or starting it at `dt`. Both give 4 instead of 5 on the course
  table. Ask the student to show their hand table.
- Text without quotes in `answers.py` → NameError; `where_am_i.py` and the check now say so.
- Weak students need up to 4 h for the lab. Offer the "Stuck?" hints early rather than the solution.
- The lesson is written at university pace (about 3 100 words). If a group is weak in maths or English, run
  §2 and §3 as a guided session on the board (worked example, then the ✏️ checks in pairs).

## Suggested class plan (reading at home + 2 sessions of 2 h 30)

0. **Before session 1:** students read the lesson (about 60 min) and do the ✏️ checks.
1. **Session 1 — hook (10 min):** the Black Sea 2017 case. Ask: "how could 20 receivers agree on a wrong position
   with no alarm?" Collect hypotheses on the board; come back to them in session 2.
2. **Board (15 min):** the least-squares valley (§2), and the storm with two clocks (§3). Pairs answer the §3
   checks (ship, atomic clock).
3. **Live coding (15 min):** the 1-D search; then ask the class how many candidates a 3-D + clock grid at 1 m would
   need, and why receivers linearise.
4. **Lab (110 min):** Steps 1–7. Walk around; look for the difficulties above.
5. **Session 2 — retrieval (10 min):** Check-yourself 1–3 from memory, on paper.
6. **Lab (100 min):** Steps 8–12. When most have done Step 10, run a 5-minute "attacker" debate: what speed did
   you find, what distance, and what would you need to catch it?
7. **Debrief (30 min):** back to the session-1 hypotheses about the Black Sea; read 2–3 EXPLAIN answers aloud
   (anonymously) and mark them together with the rubric.

**Differentiation.** Fast students: "Going further" (the real 3-D receiver, coarse-to-fine search, geometry).
Students who struggle with Python: pair them, and do TODO 4 and TODO 7 with a hand trace on the board.

# Lab 30 — Catch a lying GPS: the statistics, the guard, the attacks

**Goal:** build NAVERA Lite's spoofing guard. Session 1 (**Statistician**): the χ² test of a GPS fix against
vision, the jump gate's hole, the delay of a drift, and a ROC curve you measure by Monte Carlo. Session 2
(**Guardian**): the guard's two decisions, nine attacks against mission 29's judge with your guard in front of
it, one attack live over ROS 2, and your own attack on your own guard.
**Time:** 3 h 30 (fast) to 6 h 30 (if probability, classes or Linux are rusty), plus the lesson (75–100 min).

| Lesson | Lab step | You write |
|---|---|---|
| §1 the threat, the jump gate | Steps 0, 3 | `patient_accept_time` (TODO 4) |
| §2 hypothesis test, χ² | Step 1 | `chi2_threshold_2d` (TODO 1) |
| §3 the innovation | Step 2 | `innovation` (TODO 2) |
| §4 persistence, drift delay | Steps 4–6 | `first_alarm` (TODO 3), `drift_alarm_time` (TODO 5), `roc_point` (TODO 8), your operating point (TODO 9) |
| §5 the guard | Steps 7–10 | `SpoofGuard.on_reference` (TODO 6), `SpoofGuard.on_gps` (TODO 7) |
| §6 the limits | Steps 9, 11 | your attack, `answers.py` |

Your files: [navera_lite/spoof.py](file:./navera_lite/spoof.py) (TODO 1–7), [detection.py](file:./detection.py)
(TODO 8–9), [answers.py](file:./answers.py). Read, don't change: [scenarios.py](file:./scenarios.py) (the attacks),
[spoof_run.py](file:./spoof_run.py) (the runner), [guard_node.py](file:./guard_node.py) (the ROS node), and
`navera_lite/arbiter.py`, mission 29's judge, shipped finished.

> [!NOTE]
> The attacks (scenarios.py): a survey drone flies **north** along the coast near Sousse at 15 m/s; the spoofer
> pushes the GPS **east**, over the sea. GPS: one fix per second, σ 3 m. Day vision: one fix every 2 s, taken
> 0.1 s after a GPS fix, reaching the judge 0.5 s later, σ 15 m (the simulator's *target* accuracy) — or no stated
> accuracy at all in the `…_novision` attacks. The runner gives the jump gate the drone's top speed, 30 m/s.

# Session 1 — Statistician (2 h; up to 3 h 30 if probability or Python is rusty)

## Step 0 — The judge alone against a slow drift (no code)

Mission 29's judge has the jump gate and nothing else against spoofing. First write `PREDICT_NOGUARD` in
[answers.py](file:./answers.py), then:

```bash
python3 spoof_run.py drift --no-guard
```

It prints only the **changes**: the time, the spoofer's offset, then the judge's state, source and the error
of the position it flies on. Open [out/drift_noguard.png](file:./out/drift_noguard.png). Copy the summary's
"largest error" into `NOGUARD_MAX_ERROR_M`. Look at t = 80 s: the spoofer stops and the **true** GPS returns.
What does the judge do with it, and why? (Hint: mission 01's gate compares with the last *trusted* fix.)

## Step 1 — The threshold of a 2-D test (TODO 1)

🧰 **Mission 27's χ² numbers are in your stack:** `from navera_lite.uncertainty import chi2_threshold`;
`chi2_threshold(0.95)` → 5.991 is the gate that keeps 95 % of honest errors INSIDE. Raising an error:
`raise ValueError("speed must be >= 0, got -3")` stops the function with that message.

Write `chi2_threshold_2d(p_fa)` in [navera_lite/spoof.py](file:./navera_lite/spoof.py) (lesson §2): the same
threshold, but named by its false-alarm probability. Use mission 27's function, or the closed form of §2. Then:

```bash
python3 spoof_run.py test
```

The first three lines should be ✔. The other lines stay ✘ until you write their TODOs.

<details><summary>Stuck? Hints, one at a time</summary>

1. A false alarm is an honest d² OUTSIDE the gate: the probability of being inside is 1 − p_fa.
2. So `chi2_threshold(1 - p_fa)` (dof 2 is the default). Or by hand: P(d² > γ) = e^(−γ/2), solve for γ.
3. Refuse 0, 1 and everything outside: `if not 0 < p_fa < 1: raise ValueError(...)`.
4. You get 0.103 instead of 5.991? You passed p_fa itself to `chi2_threshold`: it wants the probability INSIDE.
   2.996? The factor 2 is missing. 2.60? `math.log10` is not ln.
</details>

## Step 2 — The innovation, and does your test keep its promise? (TODO 2)

🧰 **d² is mission 27's Mahalanobis distance:** `from navera_lite.uncertainty import mahalanobis2`;
`mahalanobis2([2.0, 3.0], [[4.0, 0.0], [0.0, 9.0]])` → 2.0 (2²/4 + 3²/9). Adding 2 × 2 matrices: build them with
`np.array([[a, b], [b, c]])` and use `+`.

`estimate.horizontal(cov)` gives (a, b, c) of a covariance (lesson 12); `geo.enu_flat(lat0, lon0, lat, lon)`
gives east and north metres **from** the first point **to** the second (mission 06);
`estimate.stated_sigma(est, cfg)` is None when an estimate states no accuracy (mission 12).

Write `innovation(gps, ref, cfg)` (lesson §3: r, S with both covariances and the time-gap term, d²). Run
`python3 spoof_run.py test` until the `innovation` lines are ✔.

<details><summary>Stuck? Hints, one at a time</summary>

1. Three steps: r = (east, north) from ref to gps; S = the sum of three 2×2 matrices; d² = mahalanobis2(r, S).
2. The covariance of an Estimate as a 2×2 matrix: `[[a, b], [b, c]]` with `a, b, c = horizontal(est.cov)`.
3. The gap term: `g = cfg["max_speed_mps"] * abs(gps.stamp_s - ref.stamp_s)`, then add g² to the two diagonal
   terms only.
4. You get 4.0 instead of 3.846 in `test`? Your S misses the GPS covariance (900 / 225). 50.0? You added σ
   (3 + 15 = 18 m), not the variances σ² (9 + 225 m²).
</details>

Before the next command, write `PREDICT_STATS` (look at every term your `innovation` puts into S, and at what
really happens in these pairs: the two sources measure the same point, 0.1 s apart). Then:

```bash
python3 spoof_run.py stats
```

20 000 honest GPS/vision pairs go through your `innovation`. Copy the measured share for p_fa 0.01 into
`STATS_SHARE_1PC`, the mean d² into `MEAN_D2`, look at [out/stats.png](file:./out/stats.png), and write
`EXPLAIN_STATS`.

## Step 3 — The jump gate's hole (TODO 4)

🧰 **A quadratic a·x² + b·x + c = 0** has the roots (−b ± √(b² − 4ac)) / (2a) when a ≠ 0. The positive root of
an upward parabola (a > 0) whose value at 0 is negative (c < 0) is the one with **+**. `math.inf` is "infinity",
a float: `math.inf > 1e300` → True.

Write `patient_accept_time(offset_m, speed_mps, v_max_mps, margin_m)` (lesson §1, with the ✏️ check's special
cases). `python3 spoof_run.py test` must show its two lines ✔. Then compute the lab's case and copy it into
`PATIENT_THEORY_DT_S`:

```bash
python3 -c "from navera_lite.spoof import patient_accept_time as f; print(f(2000.0, 15.0, 30.0, 50.0))"
```

Write `PREDICT_PATIENT`, then play the patient spoofer against the judge alone:

```bash
python3 spoof_run.py patient --no-guard
```

Find the line where the judge starts flying on the GPS with an error near 2 000 m: its time is
`PATIENT_FLOWN_T_S`. Now give the gate a "generous" top speed, the plane's 100 m/s, and copy the same time into
`VMAX100_FLOWN_T_S`:

```bash
python3 spoof_run.py patient --no-guard --vmax 100.0
```

Write `EXPLAIN_PATIENT`.

<details><summary>Stuck? Hints, one at a time</summary>

1. Name the four numbers v, s, m, d first, then a = v² − s², b = 2·v·m, c = m² − d² (lesson §1).
2. Three special cases before the formula: m ≥ d (reachable at once: 0.0); a < 0 (never: `math.inf`); a == 0 (a
   line, b·Δt + c ≥ 0: careful with b == 0).
3. You get a ZeroDivisionError? That is the a == 0 case: never divide by 2a there.
4. You get a negative number? You took the root with −√.
5. The run shows a few seconds more than 19 + your Δt: the gate accepts on the next whole-second fix, then the
   judge waits its hold-off (mission 29) before it switches from vision back to GPS.
</details>

## Step 4 — Persistence and the delay of a drift (TODO 3, TODO 5)

🧰 **`enumerate`** gives the index with each value: `for i, v in enumerate([5, 7]):` → (0, 5), (1, 7).
**`math.floor(2.7)`** → 2 (the largest whole number ≤ x).

Write `first_alarm(stats, threshold, n)` (a counter that restarts at 0, lesson §4) and then
`drift_alarm_time(drift_mps, sigma_s_m, threshold, n, period_s)`. For TODO 5, do the lesson's worked example
(u = 2 m/s → 32 s) **by hand** first, then write the code so that it does the same steps. Run
`python3 spoof_run.py test` until all the lines above the SpoofGuard lines are ✔.

Then compute the lab's drift (4 m/s, S = 243·I, p_fa 0.01, n = 5, a test every 2 s) and copy it into
`DRIFT_THEORY_S`:

```bash
python3 -c "from navera_lite.spoof import drift_alarm_time as f, chi2_threshold_2d as g; print(f(4.0, 243 ** 0.5, g(0.01), 5, 2.0))"
```

<details><summary>Stuck? Hints, one at a time</summary>

1. `first_alarm`: one counter; it grows when the value is above the threshold, goes back to 0 otherwise; the
   moment it reaches n, return the index. If the loop ends, return −1.
2. `first_alarm` returns 4 instead of 6 in `test`? Your counter does not restart at 0 after a value below the threshold.
3. `drift_alarm_time`: the test's radius is sigma_s_m·√threshold; the drift reaches it at radius / drift_mps.
4. Tests happen at 0, T, 2T…: the first one STRICTLY after that time is at (floor(t / T) + 1)·T.
5. The n-th test in a row is (n − 1)·T later. You get 34.0 instead of 32.0 for the worked example? The first
   disagreeing test is already one of the n. You get 30.0? You took the test just BEFORE the crossing (no + 1).
   In `python3 spoof_run.py test` the same two mistakes show **23.0** (n·T) and **21.0** (no + 1) instead of 22.0.
</details>

## Step 5 — A ROC curve by Monte Carlo (TODO 8)

The rule of the guard: **alarm when n tests in a row have d² > γ**. [detection.py](file:./detection.py)
simulates 2 000 honest 2-minute flights (60 tests) and 2 000 spoofed flights (a drift of 1.5 m/s that we want
caught within 40 s), for p_fa per test in {0.2 … 0.0001} and n in {1, 2, 3, 5}. Write `roc_point` (TODO 8):
it uses your `first_alarm` once per flight. Then:

```bash
python3 detection.py
```

It takes a few seconds, prints the table and writes [results.json](file:./results.json) and
[out/roc.png](file:./out/roc.png). Look at the first table: does the share of honest tests beyond γ match
p_fa now? (It should be closer than in Step 2: the simulation has no time gap.) The mean delay counts only the
spoofed flights caught within 40 s: for rules that catch few, it is biased low (the slow ones are cut off), so
compare delays only between rules with a high P_D. For rules with a high P_FA (0.2, 1), many
"detections" are honest noise that happens to cross γ in a spoofed flight: their delay is far below the
noise-free one for that reason.

<details><summary>Stuck? Hints, one at a time</summary>

1. For each row of `d2_h0`, `sp.first_alarm(row, threshold, n)`; a flight "has an alarm" when the result is ≥ 0.
2. P_FA = the number of honest flights with an alarm / the number of honest flights. P_D: the same on `d2_h1`.
3. The delay: only the spoofed flights WITH an alarm; mean of (index × period_s). None if no flight has one.
4. Every P_D is 1.0 and every P_FA 0.0? You compared with `>= 0` the wrong way, or swapped the two arrays.
</details>

> [!TASK]
> TODO 1–5 in `navera_lite/spoof.py`, TODO 8 in `detection.py`, and the Session 1 answers of Steps 0–4.
> Press **✔ Check my work**: checks 1–7.

## Step 6 — Choose an operating point (TODO 9)

The requirement: **at most 1 % of honest 2-minute flights may have an alarm** (`MAX_PFA`). Among the 24 rules,
choose the one with the **highest P_D** that meets it. Set `CHOSEN_P` and `CHOSEN_N` at the top of
detection.py and run it again:

```bash
python3 detection.py
```

> [!QUESTION]
> Look at the two best rules: are they really different, or within Monte-Carlo noise (± √(P(1 − P)/2000))?
> Find the rule closest to NAVERA's (p_fa 0.01 per test, n = 5): copy its P_D into `NAVERA_RULE_PD`. A real
> flight lasts an hour, 1 800 tests: roughly how does P_FA per flight grow with the number of tests? Then read
> results.json → `"correlated"`: copy the P_FA of the rule (0.05, 3) with ρ = 0.9 into `CORRELATED_PFA`.
> Write `EXPLAIN_ROC` and `EXPLAIN_CORRELATED`.

> [!TASK]
> TODO 9 and the Step 6 answers. Press **✔ Check my work**: checks 1–8 make the **🏅 Statistician** badge.

# Session 2 — Guardian (1 h 30 to 3 h)

## Step 7 — The guard's skeleton, then its cross-check (TODO 6)

Open `SpoofGuard` in [navera_lite/spoof.py](file:./navera_lite/spoof.py) and read what is given: `__init__`
(the counters `disagree`, `far`, `agree`, the thresholds `gamma` and `gamma_far`, the jump gate `gate`), `check()`
(a GPS fix → `on_gps`, any other source → `on_reference`), `closest_gps`, `has_reference` and `set_state`. Compare
with the lesson's state diagram (§5).

🧰 **Two counters that restart each other** — the same idea as `first_alarm`, kept between calls in `self`:

```python
if beyond:
    self.bad, self.good = self.bad + 1, 0
else:
    self.bad, self.good = 0, self.good + 1
```

Write `on_reference(ref)` (TODO 6). Its docstring gives the order of the rules: the first one that applies
wins. Your `innovation` does the maths. A worked trace (γ = 9.21, γ_far = 27.63, every gap below 500 m) —
complete the last two rows before you code:

| reference fix | d² | disagree, far, agree after it | state before → after |
|---|---|---|---|
| 10.1 s | 3.1 | 0, 0, 1 | TRUSTED → TRUSTED |
| 12.1 s | 10.4 | 1, 0, 0 | TRUSTED → TRUSTED (one fix is not evidence) |
| 14.1 s | 11.9 | 2, 0, 0 | TRUSTED → IN_DOUBT (gap 54 m ≤ 500 m) |
| 16.1 s | 30.2 | 3, 1, 0 | IN_DOUBT → ? |
| 18.1 s | 33.0 | 4, 2, 0 | ? → ? |

<details><summary>Answer</summary>
16.1 s: d² > γ_far once only (far = 1 < far_n 2) and disagree 3 < refuse_n 5, so the doubt rule applies: IN_DOUBT
stays. 18.1 s: far = 2 = far_n → REFUSED, refused_by "far" — checked before the doubt rule; disagree 4 is not
yet 5. (Entering REFUSED then empties the counters: set_state does it.)
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. Three early exits return None: an invalid ref, a ref that states no accuracy (`stated_sigma`), no GPS fix
   close in time (`self.closest_gps(ref.stamp_s)`). Remember `self.last_ref_s` between the second and the third.
2. Update the three counters (the 🧰 box), with `self.far` growing only while d² > `self.gamma_far`.
3. Then one `if / elif` chain, in the docstring's order. A REFUSED guard only looks at `self.agree`.
4. On confirmation, the GPS fix you compared becomes `self.gate.trusted`, so the jump gate starts again from it.
5. Return d² at the end (also when nothing changed).
</details>

## Step 8 — The verdict on a GPS fix (TODO 7), and the drift

Write `on_gps(gps)` (TODO 7): five rules, in the docstring's order. Trace by hand first: a guard TRUSTED with
its last GPS fix at t = 40 s receives a fix at t = 45 s while vision (σ stated) was heard at t = 44.1 s. Which
rule applies, which verdict, which `refused_by`?

<details><summary>Answer (check before you code)</summary>
45 − 40 = 5 s > gps_timeout_s 3 s, the guard is not REFUSED, and vision (σ stated) was heard 0.9 s ago
(has_reference): rule 2 → "REFUSED", refused_by "outage". Rule 5 is never reached. Had the guard already been
REFUSED, rule 2 would not apply (it says "while the GPS is not REFUSED"): rule 3 keeps it REFUSED as it was.
</details>

Then `python3 spoof_run.py test` (its last four lines).

<details><summary>Stuck? Hints, one at a time</summary>

1. The time since the last GPS fix is `gps.stamp_s - self.last_gps_s` (check() updates `last_gps_s` AFTER you).
2. Every verdict goes through `self.set_state(state, reason, refused_by)` and you return what it returns. When
   nothing changes, return `self.state, self.reason`.
3. The jump gate: `ok, why = self.gate.check(gps)`; use `why` as the reason of a refusal.
4. Rule 2 before rule 3: an outage while REFUSED changes nothing. The `test` line "REFUSED (jump), back after
   5 s of silence" says 'outage'? Your rule 2 forgot "while the GPS is not REFUSED".
5. Your guard refuses the true GPS in `jump` at t = 50 s although vision states nothing? Rule 3 needs
   `self.has_reference(...)`: without a stated reference, the gate decides (rule 4).
6. The `test` line "IN_DOUBT, then a GPS fix the gate accepts" says TRUSTED, or your drift run shows **no
   IN_DOUBT at all**? Rule 5 says *no change* when the gate accepts the fix: return `self.state, self.reason`.
   Writing `set_state("TRUSTED", …)` there erases the doubt at every GPS fix: only `on_reference` clears a doubt.
</details>

Write `PREDICT_GUARD_DRIFT`, then:

```bash
python3 spoof_run.py drift
```

Open [out/drift.png](file:./out/drift.png). Copy the summary's offsets of the first IN_DOUBT and the first
REFUSED spoofed fix into `DRIFT_DOUBT_OFFSET_M` and `DRIFT_REFUSED_OFFSET_M`, and write `EXPLAIN_DRIFT`.

## Step 9 — Every attack

The whole table, every attack with and without your guard (a few seconds). Find in it the patient spoofer when
vision states an accuracy (`patient_vision`), jam then spoof (`jamspoof`) and an honest flight with two wrong
vision matches (`glitch`); every run is drawn in out/ (for example [out/jamspoof.png](file:./out/jamspoof.png)):

```bash
python3 spoof_run.py all
```

Write `EXPLAIN_LIMITS`: which attacks still win, and what do they have in common?

> [!TASK]
> TODO 6–7, then `python3 spoof_run.py all` (it saves runs.json), and the answers of Steps 8–9. Press
> **✔ Check my work**: checks 9–13. Check 11 plays seven attacks you have not seen through your guard.

## Step 10 — Live over ROS 2

The same judge and guard as a ROS 2 node, and the drift attack published in real time on
`/navera_lite/fix/gps` and `/navera_lite/fix/day`. One terminal is enough: start the node in the **background**
(the `&` at the end), wait 2 s, then play the attack (45 s of real time):

```bash
python3 guard_node.py --ros-args --params-file navera_lite.yaml -p max_speed_mps:=30.0 &
```

```bash
python3 spoof_run.py drift --ros
```

The node's log lines (`[INFO] … [arbiter]`, `[WARN] … GPS IN_DOUBT …`) appear between the runner's lines: that is
normal, both write to the same terminal. Then stop the node:

```bash
kill %1
```

(`jobs` lists your background jobs; "no judge listens" means the node is not running yet: wait 2 s and run the
attack again.) Open [ros_drift.json](file:./ros_drift.json): find the first change with `"gps_guard": "REFUSED"`
and copy its `t` into `ROS_REFUSED_T_S`. Compare with Step 8: why is it about half a second earlier here, and why
is its offset one GPS step (4 m) smaller?

<details><summary>Read this after the live run</summary>
The live run records a change the moment the judge's status changes: the guard decides when the vision fix
ARRIVES (measured at 30.1 s, received 0.5 s later). Offline, the runner prints the verdict at each GPS fix, so
it shows the refusal at the next GPS fix (31 s, 4 m further). Same decision, two clocks.
</details>

## Step 11 — Red team: attack your own guard

You are now the spoofer, and you know the rule. The `creep` attack holds the GPS a constant offset east of
the truth from t = 10 s. Find the **largest offset your guard never REFUSES** (to the nearest 1–2 m) by trying
values, for example:

```bash
python3 spoof_run.py creep --creep 40.0
```

Change the number (try 60, then halve the interval…) and watch the summary's "first REFUSED". Put your answer
in `CREEP_MAX_M`.

Your answer is a property of **this** noise draw and of a 110 s attack. Is it above or below the test's radius
√(9.21 · 243) = 47.3 m of lesson §3? Replay your answer with two other noise draws:

```bash
python3 spoof_run.py creep --creep 44.0 --seed 31
```

(put **your** CREEP_MAX_M in place of 44.0, then do the same with `--seed 32`). Does your offset still survive?
How lucky was your draw? Count the refusals over 20 draws (about a minute):

```bash
for s in $(seq 31 50); do python3 spoof_run.py creep --creep 45.0 --seed $s | grep "first REFUSED"; done | grep -c "t ="
```

The number printed is how many of the 20 flights refused 45 m; try your own offset, and 35.0. Write `EXPLAIN_CREEP`: why such an offset
exists, whether it would survive a one-hour flight (near the radius each test disagrees about half the time), and
what would make it smaller.

> [!TASK]
> `ros_drift.json` from a complete live run and the answers of Steps 10–11. Press **✔ Check my work**: all 15
> checks make the **🏅 Guardian** badge.

## Step 12 — Look back (not graded)

Write `LOOK_BACK` in answers.py: (1) which of your guard's rules would you defend in front of a safety reviewer,
and which one worries you? (2) The guard needs a reference of stated accuracy. Over the open sea there is none:
what would you add to the vehicle? (3) Your best rule in Step 6 is not NAVERA's: who is right, for which
mission?

## Going further (optional)

- **Your own judge.** `python3 spoof_run.py all --mine` flies the judge you wrote in mission 29
  (`../29-arbiter/navera_lite/arbiter.py`) instead of the course's. Same table?
- **Vision states 30 m** (NAVERA's day vision today). In a copy of scenarios.py set `VISION_SIGMA_M = 30.0` for the
  STATED σ only (keep the noise at 15 m) and replay `drift` and `creep`: how does the bound move?
- **Delay against drift speed.** `python3 spoof_run.py drift --drift 1.0`, then 2.0, 4.0, 8.0: plot the offset at
  refusal against the drift speed. Is it roughly constant? Why (lesson §4)?
- **One attack at a time.** `python3 spoof_run.py patient_vision` (or `jamspoof`, `glitch`) prints every change
  of one attack with the guard's reasons.
- **A smarter far rule.** NAVERA refuses a clear disagreement after 3 s beyond 5σ + 50 m. Change `p_fa_far` and
  `far_n` (passed in cfg) and measure on `patient_vision` how fast the refusal comes and on `glitch` whether a good
  GPS is ever refused.

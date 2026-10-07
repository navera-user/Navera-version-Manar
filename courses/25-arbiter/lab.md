# Lab 25 — Build the arbiter, race the real one, measure its trade-offs

**Goal:** implement NAVERA's decision policy as predicates, a pure `decide()` function and a small
state machine; prove it equivalent to the real `estimator_node` on a 31-second scenario (decisions
*and* switch instants); then measure the two design trade-offs (hold-off, freshness window) and
test selection against fusion. You finish with a short written analysis.
**Time:** about 3 hours.

Your files:

| File | What you do |
|---|---|
| [arbiter.py](file:./arbiter.py) | TODO 1–8: predicates, `decide()`, class `Arbiter` |
| [compare_real.py](file:./compare_real.py) | the race against the real node — read it, do not change it |
| [experiment.py](file:./experiment.py) | TODO A, B, C1, C2: the experiments |
| [answers.py](file:./answers.py) | 9 questions on the real code |
| [report.md](file:./report.md) | your written analysis (5 sections) |

An **estimate** is a dict with the content of a `PositionEstimate` message: `source`, `stamp`
(the measurement instant), `valid`, `mode`, `lat`, `lon`, `cov` (9 numbers, m²) and `cov_type`.
The helpers `gps(stamp, sigma=3.0, **changes)` and `day(stamp, sigma=None, **changes)` (bottom of
`arbiter.py`) build them for your tests, e.g. `gps(99.0, valid=False)`.

## Step 1 — Run the demo

```bash
python3 arbiter.py
```

Every decision is `{'state': None, …}` and the switch list is empty: the functions are not written
yet. Read the top of [arbiter.py](file:./arbiter.py): the constants are the product's values
(`TIMEOUTS`, `FUTURE_TOLERANCE_S`, `SWITCH_HOLDOFF_S`, `FIX_MAX_SIGMA_M`, `MIN_STATED_SIGMA_M`).

## Step 2 — The predicates (TODO 1, 2, 3)

**TODO 1 — `is_fresh(est, now)`.** `age = now - est["stamp"]`, then the rule
`-FUTURE_TOLERANCE_S <= age < TIMEOUTS[est["source"]]`. Python accepts chained comparisons.

```bash
python3 -c "import arbiter as a; print(a.is_fresh(a.gps(99.0), 100.0), a.is_fresh(a.gps(97.0), 100.0))"
```

Expected: `True False` (exactly 3.0 s old is already stale for GPS).

**TODO 2 — `cov_ok(cov)`.** The four conditions of lesson §2, one guard clause each
(`if …: return False`), `return True` at the end. Convert with `[float(x) for x in cov]` inside a
`try/except (TypeError, ValueError)` so that `None` gives `False` instead of a crash; then check the
length (9), `math.isfinite`, the diagonal (indices 0, 4, 8), symmetry with the tolerance, and the
determinant of the horizontal block.

```bash
python3 -c "import arbiter as a; print(a.cov_ok([9,7,0, 7,4,0, 0,0,1]), a.cov_ok([9,1,0, 1,4,0, 0,0,36]), a.cov_ok(None))"
```

Expected: `False True False` (the first one has ρ = 7/6 > 1).

**TODO 3 — `stated_sigma(est)`.** `None` unless `est["cov_type"]` is in `BOUNDED_TYPES`; else
`sqrt(max(cov[0], cov[4]))`, and `None` again if that is below `MIN_STATED_SIGMA_M`.

```bash
python3 -c "import arbiter as a; print(a.stated_sigma(a.gps(1.0, sigma=40.0)), a.stated_sigma(a.day(1.0)), a.stated_sigma(a.gps(1.0, sigma=0.0)))"
```

Expected: `40.0 None None`.

> [!WARNING]
> A frequent bug: `if sigma:` is false for `0.0` **and** for `None`. Write `if sigma is None:` when
> you mean "unknown", and compare numbers explicitly.

## Step 3 — Eligibility and classification (TODO 4, 5)

**TODO 4 — `is_eligible(est, now)`**: the five predicates `V ∧ M ∧ F ∧ P ∧ C` as guard clauses,
using `is_fresh`, `position_ok` (given) and `cov_ok`. Use `est.get("valid") is not True` so that a
missing field is "not valid".

**TODO 5 — `classify(est)`** returns a tuple `(state, reason)`. Follow the four lines of the
docstring **in that order** (σ > 25 m must be tested before "σ ≤ 25 m"). Format numbers with
`f"{sigma:.0f}"`, so 40.0 is written `40`.

## Step 4 — The decision function (TODO 6)

`decide(estimates, now, active, eligible_since, holdoff_s)` is a **pure** function: everything it
needs is in its arguments. Order of the work:

1. empty list → `INITIALIZING`, reason `"waiting for first source message"`;
2. `by_source = {e["source"]: e for e in estimates}` and the list `usable` of eligible sources in
   `PRIORITY` order;
3. nothing usable → `NO_FIX`, reason = `"; ".join(...)` of `why_not(by_source[s], now)` for the
   sources heard, in `PRIORITY` order;
4. `best = usable[0]`; hold-off: if `active in usable`, `best != active` and
   `now - eligible_since[best] < holdoff_s`, the winner stays `active`;
5. `state, reason = classify(by_source[winner])`; return the dict.

```bash
python3 arbiter.py
```

Check each line against lesson §6: fresh GPS → `FIX`; GPS 4 s old with fresh day → `DEGRADED`/`day`;
HDOP 20 → `uncertainty 40 m > 25 m`; all-zero covariance → `uncertainty unknown`; all old → `NO_FIX`
with two clauses.

> [!TASK]
> Complete TODO 1–6. "Done" = `is_fresh`, `cov_ok`, `stated_sigma`, `is_eligible`, `classify` and
> `decide` follow their docstrings exactly (about 50 situations are tested, including boundaries
> such as exactly 3.0 s, exactly 25 m, exactly 2.0 s of hold-off, and `holdoff_s=4`). Press
> **✔ Check my work** — checks 1 to 7 should be green.

## Step 5 — The state machine (TODO 7, 8)

`decide()` has no memory. The class `Arbiter` holds the memory `m` of lesson §1:
`latest`, `active`, `eligible_since`, and a log `switches` of `(time, old, new)`.

- **TODO 7 — `receive(est)`**: store the estimate as the latest of its source — but drop a GPS
  estimate whose stamp is older than the stored GPS one (the real `_on_gps()` does this: a late fix
  from a buffer must not replace a newer one).
- **TODO 8 — `step(now)`**: (1) update `eligible_since` for every source in `PRIORITY` with
  `setdefault` / `pop`, **before** deciding; (2) call `decide(...)` with `self.holdoff_s`;
  (3) log a switch when the source changes (`None` included); (4) update `active` and return.

```bash
python3 arbiter.py
```

The last line must now read `switches: [(0.0, None, 'day'), (12.0, 'day', 'gps')]`: GPS returns at
10.0 s and takes over exactly 2.0 s later.

> [!QUESTION]
> Why must `eligible_since` be updated *before* `decide()`? Try the other order on paper with GPS
> returning at 10.0 s and steps every 0.5 s: when does the switch happen, and what happens to a GPS
> that becomes eligible while no source is active?

## Step 6 — Race the real arbiter

`compare_real.py` starts NAVERA's real `estimator_node` from **your** copy (`~/navera`) with the
product's settings, on your private ROS domain. It publishes a 31-second story — GPS good, day
vision joining, GPS jammed, GPS back with HDOP 20, GPS invalid, night vision dead-reckoning, a
celestial fix with a clock 60 s ahead — and records **every** `/navera/nav_status`. Then it replays
the same inputs through your `Arbiter`: `receive()` + `step()` on each arrival, `step()` on a 5 Hz
clock, exactly like the real node.

```bash
python3 compare_real.py
```

Wait about 35 s. You get two tables: the decisions at 11 moments (state, source, reason), and the
**source switches** with the real and your instants. Real instants are a few hundredths of a second
late (ROS scheduling) and the real 5 Hz timer has its own phase, so a tolerance of 0.35 s is used.
After fixing your code you do not need to restart ROS:

```bash
python3 compare_real.py --replay
```

> [!QUESTION]
> At **t = 15.0 s** ("GPS is back since 1 s") GPS is valid, fresh and first in priority — yet both
> arbiters use day vision. Which rule? At which instant does GPS take over, and in which state?

<details><summary>Answer</summary>
The hold-off: GPS returned at 14.0 s, so it takes over at 16.0 s. It is DEGRADED, because this GPS
states σ = 40 m (> 25 m).
</details>

> [!TASK]
> Run `python3 compare_real.py` until **11 of 11 decisions** are identical (same reason words) and
> **all source switches** match (same order, within 0.35 s). Checks 8–9 test your state machine on
> its own; checks 10–11 replay `real_run.json` through it.

## Step 7 — Read the real code

The real arbiter is about 700 lines, because it also protects GPS against spoofing (lesson 27).
Do not read it top to bottom: list its methods and read their docstrings.

```bash
grep -n "def " ~/navera/navera_estimator/navera_estimator/nodes/estimator_node.py
```

```bash
cat ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
```

Open [estimator_node.py](file:navera/navera_estimator/navera_estimator/nodes/estimator_node.py)
in the editor. Map each of your functions to the real method (`is_fresh` + `is_eligible` →
`_eval_source` + `_sane`, hold-off → `_select`, …). Note the things the real node does that yours
does not: the IMU liveness, the GPS plausibility gate, the de-duplication of `/navera/position`,
and the "future stamp sets no order" condition in `_on_gps()`.

> [!TASK]
> Answer the 9 questions of [answers.py](file:./answers.py): method names exactly as after `def`
> (no `self.`, no parentheses) and numbers. Q8 is a trap worth understanding: the value in the node
> and the value the product runs with are not the same — which one wins, and why?

## Step 8 — Measure the trade-offs (TODO A, B, C1, C2)

Open [experiment.py](file:./experiment.py). The inputs are synthetic and seeded (the same numbers
for everybody): a model to reason with, not a flight measurement.

- **TODO A — `holdoff_metrics(events, holdoff_s)`.** A GPS at the edge of a jammer's range
  (on-periods exponential, mean 2 s; off-periods mean 1 s; 2 messages/s) and a day vision that
  always works (σ 30 m). Walk `timeline(events, duration_s)`: on an arrival `receive` + `step`;
  on a tick `step`, then measure. Return `switches_per_min`, `gps_share`, `gps_unused_s` as the
  docstring defines them.
- **TODO B — `freshness_metrics(frame_times, window_s)`.** Day-vision frames under load (85 % of
  gaps 1–4 s, 15 % stalls of 4–10 s). One pass over the samples `t_k = k·SAMPLE_S`, moving an index
  through `frame_times`. Return `availability`, `dropouts`, `max_age_used_s`, `max_error_m`.
- **TODO C1 — `fuse(x1, s1, x2, s2)`** and **TODO C2 — `true_sigma(s1, s2, rho)`**: the formulas
  of lesson §7.

```bash
python3 experiment.py
```

It prints three tables, writes `results.json` and draws [tradeoffs.png](file:./tradeoffs.png) (open
it in the editor). You should see the switch rate fall from about 27 per minute at h = 0 while the
unused GPS time grows, and the availability rise with T while the staleness error grows linearly.

> [!TASK]
> Complete TODO A, B, C1, C2 so that `python3 experiment.py` writes `results.json`. The check calls
> your functions on the provided inputs and compares with the expected values (checks 12–13).

## Step 9 — Write the analysis

Fill in [report.md](file:./report.md): five sections (keep the `## ` headings), at least 40 words
each and 350 in total, in full sentences. Quote **your** numbers: the switch rates at h = 0 and
h = 2 s and the unused GPS time; the availability at T = 3 and 5 s and the maximum staleness error;
the claimed and the true fused σ and the spoofed fused position; the results of the race; and the
limits of these experiments. Argue — do not only copy numbers: which hold-off would *you* choose,
and why does NAVERA select rather than fuse?

> [!TASK]
> `results.json` from your finished `experiment.py`, and `report.md` with the five sections, the
> required word counts, and at least two of your measured numbers in each of sections 1–3. Press
> **✔ Check my work** — all 15 checks green.

## Going further (optional)

- **Model vs simulation.** Lesson §5 predicts that a hold-off `h` keeps a fraction `exp(−h/μ)` of
  the GPS take-overs (`μ = 2 s`). Compare `exp(−1)` with the ratio of your switch rates at h = 2 and
  h = 0. Why do they differ? (Hint: the GPS sends 2 messages per second — what happens to on- or
  off-periods shorter than 0.5 s?)
- **Run the product's own test.** NAVERA's integration test drives the real arbiter with many more
  cases (flapping GPS, jumps, spoofing). About 2 minutes; it ends with `estimator: PASS`:
  `python3 ~/navera/navera_tools/tests/test_estimator.py`
- **Break it on purpose.** Set `SWITCH_HOLDOFF_S = 0.0` in `arbiter.py` and run
  `python3 compare_real.py --replay`: which switches and moments now disagree? Put it back.
- **Eigenvalue σ.** Write `stated_sigma_eig(est)` using the largest eigenvalue of the horizontal
  block (`numpy.linalg.eigvalsh`). For which covariances does it differ from NAVERA's rule, and is
  the difference conservative or optimistic?

# Lab 25 — Build your own arbiter, then race the real one

**Goal:** write a simplified NAVERA arbiter as four small Python functions, test it on scenarios,
then play the same scenario to NAVERA's **real** `estimator_node` and compare every decision.
**Time:** about 1 h 15.

Your files: [arbiter.py](file:./arbiter.py) (your arbiter), [compare_real.py](file:./compare_real.py)
(the race — you don't change it), [answers.py](file:./answers.py) (code reading).

## Step 1 — Run the demo

```bash
python3 arbiter.py
```

You see six situations and, for each one, the decision of your arbiter. For now every decision is
`{'state': None, ...}`: the four functions are empty. Open [arbiter.py](file:./arbiter.py) and read
the top: an **estimate** is a simple dict with the same information as a `PositionEstimate`
message (`source`, `stamp`, `valid`, `mode`, `lat`, `lon`, `sigma`). `sigma = None` means
"uncertainty unknown".

## Step 2 — Is it fresh? (TODO 1)

Complete `is_fresh(est, now)`:

```python
age = now - est["stamp"]
```

then return `True` when `-FUTURE_TOLERANCE_S <= age < TIMEOUTS[est["source"]]`, `False` otherwise.
Python can compare three things in one line, exactly like in maths.

Test it in the terminal — `python3 -c` runs a one-line program:

```bash
python3 -c "import arbiter as a; print(a.is_fresh(a.gps(99.0), 100.0), a.is_fresh(a.gps(97.0), 100.0))"
```

You should see `True False`: 1 s old is fresh, 3 s old is already stale for GPS.

## Step 3 — Is it usable? (TODO 2)

Complete `is_eligible(est, now)`. Write **one `if` per rule** and `return False` as soon as one rule
fails; at the end, `return True`. That style ("guard clauses") is easy to read and easy to test:

```python
if est.get("valid") is not True:
    return False
```

For rule 4, `position_ok(lat, lon)` is already written for you (below the line). For rule 5,
`math.isfinite(x)` is `False` for `nan` and `inf`.

## Step 4 — FIX or DEGRADED? (TODO 3)

Complete `classify(est)`. It returns **two** values: `return "FIX", f"{name} fix"`. Follow the four
lines of the docstring **in that order** — the order matters (a σ of 40 m is "bounded" but too
large, so that test comes first). Use `f"{sigma:.0f}"` to write 40.0 as `40`.

## Step 5 — The decision (TODO 4)

Complete `decide(estimates, now, active, eligible_since)`:

1. Empty list → `{"state": "INITIALIZING", "source": None, "reason": "waiting for first source message"}`.
2. Build `by_source` and the list `usable` (the tip in the file does it in two lines).
3. Nothing usable → `NO_FIX`. The reason is `"; ".join(...)` of `why_not(by_source[s], now)` for
   each source heard, in `PRIORITY` order.
4. Otherwise `best = usable[0]`. **Hold-off:** if `active` is in `usable`, and `best != active`, and
   `now - eligible_since[best] < SWITCH_HOLDOFF_S` → the winner stays `active`.
5. `state, reason = classify(...)` of the winner, and return the dict.

```bash
python3 arbiter.py
```

Compare with what you expect from the course: a fresh GPS is `FIX`, an old GPS with fresh day
vision is `DEGRADED` / `day`, HDOP 20 is `DEGRADED` "uncertainty 40 m > 25 m", everything old is
`NO_FIX` with two clauses.

> [!TASK]
> Complete TODO 1 to TODO 4 in `arbiter.py`. "Done" means: `is_fresh`, `is_eligible`, `classify`
> and `decide` follow the docstrings exactly (the check tests about 40 situations, including the
> hold-off and a flapping GPS). Press **✔ Check my work** — checks 1 to 10 should be green.

## Step 6 — Race the real arbiter

Now the real thing. `compare_real.py` starts NAVERA's own `estimator_node` **from your copy**
(`~/navera`), with the product's settings file, on your private ROS domain. It then publishes a
31-second story of `PositionEstimate` messages — GPS good, day vision joining, GPS jammed, GPS back
with a bad HDOP, GPS invalid, night vision dead-reckoning, a celestial fix with a broken clock — and
writes down what the real arbiter says on `/navera/nav_status` at 11 moments. Finally it replays the
**same inputs** through your `arbiter.py`.

```bash
python3 compare_real.py
```

Wait about 35 seconds. The table at the end shows, for each moment, the real decision and yours, with
✔ or ✘. When a reason text differs, both are printed.

> [!QUESTION]
> Look at the moment **t = 15.0 s, "GPS is back since 1 s"**. GPS is valid and fresh, it is first in
> the priority list… and yet both arbiters still use day vision. Which rule is that? When does GPS
> take over?

<details><summary>Answer</summary>
The hold-off: GPS came back at 14.0 s; it must stay usable for 2 s, so it takes over at about 16.0 s.
At 17.0 s the real arbiter uses GPS — DEGRADED, because this GPS states σ 40 m (> 25 m).
</details>

> [!TASK]
> Run `python3 compare_real.py` until **11 of 11 decisions are identical** and the reason texts match
> (the numbers in the reasons may differ by a few hundredths of a second, that is fine). The check
> reads `real_run.json` and replays it through your arbiter.

## Step 7 — Read the real code

Open the real arbiter in the editor:
[estimator_node.py](file:navera/navera_estimator/navera_estimator/nodes/estimator_node.py).
It is long (about 700 lines) because it also protects against GPS spoofing (lesson 27). Don't read it
from top to bottom: search (`Ctrl+F`) for `def _` and read the **docstring** under each method.
You can also list them in the terminal:

```bash
grep -n "def " ~/navera/navera_estimator/navera_estimator/nodes/estimator_node.py
```

And the settings file:

```bash
cat ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
```

Find, for each rule you implemented, the real method that does it. Compare: your `is_fresh` +
`is_eligible` is `_eval_source` + `_sane`; your hold-off is in `_select`; your `classify` is
`_classify`. Notice how close they are — and the few things the real one does that yours does not
(a real 3×3 covariance check, the IMU liveness, the GPS protection).

> [!TASK]
> Answer the six questions of [answers.py](file:./answers.py) (method names, without `self.` and
> without parentheses), save, and press **✔ Check my work**.

## Going further (optional)

- **Run the product's own test.** NAVERA's integration test drives the real arbiter exactly like
  `compare_real.py`, with many more cases (flapping GPS, jumps, spoofing). It takes about 2 minutes:
  `python3 ~/navera/navera_tools/tests/test_estimator.py` — it prints `estimator: PASS`.
- **Change a rule and see it.** In `arbiter.py`, set `SWITCH_HOLDOFF_S = 0.0`, run
  `python3 compare_real.py` again: which moment now disagrees with the real arbiter? Put it back.
- **Watch the real status live.** In one terminal, run
  `ros2 run navera_estimator estimator_node.py`; in a second one,
  `ros2 topic echo /navera/nav_status --field reason`; in a third, `python3 compare_real.py`
  (it starts its own arbiter too, so now **two arbiters** decide on the same ROS network: the
  comparison will be wrong, and after a few seconds the real node logs an error about it — see
  `_check_single_arbiter`: in a real box, exactly one arbiter may speak). Stop the first one with
  `Ctrl+C` afterwards.

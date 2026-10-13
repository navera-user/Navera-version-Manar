# Lab 12 — Fill the contract, fool the naive judge, then make it honest

**Goal:** write the four checks of NAVERA Lite's position contract in `navera_lite/estimate.py`, measure
what a late position costs, fool arbiter v0 with four scenario files, then plug your own `eligible()`
into it, watch the attacks fail — and find the one that comes back.
**Time:** 3 h 30 to 4 h 30 in two sessions (a strong programmer: about 2 h 30).
**Fast track:** if you know Python, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further".

Your files (📝 Code tab): [navera_lite/estimate.py](file:./navera_lite/estimate.py) (**your code**: four
functions, `TODO 1–4`), [answers.py](file:./answers.py), the folder `attacks/` (your scenario files), and
the runner [contract_lab.py](file:./contract_lab.py), which runs your functions on the lab's situations
and reads the live judge for you (you only run it). Everything else in `navera_lite/` is given finished:
arbiter v0, the replay node and convert (09), the fake GPS (10). The data:
`/data/academy/12-position-message/day_vision_lag.csv`, a **synthetic** bench log of a day-vision
matcher (read only).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | nothing: a dead GPS that stays alive |
| §1 the form | Step 1 | `MY_ESTIMATE` |
| §2 covariance | Step 2 | `is_covariance` (TODO 1) |
| §3 stated σ | Step 3 | `stated_sigma` (TODO 2) |
| §4 stamps | Step 4 | `staleness_m` (TODO 3), the lag study |
| §5 checklist, attacker's view | Steps 5–6 | four attacks in `attacks/` |
| §5 checklist | Steps 7–8 | `eligible` (TODO 4), your judge live, the dead fix that comes back |
| §3 warning | Step 9 | one explanation |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is
> never marked right or wrong. Each TODO's docstring says its goal and gives one example with its result;
> `python3 contract_lab.py test` tries every example. The lesson shows how; the code is yours.

> [!WARNING] One terminal tab for the whole lab
> As in mission 09, a node started in one tab cannot be seen from another tab. Run everything in **one**
> tab and start the nodes in the background with `&`, their output in a log file. `jobs` lists them,
> `kill -INT %%` stops the most recent one (Ctrl+C for a background job), `kill -INT $(jobs -p)` stops all.
> `python3 contract_lab.py status` prints the live judge's state and message in one line.

## Session 1 — The contract (1 h 30 to 2 h)

## Step 0 — A dead GPS

No code. Check that nothing runs yet (`jobs` prints nothing), then start the judge and mission 10's fake
GPS with a clock 30 s ahead (a badly set computer clock):

```bash
jobs
```

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml > arbiter.log 2>&1 &
```

```bash
python3 -m navera_lite.ros.gps_node --ros-args -p stamp_offset_s:=30.0 > gps.log 2>&1 &
```

Ask the judge (it listens 6 s, then prints the state and the message):

```bash
python3 contract_lab.py status
```

FIX on GPS.

> [!TASK]
> **Predict** (`PREDICT_DEAD` in `answers.py`): you are about to kill the GPS. What will the judge say
> 10 s later? (Mission 11 measured a GPS that stops.)

Kill the GPS (your most recent job), then watch the judge for 45 s: each change is printed with the time
since the watch started.

```bash
kill -INT %%
```

```bash
python3 contract_lab.py status --watch 45
```

How long does the dead GPS stay FIX? Stop the judge, then read the lesson's §1 (keep "why?" for §4):

```bash
kill -INT $(jobs -p)
```

## Step 1 — Fill the contract

Open `navera_lite/estimate.py` and read the class `Estimate` (lesson §1, 🧰 dataclasses). Make one and
look at its default values:

```bash
python3 -c "from navera_lite.estimate import *; e = Estimate('gps', 35.8256, 10.6084, 100.0); print(e); print(e.alt_m, e.cov_type)"
```

> [!TASK]
> In `answers.py`, write `MY_ESTIMATE = Estimate(...)` for this message: *Night vision (the thermal
> camera) matched a frame taken at t = 812.4 s on the judge's clock; the result was published at
> t = 813.5 s. Position 35.7712° N, 10.8265° E. Its error model gives σ 18 m east, 24 m north and 30 m up;
> it does not estimate the correlations. Altitude: not measured.* Use the constants (`COV_…`), not bare
> numbers, and `math.nan` where needed (`answers.py` already imports them).

```bash
python3 -c "import answers; print(answers.MY_ESTIMATE)"
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Five questions, five groups of fields (lesson §1 table). Which instant is the measurement?
2. `cov` holds **variances**, m²: σ = 18 m → 324. Nine numbers, row-major: east at index 0, north at
   index 4, up at index 8, the correlations (indices 1, 3, and the others) 0.0.
3. The variances are known, the correlations are not: that is exactly one of the four types (lesson §3).
4. Fields with a default that you need to change: name them, e.g. `cov_type=…, alt_m=…`.
</details>

## Step 2 — Is it a covariance? (TODO 1)

Read lesson §2. **TODO 1** `is_covariance(cov9, tol=1e-9)` is lesson §2's test, with a reason for the
first rule broken (the docstring lists them in order). It must answer `(ok, reason)` for **anything** it
receives: nine good numbers, eight numbers, `None`, a word.

<details><summary>🧰 Python: refuse what is not a list of numbers, without crashing</summary>

```python
def as_floats(x):
    try:
        return [float(v) for v in x]      # TypeError if x is None or a number (not iterable),
    except (TypeError, ValueError):       # ValueError if an item is text like "abc"
        return None
as_floats([1, "2.5"]), as_floats(None), as_floats("ab")   # ([1.0, 2.5], None, None)
import math
math.isfinite(float("nan")), math.isfinite(1e308 * 10)    # (False, False) — nan and inf
all(v > 0 for v in [1.0, 2.0, -3.0])                      # False: one of them is not
a, b, c = v[0], v[1], v[4]                                # three names at once (unpacking)
```
</details>

```bash
python3 contract_lab.py test
```

The TODO 1 lines must be ✔ (the others are later TODOs).

<details><summary>Stuck? Hints, one at a time</summary>

1. Follow the docstring's order: each rule is one `if … : return False, "…"`; the last line returns
   `True, "ok"`.
2. `TypeError: 'NoneType' object is not iterable` or `object of type 'float' has no len()`: convert inside a
   `try` first (🧰 box) and answer `(False, "not 9 numbers")` when it fails or when the length is not 9.
3. Symmetry: compare the two places of b with a tolerance, never with `!=` (1.0 and 1.0 + 1e-12 are "equal").
4. You get `(True, "ok")` for a = −1, c = −1, b = 0? Its determinant is +1: test the variances
   **before** the determinant. The up variance is index 8.
5. You refuse the km-sized covariance with correlation exactly 1? Its a·c − b² is −0.0625 after rounding:
   the tolerance must grow with the numbers (lesson §2: tol × size², size = the largest of 1, a and
   c — not the up variance), not a fixed −tol, and not 0. You accept a = 9, b = 10, c = 9 when the up
   variance is 10⁶? Your size includes the up variance: leave it out.
</details>

## Step 3 — The stated σ (TODO 2)

Read lesson §3. **TODO 2** `stated_sigma(est, cfg)` takes an **Estimate** and the settings. Use your
`is_covariance` (do not test the rules again) and the constant `STATED_TYPES`. Read the minimum from
`cfg["min_stated_sigma_m"]`, never as a written number: mission 13 changes settings.

<details><summary>🧰 Python: membership, and a function that may return None</summary>

```python
3 in (1, 2, 3), 7 in (1, 2, 3)        # (True, False)
ok, _ = (False, "not finite")         # _ = "a value I do not need"
def first_positive(xs):
    for x in xs:
        if x > 0:
            return x
    return None                       # say it explicitly: "no answer"
```
</details>

```bash
python3 contract_lab.py test
```

<details><summary>Stuck? Hints</summary>

1. Three ways to return `None`, one way to return a number (lesson §3 list).
2. `AttributeError: 'tuple' object has no attribute 'cov'`: you called it with nine numbers; it takes an
   Estimate (`est.cov`, `est.cov_type`). `horizontal(est.cov)` gives `(a, b, c)`.
3. 11.42 instead of 13.33 for the tilted ellipse (2.55 instead of 3.0 for the example)? You averaged a and c: the contract takes the **larger**.
4. A number for the all-zero covariance: you forgot the 1 cm minimum. `3.0` for type 0: test the type first.
   `None` for σ exactly 0.01 m? The minimum itself is believed: refuse only σ **below** it (`<`, not `<=`).
</details>

## Step 4 — What a late position costs (TODO 3)

Read lesson §4. **TODO 3** `staleness_m(speed_mps, age_s)`: one line of maths, and a `ValueError` with a
clear sentence for a negative input (`raise ValueError("…")`).

```bash
python3 contract_lab.py test
```

Now the bench log: 160 day-vision fixes, each with the instant its photo was taken and the instant its
position was published. The matcher states σ = 30 m for every fix, and is good to 1 m at the photo's
instant. The runner uses **your** `staleness_m` to compute where each position really is when the judge
uses it (published = used, here).

> [!TIP] 🧰 What "within 30 m" means here
> σ is a *typical* error, not a maximum: if the errors were random with σ = 30 m east and north, about 4 in
> 10 would fall within 30 m (68 % within 1σ is for ONE axis; a 2-D position needs both errors small), 86 in 100 within 60 m (2σ), 99 in 100 within 90 m (3σ). This matcher is good to
> 1 m, so its "30 m" is meant as a safe bound: we ask how often the position stays inside it. Few fixes
> inside means the stated accuracy is false.

> [!TASK]
> **Predict** (`PREDICT_LAG`): a drone at 15 m/s; the fixes are about 1.6 s old. What percentage of them
> will be within the 30 m they state? Then run:

```bash
python3 contract_lab.py lag
```

Open `out/lag.png` now (each `--speed` run replaces it). NAVERA's simulator found a median of 83 m at
40 m/s (mission brief): its vision fixes were 1 to 2.5 s old, this bench log's are younger.

Now the fastest vehicle this matcher can serve honestly, with 90 % of its fixes within 30 m. **Compute it
first** from the lines the runner printed: the error is about speed × age, and 90 % of the ages are below
the p90 age, so which speed puts the p90 fix exactly 30 m behind? Then confirm it with **one** run, e.g.:

```bash
python3 contract_lab.py lag --speed 14
```

> [!TASK]
> Write `LAG_PLANE_MEDIAN_M`, `LAG_PLANE_WITHIN_PCT`, `LAG_DRONE_WITHIN_PCT` (15 m/s),
> `LAG_OLD_WINDOW_REFUSED` (fixes older than 3.0 s: NAVERA's old day-vision timeout, now 5 s) and
> `LAG_SPEED_MAX_MPS` (your computed speed, one decimal; your run should give about 90 % — a little less,
> because the match error adds up to 1 m). Then `EXPLAIN_LAG`, and now that you have read §4,
> `EXPLAIN_DEAD` (Step 0: what was the age of the fake GPS's fixes when the judge received them?).

<details><summary>Stuck? Hints</summary>

1. `staleness_m() returned None`: the stub's `return None` is still there.
2. The test says it must raise ValueError but yours returns a number: test `speed_mps < 0` and `age_s < 0`
   before computing.
3. For `LAG_SPEED_MAX_MPS`: 90 % within 30 m ⇔ the p90 error ≤ 30 m. Error ≈ speed × age, so
   speed ≈ 30 m ÷ (p90 age). The runner prints the p90 age on its first line.
</details>

> [!TIP] 🏅 End of session 1 — Contract keeper
> Press **✔ Check my work**: it tests your functions on cases they have never seen. When checks 1–7 pass,
> you earn the **Contract keeper** badge. If the class session ends here, stop here.

## Session 2 — Attack, then defend (1 h 45 to 2 h 30)

Read lesson §5 first, the attacker's view included.

## Step 5 — Four attacks on arbiter v0

You are the attacker. Arbiter v0 never asks some questions of the checklist. Write **four** scenario
files for the replay node, one per hole, in `attacks/`. Each must end with arbiter v0 saying **FIX** about
a fix that an honest judge must not call FIX:

| File | The hole it uses |
|---|---|
| `attacks/zero.csv` | a covariance that states a type but whose numbers are all zero |
| `attacks/unknown.csv` | numbers that the type says mean nothing |
| `attacks/not_psd.csv` | numbers that state a type but are not a covariance |
| `attacks/future.csv` | a stamp from the future — and a source that dies right after |

A scenario file has one fix per line, under this header:

```
t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s
0.0,gps,35.8256,10.6084,9.0,0.0,9.0,1,1,0.0
```

`t_s` is when the replay node publishes the row; `a, b, c` the horizontal covariance (lesson §2);
`valid` 1 or 0; `delay_s` how old the measurement already is when it is published (`header.stamp` =
now − delay_s, so a **negative** delay is a stamp in the future). Start from the given honest scenario
(three GPS fixes, σ 3 m). Look at it and at what v0 does with it (simulated clock, no ROS):

```bash
cat attacks/honest.csv
```

```bash
python3 contract_lab.py judge attacks/honest.csv
```

Make a copy for each attack and edit it in the 📝 Code tab (one copy shown; the others the same way):

```bash
cp attacks/honest.csv attacks/zero.csv
```

Test one attack against the simulated judge, then all of them:

```bash
python3 contract_lab.py judge attacks/zero.csv
```

```bash
python3 contract_lab.py attacks
```

For `future.csv`, one fix is enough, but it must be more than 0.5 s ahead: `delay_s = -0.4` is within the
tolerance, so even an honest judge accepts it (FIX) and it is no attack. Run the clock long after it and see
how long a dead source lives:

```bash
python3 contract_lab.py judge attacks/future.csv --until 70
```

> [!TASK]
> The four files exist, each one makes v0 say **FIX**, and each uses its own hole. Keep the positions in
> the test area (a few metres apart): a 5 km jump is refused by the jump gate, which is not the hole you
> are after.

<details><summary>Stuck? Hints</summary>

1. v0's σ is √max(a, c, 0) "straight from the numbers": what σ does it read from zeros? From numbers that
   type 0 says are meaningless?
2. For `not_psd`, pick a and c ≥ 0 and a b too large for them (lesson §2): v0 must still read a σ ≤ 25 m.
3. `delay_s` is how old the fix is when published; what is a negative age?
4. `DEGRADED gps: σ 30.0 m > 25.0 m`: your numbers give v0 a σ above 25 m; make them smaller.
   `NO_FIX … bad position`: check lat and lon. `source must be one of …`: gps, day, night or celestial.
</details>

## Step 6 — The attacks, live

The simulation says what v0 *should* do; now the real node. Start the judge, then play one attack:

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml > arbiter.log 2>&1 &
```

```bash
python3 -m navera_lite.ros.replay_node --ros-args -p file:=attacks/zero.csv > replay.log 2>&1 &
```

```bash
python3 contract_lab.py status
```

Stop that replay (your most recent job) and play the next file the same way (`unknown`, `not_psd`):

```bash
kill -INT %%
```

For `future.csv`, play it **once** and watch the judge for 20 s after its only fix (the first line may
still be the previous file's fix going stale; the replay sends its fix about 3 s after it starts):

```bash
python3 -m navera_lite.ros.replay_node --ros-args -p file:=attacks/future.csv -p loop:=false > replay.log 2>&1 &
```

```bash
python3 contract_lab.py status --watch 20
```

> [!TASK]
> In `VERDICTS_V0`, copy for each attack the line the **live** judge printed, e.g. `"FIX | gps: σ 0.0 m"`.
> If it differs from the simulation, a node from an earlier run is probably still playing (`jobs`). Then
> stop everything:

```bash
kill -INT $(jobs -p)
```

<details><summary>No status, or the old verdict?</summary>
"no status in this time": the judge is not running in this tab (`jobs`; read `arbiter.log`). The replay
waits 3 s before its first fix (discovery, mission 09) and the judge keeps the newest fix of each source:
read the status at least 5 s after you start a file. An ERROR "2 judges publish" in `arbiter.log`: two
arbiters run — `kill -INT $(jobs -p)` and start one.
</details>

## Step 7 — Your judge (TODO 4)

**TODO 4** `eligible(est, now_s, cfg)`: lesson §5's checklist, with the reasons of the docstring, in its
order. Use what you have: `is_covariance` (TODO 1), `age_s`, `TIMEOUT_KEY`, `STATED_TYPES` and
`is_finite_latlon` (already imported). Read every limit from `cfg`.

**Trace it by hand first** (defaults, now = 500.0 s); write your four verdicts as a comment above the
function: a day fix stamped 495.2 s · a GPS fix at (0, 0), `valid=False` · a celestial fix stamped 500.9 s,
type 2, a = 10⁸, b = 2·10⁸, c = 10⁸ · a GPS fix stamped 500.3 s with a NaN latitude. Then write the code.

<details><summary>Check your trace (after you wrote it)</summary>
Day 495.2 s → age 4.8 s ≤ 5 s: eligible · GPS (0, 0), valid False → "no position" (rule 1 comes before
rule 2) · celestial → "not a covariance": 10⁸·10⁸ − (2·10⁸)² &lt; 0, and rule 4 comes before rule 5 (it is
also 0.9 s in the future) · GPS with a NaN latitude → "bad position" (0.3 s ahead is within the tolerance
anyway).
</details>

```bash
python3 contract_lab.py test
```

```bash
python3 contract_lab.py attacks --eligible
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Eight outcomes, eight `return`s, in the docstring's order: the first rule broken decides.
2. `KeyError: 'radar'`: test whether the source has a timeout (`in TIMEOUT_KEY`) before you look it up.
3. A stamp 0.4 s in the future refused? The rule is "more than `future_tolerance_s` ahead":
   `age < −tolerance`.
4. A fix exactly 3.0 s old called stale? Stale is **older than** the timeout.
5. The stale reason must read `stale (5.3 s > 5.0 s)`: one decimal for both, `f"{x:.1f}"`. So an age of
   3.04 s prints `stale (3.0 s > 3.0 s)`: the rounding is only in the text, the test uses the exact age.
</details>

## Step 8 — Your judge, live

Arbiter v0 with **your** `eligible()` and `stated_sigma()`:

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml -p use_eligible:=true > arbiter.log 2>&1 &
```

Play your attacks again, as in Step 6, one after the other, and read the live verdict each time:

```bash
python3 -m navera_lite.ros.replay_node --ros-args -p file:=attacks/not_psd.csv > replay.log 2>&1 &
```

```bash
python3 contract_lab.py status
```

```bash
kill -INT %%
```

> [!TASK]
> Write `VERDICTS_MINE`: the live line for each of the four attacks (state | message). Replay
> `attacks/honest.csv` too: your judge must still say FIX.

Last, the future attack, live, **once**, with a long watch. Your judge refuses it. The source is dead
after its only fix.

> [!TASK]
> **Predict** (`PREDICT_REVIVE`): what will your judge say about this GPS 60 s later? Then run the two
> commands below and read the whole watch (75 s).

```bash
python3 -m navera_lite.ros.replay_node --ros-args -p file:=attacks/future.csv -p loop:=false > replay.log 2>&1 &
```

```bash
python3 contract_lab.py status --watch 75
```

> [!TASK]
> `EXPLAIN_REVIVE`: what did you see, and why? (What does the judge keep from a fix it refused? What
> changes when the clock reaches that fix's stamp?) `python3 contract_lab.py judge attacks/future.csv
> --eligible --until 70` shows the same thing in a second.

Your `eligible()` is right: the fix *was* from the future when it was tested. The hole is in the judge
around it, which keeps a refused fix and tests it again at every tick. Arbiter v0 stays as it is (it is
naive on purpose); the real arbiter you write in mission 29 must decide what to do with such a fix.

**Stop every node** before you press ✔ Check my work (the check starts its own judge, with your
`eligible()`, and plays its own attack):

```bash
kill -INT $(jobs -p)
```

## Step 9 — The limit of any checklist

Your judge now refuses impossible numbers, fake accuracies and, while they are in the future, stamps from
the future. Now imagine a source that states σ 3 m and is 500 m off.

> [!TASK]
> `EXPLAIN_HONEST`: why can no `eligible()` refuse that source, and what can? (Lesson §3, the warning.)

Press **✔ Check my work**. About 30 s (one check starts ROS nodes).

## Look back (not graded)

- Which of your four attacks would be the most dangerous on a real vehicle, and why?
- NAVERA stamps vision positions at the photo's exposure since a bug fix (LOC-17). What did the old
  stamp hide from the judge?
- Write `LOOK_BACK` in `answers.py`: one thing you will check in every message you publish from now on.

## Going further (optional)

- **A fifth hole.** Arbiter v0 has one more covariance hole, different from your four. Find it, write
  `attacks/fifth.csv`, and show that your judge closes it.
- **Close the revival.** In a copy of `NaiveJudge` (in your own file, not in `navera_lite/`), make
  `receive()` forget a fix that arrives from the future. Test it with the offline `play()` of
  `contract_lab.py`. What else must the judge then remember about that source?
- **Your own witness.** Write `my_source.py`: a node that publishes an honest day-vision `NavSatFix` on
  `navera_lite/fix/day` once every 2 s (use `convert.to_navsatfix` on an `Estimate`, stamped 1.5 s before
  "now", σ 30 m). Run it with the arbiter and no GPS: which state, and why?

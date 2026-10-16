# Lab 33 — One change to your stack, proved

**Goal:** change your own NAVERA Lite in ONE meaningful way and prove it like an engineer: a branch, a
pre-registration, a test that fails first, a campaign before and after flown from commits, a paired interval, a
decision by the rule, a report and a patch.
**Time:** three sessions, about 4 h 30 if you are fast, up to 9 h if Python or git is still slow for you (a ★★★ idea:
up to 11 h). The bench flies fast: a 40-run campaign takes
about 15 s; most of your time goes into choosing, the test, the change and the report.

| Lesson | Lab step | You make |
|---|---|---|
| (nothing first) | Step 0 | nothing: your whole stack, one flight, its metrics |
| §1, In NAVERA Lite | Step 1 | a repository; optionally your own parts in it |
| §7 | Step 2 | your choice from the menu, explored; a project branch |
| §2 | Step 3 | `project.json` (the pre-registration) |
| §3 | Step 4 | your red test, committed |
| §4 | Step 5 | the tag `before` and the baseline campaign |
| §3, §4 | Step 6 | the change, committed, green |
| §4, §5 | Steps 7–8 | the "after" campaign and the evaluation |
| §6 | Steps 9–10 | `REPORT.md`, `my_project.patch` |

Your files (📝 Code tab): [project.json](file:./project.json), [REPORT.md](file:./REPORT.md),
[answers.py](file:./answers.py), the whole stack in `navera_lite/` (its tests in `navera_lite/tests/`), the scenarios
in `campaign/`. Given, you only run it: [project.py](file:./project.py), the measuring bench (the check compares it
with the given one). `my_metric.py` only if no metric of the bench fits your project.

> [!NOTE]
> Everything is graded from **git** and from files the bench writes: the check reads your commits and tags, runs
> your test at `before` and after the change, recomputes every metric from your runs, flies one run of each campaign
> again from your commits, and compares your report with all that. Nothing can be typed in by hand — and nothing
> needs to be. The check cannot judge whether your change is a good idea: your teacher does (rubric in the
> teacher's notes).

# Session 1 — Pre-registered (1 h 30 to 3 h)

## Step 0 — Your whole stack (no code)

Write `PREDICT_SUITE` in [answers.py](file:./answers.py) first. Then the whole suite:

```bash
python3 -m pytest -q navera_lite/tests
```

One flight of the course's simulator with your stack, with the bench's metrics (`one` flies the working folder, for
exploring only):

```bash
python3 project.py one campaign/jam.json 101
```

It prints every metric of the bench for two windows: `fault` (from the jam to its end) and `all`. The list of what
each metric is sits at the top of [project.py](file:./project.py) (`METRICS`). Find `honest2` in the `fault` window:
an honest σ would give 0.86. Is the σ the judge states during the jam honest? Keep the answer for Step 2.

## Step 1 — A repository, and your own parts

The lesson folder becomes a git repository with a first commit tagged `start` (mission 14's tool):

```bash
bash navera_lite/tools/init_repo.sh
```

Now, optionally but recommended, put **your own** parts in the stack: the tool looks at your earlier lesson folders
(`../06-coordinates/`, `../29-arbiter/`…) and takes each part you finished, if the course's tests still pass with it.
First what it would do:

```bash
python3 -m navera_lite.tools.adopt
```

Read its table: "✔ adopt", or why not (a TODO left, a function your early version lacks, a failing test). Then:

```bash
python3 -m navera_lite.tools.adopt --apply
```

It runs the whole suite and one flight with all your parts together, and changes nothing if they fail. If it adopted
parts, commit them (still on `main`: this is the stack your project starts from):

```bash
git add navera_lite && git commit -m "use my own parts"
```

<details><summary>Stuck? Hints, one at a time</summary>

1. "no earlier lesson folder with parts of yours": your other missions are not in `~/lessons/` (a new account?).
   Skip the adoption: the course's parts are a fine stack.
2. "nothing adopted: with all of them together the stack does not pass": try one part at a time,
   `--only arbiter`, then `--only geo`, …
3. `git commit` says "nothing to commit": the tool adopted nothing. Fine.
</details>

## Step 2 — Choose, explore, branch

Read the menu below and choose ONE idea (or agree your own with your teacher). Before you write anything,
**explore** — with seeds **below 1000** only (the block you pre-register in Step 3 starts at 1000 or more and is never
flown while exploring; `plan` and the check refuse a block that overlaps the seeds in `my_runs/`):
fly the scenario where the problem shows, with `project.py one`, and look at the run (the CSV in `my_runs/`, its
`_events.log`, and the metrics). For example, for idea 4:

```bash
python3 project.py one campaign/night_lag.json 7
```

Exploring is allowed and useful **now**: it is how you choose a sensible metric, window and minimum effect. It must
stop once the rule is written. Then a branch for the project (a short name, letters and dashes):

```bash
git switch -c project/my-short-name
```

> [!TIP] 🧰 A scenario of your own
> A scenario is a JSON file like those in `campaign/` (mission 31 §5): `name`, `vehicle`, `vision`, `light`,
> `duration_s` and `faults` — a list of `[mission second, sensor, mode]`. Copy one to `campaign/my_case.json`, change
> the name and the faults, and fly it with `project.py one`. If your idea needs a NEW fault or sensor model (ideas
> 2, 3, 5), it goes into `navera_lite/sim/` in Step 4, before the tag `before`.

### The project menu

Choose **one**. ★ about a day's work, ★★ more design, ★★★ a real challenge (talk to your teacher first). Several
come from real problems of NAVERA, described in words; in your project they are **NAVERA Lite problems to solve** in
your own stack. The suggestions (scenarios, metric, guard-rail) are a start: the pre-registration is yours. A metric
or a guard-rail may be computed on only some of the campaign's scenarios: `"scenarios": [...]` inside it (Step 3).

| # | Idea | ★ | Where in NAVERA Lite | A first measurement idea |
|---|---|---|---|---|
| 1 | **An ageing fix keeps its σ.** A day fix states 15 m for the instant it was measured, yet the judge uses it up to 5 s later while the drone moves 15 m/s. NAVERA met it as a 1–2.5 s lag and fixed it on 2026-10-03 (simulator): its vision positions now state an accuracy grown by the lag. Make the σ the judge states grow with the fix's age. | ★ | `arbiter.py` (`Arbiter.step`), `estimate.py`, a setting in `settings.py` + `navera_lite.yaml` | `honest2` closer to 0.86 on `jam` + `lake`; guard-rail `fix_share` |
| 2 | **A frozen GPS.** A receiver that keeps sending the same position, still "valid". Add the fault `frozen` to the simulator's GPS (setup, before `before`), then a detector: refuse a GPS whose position has not moved for N fixes. Measure first: today the guard already refuses a frozen GPS after about 7 s (day vision disagrees); your detector must beat that. The simulated noise never repeats a position, so a hover — where a real receiver can — is not in the simulator: say so in your Limits. | ★★ | setup: `sim/world.py` (`FAULTS`, `gps_fix`); change: `arbiter.py` or `spoof.py` | `detect_s` on your frozen scenario (`"scenarios"`); guard-rail `false_alarm` on `baseline` |
| 3 | **The tilted ellipse.** NAVERA's judge reads one σ as √max(a, c) — up to √2 shorter than the long axis of a tilted ellipse (mission 27). NAVERA Lite's `stated_sigma` does the same. Setup: a vision profile whose error is DRAWN from a tilted ellipse AND STATED with it (b ≠ 0); change: the σ of the long axis. | ★★★ | setup: `sim/world.py` (`ProfileVision`, `cov_of`); change: `estimate.stated_sigma` with `uncertainty.ellipse` | `bad_fix` or `honest2`; guard-rail `fix_share` |
| 4 | **Night lock-in.** NAVERA's night gate compares a new fix with its own dead-reckoned anchor, and can lock onto a wrong place (mission 25). NAVERA Lite shows a related symptom: night vision "measured" follows only a quarter of the motion. Fly `campaign/night_lag.json` and watch the autopilot reset onto a position hundreds of metres off. Detect a night source that does not move like the vehicle. | ★★★ | `arbiter.py` or `spoof.py` (a motion-consistency rule) | `ap_err_max`; guard-rail `failsafe` (what will refusing cost?) |
| 5 | **The star fix and the compass.** NAVERA's star fix needs the camera's direction: 5.5–6.5 km with a perfect attitude, 53 km with 0.5° of tilt, 91 km with 2° of heading more (validation report, 2026-09-30). Setup: a celestial witness in the simulator whose error follows mission 26's rule from the heading the stack gives it — the setup is most of the work: agree its design with your teacher first; change: give it the TRUE heading (declination, mission 17). | ★★★ | setup: `sim/world.py`; change: `imu.py` functions used by the new witness | the celestial fix's own error, GPS jammed and the camera blind (`custom`) |
| 6 | **Inliers: one number, measured.** NAVERA's report validated "≥ 6 inliers", while the product's setting asks for 8. In NAVERA Lite the minimum is a default in two places (`match.gates`, `locate.DEFAULTS`). Make it one setting, then measure 6 vs 8 in the loop with day vision "mine" (slow: a 100 s day flight takes about 45 s — keep runs short). | ★★★ | `match.py`, `locate.py`, `sim/vision.py` reading the setting | `availability` vs `err_p95` with `vision: "mine"` |
| 7 | **The guard's patience.** The guard needs 5 disagreeing fixes in a row (mission 30). Fewer catch a drift sooner — and refuse an honest GPS more often (mission 31's R9). Measure both. | ★ | `spoof.py` settings (`GUARD_DEFAULTS`) | `detect_s` on `drift` only (`"scenarios"`); guard-rail `false_alarm` on `plane_late` + `baseline` (`"scenarios"`) |
| 8 | **A late camera.** Mission 31's failing run: the plane's pictures are 1.5 s old but stamped "now", and the guard refuses an honest GPS. Make the guard's time-gap term honest about a known camera latency. | ★★ | `spoof.py` (`innovation`), a setting | `false_alarm` on a late-camera plane scenario (`"scenarios"`); guard-rail **`detect_s`** on a plane drift scenario of yours with the same camera (`"scenarios"`) — `detected` alone cannot see a guard that catches the spoof 30 s later. Measure first: a latency added to the time-gap term is multiplied by `max_speed_mps` (100 m/s for the plane), which can blind the test; `plane_late`'s camera is on time for its first 20 s |
| 9 | **Retrain the night network.** Train mission 25's HomographyNet better (more pairs, more epochs, an augmentation) on mission 25's training places — never on the corridor you fly (that measures memory, not skill). The change is the weights file `ref_homography.pt`. | ★★★ | `ref_homography.pt` (+ your training script, committed); `homography_net.py` | `err_median` on `night_mine` (≈ 7 s per run, GPU) |
| 10 | **GPS bursts** (kind `sim`). Real receivers in streets meet multipath: short bursts of tens of metres. Add bursts to the simulated GPS and measure what they do to the stack (jump gate, guard, errors). | ★★ | `sim/sensors.py` / `sim/world.py` | `err_p95` or `false_alarm` with GPS "ok" |

A 0/1 guard-rail (`false_alarm`, `failsafe`, `detected`) needs many runs: 0 alarms in 30 runs only shows a rate below
about 0.11 (lesson §5), so a limit of 0.05 needs about 75 runs on that scenario (runs take well under a second).
With 20 runs on that scenario, a 0/1 guard-rail can only end inconclusive (0/20 still allows 0.16): decide the number
of runs NOW, in Step 3.

Your own idea is welcome (`"idea": "own"`): check with your teacher that it is **one** change you can **test** and
**measure** in a day. The lesson's worked example (the 2 s window) is not a project.

<details><summary>Stuck choosing? Hints, one at a time</summary>

1. Unsure of your Python or of the stack? Idea 1 (★) is fully guided below (Step 6 has its own hints).
2. An idea is good when you can say, in one sentence, what goes wrong today AND see it in a run.
3. Pick a ★★★ idea only with your teacher's agreement: they take longer than this lab's budget.
</details>

## Step 3 — Pre-register (project.json)

Open [project.json](file:./project.json) and fill it in (lesson §2): your title, your **hypothesis** (one sentence
the measurement can prove wrong), the idea's number, `kind` (`"stack"` unless you change the simulator's model), the
red test's file name, the scenarios, a block of seeds of **1000 or more that you never flew** (20 to 40 per scenario;
20 to 300 runs in all), the metric with its window, the minimum effect, the guard-rail. The directions ("better") are
fixed by each metric: `plan` tells you if you wrote the wrong one. A metric or the guard-rail can be computed on some
scenarios only: `"metric": {"name": "detect_s", "window": "fault", "scenarios": ["campaign/drift.json"]}`. Then:

```bash
python3 project.py plan
```

It checks the file and prints your rule in words. Read it as a reviewer would: is it the rule you want to be judged
by? Change it now if not — it is frozen in Step 5.

> [!TASK]
> `EXPLAIN_SEEDS` in [answers.py](file:./answers.py): why is the block of seeds fixed here, before the baseline,
> and not chosen after the results?

<details><summary>Stuck? Hints, one at a time</summary>

1. The metric must be defined in EVERY run it is computed on (an error metric needs rows with a position in the window): `project.py
   one` shows `n/a` where a metric is undefined. The bench refuses to drop runs.
2. The minimum effect is in the metric's unit (metres for `err_*`, a share 0–1 for `availability`, `honest2`).
3. `"guardrail": null` is allowed — but say in your report why your change has no price.
4. Idea 1: the lesson's ✏️ box on targets — `"better": "closer", "target": 0.86` for `honest2`.
</details>

## Step 4 — The red test

Write `navera_lite/tests/test_<your_name>.py` (the file named in `project.json`). It asks for the behaviour you
want, on small hand-made inputs — not on a whole flight (the campaign does that).

> [!TIP] 🧰 The shape of a red test (not about any idea of the menu)
> ```python
> import pytest
> from navera_lite.geo import haversine_m
>
> def test_the_new_behaviour():                       # what must BECOME true, on a tiny hand-made input
>     from navera_lite.geo import midpoint            # a NEW name: imported inside the test
>     lat, lon = midpoint(35.0, 10.0, 35.0, 10.2)
>     assert haversine_m(lat, lon, 35.0, 10.0) == pytest.approx(haversine_m(lat, lon, 35.0, 10.2), abs=0.5)
>
> def test_the_old_behaviour_is_kept():               # what must NOT change belongs in the test too
>     assert haversine_m(35.0, 10.0, 35.0, 10.0) == 0.0
> ```
> Before the change the first test FAILS (ImportError inside the test), the second passes: that is red. Test the
> behaviour your change produces, not the value of a setting: a test `refuse_n == 3` passes for any code that types 3.

Then run it:

```bash
python3 -m pytest -q navera_lite/tests
```

Your new tests must FAIL (an `F` and an `AssertionError` or an `ImportError` inside the test), the others pass.
Commit the test and the pre-registration together (with your new scenario, and `navera_lite/sim` if your idea
needs a new fault or sensor model):

```bash
git add project.json navera_lite/tests campaign && git commit -m "test: <what must become true> (red)"
```

```bash
python3 project.py red
```

`red` unpacks your last commit and checks it: your test fails, the rest of the suite passes, your tree is clean.

> [!TASK]
> `EXPLAIN_RED`: why must your test fail on the code without your change? What would a test that already passes there
> prove?

<details><summary>Stuck? Hints, one at a time</summary>

1. Look at mission 14's example tests and at an existing file of `navera_lite/tests/` for the shape: a function
   `test_…()` with `assert`s; `pytest.approx` for floats.
2. `red` says "pytest could not even run your test (exit code 2 or 4)": an import at the top of the file names
   something that does not exist yet. Move that import inside the test function.
3. `red` says "your test PASSES on the code without your change": it does not ask for anything new. Assert the NEW
   behaviour (idea 1: the σ the judge states for a 2 s old fix).
4. Idea 1: build an `Arbiter(dict(DEFAULTS, …))`, `receive()` a day `Estimate` with σ 15 m stamped at 100.0 s, and
   look at `step(102.0).sigma_m`. What should it be, and with which new setting?
</details>

## Step 5 — Freeze, and fly the baseline

Tag the red commit, then fly the baseline from it:

```bash
git tag before
```

```bash
python3 project.py campaign before
```

It unpacks the commit `before` into `runs/.code/`, flies every scenario × seed, and writes `runs/before/` (one CSV
and one events log per run, and `manifest.json`: which commit, which runs, a fingerprint of each CSV). `runs/` is
never committed (`runs/.gitignore`).

`campaign before` also checks that your metric (and guard-rail) is defined in every baseline run: if not, the rule
cannot be evaluated — make a new pre-registration now (hint 2), before the change.

Press **✔ Check my work**: checks 1–5 earn the badge **Pre-registered**. From then on your pre-registration is
**sealed**: the server keeps the id of `before` and of your project.json, and a later check fails if they move. A new
pre-registration after the badge needs your teacher (they reset the seal), and both go in your report.

<details><summary>Stuck? Hints, one at a time</summary>

1. "there is no tag 'before' yet": `git tag before` on the red commit (`git log --oneline` shows where you are).
2. You must change the test or project.json after tagging? That is a new pre-registration. **Before the change**
   (you are still on the red commit): edit, `git commit -am "pre-registration v2"`, `git tag -f before`, then
   `python3 project.py red` and `python3 project.py campaign before`. **If the change is already committed**, the tag
   must not land on top of it: start a fresh branch from the old red commit and bring the change back —
   Find the red commit first: `python3 project.py red` printed its id ("Red commit: …"), and `git log --oneline`
   shows it — the commit just BEFORE your change commit (if you already moved the tag, `before` is no longer it).
   ```bash
   git switch -c project/<name>-v2 <red-commit-id>   # the red commit, before your change
   # edit project.json (and the test if needed), then:
   git commit -am "pre-registration v2" && git tag -f before
   git cherry-pick <id of your change commit>      # git log project/<name> --oneline shows it
   python3 project.py red && python3 project.py campaign before && python3 project.py campaign after
   ```
   After the Pre-registered badge, ask your teacher first (the seal), and report both pre-registrations in section 8.
3. A run "stopped": the stack of that commit cannot fly the scenario — read the message (a scenario typo, a bug in a
   setup change); fix, commit, re-tag.
</details>

# Session 2 — Measured (1 h 30 to 4 h)

## Step 6 — The change

Now write the change in the stack. Run your test while you work, then the whole suite:

```bash
python3 -m pytest -q navera_lite/tests
```

When everything passes, commit (only the change: one concern) and let the bench check the commit:

```bash
git add navera_lite navera_lite.yaml && git commit -m "<part>: <what the change does>"
```

```bash
python3 project.py green
```

> [!TASK]
> `EXPLAIN_RULER`: for a "stack" project, why must `navera_lite/sim/world.py` be the same file before and after?

<details><summary>Stuck? Hints, one at a time</summary>

1. An OLD test fails after your change? Read it before touching it (lesson §3): does it pin a behaviour you are
   deliberately changing? Then make it test what it was written for (for example with your new setting at its old
   value) in the same commit, and say so in the report. Never delete a test.
2. A new setting: add it to `DEFAULTS` in `navera_lite/settings.py` AND to `navera_lite.yaml` (a test of the suite
   checks that the shipped file equals the defaults; `settings.load` refuses unknown keys).
3. `green` says "changed after the tag 'before'": your red test file changed. Put it back
   (`git checkout before -- navera_lite/tests/test_….py`) and put new tests in another file.
4. Idea 1: in `Arbiter.step` the winner's σ comes from `stated_sigma(est, self.cfg)`; the age is `now_s − est.stamp_s`;
   mission 12 §4 gives the distance a vehicle moves meanwhile. How do two independent errors add (mission 27)?
5. Idea 1: which speed? The top speed (`max_speed_mps`) is safe but far too cautious (most fixes would turn
   DEGRADED); the cruise speed is closer to the truth. Your guard-rail will tell.
</details>

## Step 7 — The "after" campaign

**Predict first** (`PREDICT_EFFECT`): what will D be, roughly, and will its interval contain 0? Then:

```bash
python3 project.py campaign after
```

It flies `HEAD` — your committed change — with the same scenarios and seeds as the baseline, after checking that the
stack has no uncommitted change and that `project.json` is the one of `before`. Every "after" campaign and every
evaluation is written in `runs/journal.txt`: if you evaluate a second version of your change against the same
baseline, section 8 of your report must name both commits and say why (lesson §2) — the check reads the journal.

## Step 8 — Evaluate and decide

```bash
python3 project.py evaluate
```

It prints the statistic before and after, D, its 95 % interval, the guard-rail, and the DECISION of your rule, and
writes `evaluation.json` and [out/project.png](file:./out/project.png) (your runs in pairs; the differences and the
interval). Compare with `PREDICT_EFFECT`.

> [!TASK]
> `EXPLAIN_PAIRED`: why do "before" and "after" fly exactly the same scenarios and seeds?

The decision is what it is. If it is "inconclusive" or "reject", that is your result — do not fly again with other
seeds and keep the better one (lesson §4). If you believe a larger campaign would decide, that is a NEW
pre-registration, which your report proposes in its Limits.

Press **✔ Check my work**: checks 1–8 earn the badge **Measured**.

<details><summary>Stuck? Hints, one at a time</summary>

1. "is not defined in run …": your metric has no value in some run (no row in its window). Every run counts: you need
   a new pre-registration (another metric, window, or `"scenarios"` for it), and your change must stay AFTER the new
   red commit. Ask your teacher to reset the seal, then:
   Find the red commit first: `python3 project.py red` printed its id ("Red commit: …"), and `git log --oneline`
   shows it — the commit just BEFORE your change commit (if you already moved the tag, `before` is no longer it).
   ```bash
   git switch -c project/<name>-v2 <red-commit-id>   # the red commit, before your change
   # edit project.json (and the test if needed), then:
   git commit -am "pre-registration v2" && git tag -f before
   git cherry-pick <id of your change commit>      # git log project/<name> --oneline shows it
   python3 project.py red && python3 project.py campaign before && python3 project.py campaign after
   ```
   Report both pre-registrations in section 8.
2. "the two campaigns did not fly the same project.json": you changed it after `before`. Restore it
   (`git checkout before -- project.json`), commit, fly "after" again.
3. The check says a run "is not what commit … flies": a CSV in `runs/` was edited or comes from an older campaign.
   Fly that campaign again.
</details>

# Session 3 — Engineer (1 h to 2 h)

## Step 9 — The report

Fill in [REPORT.md](file:./REPORT.md), section by section (lesson §6). Copy the numbers of `project.py evaluate` —
before, after, D and both ends of its interval, and the guard-rail's — correctly rounded, with at least 2 significant
digits (a value that is exactly 0 is written 0). Give the number of paired runs and the seeds. Section 7 starts with
the decision of your rule, then one or two sentences: why, with the interval. Section 8 says
what a simulation does not show.

> [!TIP] 🧰 Commit ids and dates for the report
> ```bash
> git log --oneline before~1..HEAD          # your commits since the one before the red test
> git log -1 --format=%ad --date=short before   # the date of the pre-registration
> ```

<details><summary>Stuck? Hints, one at a time</summary>

1. "is not in the report, correctly rounded": write the number as `evaluate` prints it (−0.1546, 0.8000), or rounded
   with at least 2 significant digits (−0.155, −0.15, 0.80), not truncated (−0.154 is wrong) and not as a vague −0.2.
   Minimum words: section 1: 40; sections 2–4: 30; section 5: 25; section 6: 20; section 7: 15; section 8: 50.
2. "claims a gain": your decision is not "accept", and a sentence says "better", "improves", "fixes"… Say what the
   interval allows: "not shown", "inconclusive", "rejected because…".
3. A share may be written as a percentage (0.049 → 4.9 %).
</details>

## Step 10 — The patch, the last commit

A reviewer applies your change elsewhere with `git apply`. Make the patch and check that it matches your branch (the
second command prints nothing when it does):

```bash
git diff before HEAD -- navera_lite navera_lite.yaml > my_project.patch
```

```bash
git apply --check -R my_project.patch
```

(`-R` means "in reverse": if the patch can be undone on your branch, it is exactly what your branch added.) Then
commit the report (the stack does not change any more, so your campaigns stay valid):

```bash
git add REPORT.md answers.py && git commit -m "docs: project report"
```

Press **✔ Check my work**: all 12 checks earn the badge **Engineer**.

## Look back (not graded)

1. Which fork of the garden were you most tempted by (a metric, a window, a seed, a limit)?
2. Your decision: would you merge your branch into the product today? What would you measure first, in the field?
3. `LOOK_BACK` in `answers.py`: one sentence for your future self about measuring a change.

## Going further (optional)

- **A mutant of your fix** (mission 14): break your change on purpose (a wrong sign, a missing factor) and run your
  red test. Does it catch the mutant? If not, your test does not guard your change: strengthen it in another file.
- **Teams on the same idea.** Two students with the same idea pre-register different seeds and compare their
  intervals. Do they overlap? Should they?
- **Another vehicle.** Fly your change on the plane (`"vehicle": "plane"`, 40 m/s) as a NEW pre-registration: does
  your design still hold?

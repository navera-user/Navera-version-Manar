# Lab 33 — One change to your stack, proved

**Goal:** change your own NAVERA Lite in ONE meaningful way and prove it like an engineer: a branch, a
pre-registration, a test that fails first, a campaign before and after flown from commits, a paired interval, a
decision by the rule, a report and a patch.
**Time:** 5 h 30 to 8 h in three sessions (a ★★★ idea: up to 10 h). The bench flies fast: a 40-run campaign takes
about 15 s; most of your time goes into choosing, the test, the change and the report.

| Lesson | Lab step | You make |
|---|---|---|
| (nothing first) | Step 0 | nothing: your whole stack, one flight, its metrics |
| §1, In NAVERA Lite | Step 1 | a repository; optionally your own parts in it |
| §7 | Step 2 | your choice, explored; a project branch |
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

# Session 1 — Pre-registered (2 h to 2 h 30)

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

Read lesson §7 and choose ONE idea (or agree your own with your teacher). Before you write anything, **explore**:
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

<details><summary>Stuck choosing? Hints, one at a time</summary>

1. Unsure of your Python or of the stack? Idea 1 (★) is fully guided below (Step 6 has its own hints).
2. An idea is good when you can say, in one sentence, what goes wrong today AND see it in a run.
3. Pick a ★★★ idea only with your teacher's agreement: they take longer than this lab's budget.
</details>

## Step 3 — Pre-register (project.json)

Open [project.json](file:./project.json) and fill it in (lesson §2): your title, the idea's number, `kind`
(`"stack"` unless you change the simulator's model), the red test's file name, the scenarios, a block of seeds
(20 to 40 per scenario; 20 to 300 runs in all), the metric with its window, the direction, the minimum effect, the
guard-rail. Then:

```bash
python3 project.py plan
```

It checks the file and prints your rule in words. Read it as a reviewer would: is it the rule you want to be judged
by? Change it now if not — it is frozen in Step 5.

> [!TASK]
> `EXPLAIN_SEEDS` in [answers.py](file:./answers.py): why is the block of seeds fixed here, before the baseline,
> and not chosen after the results?

<details><summary>Stuck? Hints, one at a time</summary>

1. The metric must be defined in EVERY run (an error metric needs rows with a position in the window): `project.py
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
>
> def test_the_new_setting_exists():
>     from navera_lite.settings import DEFAULTS        # a NEW name: imported inside the test
>     assert DEFAULTS["my_new_key"] == pytest.approx(2.5)
>
> def test_the_old_behaviour_is_kept():               # what must NOT change belongs in the test too
>     from navera_lite.geo import haversine_m
>     assert haversine_m(35.0, 10.0, 35.0, 10.0) == 0.0
> ```
> Before the change the first test FAILS (KeyError), the second passes: that is red.

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

Press **✔ Check my work**: checks 1–5 earn the badge **Pre-registered**.

<details><summary>Stuck? Hints, one at a time</summary>

1. "there is no tag 'before' yet": `git tag before` on the red commit (`git log --oneline` shows where you are).
2. You must change the test or project.json after tagging? Then it is a new pre-registration: commit the new
   version, move the tag (`git tag -f before`), fly the baseline again. Do it before Step 6, never after a result.
3. A run "stopped": the stack of that commit cannot fly the scenario — read the message (a scenario typo, a bug in a
   setup change); fix, commit, re-tag.
</details>

# Session 2 — Measured (2 h to 3 h)

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
stack has no uncommitted change and that `project.json` is the one of `before`.

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
   a new pre-registration with another metric or window (a new red commit, `git tag -f before`, both campaigns again).
2. "the two campaigns did not fly the same project.json": you changed it after `before`. Restore it
   (`git checkout before -- project.json`), commit, fly "after" again.
3. The check says a run "is not what commit … flies": a CSV in `runs/` was edited or comes from an older campaign.
   Fly that campaign again.
</details>

# Session 3 — Engineer (1 h to 1 h 30)

## Step 9 — The report

Fill in [REPORT.md](file:./REPORT.md), section by section (lesson §6). Copy the numbers of `project.py evaluate` —
before, after, D and both ends of its interval, and the guard-rail's — correctly rounded, with at least 2 significant
digits. Give the number of paired runs and the seeds. Section 7 starts with the decision of your rule. Section 8 says
what a simulation does not show.

> [!TIP] 🧰 Commit ids and dates for the report
> ```bash
> git log --oneline before~1..HEAD          # your commits since the one before the red test
> git log -1 --format=%ad --date=short before   # the date of the pre-registration
> ```

<details><summary>Stuck? Hints, one at a time</summary>

1. "is not in the report, correctly rounded": write the number as `evaluate` prints it, or rounded (−0.1546 → −0.155
   or −0.15), not truncated (−0.154 is wrong) and not as a vague −0.2.
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

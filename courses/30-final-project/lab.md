# Lab 30 — Your project, from proposal to patch

**Goal:** improve NAVERA with **one** change: a written proposal, a test that fails first, a
before/after measurement with bootstrap confidence intervals, a decision, a commit on a branch, a
patch and a report.
**Time:** about 4 h for parts A and B (statistics tools + the guided example), then your own project
(part C): plan 3–4 more hours (6–8 h in total) if you choose another idea.

Your files: [stats_tools.py](file:./stats_tools.py) (percentile and bootstrap — for every project),
[measure_project.py](file:./measure_project.py) (the example's measurement),
[PROJECT.md](file:./PROJECT.md) (your report). The bench data is in
`/data/academy/30-final-project/` (read only).

## Part A — The statistics tools (45 min)

### Step 1 — Look at the data

```bash
head -4 /data/academy/30-final-project/nmea_bench.txt
```

```bash
cat /data/academy/30-final-project/truth.json
```

30 minutes of a **simulated** receiver standing still at a point in Sousse, Tunisia (NAVERA's test area), one GGA
and one RMC sentence per second. The truth is known, so every fix has an exact error. The file
contains degraded episodes (3 satellites, 4 satellites, no fix, the receiver's own dead-reckoning) and
about 1 % corrupted lines. Its errors are **correlated in time** (AR(1), ρ = 0.9), like real
multipath. In the GGA line, field 7 is the fix quality, field 8 the number of satellites, field 9 the
HDOP.

### Step 2 — `percentile()` (TODO 1)

Open [stats_tools.py](file:./stats_tools.py) and complete `percentile(values, q)` with the linear
interpolation formula of the course. Do not call `np.percentile` inside it — but use it to compare:

```bash
python3 -c "import stats_tools as s; print(s.percentile([2.1, 3.4, 1.8, 2.9, 4.2, 2.5, 38.0, 3.1], 95))"
```

You should see `26.17000000000001`: 26.17 m, the worked example of the course (the last digits are floating-point rounding). Common mistakes: forgetting to sort;
`q = 100` (h = n − 1 has no right neighbour, so return the last value); an empty list must give
`math.nan`, not an `IndexError`.

### Step 3 — `bootstrap_ci()` and `block_bootstrap_ci()` (TODO 2 and 3)

Complete both functions following their docstrings. Create the random generator **once**, before the
loop: `rng = np.random.default_rng(seed)`. If you create it inside the loop, every resample is the same.
For TODO 3, `block_indices(n, block_len, rng)` is already written: read it and check that you
understand the line `starts[:, None] + np.arange(block_len)[None, :]` (a k × L table of indices).

```bash
python3 stats_tools.py
```

The demo builds a correlated error series whose **true mean is 0** and prints two 95 % CIs of its
mean. Expect something like:

```
mean = -0.121; iid bootstrap 95 % CI   [-0.168, -0.079]  width 0.089
                block bootstrap 95 % CI [-0.334, +0.037]  width 0.371
```

The iid interval **does not contain the true value 0**: it is about 4 times too narrow, as the
course predicted (√19 ≈ 4.4). The block interval does contain it.

> [!TASK]
> Complete TODO 1–3 in `stats_tools.py`. "Done" means: `percentile` equals numpy's default on any
> input; `bootstrap_ci(values, stat, n_boot, alpha, seed)` returns `(lo, hi)`, is reproducible with a
> seed and has the right width; `block_bootstrap_ci(n, metric, block_len, n_boot, alpha, seed)` calls
> `metric(idx)` with block resamples. Checks 1–4.

## Part B — The whole workflow once, on the example (about 2 h)

Follow it even if you will choose another idea: every step is the same for your own project.

### Step 4 — Start clean, make a branch

```bash
cd ~/navera && git status --short | head
```

If it lists files you changed in earlier lessons, keep them out of the project: commit them on their
own branch, or use **Reset my NAVERA copy** (it makes a backup first). Tell git who you are (once),
then create the project branch **from `base`**:

```bash
cd ~/navera && git config user.name "Your Name" && git config user.email "you@example.com"
```

```bash
cd ~/navera && git checkout -b project/min-satellites base
```

### Step 5 — Understand the code

```bash
grep -n "_VALID_GPS_QUAL\|num_sats\|def _publish_fix" ~/navera/gps_pkg/gps_pkg/nodes/gps_node.py
```

Open [gps_node.py](file:navera/gps_pkg/gps_pkg/nodes/gps_node.py) and read `_publish_fix()`. A GGA
sentence is a fix when its quality is 1, 2, 4 or 5 and it has a position. The number of satellites
is read **after** the decision, only for the log: a 3-satellite fix goes through.

### Step 6 — Write the proposal now

Open [PROJECT.md](file:./PROJECT.md) and fill in **## Proposal**: Problem, Hypothesis, Metric
(primary: p95 error of accepted fixes, lower is better; guard-rail: availability) and **Acceptance
criterion** — for the example: *accept if the 95 % CI of Δp95 is entirely below 0 m and the 95 % CI of
Δavailability stays above −10 points; moving-block bootstrap, blocks of 60 s, 2000 resamples, seed 30*.
This criterion is the constant `MAX_AVAILABILITY_LOSS = 0.10` in `measure_project.py`. Save the file
before you measure the "after" result.

### Step 7 — Measure **before** (TODO 4)

Open [measure_project.py](file:./measure_project.py). `load_epochs()` reads the file exactly like
gps_node (pynmea2, checksum required); one epoch = one GGA line, even a corrupted one (it counts as
"not accepted" — the receiver was silent for that second). Complete `summary(accepted, errors)` (its
docstring lists the keys). Then:

```bash
python3 measure_project.py
```

You should see:

```
1800 epochs (GGA lines), 1780 with a valid checksum
BEFORE: 1736 of 1800 epochs accepted (availability 96.4 %), CEP50 2.28 m, p95 43.33 m, max 146.7 m
AFTER : gps_node.fix_problem() does not exist yet on your branch — make the change (Step 9), then run me again
```

A CEP50 of 2.3 m and a p95 of 43 m: the median hides the bad episodes completely.

### Step 8 — Write the test first

Create the test file and open it:

```bash
touch ~/navera/gps_pkg/test/test_gga_validation.py
```

[test_gga_validation.py](file:navera/gps_pkg/test/test_gga_validation.py) — the design: a **pure
function** `fix_problem(gps_qual, has_pos, num_sats)` in `gps_node.py` that returns `""` for a usable
fix, or the reason why not, and a constant `MIN_SATELLITES = 4`. Your tests build real GGA sentences
with a correct checksum (the checksum is the XOR of all characters between `$` and `*`, written in two
hex digits — see `_cs()` in `navera_tools/sim/nmea_gps.py`) and parse them with
`pynmea2.parse(..., check=True)`. Cover at least:

- a normal fix (8 satellites) → `""`;
- quality 0 → starts with `"no GPS fix"`; quality 6 → contains `"non-satellite"` (old behaviour kept);
- 3 satellites → refused; 4 → accepted (the boundary);
- an empty satellite field (`num_sats=None`) → not judged; a missing position → refused.

Run it — it must **fail** (`ImportError`: the function does not exist yet):

```bash
cd ~/navera && python3 -m pytest -q gps_pkg/test/test_gga_validation.py
```

### Step 9 — The change

In `gps_node.py`: add `MIN_SATELLITES = 4` next to `_VALID_GPS_QUAL`; write `fix_problem()` (it takes
over the two existing reason texts and adds `"only N satellites (a 3-D fix needs 4) — not used"`); and
make `_publish_fix()` read `num_sats` **before** the decision and use `fix_problem(...)`: when it
returns a reason, publish the invalid estimate with that reason (the code path that already exists for
"no fix"). Keep the change small: no renaming, no reformatting. Then your test and the package's tests:

```bash
cd ~/navera && python3 -m pytest -q gps_pkg/test
```

All green (your tests plus the existing `test_ros_gps.py`). If an old test fails: fix your change, not
the test.

### Step 10 — Measure **after**, with confidence intervals (TODO 5)

Complete TODO 5 in `main()`: the paired moving-block bootstrap of the p95 of each rule, of the p95
difference, of each availability and of the availability difference (same `SEED`, so the same
resampled epochs for both rules), then the decision and `write_results(...)`. Run it again — the
2000 × 5 resamples take some seconds:

```bash
python3 measure_project.py
```

```bash
cat results.json
```

Copy the numbers into **## Measurement** of PROJECT.md as a table (before, after, difference, each with
its CI). Then try the iid version for comparison — it is one argument (`BLOCK_LEN`):

```bash
python3 -c "import measure_project as m; m.BLOCK_LEN = 1; m.main()"
```

Note the iid CIs and the decision they give in your report (as a comparison only), then run
`python3 measure_project.py` again so that `results.json` holds the block result.

> [!QUESTION]
> With blocks of 60 s, the CI of Δp95 is entirely below zero, but the decision is not "accept". Why?
> What data would you need to reach a clear decision?

<details><summary>Answer</summary>
The availability CI (about [−13.9, −2.0] points) crosses the −10 point limit fixed in the proposal:
the cost might be too high. The file has only four 3-satellite episodes, so the block bootstrap
sees few independent events. More recordings with more independent episodes (and real receivers)
would narrow the interval.
</details>

> [!TASK]
> TODO 4 and TODO 5 in `measure_project.py`; `results.json` written by the block bootstrap;
> **## Proposal** and **## Measurement** of PROJECT.md filled in. Checks 5, 7–10.

### Step 11 — Commit and export the patch

```bash
cd ~/navera && git add gps_pkg/gps_pkg/nodes/gps_node.py gps_pkg/test/test_gga_validation.py && git commit -m "gps: refuse GGA fixes computed from fewer than 4 satellites"
```

```bash
cd ~/navera && git log --oneline base..HEAD && git diff base --stat
```

```bash
cd ~/navera && git diff base > ~/lessons/30-final-project/my_project.patch
```

```bash
cd ~/navera && git apply --check -R ~/lessons/30-final-project/my_project.patch && echo "patch matches the branch"
```

Open [my_project.patch](file:./my_project.patch): lines with `+` were added, `-` removed. This file is
your change, ready for a reviewer.

### Step 12 — The report

Finish [PROJECT.md](file:./PROJECT.md): **Change** (what, where, the commit), **Test** (cases, command,
result line, "failed on base"), **Result** (the decision and why, in one honest paragraph), **Limits**
(synthetic data from one place, few independent episodes, no real receiver, effect on the arbiter not
tested…).

> [!TASK]
> Deliver the example (or your own project, part C): PROJECT.md complete, a project branch with your
> commit(s) and a clean working tree, a test that passes on your branch and **fails on base**, the
> package's tests green, and `my_project.patch` exported after your last commit. Press
> **✔ Check my work** — all 16 checks.

## Part C — Your own project

Pick an idea from the course (or your own, agreed with the teacher). Start a **new branch from
`base`**, so the example does not mix with your project:

```bash
cd ~/navera && git checkout -b project/my-idea base
```

(Replace `my-idea` with a short name.) Then the same loop: proposal → measure before → test first →
change → tests green → measure after with CIs → decision → commit → patch → report. Write your own
measurement script in this folder; reuse `percentile`, `bootstrap_ci` (independent samples, e.g. one
value per test frame) or `block_bootstrap_ci` (time series), and write `results.json` with
`write_results()` — set `project` to your branch's short name. The check always looks at the branch
you are **on** (`git branch --show-current`).

A skeleton for your own measurement script (`measure_mine.py`) — replace the three `...` parts:

```python
import numpy as np
from stats_tools import block_bootstrap_ci, percentile, write_results

# 1. load: one value per epoch (time series) for BEFORE and AFTER, on the SAME epochs
before = np.array(...)            # e.g. the error of each epoch with the base code
after = np.array(...)             # the same epochs with your change
def metric(x):                    # 2. your primary metric, as fixed in the proposal
    return percentile(x, 95)      #    (target metric: abs(coverage(x) - 86.0), better="closer")
n = len(before)
# 3. paired moving-block bootstrap: the SAME resampled epochs for before and after
ci = lambda f: block_bootstrap_ci(n, f, block_len=60, n_boot=2000, seed=30)
b, a = metric(before), metric(after)
res = {"before": {"value": b, "ci95": ci(lambda i: metric(before[i]))},
       "after": {"value": a, "ci95": ci(lambda i: metric(after[i]))},
       "difference": {"value": a - b, "ci95": ci(lambda i: metric(after[i]) - metric(before[i]))}}
lo, hi = res["difference"]["ci95"]
decision = "accept" if hi < 0 else ("reject" if lo > 0 else "inconclusive")   # for better="lower"
write_results("results.json", project="my-idea", metric="p95 error", unit="m", better="lower",
              data=..., n=n, bootstrap={"method": "moving-block", "block_len": 60, "n_boot": 2000,
              "seed": 30}, acceptance="95 % CI of the difference entirely below 0", decision=decision, **res)
```

For independent samples (one value per test frame, not a time series) use `bootstrap_ci` instead,
with the same idea.

> [!TIP]
> Stuck? Make the change smaller. A small change, well tested and honestly measured, is a much better
> project than a big one that "should work". An honest "inconclusive" with a clear plan for more data
> is a good result.

> [!TASK]
> Your project delivered with the same 8 deliverables (course, section 11). For a project other than
> the example, check 10 (re-measurement of the example) is skipped. Press **✔ Check my work**.

## Going further (optional)

- **A property-based test.** Add a `hypothesis` test to your test file (course, section 8): for every
  satellite count 0–3 and every valid quality, `fix_problem` refuses; for 4–12 it accepts. Run it with
  pytest; how many examples did it generate (`--hypothesis-show-statistics`)?
- **Choose the block length from data.** Run TODO 5 with `BLOCK_LEN` = 1, 5, 10, 20, 30, 60, 120 and
  plot the width of the Δp95 CI against L (matplotlib, save a PNG). Where is the plateau? Compare with
  the correlation time −1/ln ρ.
- **Run the whole suite** (unit tests of every package, a few minutes):
  `cd ~/navera && navera_tools/run_tests.sh`. A product team runs it before every merge.
- **Review a friend's patch.** Apply it on a fresh branch (`git checkout -b review base && git apply
  their.patch`), run their test on base and on the branch, and write them three lines: what is clear,
  what is missing, one question about their CI.

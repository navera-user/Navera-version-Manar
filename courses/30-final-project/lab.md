# Lab 30 — Your project, from branch to patch

**Goal:** improve NAVERA with **one** change, tested and measured before/after, documented in
`PROJECT.md`, committed on a branch and exported as a patch.
**Time:** 3–6 h (part 1, the guided example: 45 min; part 2, your project: the rest).

Your files: [PROJECT.md](file:./PROJECT.md) (your report — the template), and this lesson folder for
your measurement scripts and the patch.

## Part 1 — The whole workflow once, on the example (idea 1)

Follow it even if you will choose another idea: every step is the same for your project. If you choose
idea 1 as your project, this part *is* your project — then write the report with your own words and
numbers.

### Step 1 — Start clean, make a branch

```bash
cd ~/navera && git status --short | head
```

If it lists files you changed in earlier lessons, keep them out of the project: save them on their
own branch or commit, or ask the teacher about **Reset my NAVERA copy** (it makes a backup first).
Then tell git who you are (once) and create the project branch:

```bash
cd ~/navera && git config user.name "Your Name" && git config user.email "you@example.com"
```

```bash
cd ~/navera && git checkout -b project/min-satellites
```

### Step 2 — Understand

```bash
grep -n "_VALID_GPS_QUAL\|num_sats\|def _publish_fix" ~/navera/gps_pkg/gps_pkg/nodes/gps_node.py
```

Open [gps_node.py](file:navera/gps_pkg/gps_pkg/nodes/gps_node.py) and read `_publish_fix()`: a GGA
sentence is a fix when its *quality* is 1, 2, 4 or 5 and it has a position. The number of satellites is
read — but only *after* the decision, for the log. A fix from 3 satellites goes through.

### Step 3 — Measure **before**

The bench file `/data/academy/30-final-project/nmea_bench.txt` is 10 minutes of a (simulated) receiver
standing still, with some bad moments: few satellites, no fix, dead-reckoning, a corrupted line. Write a
measurement script in your lesson folder, `measure_project.py`, that:

- reads the file line by line with `pynmea2.parse(line.strip(), check=True)` (skip `ParseError`: a bad
  checksum is never a fix — exactly like `gps_node`);
- keeps the GGA sentences (`isinstance(m, pynmea2.types.talker.GGA)`);
- counts the fixes **the current rule** accepts (`qual in (1, 2, 4, 5)` and a position) and the error of
  each against `/data/academy/30-final-project/truth.json` (lesson 26's `to_local_m` + Pythagoras);
- prints the number accepted, the median, p90 and max error (lesson 29).

Run it **before** changing anything and copy the numbers into the *Measurement* section of
[PROJECT.md](file:./PROJECT.md).

### Step 4 — Write the test first

Create `~/navera/gps_pkg/test/test_gga_validation.py`. The idea: a **pure function**
`fix_problem(gps_qual, has_pos, num_sats)` in `gps_node.py` that returns `""` for a usable fix, or the
reason why not. Test it with real GGA sentences built in the test (with a correct checksum — see how
`_cs()` does it in `navera_tools/sim/nmea_gps.py`):

- a normal fix (8 satellites) → `""`;
- quality 0 → starts with `"no GPS fix"`; quality 6 → mentions `"non-satellite"` (the old behaviour must
  not change!);
- 3 satellites → refused; 4 → accepted; an empty satellite field → not judged.

Run it — it must **fail** (the function does not exist yet):

```bash
cd ~/navera && python3 -m pytest -q gps_pkg/test/test_gga_validation.py
```

### Step 5 — The change

In `gps_node.py`: add `MIN_SATELLITES = 4`, write `fix_problem()` (it takes over the two existing reason
texts), and make `_publish_fix()` use it: read `num_sats` **before** the decision, and when
`fix_problem(...)` returns a reason, publish the invalid estimate with that reason — the code path that
already exists for "no fix". Run the test again: it passes. Then the package's existing tests:

```bash
cd ~/navera && python3 -m pytest -q gps_pkg/test
```

### Step 6 — Measure **after**, commit, export

Add the *after* rule to your measurement script (`fix_problem(...) == ""`, imported with
`from gps_pkg.nodes.gps_node import fix_problem`) and run it again: fewer fixes accepted, a much smaller
p90 and max. Then:

```bash
cd ~/navera && git add gps_pkg/gps_pkg/nodes/gps_node.py gps_pkg/test/test_gga_validation.py && git commit -m "gps: refuse GGA fixes computed from fewer than 4 satellites"
```

```bash
cd ~/navera && git log --oneline base..HEAD && git diff base --stat
```

```bash
cd ~/navera && git diff base > ~/lessons/30-final-project/my_project.patch
```

Open [my_project.patch](file:./my_project.patch): lines starting with `+` were added, `-` removed. This
file is your change, ready for a reviewer.

> [!TASK]
> Fill in the six sections of [PROJECT.md](file:./PROJECT.md) for your project (if it is idea 1: with
> your own measurement). Press **✔ Check my work** — it reads your report, your branch, runs your tests
> and the package's tests, and checks the patch.

## Part 2 — Your own project

Pick an idea from the course (or your own, agreed with the teacher). If it is not idea 1, start a **new
branch from `base`**, so the example does not mix with your project:

```bash
cd ~/navera && git checkout -b project/my-idea base
```

(Replace `my-idea` with a short name.) Then the same steps: understand → measure before → test first →
change → test → measure after → commit → `git diff base > ~/lessons/30-final-project/my_project.patch`
→ `PROJECT.md`. The check always looks at the branch you are **on** (`git branch --show-current`).

> [!TIP]
> Stuck? Make the change smaller. A small change, well tested and honestly measured, is a much better
> project than a big one that "should work".

> [!TASK]
> Deliver your project: `PROJECT.md` filled in, a project branch with your commit(s), a test that passes,
> the package's tests still green, and `my_project.patch` exported **after your last commit**. Press
> **✔ Check my work**.

## Going further (optional)

- **Run the whole suite** (unit tests of every package, ~2–5 min):
  `cd ~/navera && navera_tools/run_tests.sh`. A product team runs it before every commit.
- **Review a friend's patch.** Ask for their `my_project.patch`, apply it to a fresh branch
  (`git checkout -b review base && git apply their.patch`), run their test, and write them three lines:
  what is clear, what is missing, one question.
- **Present it.** Five minutes, three slides: the problem, the numbers, the limits.

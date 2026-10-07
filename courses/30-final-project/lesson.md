# Final project: improve NAVERA

You have read NAVERA's code, rebuilt its arbiter, attacked it with a fake GPS, flown it in the
simulator and measured it honestly. Now it is your turn to **make it better** — the way the engineers
who build it work every day.

This lesson is short on theory and long on practice: how professionals turn an idea into a change that
others can trust, a menu of project ideas from easy to hard, and the deliverables the check expects.

## 1. How engineers change a product that works

NAVERA's own engineering guide (`CLAUDE.md` in your copy) starts with golden rules. Three of them are
the heart of this project:

> 1. **The system currently WORKS. Never break a working pipeline.**
> 5. **One concern per commit.** Cleaning, refactor, optimization, and new features go in separate commits.
> 6. **Measure, don't guess.** For any performance/accuracy claim, run a measurement and report the number.

And its workflow for every task: **understand → branch → change → verify → commit → report**. Here is
what each step means for you:

![The engineer's loop](assets/workflow.svg)


| Step | What you do | Tool |
|---|---|---|
| **Understand** | read the files you will touch; find who calls them (`grep -rn name ~/navera --include=*.py`) | editor, `grep` |
| **Branch** | your own line of work, so `work` stays clean: `git checkout -b project/<short-name>` | git (lesson 5) |
| **Measure before** | run your measurement on the *unchanged* code and write the numbers down | a small script |
| **Change** | the **smallest** change that does the job | editor |
| **Test** | a unit test that would have **failed before** and passes now; then the package's existing tests | pytest (lesson 14) |
| **Measure after** | the same measurement, same data, same command | the same script |
| **Commit** | a clear message: *what* and *why* in one line | `git commit` |
| **Report** | idea, change, test, measurement, result, limits — `PROJECT.md` | Markdown |
| **Share** | a patch file anybody can apply to their copy | `git diff base > my_project.patch` |

### One change, measured before and after

Why only one change? Because if you change three things and the result improves, you do not know which
one helped — or whether one of them made things worse and was hidden by the others. One change, one
measurement, one conclusion.

Why *before* and *after*? Because a number alone means nothing. "Day vision error: 12 m" — is that good?
Compared with what? "12 m, before my change 31 m, on the same 33 frames" is a result. Lesson 29 taught
you the rest: median, p90 and max, the number of samples, a baseline, and *where* it was measured.

### A test that would have failed before

The best test for a fix is one you write **first**, watch **fail** on the old code, then watch **pass**
after your change. It proves two things at once: that the test really checks your problem, and that
your change solves it. And it stays in the product forever, so that nobody breaks it again by accident.

### Honest limits

Every report in NAVERA ends with what is *not* proven. Look at VALIDATION_STATUS.md: "**Simulator
only.**", "not yet measured with NAVERA's camera", "Synthetic data only". Your project report does the
same. A limit clearly stated is not a weakness — it is what makes the rest believable.

## 2. Git for a project

You know the basics from lesson 5. The full workflow of the project, in your NAVERA copy:

```bash
cd ~/navera
git status                               # clean? (build/, install/, log/ are ignored)
git checkout -b project/min-satellites   # a branch for your project
# … edit, test …
git add gps_pkg/gps_pkg/nodes/gps_node.py gps_pkg/test/test_gga_validation.py
git commit -m "gps: refuse GGA fixes computed from fewer than 4 satellites"
git log --oneline base..HEAD             # your commits since the start
git diff base --stat                     # which files you changed
git diff base > ~/lessons/30-final-project/my_project.patch
```

`base` is a **tag** on the commit your copy started from. `git diff base` is therefore *everything
you changed* — exactly what a reviewer needs. A **patch** file is that diff saved in a file: anyone can
apply it to their own copy with `git apply my_project.patch`. That is how changes travel between
engineers (and how a teacher reviews your project).

> [!TIP]
> Your copy is built with `colcon build --symlink-install`: changes to Python files work **immediately**,
> no rebuild. Only changes to messages (`navera_msgs`) or to a package's `setup.py` need
> `colcon build --symlink-install --packages-select <package>`. And the **Reset my NAVERA copy** button
> saves your work in a backup before resetting — but commit often anyway.

## 3. Project ideas

Choose **one**. Difficulty: ★ a few lines, ★★ an afternoon, ★★★ a real challenge. Each idea says where
to start; the tests are yours to write.

| # | Idea | Difficulty | Start here |
|---|---|---|---|
| 1 | **Refuse GPS fixes from fewer than 4 satellites.** A 3-D fix needs 4 satellites; with 3, receivers guess an altitude and can be tens of metres off. Today `gps_node` only looks at the GGA *quality*. Measure on the bench NMEA file `/data/academy/30-final-project/nmea_bench.txt` (simulated, with truth). | ★ | `gps_pkg/gps_pkg/nodes/gps_node.py` (`_publish_fix`), tests in `gps_pkg/test/` |
| 2 | **A clearer status line in the operator view.** When NAVERA is NO FIX, show *for how long* ("NO FIX since 12 s"). The operator should not have to guess whether it just happened. | ★ | `simulation_web/simulation_web/resources/operator.html` (`showNoPosition`); tests in `simulation_web/test/test_operator_sim.py` |
| 3 | **An HDOP-aware jump margin.** The kinematic gate allows a fixed 50 m of GPS noise. A GPS that states σ 40 m (HDOP 20) can jump more than that without any spoofing. Make the margin `max(50, 3 × stated σ)` — as a pure function with unit tests, used by the estimator. Measure with the lesson 27 scenarios and `navera_tools/tests/test_estimator.py`. | ★★ | `navera_estimator/…/estimator_node.py` (`_check_gps_plausibility`); put the pure function in `navera_common/navera_common/` with a test in `navera_common/test/` |
| 4 | **Skip featureless frames before matching.** Lesson 20's "matchability": count SIFT features (or measure texture) and refuse a frame over sea or desert *before* the expensive search, with a clear reason. Measure the time saved and that no good frame is lost (benchmark frames, lesson 22). | ★★ | `day_pkg/day_pkg/local_matcher.py` (`locate`: "too few features…"); tests in `day_pkg/test/test_local_matcher.py` |
| 5 | **A visual-odometry drift alarm.** Lesson 23: VO drifts. Compute how far a dead-reckoned position has gone since its last measured fix and log a warning past a threshold; check it on a recorded track. | ★★ | `navera_common/navera_common/track.py` (`TrackVelocity.propagate`), `navera_common/test/test_track.py` |
| 6 | **A new fault in the simulator: "GPS frozen".** The receiver keeps sending the *same* position with a fix (a known receiver failure). Add it to the simulated receiver, then test in the simulator: does NAVERA notice? (Hint: it is *plausible* for the kinematic gate…) Report what happens. | ★★ | `navera_tools/sim/nmea_gps.py` (`MODES`, `reported`), the Faults buttons in `navera_tools/sim/sim.html` |
| 7 | **A "GPS frozen" detector.** After idea 6: in the arbiter, refuse a GPS whose position has not changed for N fixes while vision (or the IMU) says the vehicle moves. Unit-test the rule as a pure function; integration-test it with a scripted publisher (lesson 25's `compare_real.py` is a model). | ★★★ | `estimator_node.py` (`_on_gps`, `_check_gps_plausibility`) |
| 8 | **Is day vision's stated σ honest?** Record a simulator flight in shadow mode, run `evaluate_session.py`, and propose (with numbers) the σ day vision should state in the simulator. A measurement project: the deliverable is the method and the numbers, plus a test for any tool you change. | ★★★ | `navera_tools/evaluate_session.py`, `navera_tools/record_session.sh`, lesson 29 |

Your own idea is welcome too — check with the teacher that it is **one** change you can **test** and
**measure** in a few hours.

> [!WARNING]
> Projects 6 and 7 need the simulator: book it, and keep your flights short. Never change files outside
> `~/navera` and your lesson folder — your copy is yours, the product is not.

## 4. The deliverables

The check verifies five things:

1. **`PROJECT.md`** in your lesson folder, with the six sections filled in: *Idea, Change, Test,
   Measurement, Result, Limits*.
2. **A project branch** in `~/navera` (not `work`) with **at least one commit** since `base`, and
   nothing left uncommitted.
3. **A test**: your commits add or change at least one `test_*.py` file — and **it passes**.
4. **Nothing broken**: the existing unit tests of every package you touched still pass.
5. **A patch**: `my_project.patch` in your lesson folder, made with `git diff base`.

## 5. An example, from start to finish

The lab walks you through idea 1 completely, so you see every step once. Then you do your own.
Here is the example's measurement, made on the simulated bench file (600 s, receiver standing still,
truth known; 598 GGA sentences with a valid checksum) — before and after the change:

| | Fixes accepted | Median error | p90 | Max |
|---|---|---|---|---|
| Before (quality only) | 568 of 598 (95 %) | 3.3 m | 6.7 m | 150.7 m |
| After (≥ 4 satellites) | 523 of 598 (87 %) | 3.1 m | 5.5 m | 10.7 m |

And its honest limits: synthetic data where few satellites *always* means a big error (real receivers
are not that simple); a real receiver with 3 satellites and a good geometry may still be useful; NAVERA
loses 45 seconds of GPS in this file — would vision cover them? Notice also what the median *hides*:
it barely moves (3.3 → 3.1 m), while the max drops from 151 m to 11 m. Always look at the worst case.

## 🐦 How birds do it

Navi the swallow has made it. She spent the winter in Africa south of the Sahara, crossed the desert and
the sea over Tunisia in spring, found her barn in Europe, raised her young and flew back south in autumn. Next spring she will try to come
back to the **same barn** — barn swallows are famous for returning to the same nest sites year after
year.

Her first journey was the hardest. Young birds start with an **inherited program**: a direction and
roughly how long to fly. Perdeck's starlings (lesson 23) showed what that is worth alone: moved to
Switzerland, the young ones kept their direction and ended up in the wrong country, while the adults
**corrected**, because experience had given them a map. Many studies find the same pattern: first-time
migrants make more mistakes, and birds become **better navigators with experience**, adding landmarks,
calibrating their compasses, learning what works.

No bird gets it right in one go, and neither does a navigation system. NAVERA was not born perfect
either: the arbiter's rules, the honest σ, the spoofing checks, each came from one measured
improvement after another — exactly the loop of this lesson. Change **one** thing, measure it against
a baseline, keep it only if it is really better, and write down its limits.

Like the birds that inspired it, NAVERA combines several senses and cross-checks them. Your project is
one more step on that migration. Bon voyage!

## Glossary

| Word | Meaning |
|---|---|
| **branch** | a separate line of commits for one piece of work |
| **commit** | one saved step, with a message saying what and why |
| **tag** | a fixed name on a commit (`base`: where your copy started) |
| **diff / patch** | the list of changed lines between two versions / that list saved in a file |
| **regression** | something that worked and is broken by a change; tests catch them |
| **unit test** | a small automatic test of one function, without hardware or ROS graph |
| **integration test** | a test that starts real nodes and talks to them (`navera_tools/tests/`) |
| **report** | the document that lets others trust your change: idea, change, test, numbers, limits |

## Check what you learned

<details><summary>1. Why must a project change only one thing?</summary>
So that the measurement before/after tells you what that one change did. With several changes, an improvement (or a regression) cannot be attributed.
</details>

<details><summary>2. What makes a good test for a bug fix?</summary>
One that fails on the old code and passes on the new one — it proves the test checks the problem and that the change fixes it, and it protects the fix forever.
</details>

<details><summary>3. What does `git diff base > my_project.patch` contain?</summary>
Every line you changed in your NAVERA copy since it was created (the commit tagged base), in a file anybody can apply with git apply.
</details>

<details><summary>4. Your change improves the median error in the simulator from 20 m to 15 m on one flight. What do you write in "Limits"?</summary>
That it is one simulated flight (few samples, simulated sensors and images), not a real flight; that the max / p90 and availability must be checked too; and what would be needed to confirm it (more flights, real data).
</details>

Now open the **🛠️ Lab** tab.

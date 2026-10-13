# Mission 05 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — Reviewer** (Steps 0–5, badge **Reviewer** = checks 1–7, the `reviewer` milestone)
and **Session 2 — Detective** (Steps 6–10, badge **Detective** when the mission is passed).

**The repository.** `solutions/05-git/make_repo.py` (teacher only: it describes the planted bugs) builds the
invented history and packs it as `datasets/05-git/navera-lite-history.tar.gz`; students unpack it in Step 0
(`tar -xzf /data/academy/05-git/navera-lite-history.tar.gz`). Rebuild with
`python3 solutions/05-git/make_repo.py --print-key`. Dates, authors and contents are fixed, so the **hashes
never change** (the archive bytes do, through the git index timestamps: harmless). check.py hard-codes only
`main` and `v0.1`; it finds the bad commit by running the probe, so it holds no answer.

| Name | Hash | What |
|---|---|---|
| `main` | 1f76dac | tip, 40 commits (2026-03-02 → 2026-09-14) |
| `v0.1` | 7b00fee | annotated tag, commit 10 (good: probe prints 5) |
| broken | 06752fb | commit 25 `wip: guard status line` — SyntaxError in guard.py (missing `:`) |
| **first bad** | **bd4a667** | commit 30 `feat(guard): say how long GPS has been refused` (Amara, 2026-06-23) |
| review branch | 428bc49 | `kenji/fewer-refusals`, one commit forked from commit 38 (4521680) |

**The regression** (bd4a667): `elapsed_s = t_s - self.prev_t_s`, where `prev_t_s` is the time of the previous
fix, accepted **or refused**. Elapsed is therefore always 1 s, the gate never widens beyond 150 m, and after a
real 500 m jump the true GPS is locked out for ever (lesson 1's table: 7 refusals instead of 5). It shows the
same symptom as the second half of NAVERA's EST-9 (true GPS locked out), by a different mechanism.
The repository's own tests pass at every commit except 06752fb.

**Kenji's commit** treats that symptom: hunk 4 trusts any fix after 10 s of refusals (the first half of
EST-9: a patient spoofer gets in), hunk 2 raises the margin to 500 m, hunk 5 deletes the test that the new
margin makes fail ("flaky"). Hunks 1 (README typo) and 3 (`EARTH_RADIUS_M` instead of the same literal) are
safe. The look-back question 1 ties the sessions together: the bisect finds the cause his patch hid.

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Small, well-described commits on a branch; commit, branch, HEAD | §1 (three files → two commits), §2 (message, which name moves) | Steps 0, 1, 5, 8 | 1, 6, 7 |
| 2. Read a unified diff; review a patch hunk by hunk with justified verdicts | §3 (max_speed 100 → 30) | Steps 2–5 (TODO 1, 2, review.md) | 2, 3, 4, 5, 6 |
| 3. Find a regression with `git bisect run`; why ≈ log₂ n tests | §4 (200 / 2 000 suspects, broken commit) | Steps 6–7 (TODO 3, 4) | 8, 9, 10, 11 |
| 4. Undo safely and recover lost work (restore, revert, reset, reflog) | §5 (revert vs reset, reflog) | Steps 8–10 (TODO 5, revert, rescue, patch) | 12, 13, 14, 15 |

## Answer key

- Step 0: 40 commits on `main`, tag `v0.1`, branch `kenji/fewer-refusals`.
- Step 2: `git show 184a1d6` has `@@ -5,3 +5,24 @@`: 3 old lines from line 5, 24 new lines (21 added).
- Step 3: `TWO_DOT_FILES = 6` (README, yaml, geo, guard, test_guard **and** `tests/test_geo.py`, main's newer
  test shown reversed; README counts 6 changed lines because main's new section shows as deleted),
  `THREE_DOT_FILES = 5`. `run_lab.py stat`: README 1/1, yaml 1/1, geo 1/1, guard 5/0, test_guard 0/7 —
  5 files, 5 hunks.
- Step 4: `KENJI_GATE_1S_M = 600` (100 × 1 + 500; was 150). `SPOOF_ACCEPTED_AT_S = 12`: refused at t = 1
  (`refused_since_s = 1`), still refused while t − 1 ≤ 10, accepted at t = 12 (11 is the strict-inequality
  trap). Verdicts: 1 accept, 2 reject, 3 accept, 4 reject, 5 reject. The details box after the task gives
  the comparison: lesson 1's gate alone (v0.1, margin 50 m) accepts the 50 km fake only at t = 500 s
  (100 t + 50 ≥ 50 000): it only delays a spoofer; Kenji's timer makes it 12 s.
- Step 5: `git apply --include=README.md --include=navera_lite/geo.py ../review_me.patch`; 13 tests pass;
  one or two commits (geo alone at least).
- Step 6: `PROBE_BRANCH = 7`, `PROBE_V01 = 5`; `git rev-list --count v0.1..main` = 30 suspects,
  ⌈log₂ 30⌉ = 5. `run_lab.py history` with a correct `first_bad`: 5 tests (06752fb → its child tested
  instead, 265f296 bad, 63bb5b0 good, 3757182 bad, bd4a667 bad). `toy`: worst cases 1, 2, 4, 5, 6, 7, 10 for
  n = 2, 3, 16, 30, 40, 100, 1000 (= ⌈log₂ n⌉).
- Step 7: git tests 06752fb (skip, 125), 4521680 bad, 64eb8e5 good, 3757182 bad, 7485e7e good, 63bb5b0 good,
  bd4a667 bad → `FIRST_BAD = bd4a667`, `TESTS_RUN = 7`. Two more than ⌈log₂ 30⌉: after a skip git moves
  far away from the skipped commit (here to commit 38), which costs tests — look-back question 3.
  A script **without** the 125 case makes bisect name 06752fb (it is the first commit tested).
- Step 8: with the new test, 13 pass and 1 fails on main's code (the gate answers False at fix 5).
  `git revert --no-edit bd4a667` applies cleanly; `git show --stat HEAD`: guard.py 14 lines, test_guard.py 8
  lines, 2 insertions, 20 deletions. It also removes `refused_for_s()` and its test (same commit), so 13 tests
  pass afterwards, not 14, and CHANGELOG still announces the feature: that is `EXPLAIN_REVERT_COST`.
  Fixing forward (only `elapsed_s = t_s - self.last_t_s`, Going further) gives 14 passed and probe 5; it also
  passes every check if a student does it instead of the revert.
- Step 9: `git reset --hard HEAD~2` drops the test and the revert; `git reflog -5` shows them at
  `HEAD@{1}` / `HEAD@{2}`; `git reset --hard HEAD@{1}` brings them back.
- Step 10: `git format-patch main --stdout` holds 4 commits (README, geo, test, revert) and applies to main.
- Lesson checks: §3 max_speed 100 → 30: 150 m → 80 m; §4 ⌈log₂ 200⌉ = 8, ⌈log₂ 2 000⌉ = 11; Check yourself
  4: ⌈log₂ 60⌉ = 6; 6: 450 m ≥ 420 m, accepted.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_DOTS | two dots = snapshot vs snapshot, so main's 2 newer commits appear reversed; three dots = from the merge base, only Kenji's work: the reviewer's view | one side explained | restates the numbers |
| review.md Why (each hunk) | what changes + one of: correct / safe / measured, **with numbers** for 2 (150 → 600 m) and 4 (any fix after 10 s, fake accepted at t = 12); 5 names the deleted test and why it failed | verdict right, reason vague ("dangerous") | reason contradicts the verdict |
| Advice | split into concerns; measure false refusals before touching the margin; find the cause (bisect, a failing test) instead of a timer; never delete a failing test | two of these | "be careful" |
| EXPLAIN_BISECT | each test halves the 30 suspects → ≈ log₂ 30 = 5; the wip commit cannot be imported, so it is neither good nor bad: 125 skips it, 1 would make bisect name it | halving only | "bisect is fast" |
| EXPLAIN_CAUSE | elapsed measured from the previous (refused) fix → always 1 s → gate stuck at 150 m → true GPS locked out after a jump; Kenji's timer hides that symptom and lets a patient spoofer in. Bonus for the debrief: the restored gate is not EST-9-safe either (500 s instead of 12 s) — only a cross-check is (mission 30) | cause right, no link to Kenji | "a bug in guard.py" |
| EXPLAIN_REVERT_COST | the revert also removed `refused_for_s()` and its test (CHANGELOG still announces it) because the commit mixed a feature and a behaviour change; two commits, or a one-line fix forward, would have kept the feature | names what was lost, no remedy | "nothing" |
| EXPLAIN_RESCUE | reset only moved the branch name; the commits stayed in .git and the reflog listed them; uncommitted edits are the only thing git cannot give back | reflog named, no why | "I used git reflog" |

Predictions are never marked. In class, ask who predicted 5 for `PREDICT_PROBE` (most do) and who expected
exactly 5 bisect tests.

## Difficulties (seen when testing wrong solutions; to confirm with simulated students and the pilot)

- TODO 1: returning strings; treating a written count of 0 as "left out" (`int(n or 0) or 1`) — the check names it.
- TODO 2: skipping every `---`/`+++` line (the unseen patch has a removed `--- separator` line inside a hunk);
  counting the header lines (+1/+1 per file); taking the path from `+++` (a deleted file has `+++ /dev/null`).
- TODO 3: linear search (too many tests), returning the index, calling `is_bad(mid)`, `lo = mid` (endless loop),
  `hi = len(commits)` (tests the known-bad last commit). Each has its own ✘ message.
- TODO 4: no 125 case (the most common: then bisect names 06752fb, and check 11 says why); `cd` into the
  repository by absolute path (tests the student's checkout, not bisect's); comparing with `-eq` on an empty
  string prints an error but still exits non-zero (works by accident: show `[ "$n" = "5" ]`).
- TODO 5: a test that only checks the first refusal passes on main's code: the check says so.
- Students who commit README + geo in one commit (`fix(readme,geo): …`) now get check 7 ✘ (two scopes) and
  check 6 ✘ (two concerns): `git reset HEAD~1` (edits kept, unstaged), then two commits (Step 5 hint 4).
- Kenji's hunks applied but not committed (only README + geo committed): check 6 reads the working folder too,
  so no Reviewer badge with a 500 m margin lying in the folder; Step 8 hint 4 covers the revert refusal it causes.
- `lo = mid` used to freeze `run_lab.py test`; the runner now stops after 2n + 5 calls with a message, and Step 6
  hint 3 says Ctrl+C. The runner's `test` also contains the `--- separator` trap, so the skip-every-`---` mistake
  shows at Step 3, not only at Check time.
- Counting the `# first bad commit` line in `TESTS_RUN` (8 instead of 7): the Step 7 task now says not to.
- A `reset --hard HEAD~2` without the rescue, and a `my_changes.patch` made before it: checks 14 and 15 say so.
  Check 14 needs the commit the branch was on just before that reset (the reflog line just below it) to be back
  in the branch (or cherry-picked from the reflog): redoing the work by hand, or rescuing to `HEAD@{2}`, fails it.
  A Step 5 `git reset HEAD~1` (to split a commit) is ignored: only a reset after the Step 8 commits counts.
- A regression test with a wrong expected value: if the probe prints 5 on the branch, check 12 says the
  expected list is wrong (Step 8 hint 5).
- `git revert` without `--no-edit` opens an editor (nano or vi in the terminal): tell students how to save and quit,
  or insist on `--no-edit`.
- Forgetting `git bisect reset`, or saving `bisect.log` after the reset (then it is empty).
- Committing on `main` in Step 5: check 6 says main has moved; Step 1's hint gives the repair.

## Suggested class plan (reading at home about 1 h 20 + 2 sessions of 2 h; about 5 h 15 in all)

0. **Before session 1:** read the lesson (about 80 min) with the ✏️ checks.
1. **Session 1 — hook (10 min):** EST-9 read aloud from the brief; "a commit hash in a backlog: what does it prove?"
2. **Board (15 min):** decode one hunk header together; the four review questions on the lesson's timeout patch.
3. **Lab (90 min):** Steps 0–5. Stop at the Reviewer box. Last 10 min: two students read their hunk 4 verdict.
4. **Session 2 — retrieval (10 min):** Check-yourself 2–4 on paper; one bisect by hand on the board (16 commits).
5. **Lab (90 min):** Steps 6–10. Students who have not finished Step 10 finish it at home (the lab
   announces about 1 h 45 per session); the Detective badge needs no class time.
6. **Debrief (20 min):** Kenji's patch vs the cause found by bisect (symptom vs cause); revert vs fix forward;
   who needed 7 bisect tests and why (skip).

**Differentiation.** Fast: "Going further" (blame and `log -S`, cherry-pick of a mixed commit, a merge conflict,
bisect by hand). Struggling: pairs for Steps 6–7; give TODO 3's hand trace on the board; let them use
`run_lab.py history` before `git bisect run` to see the halving.

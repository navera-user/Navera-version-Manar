# Lab 5 — Reviewer, then detective

**Goal:** in the history of NAVERA Lite, review a colleague's change hunk by hunk and accept only
what is safe; then find the commit that broke the jump gate with `git bisect run`, fix it with a test,
and rescue work you "lost" on purpose.
**Time:** 3 h to 4 h (a student at ease with the terminal: about 2 h 30; up to 5 h if it is new).
**Fast track:** if you already use git daily, skip the 🧰 boxes and the "Stuck?" boxes, and do
"Going further" after Step 9.

Your files (📝 Code tab): [detective.py](file:./detective.py) (**your code**: `TODO 1–3`),
[bisect_test.sh](file:./bisect_test.sh) (`TODO 4`), [test_regression.py](file:./test_regression.py)
(`TODO 5`), [review.md](file:./review.md) (your review), [answers.py](file:./answers.py) (numbers,
predictions, explanations). Given: [run_lab.py](file:./run_lab.py) (runs your functions) and
[probe_gate.py](file:./probe_gate.py) (tests the jump gate of whatever commit is checked out).

| Lesson | Lab | You write |
|---|---|---|
| §1–§2 Commits, branches | Steps 0–1 | your identity, a branch |
| §3 Diffs and review | Steps 2–5 | `hunk_header`, `diff_stat`, `review.md`, the accepted commits |
| §4 Bisect | Steps 6–7 | `first_bad`, `bisect_test.sh` |
| §5 Undo and rescue | Steps 8–10 | `test_regression.py`, a revert, a rescue, a patch |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` is written **before** you run the step. It is never marked
> right or wrong. **Where am I?** From Step 0 on, almost every command runs **inside**
> `navera-lite-history`: the prompt ends with `05-git/navera-lite-history$`. If a command says
> `fatal: not a git repository`, run `cd ~/lessons/05-git/navera-lite-history` again. If git opens a
> long text with `:` or `(END)` at the bottom, press **`q`**.

## Session 1 — Reviewer (about 1 h 45)

## Step 0 — Build the history

Open the **⌨️ Terminal** tab. This unpacks the repository into your lesson folder (the same for every
student, to the last hash):

```bash
tar -xzf /data/academy/05-git/navera-lite-history.tar.gz
```

(To start again from zero one day: `cd ~/lessons/05-git`, `rm -rf navera-lite-history`, then the same
`tar` command. Your commits in it would be lost.)

```bash
cd navera-lite-history
```

```bash
git log --oneline --graph --all --decorate
```

Forty commits on `main`, newest at the top. Find the tag `v0.1` (the first release) and the branch
`kenji/fewer-refusals`, which leaves `main` near the top. Read a few messages: who wrote what, in which
style? (Press `q` if the list does not fit.)

## Step 1 — Who are you? Then a branch of your own

**Type** these two commands yourself (no ▶ Run button), with **your own** name and an e-mail address
(it may be invented). The values below are examples only — do not copy them:

```text
git config --global user.name "Ana Souza"
```

```text
git config --global user.email "ana.souza@example.com"
```

```bash
git config --global --list
```

Now your branch. Everything you commit today goes on it; `main` must not move.

```bash
git switch -c my-first-change
```

```bash
git status
```

> [!TASK]
> `user.name` and `user.email` are yours, and you are `On branch my-first-change`.

<details><summary>Stuck? Hints</summary>

1. *Please tell me who you are* when you commit: the two `git config` lines are missing.
2. Committed on `main` by mistake? Note the hash (`git log -1 --oneline`). No branch `my-first-change`
   yet: `git switch -c my-first-change`. Otherwise: `git switch my-first-change` and
   `git cherry-pick <hash>`. Then put `main` back where it was: `git branch -f main 1f76dac`.
3. A long `usage:` list after `git config`, and no `user.name` in `--list`? Your name has spaces: put it
   in quotes, `"Ana Souza"`.
</details>

## Step 2 — Read a hunk header

Look at one real change, the commit that created the `JumpGate` class:

```bash
git show 184a1d6
```

Find its hunk header `@@ … @@` and decode it with lesson §3: where does the hunk start in the old and
new file, and how many lines on each side?

<details><summary>🧰 Python: taking a line apart</summary>

```python
s = "-12,7"
print(s[1:])                    # 12,7     (drop the first character)
print(s[1:].partition(","))     # ('12', ',', '7')     — before, separator, after ('' if absent)
print("a b  c".split())         # ['a', 'b', 'c']       (split on spaces)
print(int("12") + 1)            # 13       (text → whole number)
```
</details>

**TODO 1** `hunk_header` in [detective.py](file:./detective.py): the four numbers of a header. Read
its docstring (two examples), then:

```bash
python3 ../run_lab.py test
```

The first two lines must be ✔ (the others are TODO 2 and 3).

<details><summary>Stuck? Hints</summary>

1. The two parts you need are the 2nd and 3rd words of the line: `"-78,7"` and `"+78,8"`.
2. Drop the sign, then separate start and count at the comma. No comma? The count is 1.
3. `('78', '7', '78', '8')` instead of `(78, 7, 78, 8)`: you return text; use `int(...)`.
4. A written `0` (`@@ -0,0 +1,3 @@`) is the count 0, not "left out": test whether the count text is
   empty, not whether the number is 0.
</details>

## Step 3 — Two dots, three dots, and the patch to review

Kenji's branch left `main` before `main`'s last two commits. Compare the two ways of asking "what is
different?" (lesson §2):

```bash
git diff --stat main..kenji/fewer-refusals
```

```bash
git diff --stat main...kenji/fewer-refusals
```

> [!TASK]
> Write `TWO_DOT_FILES` and `THREE_DOT_FILES` (how many files each one lists) and `EXPLAIN_DOTS`:
> why are they different, and which one does a reviewer want? (`git log --oneline main..kenji/fewer-refusals`
> and `git log --oneline kenji/fewer-refusals..main` show who has which commits.)

Save the reviewer's view in a file of the lesson folder (`>` from lesson 2):

```bash
git diff main...kenji/fewer-refusals > ../review_me.patch
```

**TODO 2** `diff_stat`: how many lines each file of a patch adds and removes. Run `test` again, then
compare your count with git's own count on the real patch:

```bash
python3 ../run_lab.py test
```

```bash
python3 ../run_lab.py stat ../review_me.patch
```

Every line must be ✔.

<details><summary>Stuck? Hints</summary>

1. Walk through `patch_text.splitlines()`. Remember the current file in a variable: it changes at each
   line that starts with `diff --git `.
2. Count a `+` or `-` line only when you are **inside a hunk**: after an `@@` line, until the next
   `diff --git`. Otherwise `--- a/README.md` counts as a removed line.
3. Every file one too many on both sides? You count the `---` and `+++` header lines.
4. Do **not** skip every line that starts with `---`: inside a hunk, a removed line whose text starts
   with `--` looks exactly like that. Being inside a hunk is the only safe rule.
5. A tuple cannot be changed in place: `stat[path] = (added + 1, removed)` replaces it.
</details>

## Step 4 — Review Kenji's change, hunk by hunk

First what Kenji says he did, then what he did:

```bash
git log -1 kenji/fewer-refusals
```

```bash
git apply --stat ../review_me.patch
```

```bash
git apply --check ../review_me.patch && echo "applies cleanly"
```

It applies without conflict, which says nothing about whether it is **safe**. Now read every line,
open [review_me.patch](file:./review_me.patch) in the 📝 Code tab, or:

```bash
cat ../review_me.patch
```

For each hunk, ask the four questions of lesson §3. To see a hunk in its context, open the file in
the editor ([navera_lite/guard.py](file:./navera-lite-history/navera_lite/guard.py) is the gate).
To be sure what Kenji's code does, you may also run it: `git switch --detach kenji/fewer-refusals`,
try it in `python3`, then `git switch my-first-change` to come back.

> [!TASK]
> In `answers.py`: `KENJI_GATE_1S_M` (with Kenji's settings, the largest jump accepted 1 s after the
> last trusted fix) and `SPOOF_ACCEPTED_AT_S` (with Kenji's code: a trusted fix at t = 0 s, then a
> fake fix 50 km away every second from t = 1 s: at which t is it accepted? Trace `check()` second by
> second on paper.)
>
> In [review.md](file:./review.md): for each of the 5 hunks, `Verdict: accept` or `Verdict: reject`
> and a `Why:` with numbers where you can; then your advice to Kenji.

<details><summary>Read this after you wrote SPOOF_ACCEPTED_AT_S</summary>

Lesson 1's gate alone (as in `v0.1`: no timer, margin 50 m) accepts the same fake fix too, but only at
t = 500 s (100 × t + 50 ≥ 50 000): lesson 1 said that the gate alone only **delays** a jump. A patient
spoofer gets in either way; Kenji's timer turns "after 8 minutes" into "after a few seconds, from
anywhere". NAVERA's real answer to EST-9 is a cross-check with an independent source (mission 30).
</details>

<details><summary>Stuck? Hints</summary>

1. Hunk by hunk, not file by file of opinion: a hunk that is harmless on its own is accepted even if
   its neighbour is not.
2. For the yaml hunk: compute the gate with lesson 1's formula, before and after.
3. For the guard hunk: what decides that a fix is accepted, after the change? Does it still depend on
   where the fix is?
4. For the test hunk: is the test really "flaky" (sometimes passing, sometimes failing)? Read it:
   which value does it take from `navera_lite.yaml`, and what would it give with the margin of hunk 2?
</details>

## Step 5 — Apply what you accepted, test, commit

Apply **only** the hunks you accepted, with one `--include=<path>` per accepted file (lesson §3):

```text
git apply --include=<path> --include=<path> ../review_me.patch
```

Then look at what changed, and run the repository's tests:

```bash
git status
```

```bash
git diff
```

```bash
python3 -m pytest -q tests
```

Commit, **one concern per commit**, with your own messages (lesson §2): `git add <file>` then
`git commit -m "type(scope): summary"`, once per concern. A spelling fix and a code refactor are two
concerns, so two commits, each with one scope: `docs(readme): …`, `refactor(geo): …`. A scope with a
comma, like `fix(readme,geo)`, is the sign of a commit that should be split.

```bash
git log --oneline main..my-first-change
```

> [!TASK]
> `my-first-change` has your commit(s) with the accepted hunks only, each commit one concern with a
> clear `type(scope): summary` message, nothing left uncommitted; `main` has not moved.

<details><summary>Stuck? Hints</summary>

1. Applied a file you did not mean to? Not committed yet: `git restore <file>`. Already committed:
   `git restore --source=main <file>`, then commit that correction.
2. `nothing added to commit`: you forgot `git add`.
3. A wrong message on your last commit (not shared yet): `git commit --amend -m "…"`.
4. Both files in one commit? `git reset HEAD~1` undoes the commit and keeps your edits, unstaged. Then add
   and commit **one** file at a time. (After `git reset --soft HEAD~1` both files stay **staged**, and the
   next `git commit` takes both again: `git restore --staged navera_lite/geo.py` first.)
</details>

> [!TIP] 🏅 End of session 1 — Reviewer
> Press **✔ Check my work**. When the session-1 checks pass (checks 1–7; the other ✘ lines are
> session 2), you earn the **Reviewer** badge. If the class session ends here, stop here.

## Session 2 — Detective (about 1 h 45)

## Step 6 — The bug report, and binary search by hand

> **Bug report (Priya, test pilot):** "Replay test, lesson 1's table: after a 500 m GPS jump, the GPS
> is never accepted again. With v0.1 it was accepted after 5 s."

[probe_gate.py](file:./probe_gate.py) replays lesson 1's table (the trusted fix at t = 0 s, then the
table's 7 rows: 8 fixes) through the `JumpGate` of the commit checked out now, and prints how many
fixes it refuses (5 is right).

> [!TASK]
> **Predict** (`PREDICT_PROBE`): what will it print on your branch? (Spotted a suspicious line of
> `guard.py` in Step 4 already? Write which line, and predict the number from it: Step 7 will tell you
> whether you blamed the right commit.)

```bash
python3 ../probe_gate.py
```

Now at the first release, in "detached HEAD" (lesson §2), and back:

```bash
git switch --detach v0.1
```

```bash
python3 ../probe_gate.py
```

```bash
git switch my-first-change
```

> [!TASK]
> Write `PROBE_BRANCH` and `PROBE_V01`. Then **predict** (`PREDICT_TESTS`): `git rev-list --count
> v0.1..main` says how many suspects there are; how many test runs will bisect need, and why?

```bash
git rev-list --count v0.1..main
```

<details><summary>🧰 Python: integer division and a while loop</summary>

```python
print(7 // 2, 15 // 2)         # 3 7     (// divides and drops the decimals)
lo, hi = 0, 10
while lo < hi:                 # repeats while the condition is true
    lo = lo + 3
print(lo)                      # 12
```
</details>

**TODO 3** `first_bad`: binary search, as in lesson §4. This is the least guided TODO: first redo the
lesson's 16-commit table by hand with two positions `lo` and `hi` (the answer is always between them),
then write the loop.

```bash
python3 ../run_lab.py test
```

```bash
python3 ../run_lab.py toy
```

`toy` shows which commits your function tested, and its worst case for 2 to 1 000 commits next to
⌈log₂ n⌉. Then run it on the real history (a private copy: your repository is not touched):

```bash
python3 ../run_lab.py history
```

<details><summary>Stuck? Hints</summary>

1. Start with `lo, hi = 0, len(commits) - 1`: the first bad commit is somewhere in `commits[lo..hi]`,
   and `commits[hi]` is known to be bad.
2. Test the middle `commits[(lo + hi) // 2]`. Bad → the answer is at the middle or before it.
   Good → the answer is after it.
3. Never ending (nothing printed, the terminal does not come back)? Press **Ctrl+C** to stop it. When
   the middle is good, the new `lo` must be **middle + 1**, not middle.
4. The right commit but too many tests: you test commits one by one, or you test the last one (it is
   known to be bad).
5. `is_bad() was called with 7`: give it the commit `commits[mid]`, not the position `mid`.
</details>

## Step 7 — git bisect run

**TODO 4** [bisect_test.sh](file:./bisect_test.sh): answer 0 (good), 1 (bad) or 125 (cannot be
tested) for the commit checked out now, using the probe (lesson §4, and the comments in the file).
Try it by hand on your branch (bad) and at `v0.1` (good) before you give it to git:

```bash
bash ../bisect_test.sh; echo "exit code: $?"
```

Now let git drive. Your working folder must be clean (`git status`):

```bash
git bisect start main v0.1
```

```bash
git bisect run ../bisect_test.sh
```

Read the end: `… is the first bad commit`. Save the record, **then** leave bisect:

```bash
git bisect log > ../bisect.log
```

```bash
git bisect reset
```

> [!TASK]
> `FIRST_BAD` (its hash, at least 7 characters) and `TESTS_RUN` (how many commits your script ran on:
> count the `# good`, `# bad` and `# skip` lines of [bisect.log](file:./bisect.log), without the two
> of the start, `main` and `v0.1`, and without the last line, `# first bad commit`: it is the result,
> not a test). Then read the culprit: `git show <FIRST_BAD>`.
> `EXPLAIN_BISECT`: why so few tests for 30 suspects, and why must the broken commit get 125?
> `EXPLAIN_CAUSE`: which line breaks the gate, why GPS then stays refused, and what that says about
> Kenji's patch.

<details><summary>Stuck? Hints</summary>

1. `bisect run failed: exit code 255`: your script is still the starter.
2. Bisect names `wip: guard status line`: that commit does not even import (look at the probe's
   message on stderr). For it, your script must exit 125, not 1. `git bisect reset`, fix, run again.
3. Every commit "bad", even v0.1? Compare the probe's output with `5` exactly (`[ "$n" = "5" ]`), and
   use the probe's full path `~/lessons/05-git/probe_gate.py` or `../probe_gate.py`.
4. `You need to start by "git bisect start"` or a messy state: `git bisect reset`, then start again.
5. In `git show`, compare the line that computes `elapsed_s` before and after: since which fix is the
   time counted now?
</details>

## Step 8 — Fix it the safe way: a test first, then a revert

A fix comes with a test that would have caught the bug. Copy the template into the repository's tests:

```bash
cp ../test_regression.py tests/
```

**TODO 5**: write the test in [tests/test_regression.py](file:./navera-lite-history/tests/test_regression.py)
(its docstring says what to assert). It must **fail** now, on main's code:

```bash
python3 -m pytest -q tests/test_regression.py
```

Commit the test alone (`git add tests/test_regression.py`, then `git commit -m "test(guard): …"`).
Now undo the bad commit with a **new** commit (lesson §5); `--no-edit` keeps git's message
`Revert "…"`:

```text
git revert --no-edit <FIRST_BAD>
```

```bash
python3 -m pytest -q tests
```

```bash
python3 ../probe_gate.py
```

Now look at **everything** the revert removed:

```bash
git show --stat HEAD
```

A revert undoes a **whole** commit. `refused_for_s()` and its test, the operator-display feature Amara
wrote that commit for, are gone too (count the tests before and after), and `CHANGELOG.md` still
announces it. The other way is to **fix forward**: one new commit that changes only the faulty line
(see Going further).

> [!TASK]
> On `my-first-change`: `tests/test_regression.py` committed (it fails on main's code, passes on your
> branch), the bad commit reverted, every test passing, and the probe printing 5.
> `EXPLAIN_REVERT_COST`: what else did the revert remove, and how would one-concern commits (or a
> fix forward) have avoided it?

<details><summary>Stuck? Hints</summary>

1. Your test passes on main's code too? Assert the answer of `check()` for **every** fix, including
   the 500 m fixes that must be accepted once the gate has widened.
2. A list in one line: `[gate.check(float(t), xy) for t, xy in enumerate(fixes)]`.
3. `git revert` stops with a conflict: you changed `navera_lite/guard.py` yourself. `git revert --abort`,
   `git restore --source=main navera_lite/guard.py`, commit that, and revert again.
4. `error: Your local changes … would be overwritten by revert`: a file is still changed since Step 5
   (often a rejected hunk you applied). `git status`, then `git restore <file>`, and revert again.
5. After the revert the probe prints 5 but your test still fails? Then the gate is right and **your
   expected list** is wrong. pytest says `At index i`: recompute fix i with lesson 1's table (t = 4 s:
   100 × 4 + 50 = 450 m < 500 m → refused, `False`). Commit the corrected test as a new `test(guard): …`
   commit.
</details>

## Step 9 — Disaster and rescue

First a small disaster: delete the gate.

```bash
rm navera_lite/guard.py
```

```bash
git status
```

It is committed, so git has it:

```bash
git restore navera_lite/guard.py
```

Now a big one. A careless "clean-up" moves your branch back two commits, throwing away your test and
your revert:

```bash
git reset --hard HEAD~2
```

```bash
git log --oneline -3
```

They are gone from the branch. Find them in git's journal (lesson §5):

```bash
git reflog -5
```

Bring your branch back to where it was before the reset: `git reset --hard HEAD@{1}` (or the hash the
reflog shows on that line). Then check:

```bash
git log --oneline main..my-first-change
```

```bash
git status
```

> [!TASK]
> Your branch has all its commits again, `navera_lite/guard.py` is there, `git status` shows nothing
> to commit. `EXPLAIN_RESCUE`: where were the "lost" commits, how did you find them, and what could
> git **not** have given back?

## Step 10 — Send your work for review, check, look back

Your branch is now a change for someone else to review. Export it as a patch, in mail format, with
your name and messages:

```bash
git format-patch main --stdout > ../my_changes.patch
```

```bash
git apply --stat ../my_changes.patch
```

Does it apply to `main`? Test it on `main` itself, in detached HEAD, then come back (`--check` on your
own branch would fail: your changes are already there):

```bash
git switch --detach main && git apply --check ../my_changes.patch && echo "applies to main"; git switch my-first-change
```

> [!TASK]
> `~/lessons/05-git/my_changes.patch` holds all your commits and applies cleanly to `main`.

Press **✔ Check my work**: it reads your repository (your private copy is never changed), runs your
functions and your script on cases they have never seen, and runs your test on main's code and on
your branch. When every check passes, you earn the **Detective** badge.

Then look back, without the lesson:

1. Kenji saw a real problem (GPS refused for ever). Why was his fix still wrong, and what did the
   bisect give you that his patch did not?
2. Which of your predictions was the most wrong, and why?
3. Why did your bisect need more tests than ⌈log₂ 30⌉? Look at bisect.log and lesson §4 ("a skip
   costs tests").

## Going further (optional)

- **Fix forward instead of reverting.** On a throw-away branch from your test commit
  (`git switch -c fix-forward <hash of your test commit>`), change only `elapsed_s = t_s - self.prev_t_s`
  back to `elapsed_s = t_s - self.last_t_s`. Run all the tests: your regression test passes **and**
  `test_refused_for_s` stays. Commit it as `fix(guard): …` with a body that names the bad commit. Which of
  the two fixes would you send for review, and why? (Back with `git switch my-first-change`.)

- **Who wrote this line?** `git blame navera_lite/guard.py` and `git log -S prev_t_s --oneline`
  (the commits that added or removed that text): two faster detectives when you know what to look for.
- **Pick one commit.** On a throw-away branch from `main`, try to take only Kenji's geo change with
  `git cherry-pick kenji/fewer-refusals`. What comes with it, and why would five small commits have
  been better?
- **A conflict on purpose.** `git switch -c try-merge main`, change the `gps_jump_margin_m` comment,
  commit, then `git merge kenji/fewer-refusals`. Read the `<<<<<<<` markers, keep the 50 m margin,
  `git add`, `git commit`. Back with `git switch my-first-change`; delete with `git branch -D try-merge`.
- **Bisect by hand.** `git bisect start main v0.1`, then answer `git bisect good` / `bad` / `skip`
  yourself after each `python3 ../probe_gate.py`. Does git test the same commits as `run`?

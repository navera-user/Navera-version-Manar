# Lab 5 — Commits, history, patches and a code review in NAVERA

**Goal:** work in your NAVERA copy like an engineer of the team: look at git's objects, set your
identity, create a branch, make clean commits (including a real code change), read and compare the
history, tag your work, export it as a patch, **review a colleague's patch** and apply only its safe
part, rescue a deleted file, and write your review.
**Time:** about 2 h 30.

Your files in `~/lessons/05-git/`: [answers.py](file:./answers.py),
[review.md](file:./review.md) (your review, to write) and
[review_me.patch](file:./review_me.patch) (the patch to review). All git commands run **inside your
NAVERA copy**, so first:

```bash
cd ~/navera
```

> [!NOTE]
> Every ▶ Run block below assumes you are in `~/navera`. If a command says
> `fatal: not a git repository`, run `cd ~/navera` again.

## Step 1 — Look at your repository

```bash
git status
```

You read `On branch work`, `Your branch is up to date with 'base/work'` and
`nothing to commit, working tree clean`. `base/work` is the **remote-tracking branch**: your clone's
record of the branch `work` of the remote called `base` (the academy base). "Up to date" only means
both point at the same commit; nothing is sent anywhere.

```bash
git log --oneline --graph --all --decorate
```

One line: `<hash> (HEAD -> work, tag: base, base/work) NAVERA base — fa775cd fix(bench): …`.
The **first word** is the hash of this commit in **your** repository. The second hash, `fa775cd`,
is text inside the message: the real NAVERA commit the academy copied. Keep both in mind for
`answers.py`.

```bash
git branch -vv
```

```bash
git tag
```

```bash
git remote -v
```

The remote `base` is a folder on the academy server (a path starting with `/home/shadow-team/…`).
It is outside your sandbox: you cannot fetch from it or push to it, and you do not need to.

## Step 2 — Look inside the objects

A commit is a small text object. Print yours:

```bash
git cat-file -p HEAD
```

A `tree` line (the hash of the project's root folder), the author, the committer, the message — and
no `parent`: this is the root commit. Now the tree itself, which lists blobs and sub-trees:

```bash
git cat-file -p 'HEAD^{tree}' | head -n 8
```

Check that a hash really is the SHA-1 of `blob <size>\0<content>`. Git's answer:

```bash
echo 'hello' | git hash-object --stdin
```

and Python's (`hashlib` is lesson 3's "module" idea — a standard one):

```bash
python3 -c "import hashlib; print(hashlib.sha1(b'blob 6\x00hello\n').hexdigest())"
```

The two 40-character hashes are identical: `ce01362…`.

## Step 3 — Tell git who you are

**Type** these two commands yourself (no ▶ Run button), with **your own** name and an e-mail
address (it may be invented). The names below are only examples — do not copy them:

```text
git config --global user.name "Salim Al Harthy"
```

```text
git config --global user.email "salim.alharthy@example.com"
```

```bash
git config --global --list
```

> [!TASK]
> `user.name` and `user.email` are set to **your** name and an e-mail address.

## Step 4 — Create your branch

```bash
git switch -c my-first-change
```

(The older equivalent, used in NAVERA's `CLAUDE.md` and in lesson 30, is
`git checkout -b my-first-change`.)

```bash
git branch -vv
```

Two branches; the `*` marks `my-first-change`, which starts at the same commit as `work`.

## Step 5 — First commit: a line in the README

Open [ACADEMY_README.md](file:navera/ACADEMY_README.md) in the editor and add one line **at the
end**, with your name, for example `- Aisha was here: my first commit in NAVERA!`. Save.

```bash
git status
```

```bash
git diff
```

Your line with a `+`. (If the screen ends with `(END)` or `:`, press `q`.) Stage it and look at
what the commit will contain:

```bash
git add ACADEMY_README.md
```

```bash
git diff --staged
```

```bash
git commit -m "docs(academy): add my name to the academy README"
```

```bash
git log --oneline --decorate
```

Your commit is on top. Its hash is the **first word of the line with your message** — not a hash
from the `NAVERA base — …` line. Write it now as `FIRST_COMMIT` in [answers.py](file:./answers.py)
(at least 7 characters).

> [!TIP]
> *Please tell me who you are* → step 3 is missing. *nothing added to commit* → you forgot
> `git add`.

## Step 6 — Second commit: real code, and why staging exists

Open [gps_node.py](file:navera/gps_pkg/gps_pkg/nodes/gps_node.py) and find (`Ctrl+F`) the line

```python
        self.get_logger().info("Read thread started")
```

Change **only the text between the quotes**, for example to
`"Read thread started, listening to the GPS receiver"`. Save. Now simulate a debugging leftover in
another file:

```bash
echo "# temporary debug note" >> navera_common/navera_common/geo.py
```

```bash
git status
```

Two modified files. Only the GPS change is ready; the debug note must never be committed. Check
that the Python file is still valid (no output = valid), stage **only** it, and look:

```bash
python3 -m py_compile gps_pkg/gps_pkg/nodes/gps_node.py
```

```bash
git add gps_pkg/gps_pkg/nodes/gps_node.py
```

```bash
git status
```

`gps_node.py` is under *Changes to be committed*; `geo.py` stays under *Changes not staged*.

```bash
git commit -m "fix(gps): clearer start-up log message"
```

Then throw the debug note away:

```bash
git restore navera_common/navera_common/geo.py
```

```bash
git status
```

> [!TASK]
> `my-first-change` has your two commits on top of `base`: a new line in `ACADEMY_README.md` and a
> changed log message in `gps_node.py` (still valid Python), each with a `type(scope): summary`
> message under 72 characters. The branch `work` does not move.

## Step 7 — Read and compare the history

```bash
git log --oneline --graph --all --decorate
```

`work`, `base/work` and `tag: base` still point at the base commit; `HEAD -> my-first-change` at
your last commit. The commits of your branch only, then the files they changed:

```bash
git log --oneline base..my-first-change
```

```bash
git diff --stat base...my-first-change
```

A file as it was in `base`, without changing anything:

```bash
git show base:ACADEMY_README.md | tail -n 3
```

Now switch branches and watch the **files** change:

```bash
git switch work
```

```bash
tail -n 2 ACADEMY_README.md
```

Your line has disappeared: it lives on the other branch. (Do not edit files while on `work`.)

```bash
git switch my-first-change
```

```bash
tail -n 2 ACADEMY_README.md
```

## Step 8 — Export your work as a patch

Write your commits, in mail format, into a file of the lesson folder (`>` from lesson 2):

```bash
git format-patch base --stdout > ~/lessons/05-git/my_changes.patch
```

```bash
head -n 12 ~/lessons/05-git/my_changes.patch
```

The header carries your name, the date and the message; then come the diffs. A colleague with a
copy of `base` could apply it with `git am`. Check that it is exactly your work — applying it
**in reverse** must fit your current files:

```bash
git apply --check -R ~/lessons/05-git/my_changes.patch && echo "reverse applies: the patch matches"
```

> [!TASK]
> `~/lessons/05-git/my_changes.patch` contains your README and `gps_node.py` changes and applies
> cleanly to `base`.

## Step 9 — Review a colleague's patch

A colleague, Khalid, sends you [review_me.patch](file:./review_me.patch) and asks you to apply it.
A reviewer never applies blindly. First, what does it touch?

```bash
git apply --stat ~/lessons/05-git/review_me.patch
```

Does it apply to your branch without conflict?

```bash
git apply --check ~/lessons/05-git/review_me.patch && echo "applies cleanly"
```

Now **read** it, line by line:

```bash
cat ~/lessons/05-git/review_me.patch
```

Two unrelated changes in one patch. Look at the second one in its context — the comment above
explains what the parameter protects:

```bash
grep -n -B 5 "gps_jump_margin_m" navera_estimator/navera_estimator/config/estimator_params.yaml
```

> [!QUESTION]
> The arbiter refuses a GPS fix farther than `max_speed_mps × Δt + gps_jump_margin_m` from the last
> trusted one. With `max_speed_mps = 100` and fixes 1 s apart, what is the largest accepted jump
> before and after the patch? What could a spoofer do with the new value? Did the author give any
> measurement? Which rules of `CLAUDE.md` (course, "In NAVERA") does the patch break?

Decision: the `geo.py` change (a literal replaced by the module's constant, same value) is safe;
the margin change is not. Apply the patch **except** the parameter file:

```bash
git apply --exclude=navera_estimator/navera_estimator/config/estimator_params.yaml ~/lessons/05-git/review_me.patch
```

```bash
git diff
```

Only `geo.py` changed. Verify it: it compiles, and the Muscat → Sohar distance is unchanged
(lesson 3 found 189 875 m with the same formula):

```bash
python3 -m py_compile navera_common/navera_common/geo.py
```

```bash
python3 -c "from navera_common.geo import haversine_m; print(round(haversine_m(23.588, 58.383, 24.347, 56.709)))"
```

Commit it **alone** (one concern per commit), with an honest message:

```bash
git add navera_common/navera_common/geo.py
```

```bash
git commit -m "refactor(geo): use EARTH_RADIUS_M in haversine_m"
```

```bash
git show --stat HEAD
```

Make sure the dangerous value is not in your files:

```bash
git diff base -- navera_estimator/navera_estimator/config/estimator_params.yaml
```

No output: the file is exactly as in `base`.

> [!TASK]
> Your branch has a third commit that changes **only** `geo.py` (haversine_m uses `EARTH_RADIUS_M`),
> and `estimator_params.yaml` is unchanged (`gps_jump_margin_m: 50.0`), committed and on disk.

## Step 10 — Tag your work

An **annotated** tag (`-a`) on your last commit:

```bash
git tag -a lab5 -m "Lab 5: two changes and a reviewed patch"
```

```bash
git cat-file -t lab5
```

`tag` means annotated (a lightweight tag would say `commit`).

```bash
git log --oneline --graph --all --decorate
```

> [!TASK]
> An annotated tag `lab5` points at a commit of `my-first-change`.

## Step 11 — Disaster and rescue

Delete the file that every NAVERA package uses for distances:

```bash
rm navera_common/navera_common/geo.py
```

```bash
git status
```

`deleted: navera_common/navera_common/geo.py`. It is committed, so git has it:

```bash
git restore navera_common/navera_common/geo.py
```

```bash
git status
```

`nothing to commit, working tree clean`. The restored file is your **last committed** version —
the one with `EARTH_RADIUS_M`.

> [!TASK]
> `geo.py` exists and `git status` reports a clean working tree.

## Step 12 — Answers and review

> [!TASK]
> - In [answers.py](file:./answers.py): `FIRST_COMMIT` (step 5), `NAVERA_SOURCE_COMMIT` (the hash
>   **inside** the base commit's message, step 1) and the quiz `Q1`–`Q6`.
> - In [review.md](file:./review.md): keep the four `##` headings and replace every "(write here)"
>   (at least 100 words in total). Name the rejected parameter with its old and new values, explain
>   the risk for **spoofing**, and say how you verified the part you applied.

## Step 13 — Check your work

Press **✔ Check my work**. The checker reads the git history of `~/navera` (identity, branch,
commits and their messages, the files each commit changes, the tag, the state of the folder) and
your files in the lesson folder.

> [!WARNING]
> Do not press **Reset my NAVERA copy** now: your commits would go into the backup bundle and the
> new `~/navera` would not have your branch, so these checks would fail.

## Going further (optional)

- **Fast-forward vs merge commit**, safely on throw-away branches:
  `git switch -c try-ff base`, `git merge my-first-change` (a fast-forward: no new commit). Then
  `git switch -c try-merge base`, commit one change of your own, and `git merge my-first-change`:
  git makes a merge commit with two parents (`git log --graph` shows the join). Go back with
  `git switch my-first-change` and delete the experiments with `git branch -D try-ff try-merge`.
- **A conflict on purpose**: on `try-merge`, change the same `gps_node.py` line differently before
  merging. Read the `<<<<<<<` markers, choose a version, `git add`, `git commit`.
- **Bundles**: `git bundle create ~/lessons/05-git/mine.bundle --all`, then
  `git clone ~/lessons/05-git/mine.bundle /tmp/restored` and look at `git -C /tmp/restored log --oneline --all --decorate`:
  this is how a teacher recovers your work after a Reset.
- **Who wrote what**: `git blame navera_common/navera_common/geo.py | grep EARTH_RADIUS_M` — your
  name now appears next to one line of NAVERA's geodesy.

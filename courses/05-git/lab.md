# Lab 5 — Your first commits in NAVERA

**Goal:** tell git who you are, create a branch in your NAVERA copy, make two clean commits (a
README line and a real log message of the GPS code), travel in the history, and rescue a deleted
file.
**Time:** about 50 minutes.

All the git commands run **inside your NAVERA copy**, so the first thing is to go there.

## Step 1 — Look at your repository

```bash
cd ~/navera
```

```bash
git status
```

You should read `On branch work` and `nothing to commit, working tree clean`: you are on the branch
`work`, and no file differs from the last commit.

```bash
git log --oneline
```

One single line: the commit `NAVERA base — …` that the academy made for you. Its message also
gives the hash and title of the real NAVERA commit your copy comes from. More context:

```bash
git branch
```

```bash
git tag
```

```bash
git remote -v
```

One branch (`work`, with the `*`), one tag (`base`), one remote (`base`, the academy's base copy).

## Step 2 — Tell git who you are

This time, **type the commands yourself** (there is no ▶ Run button), with **your** name and an
e-mail address between the quotes. The e-mail may be invented, it is only written in your commits:

```text
git config --global user.name "Sarra Ben Ali"
```

```text
git config --global user.email "sarra@example.com"
```

Check:

```bash
git config --global --list
```

> [!TASK]
> `git config --global user.name` and `user.email` are set to **your** name and an e-mail address.

## Step 3 — Create your branch

Never change the main line directly — create a branch for your work:

```bash
git switch -c my-first-change
```

```bash
git branch
```

Two branches now, and the `*` is on `my-first-change`. You are still on the same commit: a new
branch starts where you are.

## Step 4 — First commit: a line in the README

Open [ACADEMY_README.md](file:navera/ACADEMY_README.md) in the editor. Add one line **at the end**,
for example:

```text
- Sarra was here: my first commit in NAVERA!
```

Save (`Ctrl+S`). Now ask git what it sees:

```bash
git status
```

`modified: ACADEMY_README.md`, in red: changed in the working folder, **not staged**. See the
exact change:

```bash
git diff
```

Your line with a green `+`. (If the screen shows `(END)` or `:`, press `q`.) Stage it:

```bash
git add ACADEMY_README.md
```

```bash
git status
```

Now in green, under `Changes to be committed`. Take the snapshot:

```bash
git commit -m "Add my name to the academy README"
```

Git answers with the branch, the short hash of your new commit and `1 file changed`. Look:

```bash
git log --oneline
```

Your commit is on top of the base. **Note its hash** (the 7 characters at the start of the line):
you need it in step 8.

> [!TIP]
> If git answers *Please tell me who you are*, step 2 is missing: do it, then run the `git commit`
> again.

## Step 5 — Second commit: a log message of the GPS node

Now a change in real product code. Open
[gps_node.py](file:navera/gps_pkg/gps_pkg/nodes/gps_node.py) and find this line (around line 81;
`Ctrl+F` searches in the editor):

```python
        self.get_logger().info("Read thread started")
```

This is the message the GPS node writes in its log when it starts reading the receiver. Make it
more helpful — change **only the text between the quotes**, for example:

```python
        self.get_logger().info("Read thread started, listening to the GPS receiver")
```

Keep the quotes, the parentheses and the spaces at the start of the line. Save. Make sure the file
is still valid Python — this command prints nothing when all is well:

```bash
python3 -m py_compile gps_pkg/gps_pkg/nodes/gps_node.py
```

See the change, stage it, commit it:

```bash
git diff
```

```bash
git add gps_pkg/gps_pkg/nodes/gps_node.py
```

```bash
git commit -m "gps_node: clearer start-up log message"
```

> [!TASK]
> The branch `my-first-change` has **2 commits** of yours on top of `base`: one adds a line to
> `ACADEMY_README.md`, one changes a log message in `gps_node.py` (still valid Python). Each has a
> message that says what changed. The branch `work` is not changed.

## Step 6 — Travel in time

The whole history, drawn as a tree:

```bash
git log --oneline --graph --all
```

Your two commits, then the base. `work` still points at the base — it never moved, because you
committed on your branch. Everything you changed since the start, in one view:

```bash
git diff base --stat
```

Git compares with the tag `base` (your copy as you received it): 2 files changed. Now
look at the README **as it was** at the start, without changing anything:

```bash
git show base:ACADEMY_README.md | tail -n 3
```

No line of yours. Now the real time travel — switch to the branch `work`:

```bash
git switch work
```

```bash
tail -n 2 ACADEMY_README.md
```

Your line has **disappeared** from the file! It is not lost — it lives on the other branch.
(Don't edit or save files while you are on `work`: your changes belong on your branch.) Come back:

```bash
git switch my-first-change
```

```bash
tail -n 2 ACADEMY_README.md
```

It is back. Branches let you keep several versions of the project and jump between them in a second.

## Step 7 — Disaster… and rescue

Let's do what you must never do on a real box: delete an important file of NAVERA. `geo.py` holds
the distance and position maths that every part of NAVERA uses:

```bash
rm navera_common/navera_common/geo.py
```

```bash
ls navera_common/navera_common/
```

Gone. `rm` has no recycle bin… but git has the file in its history:

```bash
git status
```

`deleted: navera_common/navera_common/geo.py`. Bring it back:

```bash
git restore navera_common/navera_common/geo.py
```

```bash
git status
```

`nothing to commit, working tree clean`: the file is back, exactly as in your last commit.
The same works for a file you broke by editing it. Try it — add a nonsense line to the main README:

```bash
echo "oops, I broke the README" >> README.md
```

```bash
git diff
```

```bash
git restore README.md
```

```bash
git status
```

Clean again.

> [!TASK]
> `geo.py` is back and `git status` says `nothing to commit, working tree clean` (no modified or
> deleted file left).

## Step 8 — Answers

Open [answers.py](file:./answers.py) (in the lesson folder, not in NAVERA). Write the hash of your
**first** commit (the README one) — `git log --oneline` shows it again; your first commit is the
one just above the `NAVERA base` line. Then answer the three questions.

> [!TASK]
> `FIRST_COMMIT` is the short hash of your first commit on `my-first-change`, and `Q1`–`Q3` are
> answered. Save with `Ctrl+S`.

## Step 9 — Check your work

Press **✔ Check my work**. The checker looks directly at the git history of `~/navera`: your
identity, your branch, your commits, the files they change, and the state of the working folder.

> [!WARNING]
> Do not press **Reset my NAVERA copy** after this lab: it would replace `~/navera` by a fresh copy
> (your commits are saved in the backup bundle, but no longer in your copy), and these checks would
> fail.

## Going further (optional)

- Who changed what, line by line? `git blame ACADEMY_README.md` prints, for each line, the commit
  and the author that last changed it. Your line has your name.
- Look at one commit in full: `git show HEAD` (the commit you are on) and `git show HEAD~1`
  (the one before it).
- Make a third commit on your branch: in [gps_params.yaml](file:navera/gps_pkg/gps_pkg/config/gps_params.yaml)
  improve the comment above `serial_port`. Then use `git diff base --stat` to see your three
  changes. Finally, test the time machine on it: `git restore --source=base gps_pkg/gps_pkg/config/gps_params.yaml`
  puts the **original** version in your folder (`git diff` shows the difference with your commit);
  `git restore gps_pkg/gps_pkg/config/gps_params.yaml` brings back your committed version.

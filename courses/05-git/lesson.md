# Git: your time machine (and the Reset button)

Friday evening, an engineer changes one number in NAVERA's day vision to "make it a bit faster".
On Monday, the test drone drifts 200 m away from its route. What changed? Which file? Which line?
Who did it, and what was the number before? Without help, the team could search for days.

With **git**, they type one command and see, in red and green, the exact line that changed on
Friday, with the author, the date and the reason. A second command puts the old version back.
Git is a **time machine for files** — and every professional software team uses it, NAVERA's
included. In this lesson you make your own commits in your NAVERA copy, travel in its history,
undo a disaster, and understand what the dashboard's **Reset** button really does.

## Version control

Without a tool, people keep versions like this:

```
gps_node.py   gps_node_old.py   gps_node_v2.py   gps_node_v2_FINAL.py   gps_node_v2_FINAL_fixed.py
```

Nobody knows which one is used, what the differences are, or why. A **version control system**
replaces that mess with a **history**: a list of **snapshots** of the whole project, each with a
message that explains it. Git is the most used one in the world.

| Word | Meaning |
|---|---|
| **repository** (repo) | a project folder whose history git keeps. The history is stored in a hidden folder `.git` inside it |
| **commit** | one snapshot of the project, with an author, a date, a message, and a link to the commit before it (its **parent**) |
| **hash** | the unique name of a commit, like `ac803d2` (the short form of a 40-character code) |
| **branch** | a named line of work: a label that points at its latest commit |
| **tag** | a fixed label on one commit, that never moves (like `base`) |

Your `~/navera` is a git repository. Run `ls -a ~/navera` and you will see the `.git` folder.
(Never edit what is inside it by hand.)

## Who are you?

Every commit records its **author**. So before your first commit, tell git your name and e-mail —
once, for all your projects (`--global`):

```
git config --global user.name "Sarra Ben Ali"
git config --global user.email "sarra@example.com"
```

If you forget, git refuses to commit and says *Please tell me who you are*. The settings are
stored in the file `~/.gitconfig`.

## The three areas: edit, choose, save

This is the most important picture of the lesson. Git sees your work in three places:

![Working folder, staging area, history](assets/three_areas.svg)

1. The **working folder**: the real files that you edit with the editor. When you save a file,
   git notices it is **modified** — but nothing is in the history yet.
2. The **staging area**: the changes you have **chosen** to put in the next snapshot. `git add file`
   puts a file's current changes there. It is like arranging people before taking a group photo.
3. The **history**: `git commit -m "message"` takes the photo. Everything that was in the staging
   area becomes a new commit, for ever.

Why two steps (`add`, then `commit`)? Because you often change several things at once, and a good
commit holds **one** idea. With `add` you choose what goes together.

### The commands of the daily loop

| Command | What it does |
|---|---|
| `git status` | **the most useful command**: on which branch you are, which files are modified, which are staged |
| `git diff` | the exact lines changed in the working folder and not staged yet: `-` in red = removed, `+` in green = added |
| `git diff --staged` | what is staged, i.e. what the next commit will contain |
| `git add file` | stage the changes of this file |
| `git commit -m "Add my name to the README"` | make the commit, with its message |

A `git diff` looks like this:

```
--- a/gps_pkg/gps_pkg/nodes/gps_node.py
+++ b/gps_pkg/gps_pkg/nodes/gps_node.py
@@ -78,7 +78,7 @@
         self.running = True
         threading.Thread(target=self._read_loop, daemon=True).start()
-        self.get_logger().info("Read thread started")
+        self.get_logger().info("Read thread started, listening to the GPS receiver")
```

The lines without `-` or `+` are context, so you can see where the change is. `@@ -78,7 +78,7 @@`
says it is around line 78.

### A good commit message

The message is for the person who reads the history in six months — maybe you. It says **what**
changed and, if not obvious, **why**, in one short sentence: *"gps_node: clearer start-up log
message"*. Not *"update"*, not *"stuff"*, not *"asdf"*.

## Reading the history

| Command | Shows |
|---|---|
| `git log` | every commit: hash, author, date, message (newest first) |
| `git log --oneline` | one line per commit: short hash + message |
| `git log --oneline --graph --all` | all the branches, drawn as a little tree |
| `git show ac803d2` | one commit and its diff |
| `git show base:ACADEMY_README.md` | a file **as it was** in another commit (here: the tag `base`) |
| `git diff base` | everything that differs between `base` and your working folder now |

> [!TIP]
> When a git output is longer than the screen, git shows it in a viewer: you see `:` or `(END)` at
> the bottom. Scroll with the arrow keys or `Space`, and press **`q`** to quit.

## Undo: the time machine

| Situation | Command |
|---|---|
| I changed (or deleted!) a file and I want it back as in the last commit | `git restore file` |
| I staged a file by mistake (`git add`) and want to unstage it (the edits stay) | `git restore --staged file` |
| I want a file as it was in an older commit | `git restore --source=base file` |

`git restore` brings back a file **even after `rm`** — remember lesson 2: "the terminal has no
recycle bin". In a git repository, every committed file is safe: git has a copy in its history.

> [!WARNING]
> `git restore file` **throws away** the changes you did not commit in that file. That is what you
> want after a mistake — but it cannot be undone itself. Changes that were never committed are the
> only ones git cannot give back. Hence the golden rule: **commit small, commit often.**

You may also meet the older form `git checkout -- file`: it does the same as `git restore file`.

## Branches: try things without fear

A **branch** is a separate line of commits. You start a branch, try your idea there, and the main
line stays untouched. If the idea works, it can be merged later; if not, you just leave the branch.

![Branches: work stays at base, my-first-change gets your commits](assets/branches.svg)

| Command | What it does |
|---|---|
| `git branch` | lists the branches; `*` marks the one you are on |
| `git switch -c my-idea` | **c**reates the branch `my-idea` here and moves onto it |
| `git switch work` | moves onto the existing branch `work`: your files change to its version! |

When you switch branches, git **changes the files in your folder** to match that branch. Commit
(or restore) your changes before switching, otherwise git may refuse to switch, to protect them.
The name of the branch you are on is called **HEAD** in git's messages.

> [!NOTE]
> In the real NAVERA team, nobody works directly on the main line. Each task gets its own branch,
> like `fix/acceptance` (that name appears in `docs/ACCEPTANCE_FINDINGS_2026-10-03.md`), and only tested
> work joins the main line.

## Your copy of NAVERA

When your account was created, the academy made `~/navera` like this:

- it took **one commit** of the real NAVERA repository (you can read which in your first
  `git log` line: `NAVERA base — <hash> <message>`), and saved it as **one commit** tagged **`base`**;
- your copy is a **clone** of that: a full repository of its own, with a branch called **`work`**;
- the place it was cloned from is registered as a **remote** called `base` (`git remote -v`).

When you type `git diff base`, git uses the **tag** `base`, which is exactly what you want:
"my copy as I received it".

Your copy has no link to the real product: you can commit, branch, break and fix anything. Nothing
you do in `~/navera` ever reaches the real NAVERA repository.

## The Reset button

In the 👤 menu, **Reset my NAVERA copy** gives you a brand new `~/navera`. It does **not** simply
delete your work. In order, the server:

1. stages and commits everything you left uncommitted, with the message `auto-save before reset`;
2. packs your **whole repository** — all branches, all commits — into a single file called a
   **git bundle**, kept on the server in your backup folder (`navera-<date>-<time>.bundle`);
3. deletes `~/navera` and clones a fresh copy of the base (with its build).

So nothing is lost: your teacher can open the bundle and give you back any commit. But after a
reset, your branches are **not in `~/navera` any more** — for this lesson, that means its checks
would fail. Reset only when you really want a clean start.

The other button, **↺ Reset lab files**, is different: it only puts back the files of the current
lesson in `~/lessons/<lesson>/` (keeping a backup copy). It never touches `~/navera`.

## In NAVERA

The NAVERA team writes its working rules in [CLAUDE.md](file:navera/CLAUDE.md), at the root of the
repository. Three of its "golden rules" are about git:

```text
2. Always work on a git branch, never directly on main. Commit small, commit often.
3. Never commit large files. No .mbtiles, .npz, .pth, ... The .gitignore already
   excludes these — keep it that way.
5. One concern per commit. Cleaning, refactor, optimization, and new features go in
   separate commits.
```

and its workflow for every task is: understand → **branch** → change → verify → **commit** with a
clear message → report. That is exactly what you will do in the lab.

Rule 3 explains a file you can open: [.gitignore](file:navera/.gitignore) lists what git must
**ignore** — the 10 GB satellite map, the neural network weights, and the `build/`, `install/`,
`log/` folders made by the build. Those are too big or can be re-made, so they are never committed.
That is why `git status` does not show them.

The product's real history is full of messages like `fix(day): height filter, odometry gate,
heading-aware map bias, re-acquisition` or `feat(bench): screen_mission — …`: a type
(`feat` = new feature, `fix` = correction), the part of the product in brackets, and what changed.
Even the accuracy documents point to commits: `docs/VALIDATION_STATUS.md` cites a commit hash as
proof of when the IMU was verified.

## Words of this lesson

| Word | Meaning |
|---|---|
| **git** | the version control tool: it keeps the history of a folder |
| **repository** | a folder with its history (in `.git`) |
| **commit** | a snapshot of the project, with author, date and message |
| **hash** | the unique name of a commit (`ac803d2`) |
| **working folder** | the files as they are on disk now |
| **staging area** | the changes chosen for the next commit (`git add`) |
| **diff** | the list of changed lines between two versions |
| **branch** | a named line of commits (`work`, `my-first-change`) |
| **HEAD** | the branch / commit you are on now |
| **tag** | a fixed label on one commit (`base`) |
| **clone** | a complete copy of a repository |
| **remote** | another repository your clone knows by a name (`base`) |
| **bundle** | a whole repository packed into one file (the Reset backup) |

## Check what you learned

<details><summary>1. You edited three files but want only one of them in the next commit. How?</summary>
<code>git add</code> only that file, then <code>git commit</code>. The two others stay modified in the working folder,
for a later commit.
</details>

<details><summary>2. What is the difference between <code>git diff</code> and <code>git diff --staged</code>?</summary>
<code>git diff</code> shows the changes not staged yet; <code>git diff --staged</code> shows what is staged, i.e. what the
next commit will contain.
</details>

<details><summary>3. You ran <code>rm geo.py</code> by mistake in your NAVERA copy. Is it lost?</summary>
No: it was committed in <code>base</code>, so <code>git restore navera_common/navera_common/geo.py</code> brings it back.
Only changes that were never committed cannot be recovered.
</details>

<details><summary>4. You commit on branch <code>my-first-change</code>, then run <code>git switch work</code>. Where is your change?</summary>
Still in the history, on <code>my-first-change</code>. The files in the folder now show the <code>work</code> version (without
your change). <code>git switch my-first-change</code> brings them back.
</details>

<details><summary>5. What does the Reset button keep, and where?</summary>
Everything: it commits what was uncommitted, then saves the whole repository (all branches) as a git bundle
in your backup folder on the server, before giving you a fresh copy.
</details>

Now open the **🛠️ Lab** tab.

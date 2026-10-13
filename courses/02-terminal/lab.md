# Lab 2 — Ground engineer: the box on the bench and the flight logs

**Goal:** work on a NAVERA Lite box entirely from the terminal: explore the stack's skeleton, tidy the
box's files, repair a permission fault, find and stop an orphan arbiter, restart a hung node; then
answer questions about two flights with pipelines and write a script that summarises any log.
**Time:** 2 h 30 to 3 h 30 (up to 5 h if you have never used a terminal: plan the two sessions on two days).

Your files (📝 Code tab): [answers.py](file:./answers.py) (your answers), [cheatsheet.md](file:./cheatsheet.md)
(every command), [mission_brief.txt](file:./mission_brief.txt), `box.sh` (the simulated box; you don't
edit it), `inbox/` (files copied from the box, in a mess), `navera_lite/` (your stack: empty today).

| Lesson | Lab | You do |
|---|---|---|
| (nothing to read first) | Step 0 | start the box and watch its decisions |
| §1–§2 Shell, paths, find | Steps 1–3 | explore the skeleton (Q1–Q5), tidy the inbox |
| §3 Permissions | Step 4 | a script without x, a service without its group (P1–P3) |
| §4 Environment | Step 5 | E1, E2, `ros_env.txt` |
| §5 Processes, signals | Step 6 | the orphan arbiter, the hung camera |
| §6 Streams, pipelines | Steps 7–8 | `ls_out.txt`/`ls_err.txt`, Q6–Q8 |
| §7 Scripts | Steps 9–10 | `log_report.sh`, the flight report |

> [!NOTE]
> **Type** the commands as much as you can (with `Tab` completion); the ▶ Run button is there when you
> are stuck. If you get lost: `cd ~/lessons/02-terminal`. **Predict, then run:** each `PREDICT_…` is
> written *before* the step that answers it, and is never marked right or wrong.

## Session 1 — The box on the bench (about 1 h 30)

## Step 0 — Start the box

A NAVERA Lite box is simulated in your lesson folder: a few small programs that behave like the box's
services. Start it (it takes about seven seconds), and look at the last decisions of its arbiter:

```bash
./box.sh start
```

```bash
tail -n 6 box/log/decisions.log
```

Run the `tail` again a few times, and read the messages, not only the states. A box should judge with
**one** arbiter. Keep this picture in mind: you will explain it in Step 6. (The box lives in this
terminal tab: a "＋ new" terminal is a separate sandbox and does not see it. If you close the terminal or
reload the page, run `./box.sh start` again.)

## Step 1 — Orientation

```bash
pwd
```

```bash
ls -la
```

Read the first column: `d` for a folder, `-` for a file, then the 9 permission bits. `box.sh` has `x`
bits; most files do not. (`.academy_version` is the academy's own file: ignore it.)

```bash
cat mission_brief.txt
```

`wc -l mission_brief.txt` prints `20 mission_brief.txt`; `wc -l < mission_brief.txt` prints only `20`.
**Why?** (Who opens the file in each case: `wc`, or the shell? Lesson §6.) You will need the second form
in Step 9.

## Step 2 — Explore the NAVERA Lite skeleton

The skeleton of the stack you will build is read-only course data:

```bash
cd /data/academy/02-terminal/navera_lite_tree
```

```bash
ls
```

```bash
cat README.md
```

Type `cd navera_lite/r` and press `Tab`: the shell completes `ros/`. Press `Enter`, then `pwd` and
`ls`. Look at one file: `cat arbiter_v0.py` — names and one-line descriptions, no code yet. `cd ..`
twice brings you back to the skeleton's top folder (check with `pwd`).

Now answer **Q1–Q5** of [answers.py](file:./answers.py) from the skeleton's top folder. Paths are written
relative to it (`"navera_lite/geo.py"`).

- **Q1** `ls` shows one level; `find` visits every sub-folder. Count with `| wc -l`. Which folder
  do you search in?
- **Q2** `grep -r` searches inside every file of a folder; `-l` prints only the file names:

  ```bash
  grep -rl "def mahalanobis2" .
  ```

  Three names: which one is the **source**?
- **Q3** `find` prints names on its output, but `wc -l` wants names as **arguments**. `xargs CMD` turns
  its input lines into arguments of CMD. Build the pipeline yourself; the last line of `wc` is the total.
- **Q4** `ls deploy/systemd`, then count only the names that end in `.service` (a wildcard, and `wc -l`).
- **Q5** search the part files for the words `mission 17`.

<details><summary>Stuck? Hints</summary>

1. Q1 = 140? You searched from `.`: that counts the copies in `build/` and `install/` too. Search in
   `navera_lite`. Q1 = 0? Did you quote `"*.py"`?
2. Q2: the source is the path that does not start with `build/` or `install/`. Drop the `./`.
3. Q3: `find navera_lite/ros -name "*.py" | xargs wc -l`. The total line says `total`; do not add the
   numbers yourself.
4. Q4 = 5? The `.target` file is not a service: a wildcard `*.service` keeps only the units.
5. Q5: `grep -l` prints only the names of the matching files. Which files are the *part* files
   (`navera_lite/*.py`)?
</details>

Go back to your lesson folder:

```bash
cd ~/lessons/02-terminal
```

> [!TASK]
> Q1–Q5 are answered in `answers.py` (saved with `Ctrl+S`).

## Step 3 — Tidy the inbox

```bash
ls -l inbox
```

Ten files from the box: three camera views (`.jpg`, synthetic images rendered from the course map),
two flight logs, three cache files (`.tmp`), the pilot's notes and a pre-flight script. Build the
mission folder:

```bash
mkdir -p mission/photos mission/logs mission/docs mission/bin mission/deploy
```

Move all the camera views with one wildcard (the shell expands `inbox/*.jpg` into three names first):

```bash
mv inbox/*.jpg mission/photos/
```

Now **type yourself**: move the two `.log` files into `mission/logs/`; move `inbox/notes_for_pilot.txt`
to `mission/docs/notes.txt` (move and rename in one `mv`); move `inbox/preflight.sh` into
`mission/bin/`. Then only the `.tmp` files are left. **Look first** with the pattern you will delete:

```bash
ls inbox/*.tmp
```

If it lists exactly the three cache files, delete them, then the empty folder:

```bash
rm inbox/*.tmp
```

```bash
rmdir inbox
```

`rmdir` refuses a folder that is not empty: if it complains, `ls inbox` shows what you forgot. Then
`ls -R mission`, and open a view in the editor: [mission/photos/cam_0001.jpg](file:./mission/photos/cam_0001.jpg).

> [!TASK]
> `mission/photos`, `logs`, `docs`, `bin`, `deploy` exist; the 3 views and the 2 logs are **moved**
> there; the notes are `mission/docs/notes.txt`; `preflight.sh` is in `mission/bin/`; the `.tmp` files
> and `inbox/` are gone.

## Step 4 — Permissions

**4a. A script without x.**

```bash
ls -l mission/bin/preflight.sh
```

```bash
./mission/bin/preflight.sh
```

`Permission denied`. Read it in the editor: [preflight.sh](file:./mission/bin/preflight.sh) (a shebang,
`${ROS_DOMAIN_ID:-NOT SET}`, `[ -f … ]`, `exit 0` / `exit 1`: the syntax of lesson §7). Without the x
bit it still runs through bash:

```bash
bash mission/bin/preflight.sh
```

Now give the **owner** the execute permission with `chmod` (type it yourself), check with `ls -l`, and run
`./mission/bin/preflight.sh` again. It now runs, and reports a problem with the GPS service.

**4b. A service without its group.** The engineer of a test box saved some evidence:

```bash
ls /data/academy/02-terminal/evidence
```

```bash
cat /data/academy/02-terminal/evidence/README.txt
```

Read the four other files with `cat`. Be the detective: why does the GPS reader work when the
developer starts it by hand, but not as a service? Write **P1** (the octal mode of the port) and **P2**
(the missing group).

<details><summary>Stuck? Hints</summary>

1. `ls_dev.txt`: owner, group and mode of the port. `rw-` = 6.
2. Compare the groups in `id_developer.txt` and `id_navera_lite.txt`. Which group of the port's line
   does the developer have, and the service user not?
</details>

The fix belongs in the service's **unit file**, the file that tells systemd how to run the service. Copy
the skeleton's unit into your mission folder (`cp`, not `mv`: the skeleton is read-only, and it is the
reference):

```bash
cp /data/academy/02-terminal/navera_lite_tree/deploy/systemd/navera_lite-gps.service mission/deploy/
```

Open [mission/deploy/navera_lite-gps.service](file:./mission/deploy/navera_lite-gps.service). In the
`[Service]` section, add **one line** that gives the service's user the extra group: the setting is
called `SupplementaryGroups`. The skeleton's camera unit already does this for its own device: read
`cat /data/academy/02-terminal/navera_lite_tree/deploy/systemd/navera_lite-camera.service` and do the
same for the GPS. Unit files are not YAML or Python: write `SupplementaryGroups=` followed directly by
the group's name (systemd tolerates spaces around `=`, but the usual style has none). Change nothing
else. Save, then compare with the original — `diff` prints only the lines that differ:

```bash
diff /data/academy/02-terminal/navera_lite_tree/deploy/systemd/navera_lite-gps.service mission/deploy/navera_lite-gps.service
```

```bash
./mission/bin/preflight.sh; echo "exit code: $?"
```

`PRE-FLIGHT OK` and exit code `0`. (If it says the map is missing, the data disk is not connected: not
your mistake, tell the teacher and go on.)

<details><summary>Stuck? Hints</summary>

1. `diff` shows `> SupplementaryGroups=dialout` and nothing else: right. A line starting with `<` means
   you changed or deleted an original line.
2. Changing `Group=navera_lite` into `Group=dialout` is wrong: the service would lose its own group.
   `User=root` "works" and is exactly what a service must never do.
3. The line goes between `[Service]` and `[Install]`; in `[Install]` systemd ignores it.
</details>

> [!TASK]
> `mission/bin/preflight.sh` is executable by its owner and unchanged; `mission/deploy/navera_lite-gps.service`
> is the original plus one `SupplementaryGroups=dialout` line in `[Service]`; P1, P2 and **P3** (the
> octal mode of your `preflight.sh` now, read on `ls -l`) are in `answers.py`.

## Step 5 — The environment

```bash
echo $ROS_DOMAIN_ID
```

```bash
env | grep ^NAVERA_LITE
```

Write **E1** (the value of `ROS_DOMAIN_ID`, a number) and **E2** (the value of `NAVERA_LITE_MAP`, in
quotes). Now see inheritance. A shell variable is not given to a child process; an exported one is:

```bash
MY_SPEED_KMH=90
```

```bash
bash -c 'echo "child sees: [$MY_SPEED_KMH]"'
```

```bash
export MY_SPEED_KMH
```

```bash
bash -c 'echo "child sees: [$MY_SPEED_KMH]"'
```

(The single quotes stop **your** shell from replacing `$MY_SPEED_KMH`: the child does it.) A setting for
one command only: `ROS_DOMAIN_ID= ./mission/bin/preflight.sh` — read its first line.

A colleague left a note in the environment of this box:

```bash
export MY_NOTE="read ROS_DOMAIN_ID first"
```

Now **build the pipeline yourself**: `env`, then a `grep` that keeps only the lines that **start** with
`ROS_`, then `sort`, all redirected into `ros_env.txt`. Check with `cat ros_env.txt`: is `MY_NOTE` in it?
It must not be (lesson §6: `^`).

> [!TASK]
> E1 and E2 are filled in; `ros_env.txt` holds only the `ROS_…` variables, sorted (with
> `ROS_DOMAIN_ID` and `ROS_LOCALHOST_ONLY=1`).

## Step 6 — The detective: two arbiters

Back to Step 0's picture:

```bash
tail -n 6 box/log/decisions.log
```

One judge says FIX, another NO_FIX, every second: two arbiters are running, with the same node name.
Which one does not belong? First, without stopping anything:

> [!TASK]
> **Predict** (`PREDICT_PKILL`): what would `pkill -f navera_lite_arbiter` do on this box, exactly?
> (Which processes, and what happens a second later? Remember what a supervisor does, lesson §5.)

Now investigate. Find the PIDs and command lines:

```bash
pgrep -a -f navera_lite_arbiter
```

Then the parents and start times — write the two PIDs you found after `-p`, separated by a comma (for
example `ps -o pid,ppid,lstart,args -p 23,71`; your numbers differ). Then look at each **parent**:
`ps -o pid,args -p PPID`. The whole family: `ps -ef | cut -c1-120` (the very long line of PID 1 is the
sandbox itself). The box's journal tells the story too (its times and the `STARTED` times of `ps` may
differ by a second: they are read at slightly different moments):

```bash
cat box/log/journal.log
```

Which arbiter listens to a simulator that no longer runs? Who started it, and is that parent still
alive? When you are sure, stop **that PID** politely: `kill` followed by the number (not `kill -9`, not
`pkill`). Then check: `pgrep -a -f navera_lite_arbiter` and `tail -n 4 box/log/decisions.log`.

<details><summary>Stuck? Hints</summary>

1. `ps -o pid,ppid,lstart,args -p A,B` with your two PIDs. The older one is not automatically the bad
   one: whose parent is still alive?
2. `ps -o pid,args -p` on the other PPID: is it a supervisor of the box?
3. The command lines differ: `--params-file box/config/sim.yaml` vs `navera_lite.yaml`.
4. You stopped the wrong one? The supervisor starts it again a second later (see the journal): no harm,
   and you have already observed the next paragraph. Find the orphan and stop it; no need to restart the box.
</details>

**Observe your prediction.** The orphan is gone; now see what a supervisor does with a kill. Find the
PID of the remaining arbiter, `kill` it, wait 2 s, then run `pgrep -a -f navera_lite_arbiter` and
`tail -n 3 box/log/journal.log`. Same PID or a new one? Compare with your PREDICT_PKILL: what would
`pkill` have done to the orphan **and** to this one?

> [!TASK]
> The orphan arbiter received SIGTERM (its journal line says so); the supervised arbiter was stopped and
> restarted by its supervisor; `ORPHAN_PPID` and `EXPLAIN_ORPHAN` (two clues that told you which one was
> the orphan) are in `answers.py`.

**The hung camera.** The journal also complains about the camera reader:

```bash
grep camera box/log/journal.log
```

Restart it the right way: the supervisor starts it again when it ends, so you only have to end it.
Find its PID (`pgrep -a -f box/bin/camera`), send **SIGTERM** (`kill PID`), wait five seconds, and check
whether it is still alive (`ps -p PID`) and what the journal says. Use the next step of the ladder only
if you need it. Then read the end of the journal: `tail -n 5 box/log/journal.log`.

> [!TASK]
> The camera reader received SIGTERM first, and SIGKILL at least 2 s later; a new camera reader runs.
> `KILL_EXIT_CODE` (read in the journal) and `EXPLAIN_KILL` are in `answers.py`.

Stop the box when you are done (the next steps do not need it):

```bash
./box.sh stop
```

> [!TIP] 🏅 End of session 1 — Orphan hunter
> Press **✔ Check my work**. When checks 1–8 pass, you earn the **Orphan hunter** badge (checks 9–15
> are session 2). If you start the box again, nothing is lost: earlier runs are kept in `box/old/`, the
> check reads them all, and one correct run is enough.

## Session 2 — The flight logs (about 1 h 30)

The two logs in `mission/logs/` are **synthetic**: written for this lab in the format of NAVERA Lite's
nodes, with simulated GPS losses, on a flight along the Sousse coast and one over an inland test range.

## Step 7 — stdout and stderr

`ls` with one file that exists and one that does not prints a normal line **and** an error:

```bash
ls navera_lite.yaml no_such_file.yaml
```

```bash
ls navera_lite.yaml no_such_file.yaml > ls_out.txt
```

The error still appears: only stdout went into the file. Now **write the command yourself** that sends
stdout into `ls_out.txt` and stderr into `ls_err.txt` (nothing on the screen), and look at both files.

> [!TASK]
> `ls_out.txt` holds the normal output of that `ls`, `ls_err.txt` its error message.

## Step 8 — Questions with pipelines

Look at the start and the end of a log, and convert the time of its first line:

```bash
head -n 4 mission/logs/sousse_2026-09-21.log
```

```bash
TZ=Africa/Tunis date -d @1789975800 +%T
```

`08:30:00`: the flight started at 08:30 in Sousse (07:30 UTC). (The academy computer's clock happens to
be set to Tunisian time, so `date` alone gives the same answer here. A robot's computer is usually on
UTC: always write `TZ=…` or `-u`.) Count the WARN lines in two ways:

```bash
grep -c WARN mission/logs/sousse_2026-09-21.log
```

```bash
grep -c "^\[WARN\]" mission/logs/sousse_2026-09-21.log
```

They differ: find the line that makes the difference with `grep WARN … | grep -v "^\[WARN\]"`.

> [!TASK]
> **Predict** (`PREDICT_UNIQ`): if you forget `sort`, how many lines does
> `grep "^\[WARN\]" mission/logs/sousse_2026-09-21.log | cut -d' ' -f3 | uniq -c` print: 3, about 10,
> about 40, or 84? Why? Write your guess, then run it and count its lines with `| wc -l`.

Now answer with pipelines you build yourself, one stage at a time (`↑` recalls the last command; add a
stage, look, add the next):

- **Q6** the node with the most WARN lines in the Sousse log (lesson §6 shows the method on another log);
- **Q7** the Tunisian time of the first `state NO_FIX` in the Sousse log: `grep -m 1`, then the time
  field, then only the whole seconds (`cut -c2-11` keeps characters 2 to 11 of
  `[1789976724.070430279]`), then `TZ=Africa/Tunis date -d @SECONDS +%T`;
- **Q8** the number of **different** nodes that wrote an ERROR line, in both logs together
  (`cat mission/logs/*.log | …`).

<details><summary>Stuck? Hints</summary>

1. Q6: it is lesson §6's worked example on another file: the same five stages. Write the name without
   brackets and colon.
2. Q7: one hour off? You wrote UTC (`date -u`); Tunisia is UTC+1.
3. Q8: ERROR lines, then field 3, then `sort -u`, then `wc -l`. 7? You counted lines, not different
   nodes. 2? You read the Sousse log only.
4. Still stuck on Q6: `grep "^\[WARN\]" … | cut -d' ' -f3 | sort | uniq -c | sort -rn | head -n 1`.
</details>

> [!TASK]
> Q6, Q7, Q8 and PREDICT_UNIQ are in `answers.py`.

## Step 9 — Your script: `log_report.sh`

Write `mission/bin/log_report.sh`, a script that summarises **any** log in this format:

```bash
touch mission/bin/log_report.sh
```

Open [mission/bin/log_report.sh](file:./mission/bin/log_report.sh). The specification:

- Usage: `./mission/bin/log_report.sh LOGFILE` (exactly one argument). First line `#!/bin/bash`, then
  `set -e`.
- No argument (or more than one): a usage message on **stderr**, nothing on stdout, exit code 2.
  A file that does not exist: a message on stderr, exit code 1.
- Otherwise print **exactly these 7 lines** (here for the Sousse log; your numbers come from the file):

  ```text
  file: sousse_2026-09-21.log
  lines: …
  INFO: …
  WARN: …
  ERROR: …
  nodes: …
  no_fix: …
  ```

  `file` is the name without the folders; `lines` all the lines; `INFO`, `WARN`, `ERROR` the lines whose
  **severity** (first field) is that level; `nodes` the number of **different** node names (field 3);
  `no_fix` the lines that contain `state NO_FIX`.

Lesson §7's `count_level.sh` shows every piece you need, but not this script: write it yourself.

> [!TIP] 🧰 Build it in 4 runs, not 1
> (1) shebang, `set -e`, the `$#` test with `>&2` and `exit 2`; `chmod u+x`; test without an argument.
> (2) the `-f` test and `exit 1`; test on `/tmp/nothing.log`. (3) the `file:` and `lines:` lines only;
> run it on the Sousse log. (4) the counts, one per line; compare WARN with Step 8. Run after each part:
> one new error at a time is much easier to find.

Make it executable, then test it on a log, without an argument, and on a missing file:

```bash
./mission/bin/log_report.sh mission/logs/sousse_2026-09-21.log
```

```bash
./mission/bin/log_report.sh; echo "exit code: $?"
```

```bash
./mission/bin/log_report.sh /tmp/nothing.log; echo "exit code: $?"
```

Compare your WARN count with Step 8. The check also runs your script on **a log it has never seen**:
it has no ERROR line at all, and INFO messages that contain the words WARN and ERROR. Before you press
Check, make your own test log with no ERROR line and run your script on it:

```bash
grep -v "^\[ERROR\]" mission/logs/range_2026-09-22.log > /tmp/no_error.log
```

```bash
./mission/bin/log_report.sh /tmp/no_error.log; echo "exit code: $?"
```

<details><summary>Stuck? Hints</summary>

1. The script stops after `WARN:` with no message on a log without ERROR lines: `grep -c` found 0 and
   exited with 1 under `set -e`. Add `|| true` (lesson §7).
2. `file: mission/logs/sousse…`: use `basename`.
3. `lines: 310 mission/logs/…`: `wc -l < "$log"` prints the number only.
4. `WARN: 85` instead of 84: anchor the pattern, `"^\[WARN\]"`.
5. `nodes: 310`, `nodes: 1` or `nodes: 183`: field 3, then `sort -u` (`uniq` alone counts runs), then `wc -l`.
6. Exit code 0 without an argument: test `$#` and `exit 2`.
</details>

Then save one report per flight with a `for` loop (`basename "$f" .log` also removes the `.log` ending):

```bash
for f in mission/logs/*.log; do ./mission/bin/log_report.sh "$f" > "mission/docs/report_$(basename "$f" .log).txt"; done
```

```bash
head mission/docs/report_*.txt
```

> [!TASK]
> `mission/bin/log_report.sh` has a shebang, is executable, fails correctly without an argument or with a
> missing file, and prints the exact 7 lines for any log; `mission/docs/report_sousse_2026-09-21.txt` and
> `mission/docs/report_range_2026-09-22.txt` hold its output for the two flights.

## Step 10 — The flight report

Write `mission/docs/flight_report.md` for the test team (create it with `touch`, write it in the editor),
with three sections:

- `## Sousse` — the numbers of the flight from your report (lines, WARN, ERROR, **NO_FIX** count), the
  **Tunisian time of the first NO_FIX**, and one or two sentences on what happened: read the WARN lines
  around it (`grep -n`), where was the drone, why did vision fail?
- `## Range` — the same numbers (**NO_FIX** and **ERROR** counts), and what the arbiter did with the GPS
  jump (`grep -n "jump" mission/logs/range_2026-09-22.log`).
- `## Conclusion` — at least 40 words: what the two flights show about day vision as a backup of GPS, and
  one recommendation for the next test.

> [!TASK]
> `mission/docs/flight_report.md` has the three sections; each flight section gives its NO_FIX and ERROR
> counts, the Sousse section the Tunisian time of the first NO_FIX; the conclusion has at least 40 words.

## Step 11 — Check, then look back

Press **✔ Check my work**. Each ✘ names what is missing and gives a hint. When everything passes, you earn
the **Log detective** badge. Then, without the lesson:

1. Explain to a colleague, in three sentences, how you told the orphan arbiter from the good one.
2. Which `Permission denied` of today was a missing bit, and which a missing group? How did you tell?
3. Which of your predictions was the most wrong, and why?

> [!NOTE]
> Made a mess? **↺ Reset lab files** puts this lesson's files back as at the start (your current files
> are kept in a backup).

## Going further (optional)

- **A watchdog.** Write `mission/bin/watchdog.sh CMD…` that runs a command, starts it again when it ends
  with a non-zero code, and gives up after 3 tries (exit code 1). This is what the supervisor of the box
  does, and what NAVERA once lacked ("crashed nodes never restarted"). Test it with
  `./mission/bin/watchdog.sh bash -c 'exit 3'`.
- **Several files.** Make your script accept several logs (`for f in "$@"`) and print one block per file;
  what should the exit code be if one file is missing?
- **awk.** `awk '{print $3}' mission/logs/*.log | sort | uniq -c` counts nodes without `cut`. Add a line
  `first_no_fix: HH:MM:SS` (Tunisian time, or `-` when there is none) to a copy of your script.
- **Durations.** With the Unix times of a `state DEGRADED` line and the next `state FIX`, compute how long
  a GPS loss lasted: `echo $(( 1789976223 - 1789976103 ))`.
- **Disk usage.** `du -sh /data/academy/02-terminal/navera_lite_tree/*`: which folder is the biggest, and
  why is that a reason never to edit `build/` or `install/`?

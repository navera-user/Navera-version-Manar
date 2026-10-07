# Lab 2 — Ground engineer for the NAVERA training flights

**Goal:** process the files of two training flights entirely from the terminal: tidy them, fix a
permission, record the environment, stop a running process cleanly, write a reusable bash script
that summarises any NAVERA log, explore the NAVERA code, and write a short flight report.
**Time:** about 3 hours.

**The data.** The two logs (`sousse_2026-09-21.log`, `range_2026-09-22.log`) are **synthetic**: they
were generated for this lab in the exact format of NAVERA's ROS 2 nodes, and the GPS losses in them
are simulated. The three photos are real aerial frames from NAVERA's test data, which covers
**Sousse, Tunisia**, where NAVERA is developed.

Click the **⌨️ Terminal** tab. Every `bash` block has a **▶ Run** button, but type as much as you
can yourself, with `Tab` completion: your fingers learn faster than your eyes. Use `↑` to recall and
edit a previous command.

> [!NOTE]
> **Paths in this lab.** The terminal starts in `~/lessons/02-terminal`, which is the same folder as
> `/home/student/lessons/02-terminal`. If you get lost, `cd ~/lessons/02-terminal` brings you back.
> Commands such as `find` print long paths (`/home/student/navera/…`); that is the same as `~/navera/…`.

## Step 1 — Orientation

```bash
pwd
```

```bash
ls -la
```

You see `answers.py`, `fake_node.sh`, `inbox/` and `mission_brief.txt`, plus `.`, `..` and
`.academy_version` (a file the academy uses: ignore it). Read the
first column of `ls -la`: `d` for a folder, `-` for a file, then the 9 permission bits. `fake_node.sh`
has `x` bits; the other files do not. The third and fourth columns are the owner (`student`) and the
group — the group may show a name of the host computer, such as `shadow-team`; ignore it.

```bash
cat mission_brief.txt
```

```bash
wc -l mission_brief.txt
```

It should say 20. `wc -l < mission_brief.txt` prints only the number: try it and compare.

## Step 2 — Look before you touch

```bash
ls -l inbox
```

Ten files: three photos, two logs, three temporary files, the pilot's notes and a script. Look at the
start and the end of a log, and count its lines:

```bash
head -n 8 inbox/sousse_2026-09-21.log
```

```bash
tail -n 3 inbox/sousse_2026-09-21.log
```

```bash
wc -l inbox/*.log
```

Each line is `[LEVEL] [unix_seconds.nanoseconds] [node]: message` (course, section 7). Convert the
time of the first line into a date — first in UTC, then in Tunisian time:

```bash
date -u -d @1789975800
```

```bash
TZ=Africa/Tunis date -d @1789975800
```

The flight started at 08:30 in Sousse, which is 07:30 UTC (Tunisia = UTC+1).

## Step 3 — Walk around your NAVERA copy

```bash
cd ~/navera
```

```bash
ls
```

There are about 40 names. You will use only a few in this course: `day_pkg` (day vision),
`gps_pkg`, `navera_estimator` (the arbiter), `navera_msgs` (message definitions), `navera_output`
(output to the autopilot), `deploy` (installation), `navera_tools`, `docs`. The `isaac_ros_*` folders
are libraries from NVIDIA; `build/`, `install/` and `log/` are made by the build.

Type `cd navera_m` and press `Tab`: the shell completes `navera_msgs/`. Type `m`, `Tab` again, `Enter`.

```bash
pwd
```

The answer is `/home/student/navera/navera_msgs/msg` — the same folder as `~/navera/navera_msgs/msg`.

```bash
ls -l
```

```bash
cd ~/lessons/02-terminal
```

## Step 4 — Build the mission folder and sort the inbox

```bash
mkdir -p mission/photos mission/logs mission/docs mission/bin
```

```bash
ls mission
```

Move all the photos with one wildcard. The shell expands `inbox/*.jpg` into the three names before
`mv` runs:

```bash
mv inbox/*.jpg mission/photos/
```

Now **type yourself**: move the two `.log` files into `mission/logs/`, move
`inbox/notes_for_pilot.txt` to `mission/docs/notes.txt` (move and rename in one `mv`), and move
`inbox/preflight.sh` into `mission/bin/`. Then only the `.tmp` files are left. **Look first** with
the same pattern you will delete:

```bash
ls inbox/*.tmp
```

If it lists exactly the three cache files, delete them and remove the now-empty folder:

```bash
rm inbox/*.tmp
```

```bash
rmdir inbox
```

`rmdir` refuses a folder that is not empty: if it complains, `ls inbox` shows what you forgot.

```bash
ls -R mission
```

Open a photo in the editor: [mission/photos/frame_0001.jpg](file:./mission/photos/frame_0001.jpg).

> [!TASK]
> `mission/photos`, `mission/logs`, `mission/docs`, `mission/bin` exist; the 3 photos and the 2 logs
> are **moved** (not copied) there; the notes are `mission/docs/notes.txt`; `preflight.sh` is in
> `mission/bin/`; the `.tmp` files and the `inbox` folder are gone.

## Step 5 — Permissions: make the pre-flight script executable

```bash
ls -l mission/bin/preflight.sh
```

`-rw-r--r--` (or `-rw-rw-r--`): nobody may execute it. Try:

```bash
./mission/bin/preflight.sh
```

`Permission denied`. Read the script in the editor:
[preflight.sh](file:./mission/bin/preflight.sh). Its first line is a shebang, and it uses
`${ROS_DOMAIN_ID:-NOT SET}`, `[ -e "$f" ]`, a `for` loop and `exit 0` / `exit 1` — the syntax of the
course. Without the x bit you can still run it through bash:

```bash
bash mission/bin/preflight.sh
```

Now give the owner the execute permission — **type it yourself** with `chmod` (symbolic `u+x`, or the
octal mode that gives `rwxr-xr-x`). Check with `ls -l`, then:

```bash
./mission/bin/preflight.sh
```

```bash
echo $?
```

`PRE-FLIGHT OK` and exit code `0`.

> [!TASK]
> `mission/bin/preflight.sh` is executable by its owner, unchanged, and prints `PRE-FLIGHT OK`.

## Step 6 — Copy NAVERA's GPS settings

```bash
find ~/navera -name gps_params.yaml
```

Two results: one under `install/` (a link made by the build) and the **source** in
`gps_pkg/gps_pkg/config/`. Copy the source — `cp`, not `mv`: NAVERA needs it.

```bash
cp ~/navera/gps_pkg/gps_pkg/config/gps_params.yaml mission/docs/
```

```bash
head -n 6 mission/docs/gps_params.yaml
```

The serial port `/dev/ttyTHS1` and 9600 baud: the device of the course's permissions section.

> [!TASK]
> `mission/docs/gps_params.yaml` is an exact copy, and the original is still in `~/navera`.

## Step 7 — Environment variables

```bash
echo $ROS_DOMAIN_ID
```

```bash
env | grep ^NAVERA_
```

Write the value of `ROS_DOMAIN_ID` as `E1` and the value of `NAVERA_MBTILES` as `E2` in
[answers.py](file:./answers.py).

See inheritance in action. A shell variable is **not** given to a child process; an exported one is:

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

(The single quotes stop **your** shell from replacing `$MY_SPEED_KMH`: the child shell does it.)
Now save the ROS part of your environment, sorted, into a file. **Build the pipeline yourself**:
`env`, then a `grep` that keeps only the lines that **start** with `ROS_`, then `sort`, redirected
into `ros_env.txt`. Check it:

```bash
cat ros_env.txt
```

> [!TASK]
> `E1` and `E2` are filled in, and `ros_env.txt` contains only the `ROS_…` variables, sorted
> (including `ROS_DOMAIN_ID` and `ROS_LOCALHOST_ONLY=1`).

## Step 8 — stdout and stderr

`ls` with one file that exists and one that does not prints a normal line **and** an error:

```bash
ls ~/navera/README.md ~/navera/NO_SUCH_FILE.md
```

Both reach the screen, but by two different streams. Prove it — only stdout goes into the file:

```bash
ls ~/navera/README.md ~/navera/NO_SUCH_FILE.md > ls_out.txt
```

The error still appeared. Now **write the command yourself** that sends stdout into `ls_out.txt` and
stderr into `ls_err.txt` (nothing on the screen), then look at both files with `cat`.

> [!TASK]
> `ls_out.txt` holds the normal output of that `ls` and `ls_err.txt` its error message.

## Step 9 — Processes and signals

First, the foreground. This command waits 1000 s:

```bash
sleep 1000
```

The prompt does not come back. Press **Ctrl+C**: the terminal sends SIGINT and `sleep` dies. Check
the exit code — 130 = 128 + 2 (SIGINT):

```bash
echo $?
```

Now a pretend ROS node in the **background**. Read [fake_node.sh](file:./fake_node.sh) first: it
writes its PID into `fake_node.pid` and a line into `fake_node.log` when it catches SIGINT or SIGTERM.

```bash
./fake_node.sh &
```

The shell prints `[1]` and a PID, and the prompt comes back. Find it in three ways:

```bash
jobs
```

```bash
pgrep -a -f fake_node.sh
```

```bash
cat fake_node.pid
```

```bash
ps -f
```

In `ps -f`, the PPID of `fake_node.sh` is the PID of your `bash`, and the `sleep 1` below it has
`fake_node.sh` as its parent. Now stop it **politely, by its PID** — type `kill` followed by the
number you found (for example `kill 4321`; your number is different). Do not use Ctrl+C, `kill -9`,
`pkill` or `killall`. Then read the log:

```bash
cat fake_node.log
```

You should see `received SIGTERM, shutting down cleanly`. With `kill -9` the last line would be
missing: SIGKILL cannot be caught. (If you ran it twice, stop every copy: `pgrep -a -f fake_node.sh`
must print nothing at the end.)

> [!TASK]
> `fake_node.log` shows that `fake_node.sh` started and then **received SIGTERM**, and no
> `fake_node.sh` is still running.

## Step 10 — Reading the logs with pipelines

Count the WARN lines of the Sousse flight in two ways:

```bash
grep -c WARN mission/logs/sousse_2026-09-21.log
```

```bash
grep -c "^\[WARN\]" mission/logs/sousse_2026-09-21.log
```

The numbers differ by one. Which line is counted by the first command and not by the second?
`-v` inverts a match — the second grep keeps the lines that do **not** start with `[WARN]`:

```bash
grep WARN mission/logs/sousse_2026-09-21.log | grep -v "^\[WARN\]"
```

An INFO line that only *mentions* WARN. A severity is the **first field**, so anchor your patterns.

Which nodes complained? Build the pipeline of the course step by step — run it, then press `↑` and
add the next stage each time:

```bash
grep "^\[WARN\]" mission/logs/sousse_2026-09-21.log | cut -d' ' -f3 | sort | uniq -c | sort -rn
```

When did the arbiter first lose every source? `-m 1` stops at the first match:

```bash
grep -m 1 "state NO_FIX" mission/logs/sousse_2026-09-21.log
```

Keep only the time field, then only the whole seconds (characters 2 to 11 of `[1789976724.070430279]`):

```bash
grep -m 1 "state NO_FIX" mission/logs/sousse_2026-09-21.log | cut -d' ' -f2 | cut -c2-11
```

Convert that number to Tunisian time with `TZ=Africa/Tunis date -d @NUMBER +%T` (replace NUMBER).

> [!TASK]
> In `answers.py`: **Q6** = the node with the most WARN lines in the Sousse log (just its name, without
> brackets), **Q7** = the Tunisian time of the first `state NO_FIX` in the Sousse log, as `"HH:MM:SS"`.

## Step 11 — Exploring the NAVERA code with find, grep and xargs

Answer Q1–Q5 of [answers.py](file:./answers.py). Any of the forms `"~/navera/x/y"`,
`"/home/student/navera/x/y"` or `"x/y"` is accepted for a path. Some help:

- **Q1** — `ls` shows only one level; `find` visits every sub-folder:

  ```bash
  find ~/navera/day_pkg -name "*.py" | wc -l
  ```

- **Q2** — `find ~/navera -name PositionEstimate.msg`, and keep the result outside `build/` and `install/`.
- **Q3** — the total number of lines of Python of the arbiter package. `wc -l` needs the file names
  as arguments; `xargs` builds that command from `find`'s output, and the last line is the total:

  ```bash
  find ~/navera/navera_estimator -name "*.py" | xargs wc -l
  ```

- **Q4** — `ls ~/navera/deploy/systemd/*.service` then count the lines with `wc -l`.
- **Q5** — `find ~/navera -name nmea.py`: the package is the first folder after `navera/`.

Which file decides the ROS domain on a deployed box? Search **inside** files with `grep -rn`:

```bash
grep -rn "ROS_DOMAIN_ID=42" ~/navera/deploy
```

<details><summary>Answer (not graded)</summary>
Three files contain it. <code>deploy/navera.env.example</code> is the template of <code>/etc/navera/navera.env</code>, the
settings file of a deployed box: the line <code>ROS_DOMAIN_ID=42</code> written there <b>decides</b> the domain (the systemd
units load it with <code>EnvironmentFile=</code>). <code>deploy/systemd/navera_boot_lib.sh</code> is only the safety net: it
uses 42 when the value is not a number. <code>deploy/README.md</code> is documentation.
</details>

and for the theory questions: **Q8** is the octal form of `rw-r-----` and **Q9** the name of the
signal sent by Ctrl+C (both in the course).

> [!TASK]
> Q1–Q5, Q8 and Q9 are answered in `answers.py` (saved with `Ctrl+S`).

## Step 12 — Your script: `log_report.sh`

Write `mission/bin/log_report.sh`, a script that prints a summary of **any** NAVERA log. Create the
file and open it in the editor:

```bash
touch mission/bin/log_report.sh
```

Open [mission/bin/log_report.sh](file:./mission/bin/log_report.sh). The specification:

- Usage: `./mission/bin/log_report.sh LOGFILE` (exactly one argument).
- First line `#!/bin/bash`, then `set -e`.
- Without an argument: a usage message on **stderr**, nothing on stdout, exit code 2.
  If the file does not exist: a message on stderr and exit code 1.
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

  `file` is the name without the folders (`basename`); `lines` all the lines; `INFO`, `WARN`,
  `ERROR` the lines whose **severity** (first field) is that level; `nodes` the number of
  **different** node names (field 3); `no_fix` the lines that contain `state NO_FIX`.

Make it executable, then test it — on a log, without an argument, and on a missing file:

```bash
./mission/bin/log_report.sh mission/logs/sousse_2026-09-21.log
```

```bash
./mission/bin/log_report.sh; echo "exit code: $?"
```

```bash
./mission/bin/log_report.sh /tmp/nothing.log; echo "exit code: $?"
```

Compare your WARN count with Step 10. The checker will also run your script on a **log it has never
seen**: it has no ERROR line at all, and an INFO message that contains the words WARN and ERROR.
Re-read the `set -e` rule of the course before you press Check: **every** `grep -c` in your script
needs `|| true`, also the ones inside `echo "…$(…)"`.

Finally, save one report per flight with a `for` loop. `basename "$f" .log` also removes the `.log`
ending:

```bash
for f in mission/logs/*.log; do ./mission/bin/log_report.sh "$f" > "mission/docs/report_$(basename "$f" .log).txt"; done
```

```bash
head mission/docs/report_*.txt
```

> [!TASK]
> `mission/bin/log_report.sh` has a shebang, is executable, fails correctly without an argument or
> with a missing file, and prints the exact 7-line summary for any log;
> `mission/docs/report_sousse_2026-09-21.txt` and `mission/docs/report_range_2026-09-22.txt` hold its
> output for the two flights.

## Step 13 — The flight report

Write `mission/docs/flight_report.md` for the test team (create it with `touch`, edit it in the
editor). It must have three sections with these headings:

- `## Sousse` — the numbers of the flight from your report (lines, WARN, ERROR, **number of NO_FIX
  events**), the **Tunisian time of the first NO_FIX** (`HH:MM:SS`), and in one or two sentences what
  happened (look at the WARN messages around it: where was the drone, why did vision fail?).
- `## Range` — the same numbers (**NO_FIX** and **ERROR** counts), and what the arbiter did with the
  GPS jump (`grep -n "jump" mission/logs/range_2026-09-22.log`).
- `## Conclusion` — at least 40 words: what the two flights show about day vision as a backup of GPS,
  and one recommendation for the next test.

> [!TASK]
> `mission/docs/flight_report.md` has the three sections; each flight section gives its NO_FIX and
> ERROR counts, the Sousse section the Tunisian time of the first NO_FIX, and the conclusion has at least 40 words.

## Step 14 — Check your work

Press **✔ Check my work**. Each red line names what is missing and gives a hint.

> [!NOTE]
> Made a mess? **↺ Reset lab files** puts this lesson's files back as at the start (your current
> files are kept in a backup). It never touches `~/navera`.

## Going further (optional)

- **awk**, the next tool after `cut`: `awk '{print $3}' mission/logs/*.log | sort | uniq -c` does the
  node count without `cut`, and `awk '$1=="[ERROR]"' mission/logs/*.log` prints the ERROR lines. Add a
  line `first_no_fix: HH:MM:SS` (Tunisian time, or `-` when there is none) to a copy of your script.
- **Durations.** With the Unix times of the `state DEGRADED` and the next `state FIX` lines, compute
  how long each GPS loss lasted, with shell arithmetic: `echo $(( 1789976223 - 1789976103 ))`.
- **History.** `history | tail -n 20` lists your last commands. (In a brand-new terminal the history
  can be empty: it is saved when a shell exits.) Turn the commands of Steps 4–6 into a script
  `mission/bin/tidy.sh` that does the whole tidy-up on a fresh copy of the inbox.
- **Disk usage.** `du -sh ~/navera/*_pkg | sort -h` — which package is the biggest, and why?

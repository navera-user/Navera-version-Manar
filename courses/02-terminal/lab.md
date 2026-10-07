# Lab 2 — Ground engineer for a day

**Goal:** tidy the files of two test flights, then explore the NAVERA code to answer six questions —
using only the terminal.
**Time:** about 50 minutes.

Click the **⌨️ Terminal** tab. Every command below has a **▶ Run** button, but try to **type** most
of them yourself: your fingers learn faster than your eyes. Use `Tab` to complete names.

## Step 1 — Where am I?

```bash
pwd
```

You should see `/home/student/lessons/02-terminal`: the terminal starts in the folder of the lesson.
Now list what is here:

```bash
ls
```

You see `answers.py`, `inbox` (in another colour: it is a folder) and `mission_brief.txt`.
Look at the details and at the hidden files:

```bash
ls -la
```

The first column starts with `d` for folders and `-` for files. `.` and `..` are "here" and "the
folder above", which every folder contains.

## Step 2 — Read the mission brief

```bash
cat mission_brief.txt
```

That is your job for today. Now try the "pieces of a file" commands:

```bash
head -n 5 mission_brief.txt
```

```bash
tail -n 3 mission_brief.txt
```

```bash
wc -l mission_brief.txt
```

`wc -l` should say `20`. Now look into the inbox — without going there:

```bash
ls -l inbox
```

Nine files in a mess: photos (`.jpg`), flight logs (`.log`), notes (`.txt`) and temporary files
(`.tmp`). Read the end of a log:

```bash
tail -n 5 inbox/flight_0930.log
```

## Step 3 — Walk around your NAVERA copy

Go into NAVERA and look:

```bash
cd ~/navera
```

```bash
ls
```

The prompt changed to `~/navera`. Go down into a package, then climb back up:

```bash
cd day_pkg
```

```bash
ls
```

```bash
cd ..
```

```bash
pwd
```

You are back in `/home/student/navera`. Now practise **Tab completion**: type `cd navera_m` then
press `Tab` — the shell completes `navera_msgs/`. Type `ms`, `Tab` again → `navera_msgs/msg/`.
Press `Enter`, then:

```bash
ls
```

You see the three message files of NAVERA. Now go home, and come back to the lesson:

```bash
cd
```

```bash
cd ~/lessons/02-terminal
```

> [!TIP]
> Lost? `cd ~/lessons/02-terminal` always brings you back to the lab folder, from anywhere.

## Step 4 — Build the mission folder

Create three folders in one command. `-p` creates `mission` too, because it does not exist yet:

```bash
mkdir -p mission/photos mission/logs mission/docs
```

Nothing is printed: it worked. Check:

```bash
ls mission
```

> [!TASK]
> The folders `mission/photos`, `mission/logs` and `mission/docs` exist inside `~/lessons/02-terminal`.

## Step 5 — Sort the inbox with wildcards

Move all the photos at once. The shell replaces `inbox/*.jpg` by the three photo names:

```bash
mv inbox/*.jpg mission/photos/
```

Your turn: move the two `.log` files into `mission/logs/` with the same trick (type it yourself;
the answer is under the line if you are stuck).

<details><summary>Show the command</summary>

<code>mv inbox/*.log mission/logs/</code>
</details>

Now move the pilot's notes **and rename them** `notes.txt` in one go:

```bash
mv inbox/notes_for_pilot.txt mission/docs/notes.txt
```

Only the temporary files are left. Before deleting, **always look first** with the same pattern:

```bash
ls inbox/*.tmp
```

Exactly the three `cache_0…tmp` files, nothing else? Then delete them:

```bash
rm inbox/*.tmp
```

The inbox is now empty, so `rmdir` can remove it (it would refuse if a file were left):

```bash
rmdir inbox
```

Admire your work — `ls -R` lists a folder and all its sub-folders (`-R` = recursive):

```bash
ls -R mission
```

Open a photo in the editor: [mission/photos/frame_0001.jpg](file:./mission/photos/frame_0001.jpg)
(the editor shows images). It is a real aerial photo taken from a drone. And read the notes with the
terminal:

```bash
cat mission/docs/notes.txt
```

> [!TASK]
> The 3 photos are in `mission/photos/`, the 2 logs in `mission/logs/`, the notes are
> `mission/docs/notes.txt`, the `.tmp` files are deleted and the `inbox` folder is gone.

## Step 6 — Copy NAVERA's GPS settings

The GPS settings of NAVERA are in a file called `gps_params.yaml`. Where? Ask `find`:

```bash
find ~/navera -name gps_params.yaml
```

You get two answers. One is inside `install/` — a copy made by the build. The other one, in
`gps_pkg/gps_pkg/config/`, is the **source** file. **Copy** it (do not move it! NAVERA needs it):

```bash
cp ~/navera/gps_pkg/gps_pkg/config/gps_params.yaml mission/docs/
```

```bash
head -n 8 mission/docs/gps_params.yaml
```

You can read which serial port and which speed (baud rate) the GPS receiver uses — lesson 15 is
all about it.

> [!TASK]
> `mission/docs/gps_params.yaml` is an exact copy of NAVERA's GPS settings file, and the original is
> still in `~/navera`.

## Step 7 — Stop a command, and look back

Some commands run for a long time. This one waits 1000 seconds:

```bash
sleep 1000
```

The prompt does not come back. Click in the terminal and press **`Ctrl+C`**: `^C` appears and the
prompt is back. That is how you stop anything that runs too long or that you started by mistake.

Now press the **`↑`** key a few times: your previous commands come back. Press `Ctrl+C` to drop the
line without running it. Then show your last 10 commands:

```bash
history | tail -n 10
```

## Step 8 — Explorer: answer the questions

Open [answers.py](file:./answers.py). For each question, find the answer **with the terminal**,
then write it in the file. Numbers without quotes (`Q1 = 12`), paths and names in quotes
(`Q2 = "gps_pkg/README.md"`). Paths start at the package folder, not with `~/navera/`.

Some help for each question:

- **Q1** — `ls ~/navera/day_pkg/day_pkg/*.py` shows only one folder. `find` searches every
  sub-folder; pipe it into `wc -l` to count the lines:
  ```bash
  find ~/navera/day_pkg -name "*.py"
  ```
  …now run it again with `| wc -l` at the end (press `↑` to get it back, then add the end).
- **Q2** — use `find ~/navera -name …` with the file name. Ignore the result in `install/`.
- **Q3** — `wc -l` followed by the path you found.
- **Q4** — the word is *inside* a file, so it is a job for `grep -rl`:
  ```bash
  grep -rl PositionEstimate ~/navera/day_pkg
  ```
  Then try `grep -rn PositionEstimate ~/navera/day_pkg | head -n 5` to see the lines themselves.
- **Q5** — `find` again, with the name `nmea.py`.
- **Q6** — combine three commands with two pipes: print both logs of `mission/logs`, keep the lines
  containing `GPS LOST`, count them. (Look at the pipe picture in the course tab.)

> [!TASK]
> Write the six answers in `answers.py` and save with `Ctrl+S`.

## Step 9 — Save results into files with `>`

Send the list of NAVERA's folders into a file instead of the screen:

```bash
ls ~/navera > packages.txt
```

Nothing is printed: the output went into `packages.txt`. Look at it:

```bash
head -n 5 packages.txt
```

Now the same with `grep`: keep the lines that list NAVERA's **sources** in the message definition,
and save them:

```bash
grep SOURCE_ ~/navera/navera_msgs/msg/PositionEstimate.msg > sources.txt
```

```bash
cat sources.txt
```

You see the list of every position source NAVERA knows: GPS, day vision, night vision,
celestial… This is how the code says "this position came from the camera".

Finally, `>>` **adds** at the end of a file without erasing it. Add a line to the pilot's notes:

```bash
echo "Checked by the ground engineer." >> mission/docs/notes.txt
```

```bash
tail -n 2 mission/docs/notes.txt
```

> [!TASK]
> `packages.txt` contains the output of `ls ~/navera`, and `sources.txt` contains the `SOURCE_`
> lines of `PositionEstimate.msg`.

## Step 10 — Check your work

Press **✔ Check my work**. Each red line tells you what is missing, with a hint.

> [!NOTE]
> Made a mess of the inbox? **↺ Reset lab files** puts the lesson's files back as they were at the
> start (your current files are kept in a backup).

## Going further (optional)

- How many Markdown documents (`.md`) does NAVERA have, **not** counting `build/` and `install/`?
  Tip: `find ~/navera -name "*.md" | grep -v install | grep -v build | wc -l` (`grep -v` keeps the
  lines that do **not** match).
- Day vision only searches the map inside a circle around the last known position. Find the
  biggest radius it allows: `grep -n "R_MAX_M" ~/navera/day_pkg/day_pkg/nodes/day_subscriber.py`
  (you will meet this 600 m circle again in lesson 3).
- Which packages are the biggest? `du -sh ~/navera/*_pkg` prints the size of each one (`du` = disk
  usage, `-s` = one total per folder, `-h` = human units like K and M).

# The terminal: your robot's control room

A NAVERA box is bolted inside a drone, on a field outside Sousse. It has **no screen, no mouse and
no keyboard**. The test flight is over and the engineer wants to know: *did the GPS drop out? Did
day vision take over? Where are the camera photos?* She plugs her laptop into the box, opens a
window full of text… and types. In ten seconds she has her answers.

That window is the **terminal**. Every robot engineer lives in it, because a robot's computer is
almost never in front of you: it is in a drone, in a boat, on a rover, or in a data centre. Typing
commands is the one way of working that is the same everywhere. In this lesson you learn the
twenty commands that do 95 % of the job.

## What is the terminal?

The **terminal** is a window where you type **commands** instead of clicking. The program that reads
what you type and runs it is called the **shell** (ours is called `bash`). When it is ready, the
shell shows a **prompt**:

```
student@navera:~/lessons/02-terminal$
```

| Part | Meaning |
|---|---|
| `student` | who you are (your user name) |
| `navera` | the name of the computer |
| `~/lessons/02-terminal` | the folder you are in right now |
| `$` | "I'm ready, type a command" |

A command is a line of words separated by spaces:

```
ls  -l  ~/navera
│    │    └── argument: WHAT to work on (here, a folder)
│    └─────── option:   HOW to do it (here, "long" format) — starts with -
└──────────── command:  WHAT to do (here, "list")
```

You type the line, press `Enter`, the shell runs it, prints the result, and shows a new prompt.
If nothing is printed, that usually means **it worked**: Linux commands are quiet when all is well.

> [!TIP]
> Spaces matter. `ls -l` works, `ls-l` does not ("command not found"). Upper and lower case matter
> too: `Ls` is not `ls`, and `Notes.txt` is not `notes.txt`.

## Where am I? Folders and paths

Your files are organised like a tree of folders inside folders. The very top is called the
**root** and is written `/`. Your own space is your **home folder**, `/home/student`, which has a
short name: `~` (the *tilde*).

![The tree of folders: from the root / down to your lesson folder](assets/tree.svg)

A **path** is the list of folders to cross to reach a file, separated by `/`.
For example `/home/student/navera/navera_msgs/msg/PositionEstimate.msg`.

Three commands are your compass:

| Command | Means | Example |
|---|---|---|
| `pwd` | **p**rint **w**orking **d**irectory: where am I? | `/home/student/lessons/02-terminal` |
| `ls` | **l**i**s**t what is here | `answers.py  inbox  mission_brief.txt` |
| `cd` | **c**hange **d**irectory: go somewhere | `cd ~/navera` |

### Absolute and relative paths

- An **absolute path** starts with `/` (or `~`): it works from anywhere, like a full postal address.
  `cd /home/student/navera` always goes to the same place.
- A **relative path** starts from where you are, like "the second door on the left".
  If you are in `~/navera`, then `cd day_pkg` goes to `~/navera/day_pkg`.

Some special names:

| Name | Means |
|---|---|
| `~` | your home folder, `/home/student` |
| `.` | "here", the current folder |
| `..` | the folder **above** (the parent) |
| `cd` alone | go home |
| `cd -` | go back to the folder you were in before |

So `cd ..` climbs one level, and `cd ../..` climbs two.

### Useful options of `ls`

| Command | Shows |
|---|---|
| `ls` | the names |
| `ls -l` | one per line, with size, date and permissions (a `d` at the start = a folder) |
| `ls -a` | also the **hidden** files, whose names start with a dot (`.bashrc`, `.git`) |
| `ls -la` (or `ll`) | both |
| `ls ~/navera/day_pkg` | the contents of another folder, without going there |

## Looking inside files

| Command | What it does |
|---|---|
| `cat file` | prints the **whole** file (great for short files) |
| `head file` | the first 10 lines; `head -n 3 file` the first 3 |
| `tail file` | the last 10 lines; `tail -n 3 file` the last 3 |
| `wc -l file` | counts the lines (**w**ord **c**ount, `-l` = lines) |

A long file printed with `cat` scrolls off the screen in a flash. Engineers use `head` and `tail`
instead — for example `tail -n 20` on a log shows **what happened last**, which is usually what you
want after a problem.

> [!NOTE]
> There is also `less file`, a viewer that lets you scroll with the arrow keys. It takes over the
> terminal until you press `q` to quit. If you ever feel "stuck" in a screen like that, press `q`.
> In this course `head`, `tail` and the **📝 Code** editor are all you need.

## Making, copying, moving and deleting

| Command | What it does |
|---|---|
| `mkdir photos` | **m**a**k**e a **dir**ectory (folder) |
| `mkdir -p mission/photos` | make it **and** its parents if they don't exist yet |
| `cp a.txt b.txt` | **c**o**p**y a file (you now have two) |
| `cp a.txt docs/` | copy into a folder (same name) |
| `cp -r folder/ backup/` | copy a whole folder (`-r` = recursive: everything inside) |
| `mv a.txt docs/` | **m**o**v**e a file into a folder (you still have one) |
| `mv old.txt new.txt` | rename (a rename is just a move in the same folder) |
| `mv inbox/old.txt docs/new.txt` | move **and** rename in one go |
| `rm file` | **r**e**m**ove (delete) a file |
| `rmdir folder` | remove an **empty** folder |
| `rm -r folder` | remove a folder and everything in it |

> [!WARNING]
> **The terminal has no recycle bin.** `rm` deletes for good, straight away, without asking.
> Two habits keep you safe:
> 1. Before `rm something`, run `ls something` with **exactly the same words** and read what it lists.
> 2. Prefer `rmdir` for folders: it refuses to delete a folder that is not empty.
>
> (Your NAVERA copy can be rebuilt with the Reset button, and lesson 5 shows how git protects you —
> but on a real box, a deleted map is gone.)

## Wildcards: one name for many files

A **wildcard** is a special character that matches many names. The shell replaces the pattern by
every name that fits, **before** running the command.

| Pattern | Matches | Example in your inbox |
|---|---|---|
| `*` | any characters (even none) | `*.jpg` → all the photos |
| `?` | exactly one character | `cache_0?.tmp` → `cache_01.tmp`, `cache_02.tmp`, `cache_03.tmp` |
| `[12]` | one of the characters listed | `frame_000[12].jpg` → frames 1 and 2 |

So `mv inbox/*.jpg mission/photos/` is really `mv inbox/frame_0001.jpg inbox/frame_0002.jpg
inbox/frame_0003.jpg mission/photos/` — the shell typed the long version for you.
That is also why the "`ls` first, then `rm`" habit works so well: `ls inbox/*.tmp` shows exactly
the files that `rm inbox/*.tmp` would delete.

## Typing less: the four keys of a pro

| Key | What it does |
|---|---|
| `Tab` | **completes** the name you are typing. Type `cd ~/nav` then `Tab` → `cd ~/navera/`. If nothing happens, press `Tab` twice: the shell shows all the possibilities. |
| `↑` / `↓` | brings back your previous commands, to run them again or fix a typo |
| `Ctrl+C` | **stops** the command that is running (a program that never ends, a mistake…) |
| `Ctrl+L` | clears the screen (same as the command `clear`) |

`history` prints the list of everything you typed, with a number in front of each line.

Tab completion is not just lazy: it **prevents mistakes**. If `Tab` does not complete a name, the
name is wrong or the file is not where you think — you know it before running anything.

> [!TIP]
> Because `Ctrl+C` means "stop" in a terminal, copy and paste are different there. In most
> terminals, select the text with the mouse and use **right-click → Copy / Paste**, or
> `Ctrl+Shift+C` / `Ctrl+Shift+V`. The **▶ Run** buttons in the lessons do the typing for you.

## Searching: `find` for names, `grep` for contents

NAVERA has hundreds of files. Nobody remembers where everything is — engineers **search**.

**`find`** looks for files by their **name**, in a folder and all its sub-folders:

```
find ~/navera -name "gps_params.yaml"         a file with exactly this name
find ~/navera/day_pkg -name "*.py"            every Python file in day_pkg
find ~/navera -type d -name "test"            only folders (-type d) called test
```

Put the pattern in quotes (`"*.py"`): then `find` receives the star itself and searches every
sub-folder, instead of the shell replacing it right away with the names of the current folder.

**`grep`** looks **inside** files for a line containing a word:

```
grep "GPS LOST" flight.log                    the lines of flight.log that contain GPS LOST
grep -n "winner" flight.log                   -n: with the line numbers
grep -i "gps" flight.log                      -i: ignore upper/lower case
grep -c "GPS LOST" flight.log                 -c: only the number of matching lines
grep -r "haversine_m" ~/navera/navera_common  -r: in every file of every sub-folder
grep -rl "PositionEstimate" ~/navera/day_pkg  -l: only the names of the files that match
```

| You know… | Use |
|---|---|
| the file's **name** (or part of it) | `find` |
| a **word** that is written in the file | `grep` |

A typical engineer's question: "*which files use the message `PositionEstimate`?*" — that is a word
inside files, so: `grep -rl PositionEstimate ~/navera/day_pkg`. And "*where is
`PositionEstimate.msg`?*" — that is a name, so: `find ~/navera -name "PositionEstimate.msg"`.

## Pipes and redirection: plugging commands together

Every command prints its result on the screen — that is its **output**. Two symbols let you send
that output somewhere else.

**The pipe `|`** sends the output of one command **into** the next one, like a water pipe between
two machines. Each command does one small job; together they answer a real question.

![A pipe: cat → grep → wc, only the final number reaches the screen](assets/pipe.svg)

```
cat mission/logs/*.log | grep "match OK" | wc -l
```

reads: "print every line of the logs, keep only those with *match OK*, count them".
More examples:

```
ls ~/navera | wc -l                           how many names in ~/navera?
find ~/navera/day_pkg -name "*.py" | wc -l    how many Python files in day_pkg?
history | tail -n 5                           your last 5 commands
grep -r "import" ~/navera/gps_pkg | head -n 3 only the first 3 results
```

**Redirection `>`** sends the output **into a file** instead of the screen:

```
ls ~/navera > packages.txt         creates packages.txt (or REPLACES it!) with the list
echo "flight checked" >> notes.txt ADDS a line at the end of notes.txt
```

| Symbol | Means |
|---|---|
| `a \| b` | the output of `a` becomes the input of `b` |
| `a > file` | write the output of `a` into `file` — **erases** what was in it |
| `a >> file` | **add** the output of `a` at the end of `file` |

`echo` simply prints its words: `echo hello` prints `hello`. With `>>` it is the quickest way to
add a line to a file.

> [!WARNING]
> `>` empties the file **first**. `grep word notes.txt > notes.txt` destroys `notes.txt` before grep
> even reads it. Always write into a **new** file name.

## 🐦 How birds do it

A NAVERA box has no screen. Neither does the tiny backpack that scientists fit on a bird.

To study migration, ornithologists (bird scientists) put small **tracking tags** on birds. Some tags,
used on large birds like **white storks**, contain a GPS receiver and a mobile-phone chip: from time
to time they send the bird's latest positions through the phone network. The scientist reads them on
a computer far away, without ever touching the bird again. It is the same situation as the engineer
in the field: the machine is somewhere you cannot click, so you talk to it in **text**.

What arrives is text, too — thousands of lines, one per position. A line might look like
`2025-09-14 07:30:00,36.85,10.32,stork_17`: date, time, latitude, longitude, bird. Big public
databases such as Movebank hold millions of such lines, for thousands of animals. And the first tools
a scientist reaches for are the ones of this lesson: `grep stork_17 tracks.csv` keeps one bird,
`| wc -l` counts its positions, `> stork_17.csv` saves them in a new file.

Navi likes the storks' story because of Tunisia. Storks are **soaring** birds: they glide on rising
warm air, called *thermals*, to save energy. Thermals form over land, not over cold sea, so storks
avoid long sea crossings and squeeze through narrow places such as the Strait of Gibraltar. Plot their
lines of text on a map and you see that funnel appear.

NAVERA's flight logs are no different: lines of text that you search, cut, count and save from the
terminal.

## In NAVERA

The real NAVERA box is installed and started from the terminal: the installer
`deploy/install.sh`, the pre-flight check `navera_tools/check_box.py`, the simulator
`navera_tools/run_sim.sh` and the test suite `navera_tools/run_tests.sh` are all commands you
type. Open [run_tests.sh](file:navera/navera_tools/run_tests.sh) and look near the top: the very
tools of this lesson, chained with pipes, are how NAVERA finds its own tests.

```text
mapfile -t UNIT < <(find . -path ./build -prune -o -path ./install -prune -o \
    -path '*/test/test_*.py' -print \
  | grep -vE 'test_(flake8|pep257|copyright)\.py$' \
  | while read -r f; do
      pkg=$(echo "$f" | cut -d/ -f2)
      [ -e "$pkg/COLCON_IGNORE" ] || echo "$f"
    done | sort)
```

You don't need to understand every symbol yet, but you can already read the idea:

1. `find .` lists every file whose path looks like `*/test/test_*.py` (it skips `build` and
   `install`, the copies made by the build — exactly like you will in the lab);
2. `| grep -v …` **removes** (`-v` = invert) the style-checking tests;
3. `| while read … echo` keeps only files of packages that are not switched off;
4. `| sort` puts the list in alphabetical order.

The same goes for the box's logs, its map files and its settings: on a real vehicle, the terminal
is how you inspect and fix NAVERA.

> [!NOTE]
> Your copy has two folders that the code does not live in: `build/` and `install/`. They are made
> by the build tool (`colcon`, lesson 9) and contain **copies and links** of the source files.
> When you search, the file you want to read or change is almost always the one **outside** them.

## Words of this lesson

| Word | Meaning |
|---|---|
| **terminal** | the window where you type commands |
| **shell** | the program that runs your commands (`bash`) |
| **prompt** | the text before the cursor; it shows who and where you are |
| **command / option / argument** | what to do / how (`-l`) / on what (`~/navera`) |
| **folder (directory)** | a container of files and other folders |
| **path** | the folders to cross to reach a file, separated by `/` |
| **absolute / relative path** | from the root `/` (or `~`) / from where you are |
| **home (`~`)** | your own folder, `/home/student` |
| **wildcard** | `*`, `?`: a pattern that matches many names |
| **output** | what a command prints |
| **pipe (`\|`)** | sends one command's output into the next command |
| **redirection (`>`, `>>`)** | sends a command's output into a file (replace / add) |

## Check what you learned

<details><summary>1. You are in <code>~/navera/day_pkg/day_pkg</code>. Where does <code>cd ../..</code> take you?</summary>
Two levels up: <code>~/navera</code>. (<code>..</code> → <code>~/navera/day_pkg</code>, then <code>..</code> again → <code>~/navera</code>.)
</details>

<details><summary>2. What is the difference between <code>cp a.txt docs/</code> and <code>mv a.txt docs/</code>?</summary>
After <code>cp</code> you have two files (the original and the copy in docs/). After <code>mv</code> you have only
one, now in docs/.
</details>

<details><summary>3. You want every Python file that contains the word <code>haversine_m</code>. find or grep?</summary>
<code>grep</code>, because the word is <i>inside</i> the files: <code>grep -rl haversine_m ~/navera --include="*.py"</code>.
<code>find</code> only looks at names.
</details>

<details><summary>4. What does <code>ls ~/navera | wc -l</code> print?</summary>
One number: how many names <code>ls</code> listed in <code>~/navera</code>. The list itself never reaches the screen:
it goes through the pipe into <code>wc -l</code>, which counts its lines.
</details>

<details><summary>5. Why is <code>sort notes.txt > notes.txt</code> a bad idea?</summary>
<code>></code> empties notes.txt before <code>sort</code> reads it: you end up with an empty file. Write into a new
name: <code>sort notes.txt > sorted.txt</code>.
</details>

Now open the **🛠️ Lab** tab.

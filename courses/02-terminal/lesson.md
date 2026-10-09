# Linux and the shell for robotics

> [!NOTE] In short
> - A NAVERA box has no screen, so engineers control it and read its logs with text commands in a
>   **terminal**.
> - You learn the file system, permissions, processes and signals, and environment variables.
> - You learn **pipes** (`|`), text tools such as `grep`, and short **bash** scripts.
> - In the lab you study two synthetic NAVERA flight logs (Sousse and an inland test range) and write a
>   script that summarises any NAVERA log.
> - NAVERA's own test script uses the same pipes, and the same signals: SIGTERM first, then
>   SIGKILL.

A survey drone lands on a beach north of Sousse port after a training flight. Inside it, a NAVERA box:
no screen, no keyboard, no mouse. The test engineer has three questions. *Did the GPS drop out? Did
the arbiter switch to day vision, and for how long? Did any node report an error?* She connects her
laptop to the box over the network, opens a **terminal**, and types four short commands joined by
`|`. Twenty seconds later she has the answers, with exact times.

Every robot computer works like this. The computer is inside a drone, a boat or a rover, or in a
server room. It runs **Linux**, and engineers talk to it in text. This lesson gives you the working
knowledge of Linux that a robotics engineer uses every day: the file system, permissions, processes
and signals, environment variables, streams and pipes, the text tools, and small **bash** scripts.
In the lab you will use them on two (synthetic) NAVERA flight logs from Sousse and an inland test
range, and you will write a log-report script that works on any NAVERA log.

> [!NOTE]
> You do not have to memorise every option. Professionals look things up all the time:
> `man grep` opens the manual of `grep` (quit with `q`), and `grep --help` prints a short summary.

## 1. The shell and the anatomy of a command

The **terminal** is the window. The **shell** is the program inside it that reads your line, runs it
and shows the result. Ours is **bash**. When it waits for you, it shows a **prompt**:

```
student@navera:~/lessons/02-terminal$
```

This means: user `student`, on the computer (host) `navera`, in the folder `~/lessons/02-terminal`,
and `$` = "ready". A command line is a list of words separated by spaces:

```
grep  -c  "state NO_FIX"  mission/logs/sousse_2026-09-21.log
│     │   │               └── argument 2: a file
│     │   └── argument 1: the pattern (quotes keep the two words together)
│     └── option: "count the matching lines" (options start with -)
└── the command (a program on the disk: /usr/bin/grep)
```

Spaces separate words, so a file name with a space must be quoted (`"my file.txt"`). Case matters:
`Notes.txt` and `notes.txt` are two different files. A command that succeeds usually prints
**nothing**: in Linux, silence means success.

## 2. The file system

Linux has **one tree** of folders (also called **directories**). Its top is the **root**, written
`/`. Disks, USB sticks and even devices appear somewhere inside this tree.

![The Linux tree, from / down to your lesson folder](assets/tree.svg)

| Folder | What it holds |
|---|---|
| `/etc` | system settings (text files). A NAVERA box keeps its site settings in `/etc/navera/navera.env` |
| `/dev` | **devices as files**: `/dev/ttyTHS1` is the Jetson serial port of the GPS receiver, `/dev/video0` a camera |
| `/proc` | live information about running programs: `/proc/<PID>/` for each process |
| `/tmp` | temporary files, deleted at reboot |
| `/usr/bin` | the programs themselves (`ls`, `grep`, `python3`…) |
| `/home/student` | **your home folder**, written `~` for short |
| `/data` | read-only course data in this academy (the satellite map, datasets) |

A **path** names a file by the folders to cross: `/home/student/navera/navera_msgs/msg/PositionEstimate.msg`.

- An **absolute path** starts at the root `/`. It means the same thing from anywhere.
- A **relative path** starts from the **current folder** (the **working directory**). If you are in
  `/home/student/navera`, the relative path `navera_msgs/msg` means `/home/student/navera/navera_msgs/msg`.
- `~` is replaced by the shell with `/home/student`. So **`~/navera/day_pkg` and
  `/home/student/navera/day_pkg` are exactly the same folder**. Commands like `find` print the long
  form; you may type the short one.
- `.` is the current folder and `..` its parent. `cd ..` climbs one level, `cd -` goes back to the
  previous folder, `cd` alone goes home.

| Command | Does |
|---|---|
| `pwd` | print the working directory |
| `ls`, `ls -l`, `ls -la` | list; long format; include hidden files (names starting with `.`) |
| `cd path` | change directory |
| `cat`, `head -n 5`, `tail -n 5`, `wc -l` | show a file; its first / last 5 lines; count its lines |
| `less file` | scroll a long file (`q` quits) |
| `mkdir -p a/b` | make folders, with parents |
| `cp a b`, `cp -r dir1 dir2` | copy a file; copy a folder and everything in it (**recursive**) |
| `mv a b` | move or rename |
| `rm file`, `rmdir dir` | delete a file; delete an **empty** folder |

> [!WARNING]
> `rm` has no recycle bin. Before `rm pattern`, run `ls pattern` with exactly the same pattern and
> read the list. In lesson 5 you will see how git can bring back a committed file — but on a real
> box, a deleted map or log is gone.

### Wildcards (globbing)

`*` (any characters), `?` (exactly one character) and `[12]` (one of the listed characters) are
**wildcards**. The **shell** replaces the pattern with the matching names **before** the command
runs: `mv inbox/*.log mission/logs/` becomes `mv inbox/range_2026-09-22.log
inbox/sousse_2026-09-21.log mission/logs/`. The command itself never sees the `*`. This is also why
you write `find . -name "*.py"` **with quotes**: you want `find` to receive the `*` and apply it in
every sub-folder, not the shell to expand it in the current folder only.

## 3. Users, groups and permissions

Linux is multi-user. Every file has an **owner** (a user), a **group**, and three sets of
**permissions**: for the owner (**u**), for the members of the group (**g**), and for all others
(**o**). Each set has three bits: **r** read, **w** write, **x** execute (for a folder, x means
"may enter it").

```
-rwxr-x---  1  student  dialout  1203  Oct  7 10:39  preflight.sh
│└┬┘└┬┘└┬┘     │        │
│ u  g  o      owner    group
└ type: - file, d directory, l link, c character device
```

Each set is also written as one **octal** digit: r = 4, w = 2, x = 1, added together.

| Symbols | Sum | Octal | Typical use |
|---|---|---|---|
| `rwx r-x r-x` | 4+2+1, 4+0+1, 4+0+1 | **755** | a program or script everyone may run |
| `rw- r-- r--` | 6, 4, 4 | **644** | a normal text file |
| `rw- rw- ---` | 6, 6, 0 | **660** | a device shared by one group, e.g. a serial port |
| `rwx --- ---` | 7, 0, 0 | **700** | private to the owner |

**Worked example.** `rw-r-----` → owner `rw-` = 4+2+0 = 6, group `r--` = 4, others `---` = 0 →
**640**. Conversely `chmod 750 file` gives `rwxr-x---`.

`chmod` changes permissions, symbolically (`chmod u+x file`, `chmod go-w file`) or in octal
(`chmod 755 file`). Only the owner (or the administrator, **root**) may do it.

> [!NOTE]
> In this academy, `ls -l` may show a group name other than `student` in the group column. It is
> only the name of a group on the host computer that runs the sandboxes.
> It changes nothing for you: ignore it.

### Why robots care: devices and the execute bit

On the Jetson, the GPS serial port `/dev/ttyTHS1` is owned by `root`, group `dialout`, mode `0660`.
A program can read the GPS only if its user is in the group `dialout`. That is why NAVERA's GPS
service declares `SupplementaryGroups=dialout` (see "In NAVERA"). "Permission denied" on a device
almost always means a missing group, never a broken sensor.

A text file becomes a runnable program in two steps:

1. Its first line is a **shebang**, `#!/bin/bash`: it tells Linux which interpreter must read the file.
2. It has the **x** bit: `chmod +x script.sh`. Then `./script.sh` runs it. (`./` is needed because
   the current folder is not in the `PATH`, see section 5.) Without the x bit you get
   `Permission denied`; `bash script.sh` still works, because then `bash` is the program and the
   script is only a file it reads.

## 4. Processes and signals

A running program is a **process**. Each one has a number, the **PID** (process ID), and a parent
(the process that started it, often your shell).

| Command | Does |
|---|---|
| `ps -f` | the processes of this terminal, with PID and parent PID (PPID) |
| `ps -ef` | all processes of the machine |
| `pgrep -a -f fake_node` | **search**: PID and full command line of the processes whose command contains `fake_node` |
| `top` | live table of processes by CPU use (`q` quits) |
| `cmd &` | start `cmd` in the **background**: the prompt comes back at once; the shell prints `[1] 4321` (job number, PID) |
| `jobs`, `fg %1` | list this shell's background jobs; bring job 1 back to the foreground |
| `echo $!` | the PID of the last background process |

A **signal** is a short message from the system to a process. A program can **catch** most signals
and react (for example, close its files cleanly), except `SIGKILL`.

| Signal | Number | Sent by | Effect |
|---|---|---|---|
| `SIGINT` | 2 | **Ctrl+C**, to the foreground program | "interrupt" — ROS 2 nodes catch it and shut down cleanly |
| `SIGTERM` | 15 | `kill PID` (the default) | "please terminate" — the polite way; systemd uses it to stop a service |
| `SIGKILL` | 9 | `kill -9 PID` | immediate death; **cannot be caught**: no clean-up, files may stay half-written |

Good practice is a **ladder**: Ctrl+C (or `kill PID`), wait a few seconds, and only then `kill -9 PID`.
NAVERA's own test runner does exactly this (see "In NAVERA").

> [!WARNING]
> **Kill exact PIDs, never by name pattern.** `pkill python3` or `killall ros2` stop *every*
> matching process you are allowed to stop — on a shared robot or a shared lab computer, that can be
> a colleague's node or the simulator of the whole class. First **find** the PID (`pgrep -a -f …`,
> `ps -ef`), read the full command line, then `kill <that PID>`.

When a process ends, it returns an **exit code**: `0` = success, anything else = failure. The shell
keeps the code of the last command in `$?`:

```
$ grep -q "state NO_FIX" mission/logs/sousse_2026-09-21.log ; echo $?
0
```

`-q` makes grep quiet: only its exit code answers ("found" = 0, "not found" = 1, error = 2). A process
stopped by a signal returns 128 + the signal number: 130 after Ctrl+C, 143 after `SIGTERM`,
137 after `SIGKILL`.

## 5. Environment variables

Every process carries a small dictionary of **environment variables**: names with text values. A
child process receives a **copy** of its parent's environment. This is how settings reach programs
without changing their code.

| Command | Does |
|---|---|
| `env` | print all environment variables |
| `echo $ROS_DOMAIN_ID` | print one value (the shell replaces `$NAME` by its value) |
| `MY_VAR=12` | a **shell variable**: only this shell sees it |
| `export MY_VAR=12` | also give it to every program started **from now on** in this shell |
| `NAME=value cmd` | set it for that one command only |
| `echo ${MY_VAR:-none}` | the value, or `none` if it is unset or empty |

Because a child gets a copy, a program can never change the environment of the shell that started
it. And a value you `export` in one terminal does not exist in another terminal.

**`PATH`** is the list of folders where the shell looks for commands, separated by `:`.
`which grep` shows which file runs when you type `grep`.

### ROS 2 uses the environment

ROS 2 programs (nodes) find each other with a discovery protocol (DDS). Two variables decide who can
see whom:

- **`ROS_DOMAIN_ID`** (an integer): nodes only talk to nodes with the **same** domain ID. DDS turns it
  into network port numbers. The discovery port is `7400 + 250 × domain`: for domain 42,
  `7400 + 250 × 42 = 17 900`. Two different domains use different ports, so their traffic never
  meets. The ROS 2 documentation recommends values from 0 to 101 on Linux.
- **`ROS_LOCALHOST_ONLY=1`**: talk only inside this computer, never on the network.

In this academy, each student has their own `ROS_DOMAIN_ID`: this is why you never see the topics of
your neighbours. NAVERA's own settings are also environment variables, read by its code with
`os.environ`. In your sandbox you can see some of them: `env | grep ^NAVERA_` shows, for example,
`NAVERA_MBTILES` (the path of the satellite map).

## 6. Streams, redirection and pipes

Every process has three **streams**, numbered by **file descriptors**: **0 = stdin** (input),
**1 = stdout** (normal output), **2 = stderr** (error messages). By default all three are the
terminal. Redirection sends them elsewhere:

| Syntax | Meaning |
|---|---|
| `cmd > out.txt` | stdout into a file (the file is **emptied first**) |
| `cmd >> out.txt` | stdout appended at the end of the file |
| `cmd 2> err.txt` | stderr into a file |
| `cmd > all.txt 2>&1` | stdout into the file, **then** stderr to "where stdout goes now" (the same file) |
| `cmd 2> /dev/null` | throw the error messages away (`/dev/null` swallows everything) |
| `cmd < in.txt` | stdin from a file |
| `a \| b` | a **pipe**: stdout of `a` becomes stdin of `b` |

![A pipeline: each program does one small job; stderr bypasses the pipe](assets/pipe.svg)

Order matters in `> file 2>&1`: the shell reads left to right. `2>&1 > file` would send stderr to the
**old** stdout (the screen). And never redirect into the file you are reading: `sort a.txt > a.txt`
empties `a.txt` before `sort` reads it.

## 7. The text tools

Logs and settings are text, so a handful of small tools answers most questions.

| Tool | Example | Does |
|---|---|---|
| `grep` | `grep -c "^\[WARN\]" f.log` | lines matching a pattern; `-c` count, `-v` invert, `-n` line numbers, `-i` ignore case, `-r` recursive, `-l` file names only, `-q` quiet, `-m 1` stop after the first match |
| `cut` | `cut -d' ' -f3` | keep field 3, fields separated by a space |
| `sort` | `sort`, `sort -n`, `sort -rn` | sort lines (text order, numeric, reverse numeric) |
| `uniq -c` | `sort \| uniq -c` | count runs of identical lines (so **sort first**) |
| `wc -l` | `wc -l < f.log` | count lines (with `<`, only the number is printed, not the file name) |
| `find` | `find ~/navera -name "*.py" -type f` | files by name, type, size, date |
| `xargs` | `find … \| xargs wc -l` | turn input lines into **arguments** of a command |
| `date` | `date -d @1789976724` | turn a Unix time (seconds since 1970-01-01 UTC) into a date |

`grep` patterns are **regular expressions**: `^` means "start of the line", `$` "end of the line",
`.` "any character". Square brackets have a special meaning (a set of characters), so to match a
real `[` you write `\[`. Hence `"^\[WARN\]"`: lines that **start** with `[WARN]`. Without `^`, a line
like `[INFO] … previous WARN cleared` would also be counted.

**Time zones.** Logs store time in **UTC**; Tunisia is **UTC+1** all year (no daylight saving).
`TZ=Africa/Tunis date -d @1789976724 +%T` prints the Tunisian wall-clock time `08:45:24`.
(Other zones: `TZ=Asia/Singapore` is UTC+8, `TZ=America/New_York` changes with daylight saving.)

**`xargs`** solves a common problem: `wc -l` wants file names as arguments, but `find` prints them on
stdout. `find ~/navera/navera_estimator -name "*.py" | xargs wc -l` builds the command
`wc -l file1 file2 …` for you; its last line is the total. (`xargs cat | wc -l` gives the same total.)

### Reading a ROS 2 log line

NAVERA's nodes write their messages in the ROS 2 console format:

```
[WARN] [1789976724.123456789] [estimator_node]: state NO_FIX: no source usable
 │      │                      │                 └── the message
 │      │                      └── the node that wrote it
 │      └── time: Unix seconds . nanoseconds (UTC)
 └── severity: DEBUG, INFO, WARN, ERROR, FATAL
```

Split on spaces, the severity is field 1, the time field 2, the node field 3. The arbiter
(`estimator_node`) reports its state — **FIX**, **DEGRADED** or **NO_FIX** — and the active source.

**Worked example.** "Which node complained most during the Sousse flight?"

```
grep "^\[WARN\]" sousse.log | cut -d' ' -f3 | sort | uniq -c | sort -rn | head -n 1
```

grep keeps the WARN lines (84), cut keeps `[day_subscriber]:` etc., sort groups equal names, uniq -c
counts each group, `sort -rn` puts the biggest count first, head keeps one line: `61 [day_subscriber]:`.

## 8. Bash scripts

A **script** is a file of commands. Bash adds variables, tests and loops:

```bash
#!/bin/bash
# count_level.sh — how many lines of a log have a given severity
# usage: ./count_level.sh LOGFILE LEVEL
set -e                                  # stop at the first command that fails

if [ $# -ne 2 ]; then                   # $# = number of arguments
    echo "usage: $0 LOGFILE LEVEL" >&2  # message on stderr (>&2)
    exit 2
fi
log="$1"                                # $1, $2 = the arguments; NO spaces around =
level="$2"
if [ ! -f "$log" ]; then                # -f: "is a regular file"; ! = not
    echo "no such file: $log" >&2
    exit 1
fi
n=$(grep -c "^\[$level\]" "$log" || true)   # $(...): see below
echo "$level: $n"
```

```bash
for f in mission/logs/*.log; do         # a loop over the files of a pattern
    echo "$(basename "$f"): $(wc -l < "$f") lines"
done
```

**Command substitution** `$(command)`: bash runs the command and puts its **output** (the text it
prints) in place of the `$( )`. `n=$(grep -c …)` stores the count in `n`; `echo "lines: $(wc -l < f)"`
prints the text with the number inside. Try it: `echo "I am $(whoami)"`.

Rules that avoid 90 % of script bugs:

- **No spaces around `=`** in an assignment: `n=3`, not `n = 3` (that runs a command called `n`).
- **Quote variables**: `"$log"`. Without quotes, a value with spaces becomes several words.
- In `[ … ]` you **need** the spaces: `[ "$n" -gt 0 ]`. Numbers: `-eq -ne -lt -le -gt -ge`;
  text: `=` and `!=`; files: `-f` (file), `-d` (folder), `-e` (exists), `-x` (executable).
- `set -e` stops the script at the first failing command. Careful: **`grep` exits with 1 when it
  finds nothing**, so under `set -e` an assignment `n=$(grep -c …)` that counts 0 matches stops your
  script silently. `|| true` ("or else do nothing, successfully") keeps it going; grep still prints `0`.
  Bash is not consistent here: in `echo "x: $(grep -c …)"` the script does **not** stop (the exit
  code of `echo` counts, and echo succeeds), but in `n=$(grep -c …)` it **does**. Do not try to
  remember which case is which. **The rule: always write `|| true` after a grep that may find
  nothing**, inside `$( )` or not.
- Errors and usage messages go to **stderr** (`>&2`) and the script ends with a **non-zero exit
  code**. Normal results go to stdout. Then other programs can pipe your output safely.
- `basename path` prints the last part of a path: `basename mission/logs/sousse_2026-09-21.log`
  → `sousse_2026-09-21.log`.

## 🐦 How birds do it

You cannot ask a falcon over the Mediterranean where it went. Ornithologists do the next best thing:
they fit a tiny solar-powered tag that records GPS positions and sends them by satellite or by the
mobile-phone network. Tagged birds include **Eleonora's falcons**, which breed on rocky islands of the
Mediterranean — in Greece, Sardinia and off the coast of Morocco — and spend the northern winter in
Madagascar; and **steppe eagles**, which breed in the steppes of Central Asia, many of which spend
the winter in East Africa. The tags showed routes that nobody could have followed with binoculars: long
journeys over sea and desert, with stopovers.

What reaches the scientist is **text**: one line per position, like
`2025-10-14T06:30:00Z,9.03,38.74,eagle_07` (time in UTC, latitude, longitude, bird). A season of
tracking is tens of thousands of such lines. The first tools are the ones of this lesson:
`grep eagle_07 tracks.csv` keeps one bird, `cut -d, -f1` keeps the times, `| wc -l` counts the fixes,
`> eagle_07.csv` saves them. Like the NAVERA box, the tag is far away and has no screen; the only way
to know what happened is to read its log.

Navi, the swallow of this course, has no tag — barn swallows are too light for a GPS-satellite tag,
so they are studied with even smaller **geolocators** that log only light levels. But the method is the
same: a device records, the engineer reads lines of text, and a short pipeline turns them into an answer.

## In NAVERA

**Finding the tests with a pipeline.** [run_tests.sh](file:navera/navera_tools/run_tests.sh) is how
NAVERA runs its test suite. It builds its list of test files with `find`, `grep -v`, `cut` and `sort`:

```bash
mapfile -t UNIT < <(find . -path ./build -prune -o -path ./install -prune -o \
    -path '*/test/test_*.py' -print \
  | grep -vE 'test_(flake8|pep257|copyright)\.py$' \
  | while read -r f; do
      pkg=$(echo "$f" | cut -d/ -f2)
      [ -e "$pkg/COLCON_IGNORE" ] || echo "$f"
    done | sort)
```

`find` lists the test files but skips (`-prune`) the generated folders `build/` and `install/`;
`grep -v` removes the style checkers; `cut -d/ -f2` extracts the package name from `./pkg/test/…`;
the `[ -e … ] ||` test drops packages that contain a `COLCON_IGNORE` file; `sort` orders the list.

**Signals, the polite way first.** The same file stops a test that hangs with the signal ladder of
section 4 — SIGTERM to the whole process group, 5 s of patience, then SIGKILL:

```bash
      echo "TIMED OUT after ${limit} s: $*"
      kill -TERM -- "-$pid" 2>/dev/null; sleep 5; kill -KILL -- "-$pid" 2>/dev/null
```

**Environment and permissions in a service.** On a deployed box, systemd starts each NAVERA part as a
service. [navera-gps.service](file:navera/deploy/systemd/navera-gps.service) loads the site settings
as environment variables and gives the service the group that may open the GPS serial port:

```ini
# Site settings shared by all NAVERA units (data paths, ROS_DOMAIN_ID...).
# The leading "-" keeps the unit working if the file does not exist.
EnvironmentFile=-/etc/navera/navera.env
User=navera
Group=navera
# /dev/ttyTHS1 is root:dialout 0660 on JetPack.
SupplementaryGroups=dialout
Restart=always
```

**The ROS domain.** [navera_boot_lib.sh](file:navera/deploy/systemd/navera_boot_lib.sh) makes sure
`ROS_DOMAIN_ID` is a number before it sources ROS; otherwise NAVERA isolates itself on domain 42,
loopback only. `${ROS_DOMAIN_ID:-0}` and `export` are exactly the syntax of section 5:

```bash
    if [[ ! "${ROS_DOMAIN_ID:-0}" =~ ^[0-9]+$ ]]; then
        export ROS_DOMAIN_ID=42 ROS_LOCALHOST_ONLY=1
    fi
    source /opt/ros/humble/setup.bash
```

> [!NOTE]
> Your copy has two folders that the source code does not live in: `build/` and `install/`. The
> build tool `colcon` (lesson 9) makes them; they hold copies and links of the sources. When you search,
> the file to read or change is the one **outside** them — exactly what `-prune` does above.

## Glossary

| Term | Meaning |
|---|---|
| **shell / bash** | the program that reads and runs your command lines |
| **working directory** | the current folder; relative paths start there (`pwd`) |
| **absolute / relative path** | starts at `/` / starts at the working directory |
| **`~` (home)** | `/home/student`; `~/navera` = `/home/student/navera` |
| **wildcard (glob)** | `*`, `?`, `[…]`, expanded by the shell into matching names |
| **permission bits** | r, w, x for owner, group, others; octal r=4 w=2 x=1 |
| **shebang** | first line `#!/bin/bash`: which interpreter runs the file |
| **process / PID** | a running program / its number |
| **signal** | a message to a process: SIGINT (2, Ctrl+C), SIGTERM (15, `kill`), SIGKILL (9, cannot be caught) |
| **exit code** | the number a process returns; 0 = success; in `$?` |
| **environment variable** | named text value inherited by child processes (`export`) |
| **`ROS_DOMAIN_ID`** | integer that separates ROS 2 networks; same ID = can talk |
| **stdin / stdout / stderr** | streams 0 / 1 / 2 of a process |
| **redirection** | `>`, `>>`, `2>`, `2>&1`, `<`: connect a stream to a file |
| **pipe** | `\|`: stdout of one command into stdin of the next |
| **regular expression** | a text pattern: `^` start, `$` end, `.` any character, `\[` a real bracket |
| **Unix time** | seconds since 1970-01-01 00:00 UTC |

## Check what you learned

<details><summary>1. You are in <code>/home/student/navera/day_pkg/day_pkg</code>. Write two other forms of the path <code>../../navera_msgs</code>.</summary>
<code>/home/student/navera/navera_msgs</code> (absolute) and <code>~/navera/navera_msgs</code> (with the tilde). All three name the same folder.
</details>

<details><summary>2. <code>ls -l</code> shows <code>-rw-r--r-- preflight.sh</code>. Why does <code>./preflight.sh</code> fail, and which command fixes it? What is the octal mode afterwards?</summary>
There is no x bit, so Linux refuses to execute the file ("Permission denied"). <code>chmod u+x preflight.sh</code> gives <code>rwxr--r--</code> = 744; <code>chmod +x</code> gives <code>rwxr-xr-x</code> = 755. (<code>bash preflight.sh</code> would work without x.)
</details>

<details><summary>3. A node does not stop with Ctrl+C. What do you do, in order — and why not <code>pkill python3</code>?</summary>
Find its PID (<code>pgrep -a -f name</code> or <code>ps -ef</code>), read the command line, then <code>kill PID</code> (SIGTERM). If it is still alive after a few seconds, <code>kill -9 PID</code> (SIGKILL, no clean-up). <code>pkill python3</code> would also stop every other Python program you own — on a shared machine, possibly other people's work.
</details>

<details><summary>4. In terminal A you type <code>export ROS_DOMAIN_ID=7</code>. A node started in terminal B does not see the nodes of terminal A. Why?</summary>
An exported variable is copied only to processes started from <b>that</b> shell. Terminal B has its own environment, with its own ROS_DOMAIN_ID; different domains use different ports (7400 + 250 × domain), so the nodes never discover each other.
</details>

<details><summary>5. What do <code>cmd > out.txt 2>&1</code> and <code>cmd 2>&1 > out.txt</code> do?</summary>
The first sends stdout to out.txt, then stderr to the same place: both in the file. The second first sends stderr to where stdout is <i>at that moment</i> (the screen), then stdout to the file: errors still appear on the screen.
</details>

<details><summary>6. A script with <code>set -e</code> contains <code>n=$(grep -c "^\[ERROR\]" "$1")</code>. It stops silently on a log with no ERROR line. Why, and how do you fix it?</summary>
grep exits with code 1 when it finds no match (it still prints 0). Under <code>set -e</code> that non-zero code stops the script. Write <code>n=$(grep -c "^\[ERROR\]" "$1" || true)</code>.
</details>

Now open the **🛠️ Lab** tab.

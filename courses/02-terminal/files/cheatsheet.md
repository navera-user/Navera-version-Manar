# Mission 02 — cheat sheet

Every command of the lesson and the lab, with the options used. `man CMD` (quit with `q`) or
`CMD --help` gives the rest.

## Moving around and files

| Command | Does |
|---|---|
| `pwd` | print the working directory |
| `ls`, `ls -l`, `ls -la`, `ls -R` | list; long format; with hidden files (`.name`); every sub-folder too |
| `cd PATH`, `cd ..`, `cd -`, `cd` | go to PATH; one level up; back to the previous folder; home |
| `cat F`, `head -n 5 F`, `tail -n 5 F` | show a file; its first / last 5 lines |
| `tail -f F` | follow a file as it grows (`Ctrl+C` stops) |
| `wc -l F`, `wc -l < F` | count lines (with `<`: the number only) |
| `mkdir -p a/b` | make folders, with their parents |
| `cp a b`, `cp -r d1 d2` | copy a file; a folder and everything in it |
| `mv a b` | move or rename |
| `rm F`, `rmdir D` | delete a file; delete an **empty** folder |
| `diff a b` | the lines that differ between two files (nothing = identical) |
| `du -sh D` | disk space used by a folder |
| `find D -name "*.py" -type f` | files under D whose name matches (quote the pattern) |
| `basename PATH [.ext]` | the last part of a path (without `.ext`) |

Wildcards (expanded by the shell): `*` any characters, `?` one character, `[12]` one of these.

## Permissions and users

| Command | Does |
|---|---|
| `ls -l F` | mode, owner, group: `-rwxr-x---  student  student` |
| `chmod u+x F`, `chmod go-w F` | add x for the owner; remove w for group and others |
| `chmod 750 F` | set the mode in octal (r = 4, w = 2, x = 1; owner, group, others) |
| `id`, `id NAME` | your user and groups; another user's |
| `stat -c %a F` | the octal mode of F |

## Processes and signals

| Command | Does |
|---|---|
| `ps -ef` | every process: UID, PID, PPID, start, command (`\| cut -c1-120` shortens long lines) |
| `ps -o pid,ppid,lstart,args -p 41,77` | chosen columns for chosen PIDs (`lstart` = start date and time) |
| `ps -p PID` | is this PID still running? |
| `pgrep -a -f TEXT` | PID and command line of the processes whose command line contains TEXT |
| `cmd &`, `jobs`, `fg %1`, `echo $!` | run in the background; list jobs; job 1 to the foreground; PID of the last background job |
| `Ctrl+C` | SIGINT (2) to the program in the foreground |
| `kill PID` | SIGTERM (15): "please terminate" |
| `kill -9 PID` | SIGKILL (9): immediate, cannot be caught: the last step of the ladder |
| `echo $?` | exit code of the last command: 0 success; 128 + n after signal n (130, 143, 137) |

Never `pkill` or `killall` by name on a shared machine: find the exact PID.

## Environment

| Command | Does |
|---|---|
| `env`, `echo $NAME` | all variables; one value |
| `export NAME=value` | give it to every program started afterwards from this shell |
| `NAME=value cmd` | for this one command only |
| `${NAME:-default}` | the value, or `default` if unset or empty |
| `which cmd` | which file runs when you type `cmd` |

## Streams

| Syntax | Meaning |
|---|---|
| `cmd > f`, `cmd >> f` | stdout into f (emptied first); appended |
| `cmd 2> f`, `cmd 2> /dev/null` | stderr into f; thrown away |
| `cmd > f 2>&1` | both into f |
| `cmd < f` | stdin from f |
| `a \| b` | stdout of a into stdin of b |

## Text tools

| Command | Does |
|---|---|
| `grep PAT F` | lines matching PAT. `-c` count, `-v` the others, `-n` line numbers, `-i` any case, `-m 1` first only, `-q` quiet (exit code only: 0 found, 1 not found), `-r` a whole folder, `-l` file names only |
| `cut -d' ' -f3` | field 3, fields separated by a space; `cut -c2-11` characters 2 to 11 |
| `sort`, `sort -n`, `sort -rn`, `sort -u` | text order; numbers; numbers, biggest first; one copy of each line |
| `uniq -c` | count runs of identical **neighbouring** lines (sort first) |
| `head -n 1` | the first line |
| `xargs CMD` | input lines become arguments: `find … \| xargs wc -l` |
| `date -u -d @SECONDS +%T` | a Unix time as HH:MM:SS in UTC; `TZ=Africa/Tunis date -d @S +%T` in Tunisia (UTC+1) |

Patterns: `^` start of line, `$` end of line, `.` any character, `\[` a real `[`.

## Bash scripts

```bash
#!/bin/bash                      # shebang: first line
set -e                           # stop at the first failing command
[ $# -ne 1 ] && { echo "usage: $0 FILE" >&2; exit 2; }
f="$1"                           # no spaces around =, quote "$f"
if [ ! -f "$f" ]; then echo "no such file: $f" >&2; exit 1; fi
n=$(grep -c "PATTERN" "$f" || true)      # || true: grep exits 1 when it finds nothing
echo "count: $n"
for x in a b c; do echo "$x"; done
```

Tests: numbers `-eq -ne -lt -le -gt -ge`, text `= !=`, files `-f -d -e -x`, `!` = not.

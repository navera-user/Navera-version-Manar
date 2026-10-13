# Mission 02 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — the box on the bench** (Steps 0–6, badge **Orphan hunter** = checks 1–8,
milestone `orphan-hunter`) and **Session 2 — the flight logs** (Steps 7–11, badge **Log detective** =
all 15 checks). NAVERA's code is not used anywhere: the stack explored is the NAVERA Lite **skeleton**
(`datasets/02-terminal/navera_lite_tree/`, names and one-line docstrings only, `...` bodies), and the
"box" is a set of small bash scripts in `courses/02-terminal/files/box/` started by `box.sh`.

Data: `solutions/02-terminal/make_dataset.py` (deterministic, teacher only; run it from the academy folder) writes into `datasets/02-terminal/` the skeleton, `examples/` (the lesson's
bench log), `evidence/` (Step 4b), and into `courses/02-terminal/files/inbox/` the two synthetic logs,
three synthetic camera views (rendered from the course's OSM map with `datasets/_map/render_view.py`,
"© OpenStreetMap contributors" written on each image) and three cache files. Run it again after a change
of the NAVERA Lite reference settings (`navera_lite.yaml` is copied into the skeleton).

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Diagnose `Permission denied`: `ls -l`, `id`, octal, x bit vs group | §3 (camera service, octal) | Step 4 (preflight x bit; evidence → `SupplementaryGroups=dialout`) | 3, 4, 5 (P1–P3) |
| 2. Find, identify (PID, PPID, start, command line) and stop a process; TERM then KILL | §5 (two camera readers, 143; unit file) | Step 0, Step 6 (orphan arbiter, supervisor observed, hung camera) | 7, 8 |
| 3. Answer log questions with pipelines; stdout vs stderr | §2 (paths, find), §4 (env), §6 (WARN by node, `grep` without `^`, `ls` error) | Steps 2, 3, 5, 7, 8 | 1, 2, 5, 6, 9, 10 |
| 4. Write a bash script that is right on unseen input | §7 (three bugs) | Steps 9–10 | 11–15 |

## Answer key

- Box timing (`box.sh start`, about 7 s): the three supervisors start first, the simulator 4 s later, so the
  orphan is the **younger** arbiter: "kill the oldest" kills the good one (the supervisor restarts it; the
  lesson's §5 ✏️ check 1 is tested here).
- Step 0/6: `decisions.log` alternates `state FIX source=gps` (supervised arbiter, `box/config/navera_lite.yaml`)
  and `state NO_FIX … (gps: no message on /sim/fix/gps)` (the orphan, `box/config/sim.yaml`), once per second each.
- Step 2 (skeleton): **Q1 = 54** (`find navera_lite -name "*.py" | wc -l`; 140 from the top folder with the
  build/install copies, the check names that mistake); **Q2 = `navera_lite/uncertainty.py`**; **Q3 = 134**
  (`find navera_lite/ros -name "*.py" | xargs wc -l`, total); **Q4 = 4** (gps, arbiter, camera, replay;
  `navera_lite.target` is not a service); **Q5 = `imu.py`**.
- Step 3: 10 files in the inbox (3 views, 2 logs, 3 `.tmp`, notes, preflight.sh).
- Step 4: **P1 = 660** (`crw-rw---- root dialout`); **P2 = `dialout`** (the developer has it, `navera_lite`
  does not). **P3** = the student's own mode: the starter is `rw-r--r--`, so `chmod u+x` gives **744**
  (`chmod +x` 755); the check reads the real mode. The fix: one line `SupplementaryGroups=dialout` in
  `[Service]`; `diff` shows `> SupplementaryGroups=dialout`. `preflight.sh` then prints `PRE-FLIGHT OK`
  (exit 0). The skeleton's camera unit (`SupplementaryGroups=video`, commented "/dev/video0 is root:video 0660")
  is a deliberate worked example; the lab points to it. systemd accepts spaces around `=`, so
  `SupplementaryGroups = dialout` passes both preflight and check 4. `preflight.sh` reads the port's group
  from the evidence file and looks only between `[Service]` and `[Install]` (it agrees with check 4).
  Without the data disk it reports the map missing; check 4 is then skipped when the unit is right.
- Step 5: `export MY_NOTE="read ROS_DOMAIN_ID first"` makes the `^` matter: `env | grep ROS_` keeps MY_NOTE
  and check 5 names that line.
- Step 5: E1 = the student's `ROS_DOMAIN_ID` (200 + their index; 202 in `try_lesson`), E2 = `/data/map.mbtiles`.
  `ros_env.txt`: `ROS_DISTRO=humble`, `ROS_DOMAIN_ID=…`, `ROS_LOCALHOST_ONLY=1`, `ROS_PYTHON_VERSION=3`, `ROS_VERSION=2`.
- Step 6: `pgrep -a -f navera_lite_arbiter` gives two PIDs. The orphan has **PPID 1** (`ORPHAN_PPID = 1`),
  started ~4 s **later**, by `sim_launcher` (gone), with `--params-file box/config/sim.yaml`; the other's parent
  is `box/bin/supervise arbiter`. Then the student kills the supervised arbiter on purpose ("Observe your
  prediction") and sees it come back with a new PID. Check 7 needs both: the orphan's SIGTERM line, and a
  supervised arbiter stopped and restarted, in any order (a student who kills the good one first has just
  done the observation: no dead end, no box restart needed). `PREDICT_PKILL` (not marked): both arbiters get SIGTERM, the supervisor
  restarts its own one a second later, the orphan stays dead — so `pkill` "works" here by luck, at the cost
  of a one-second gap in the judge, and would kill the wrong things on a shared machine. Camera: the first
  reader catches SIGTERM and keeps running ("waiting for the camera driver"); `kill -9` ends it; the
  supervisor writes `ended by signal KILL (exit code 137)` (**KILL_EXIT_CODE = 137**) and starts a new reader
  that works. The check reads every run's journal (`box/log/` and `box/old/*/`) and passes if one run is right.
- Step 7: `ls_out.txt` = `navera_lite.yaml`; `ls_err.txt` = `ls: cannot access 'no_such_file.yaml': No such file or directory`.
- Step 8: `grep -c WARN` 85 vs `grep -c "^\[WARN\]"` 84 (the INFO line "previous WARN cleared, gps trusted
  again"). `PREDICT_UNIQ` (choices 3 / about 10 / about 40 / 84): without `sort`, `uniq -c` prints **43** lines
  (runs). The sandbox clock is on Tunisian time, so `date` without `TZ=` also gives Q7 here; the lab says so. **Q6 = `day_vision`**
  (61; nmea 18, arbiter 5). **Q7 = `08:45:24`** (Unix 1789976724; UTC 07:45:24, which the check names).
  **Q8 = 3** (camera, output, imu; 7 ERROR lines in all).
- Step 9 (`log_report.sh`): Sousse `lines 310, INFO 221, WARN 84, ERROR 5, nodes 6, no_fix 2`; Range
  `lines 240, INFO 211, WARN 27, ERROR 2, nodes 6, no_fix 1`. Hidden log of check 13 (34 lines): no ERROR
  line, INFO lines containing "WARN" and "ERROR", a node `clock` that appears once.
- Step 10: Sousse NO_FIX 2, ERROR 5, first NO_FIX 08:45:24 over the sea (no match for day vision, dead-reckoning
  limit 120 s). Range NO_FIX 1, ERROR 2; the 2412 m GPS jump refused by the jump gate ("reachable 150 m"), GPS
  accepted again after agreeing with day vision (gap 21 m).

Wrong solutions tested (each fails with the message shown): no `|| true` → "stopped after the WARN line… add
|| true"; unanchored grep → "WARN: 85"; nodes without `sort -u` → "nodes: 310"; no `basename`; usage on
stdout with exit 0; `wc -l "$log"` → "lines: 310 mission/logs/…"; `Group=dialout` instead of a new line;
the line in `[Install]` (preflight also refuses it); Q1 = 140, Q7 in UTC; only the supervised arbiter killed
("the orphan still runs: find it by its parent … no need to restart the box"); the orphan stopped but no
observation; `kill -9` on the camera before its SIGTERM line; `kill -9` on the orphan; KILL less than 2 s after
TERM; `EXPLAIN_ORPHAN = "It was definitely the first one in the list…"` (fails: no parent idea); a flight report
of numbers plus 40 × "word" (fails: no domain words, no recommendation); `env | grep ROS_` without `^`;
`uniq` instead of `sort -u` (nodes: 183).

Known limits of the grader: the journal is a file in the student's folder, so a student could forge its lines
(the exact format is needed; the rubric questions reveal it). check.py holds the hidden log of check 13
(`hidden_log()`) and the expected constants; while a check runs, a student's script could read check.py — a
platform fix is in progress (not handled in this mission).

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_ORPHAN | two independent clues: PPID 1 (its starter is gone, while the other's parent is the supervisor) **and** command line (`sim.yaml`) or the journal (`sim_launcher started … as pid N`); bonus: it is the *younger* one, so age alone misleads | one clue only, or "it said NO_FIX" without linking it to a process | "the first one in the list", "the oldest" |
| EXPLAIN_KILL | the reader **caught** SIGTERM and kept waiting (a program may catch or ignore TERM); KILL cannot be caught, so no clean-up and no last message; the supervisor reported 137 (128 + 9) and started a new reader (bonus: a process stuck in the kernel, state D, would not even die from KILL) | two of the three | "kill -9 is stronger" |
| PREDICT_PKILL, PREDICT_UNIQ | never marked; discuss in class | | |
| flight_report.md Conclusion | vision covered GPS over land, not over the sea (nothing to match) → NO_FIX and the autopilot's failsafe; a concrete recommendation (route over land under jamming, investigate camera timeouts, a source that works over water) | numbers repeated, vague recommendation | off-topic |

## Difficulties seen in testing (simulated students and the builder's run)

- `find . -name "*.py"` from the skeleton's top folder (140, the copies) — the most common Q1 error.
- `cp` into a folder that does not exist yet (`mission/deploy` is created in Step 3; students who skip it get
  "No such file or directory"). `mv` from `/data/…` fails with "Read-only file system": a good teaching moment.
- `ps -ef` shows a very long first line (PID 1 is the sandbox itself, `bwrap …`): tell students to use
  `| cut -c1-120` or `ps -o pid,ppid,lstart,args -p …`.
- Students who close the terminal lose the box (the sandbox ends): `./box.sh start` again; the old journals
  stay in `box/old/`, and the check accepts any run done right.
- The `set -e` + `grep -c` trap is still the main script error; check 13 names it.
- Strong students finish Session 1 in about 50 min; push them to the watchdog in "Going further".

## Suggested class plan (reading at home ~60 min + two sessions of 1 h 45; novices: about 5 h in all, two days)

1. **Session 1 — hook (10 min):** the two NAVERA stories of the brief (2026-09-28 and 2026-10-01).
   "Two arbiters on one network: how would you even notice?" Everyone runs Step 0 together and watches
   `decisions.log` flicker.
2. **Lab (85 min):** Steps 1–6. Board moment at Step 6: draw the process tree from `ps -ef` together
   (supervisors, the orphan under PID 1). End with check 1–8 → **Orphan hunter**.
3. **Session 2 — retrieval (10 min):** Check-yourself 1–3 on paper; who was surprised by `PREDICT_PKILL`?
4. **Lab (85 min):** Steps 7–10. When most reach Step 9, show `set -e` stopping silently on a log without
   ERROR lines (live, 3 min).
5. **Debrief (10 min):** read two flight-report conclusions with the rubric.

**Differentiation.** Fast: the watchdog and `awk` items of "Going further". Struggling: pairs; give the
Step 8 Q6 pipeline from the lesson table, and the hint sequence of Step 9; the cheat sheet answers most
"which option?" questions.

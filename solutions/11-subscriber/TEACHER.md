# Mission 11 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

The mission runs in two sessions. **Session 1 — Memory** (Steps 0–4, no ROS: polling bug, `TripComputer.update`,
`speed_window`, `Watchdog.silent`, the noisy drive; badge **Trip computer** = the `trip-computer` milestone, checks
1–6). **Session 2 — On the wire** (Steps 5–9: the trip node's `listen`/`on_fix`, bad fixes through it, the blocking
callback, the judge noticing a silent GPS; badge **Watchdog** when the mission is passed).

What changed from the old mission 11 (rebuild plan §B "11 → 11, trim"): no NAVERA node is run any more (the lab used
NAVERA's estimator and GPS bridge); the judge is NAVERA Lite's **arbiter v0** (given since mission 09) fed directly by
the mission-10 `gps_node`. The student's code is `navera_lite/ros/trip_node.py` TODO 1–5 (generated from
`solutions/_navera_lite/navera_lite/ros/trip_node.py`, tags `# @part 11 …`). The Rayleigh derivation moved to
mission 27 (one "read after" box remains in Step 4); executors are one blocking-callback demo (`blocking_demo.py`,
given) instead of a TODO; the polling bug (OUT-5) is reproduced in pure Python (`polling.py`, given).

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. A subscriber with memory: judge each fix by its stamp, refuse with the reason, keep state | §1 (queue), §3 (plane trace, 5-fix check) | Steps 1–2 (TODO 1), 5–6 (TODO 4–5) | 1, 2, 7, 8, 9 |
| 2. Noise of a speed from positions; window vs delay | §4 (σ 2 m at 5 Hz) | Steps 3–4 (TODO 2) | 3, 6 |
| 3. Silence needs a timer; when the alarm comes | §5 (4 Hz watchdog) | Step 3 (TODO 3), Step 8 | 4, 8, 11 |
| 4. Executor and slow callbacks; on arrival vs polling | §2 (groups; 10 Hz × 0.15 s), §6 (poll at 50 Hz) | Steps 0, 7 | 5, 10 |

## Answer key (every number recomputed by script or measured on 2026-10-13, Jetson Orin Nano)

- **Step 0** (`polling.py`, seed 5, phase 150 ms: each tick 50 ms after a nominal arrival, so a crossing is
  almost always a LATE position, the case of lesson §6 and polling.svg): defaults → DROPPED 30, DOUBLED 30, longest
  wait 400 ms, first ticks `#0 … #7 #7(again) #9(#8 lost) #10 #11`. `--jitter-ms 0` → 0 and 0 (a constant phase never
  crosses a tick). `--poll-hz 10` → DROPPED 2, **DOUBLED 301** (every second tick repeats). `--mode arrival` → 0 and 0
  (its "longest wait" 370 ms is the sender's own jitter). `PREDICT_POLL`: most students say "nothing, same rate".
  Answers: `DROPPED_5HZ = 30`, `DOUBLED_5HZ = 30`, `DOUBLED_10HZ = 301` (exact, deterministic). (Round 1 used phase
  30 ms, which showed the early/mirror case first and confused students; lesson §6 now names both.)
- **Step 1–2**: `run_trip.py test` all ✔; `trace` reproduces lesson §3's table (450 m, 5 accepted, 3 refused).
- **Step 4** (`run_trip.py drive`, seed 33): cruising mean 10.75 (1 s) / 9.97 m/s (10 s), **std 4.11 / 0.40 m/s**
  (theory √2·3/1 = 4.24 and 0.42); **parked mean 5.51 m/s** (window 1 s; Rayleigh mean 1.2533 × √2 × 3 ≈ 5.32) and
  0.55 m/s (10 s); **LAG_S = 9.0 s** (theory: the chord speed falls linearly from 10 to 0 over the 10 s after the stop,
  below 1 m/s after about 9 s); odometer 993 m for a 600 m drive. The seed was chosen among 40 so that the numbers sit
  close to the theory (other seeds: std 3.1–5.5 m/s). The check accepts ±0.02 (±0.011 for the window std, ±0.01 lag).
- **Step 5**: `ros2 node info /trip` lists `/navera_lite/fix/gps: sensor_msgs/msg/NavSatFix` under Subscribers and
  `/navera_lite/trip` under Publishers; the echo shows distance growing 10 m/s, `speed_mps` 10.00, `silent` false.
- **Step 6** (`bad_fixes.csv`, made by `make_files.py`): refusals at rows t = 5 (no position), 8 (bad position, NaN),
  11 (jump, 5 km), 14 (old fix: `delay_s` 2.5 → stamp ≈ 11.5 s, older than the fix accepted at 13 s). End:
  **fixes 16, refused 4, last_refusal "old fix", distance_m 190.0**, speed 10.00, silent true. Measured identical on
  the host and in the sandbox.
- **Step 7** (`blocking_demo.py`, GPS at 5 Hz, 0.3 s of work, ρ = 1.5):

  | Run | host | sandbox |
  |---|---|---|
  | single: ticks / longest gap / max age | 33 / 302 ms / 1.97 s | 43 / 374 ms / 1.99 s |
  | multi | 100 / 101 ms / 1.97 s | 100 / 103 ms / 1.98 s |
  | shared | 34 / 320 ms / 1.97 s | 33 / 396 ms / 1.99 s |
  | single --work 0.1 | 100 / 113 ms / 0.00 s | 100 / 119–205 ms / last 0.00 s (first/max 0.14–0.40 s, start-up) |

  With `--work 0.1` the gap can reach one period plus one callback (≈ 200 ms; measured 113–205 ms); the
  check names it if a student copies that run as GAP_SINGLE_MS.

  Max age ≈ depth × T = 10 × 0.2 s = 2 s (the queue holds the 10 newest; the callback takes the oldest). About 7 fixes
  in 8 s are never handled. The check accepts GAP_SINGLE_MS 250–900, GAP_MULTI_MS 90–200, AGE_MULTI_S 1.3–2.7.
- **Step 8**: "GPS silent for … s" values 3.12, 3.04, 3.01 (host) and 3.08, 3.02, 3.16 (sandbox): `gps_timeout_s`
  3.0 s by stamp + at most one 0.2 s tick (5 Hz) + a few ms of latency. The trip node logs `GPS silent` usually 0–1 s
  later (its watchdog is checked by the 1 Hz publishing timer: 3–4 s after the last arrival; sandbox: 0.5–0.9 s later),
  sometimes up to ~0.2 s earlier (reviewers saw −0.02 to −0.13 s). The check accepts
  2.95–3.7 s and refuses the example values of answers.py. (Measured from the moment of Ctrl+C the silence is 2–4 s,
  since the last fix came up to 1 s before; that is why the listener measures from the last fix's stamp.)
- Lesson checks: answers are in the lesson's `<details>`; numbers verified: §2 longest gap 0.3 s (rclpy runs a ready timer before a ready subscription), ρ 0.6, queue +0.33/s, full ≈ 30 s,
  age 5 s; §2 check 1.5 / 1 s / one in three dropped; §3 check 90 m, 2 refused; §4 7.1 / 0.71 m/s, check 14.1 / 1.41;
  §5 3.5 s, check 3.0–3.25 s; Check yourself 1: ρ 1.2, 2.5 s.

**Unseen data in check.py** (constants; computed with the reference `trip_node.py`): 4 fixes near Quito (distance
83.269 m); an 11-fix sequence near Reykjavik with `TripComputer(20.0, 10.0)` that separates the common mistakes (gate
from a refused fix, "old fix" against a refused stamp, same stamp as the last accepted, gate before stamp, first rule wins, Null Island, ±∞;
4 accepted, 7 refused, 124.0 m); 5 irregular fixes near Sydney (windows 5 / 6 / 100 s → 10.0884 / 10.0731 /
9.1327 m/s; 0.5 s and an empty list → None); a `Watchdog(2.5)` boundary sequence; and on the wire a 14-row scenario near Reykjavik
played by `replay_node` at rate 2 (expected: fixes 10, refused 4, last "bad position", 104.0 m, then silent).

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_POLLING | a late or early (jittered) position crosses a tick → that tick repeats the old one, the next sees two and forwards only the newest; on arrival = one send per position, no clock to cross; mentions that a perfect clock (jitter 0) shows nothing, which is why the bug is intermittent | the drop/double mechanism without jitter, or "on arrival" without why | "the timer is too slow" |
| EXPLAIN_WINDOW | the same two-fix noise over a 10× longer time → ~10× less spread (0.40 vs 4.11); cost: the value describes the last 10 s, ~9 s to read "stopped"; a driver gets the window speed (the parked 5.5 m/s is absurd) | one side only | repeats the numbers |
| EXPLAIN_BLOCKING | two threads AND two groups let the timer run while the fix callback works; the fix callback is still one exclusive callback with ρ = 1.5 → queue full, fixes ~2 s old (depth × T); shared group = default exclusive group → threads cannot help | timer part right, fixes not explained (or the reverse) | "multi is faster" |
| EXPLAIN_SILENCE | no message → no callback; the 5 Hz tick finds the fix stale once its age > 3.0 s → 3.0–3.2 s after the stamp; the trip node times from the arrival and checks once a second → usually later (up to ~1 s), sometimes up to ~0.2 s earlier; either order is right if explained | the timeout without the tick (or the reverse) | "the GPS was stopped" |

PREDICT_… items are graded as "written" only. Use the most-wrong predictions in class (Look back 3).

## Difficulties seen (build, sandbox runs, round-1 simulated students: strong, weak, expert)

- **NAVERA vs NAVERA Lite, late fixes.** NAVERA's late-fix rule compares with the newest fix *received*; the trip
  computer uses the last *accepted* one (simpler, and the check enforces it). A student who asks is right that both
  exist.
- **Two watchdogs (Step 8).** The judge measures from the stamp with a 5 Hz tick (3.0–3.2 s); the trip node from the
  arrival with a 1 Hz tick (3.0–4.0 s). The trip node is usually later, but not always (a weak tester saw it 0.04 s
  earlier): the lab now says "usually" and has a "read after you measured" box. Accept both in EXPLAIN_SILENCE if
  explained.
- **Measured answers need evidence.** `blocking_demo.py` appends each run to `out/blocking.json` and
  `status_listener.py` each silence to `out/silence.json`; the check requires the answers to match a logged run
  (±1 ms, ±0.01 s). The listener now forgets the last GPS stamp after each NO_FIX, so a GPS stopped too soon after
  FIX prints "not measured" instead of a false 14.9 s (seen by the expert under load).
- **One terminal.** Session 2 uses background jobs and log files (each dashboard terminal tab has its own network);
  `jobs` before starting a node, `kill -INT $(jobs -p)` at the end of each step.
- **Step 6 discovery.** replay_node now waits `start_delay_s` = 3.0 s by default; with 1.0 s the trip node missed
  the first row in 2 of 4 runs (15 / 180 m instead of 16 / 190 m).
- **"3.0 s > 3.0 s"** in the judge's reason is rounding (3.04 > 3.0); say so if asked.

- **Leftover nodes.** A trip node or a GPS left running in the background makes tests 7–8 fail with the
  `publishers_ok` message ("2 node(s) publish on /navera_lite/trip…"). Step 8 ends with "stop everything".
- **Discovery lag.** `ros2 node info /trip` right after starting the node can say "Unable to find node": wait 2 s.
  The lab uses the typed `ros2 topic echo … DiagnosticStatus --once`, which waits for the publisher.
- **Replay looping.** Without `-p loop:=false`, bad_fixes.csv starts again and the jump back to the start is refused
  ("jump"), so the counts keep changing. Step 6 says to use it and to start a FRESH trip node.
- **Order of the rules.** The commonest TODO 1 mistakes (verified with mutants, see the build report): gate before the
  stamp test (the lab's hint 3 and the check name it), gate measured from a refused fix, refused fix appended.
- **The parked speed** surprises everybody (5.5 m/s): the "read after" box and mission 27.
- **`--work` must be a float** in `blocking_demo.py` (argparse accepts `0.1`, not `.1s`).

## Suggested class plan (reading at home 1 h; two sessions, about 4 h 30 in all)

- Before session 1: the lesson, with its ✏️ checks.
- **Session 1 (1 h 30):** 5 min Step 0 together (predict on the board, then run: the class sees 30 dropped / 30 doubled, then 0/0
  without jitter). 50 min TODO 1–3 with `run_trip.py test`. 20 min Step 4; 10 min discussion: why a parked car shows
  5.5 m/s and why the odometer reads 993 m. Badge.
- **Session 2 (1 h 45):** 30 min TODO 4–5 and Step 5; 20 min Step 6; 20 min Step 7 (ask two students to put their
  single and multi numbers on the board); 25 min Step 8; 10 min check and Look back.
- **Fast students:** Going further (smarter odometer; arrival vs stamp with `stamp_offset_s:=-0.8`; reentrant group
  and a shared counter).
- **Struggling students:** for §2, write 1/T (come per second) and 1/S (finished per second) on the board; give them the lesson's §3 trace as a paper exercise before TODO 1; pair them for Session 2
  (one runs the terminals, one writes answers.py); Steps 7–8 can be shown on the projector if time is short (the
  check needs each student's own out/blocking.json and out/silence.json, so they still run them).

## Files

- `make_files.py` regenerates `courses/11-subscriber/files/bad_fixes.csv` (deterministic).
- `answers.py` is a complete solution (numbers measured as above); `out/blocking.json` and `out/silence.json` are the
  matching evidence logs (copied over the lesson folder by `try_lesson --solution`).
- `navera_lite/` is generated by `tools/lite_build.py 11-subscriber` (never edit it here).

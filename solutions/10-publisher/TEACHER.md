# Mission 10 — teacher notes (Your first publisher: a fake GNSS receiver)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite: the students write `navera_lite/ros/gps_node.py`
(reference in `solutions/_navera_lite/navera_lite/ros/gps_node.py`, tags `# @part 10 todo 1–6`; `TOPIC`,
`ALTITUDE_M`, `DEFAULTS`, `FakeGps.__init__/now_s`, `NODE_CLASS` and `main` are given). Mission 13 later adds
`make_descriptor` and `CheckedGps` to the same file (its own `@part 13` tags, cut out of this copy).
Given finished: `vehicle.py` (03), `geo.py` (06), and mission 09's ROS layer (`estimate`, `guard`, `settings`,
`ros/convert`, `ros/qos`, `ros/runner`, `ros/arbiter_v0`, `ros/replay_node`). Manifest:
`solutions/_navera_lite/manifest.d/10-publisher.json`; build with ROS sourced:
`source /opt/ros/humble/setup.bash && python3 tools/lite_build.py 10-publisher`.

No NAVERA code: the old lesson quoted NAVERA's bench simulator and pointed at NAVERA's GPS node and `geo.py`;
the old `analysis.py` imported NAVERA's `dead_reckon`. All gone. NAVERA appears in words only: backlog EST-1,
EST-7, OUT-3, GPS-4, GPS-5, LOC-30 (code review of 2026-09-28), validation report 2026-10-03 (ArduPilot SITL
integration defects; GPS path bench-tested with simulated sensors; future stamps and zero covariances
refused), ARCHITECTURE (two stamps, altitude NaN when unknown). **Removed from the old mission:** the flat-Earth
error study (taught in 06), `velocity_ne` (replaced by `step()` on 03's `ground_velocity` + 06's `offset`),
`ros2 topic bw` and the 128-byte message-size paragraph. **Fixed (rebuild plan §B):** TODO comments no longer
are the code; jitter is now visible and checked (a hard-coded dt fails check 6); the orphaned
`publisher_node.svg` is replaced by `node_anatomy.svg`; E[·] is gone; sin for east / cos for north is explained
(§3, from 03's heading convention).

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 write an rclpy node class (parameters, timer, publisher); what spin does | §1 Heartbeat, ✏️; §2 parameters, type trap, ✏️ | Steps 1, 5 (TODO 4–5, `run_gps.py node`), 6 (live, param set) | 5, 7 |
| 2 integrate with the real dt; measure rate and jitter | §3 (stamps, busy timer measured, worked 20.8 vs 20.0 m, step example), ✏️ | Steps 2–3 (TODO 1, `drive`), 6 (TODO 6, `ros2 topic hz`), 7 (`jitter`) | 1, 2, 6, 9, 10 |
| 3 fill NavSatFix honestly (stamp, floats, m², UNKNOWN) | §4 table, worked σ 2.5 m, warning box, ✏️ four problems | Step 4 (TODO 2–3) | 3, 4, 6, 7 |
| 4 predict how a judge reads stamp/covariance; find where it is fooled | §5 rules, worked, ✏️; box after Step 9 | Steps 8–9 (A–D), 10 (memo) | 8, 11, 12, 13 |

Badges: **Builder** = checks 1–10 (session 1), **Saboteur** = all 13.
Note: `arbiter_v0.py` (given, mission 09) describes its own holes in its docstring; the lab asks students to
predict from lesson §5 only. The exact B message and EXPLAIN_JUMP need a run.

## Answer key

Every number below is printed by the runner or measured in the student sandbox
(`tools/try_lesson.py 10-publisher --solution --shell …`, 2026-10-13, Jetson Orin Nano).

| Item | Value | Where it comes from |
|---|---|---|
| BUG_SPEED_10HZ_MPS | 100.0 | 10 m in 0.1 s; `run_gps.py bug --rate 10` confirms (the 5 Hz figure shows 50: refused with a message) |
| NOMINAL_ERROR_M | 12.48 (accepted 12.38–12.58) | computed by the student from the stamps: 12 × (6.04 − 10 × 0.5) = 12.48; `drive` hides the NOMINAL columns until `drive --reveal`. 12 m/s × 6.04 s = 72.48 m vs 10 calls × 6 m = 60 m. Two ticks lost (deadlines 3.5 and 4.0; 4.5 called late at 4.58). 12.96 = the largest error (at 4.58 s): refused with a message |
| NOMINAL_SPEED_MAX_MPS | 14.29 (accepted ±0.1) | 6 m / 0.42 s (1.08 → 1.50). Minimum 4.11 (6 m / 1.46 s across the stall). 12.0 = the real one: refused with a message |
| MEASURED_RATE_HZ | 1.000 (accepted 0.9–1.1) | `ros2 topic hz`, default node: "average rate: 1.000" |
| MEASURED_STD_S | about 0.0004 (accepted 0 ≤ x < 0.1) | "std dev: 0.00040s"–"0.00046s" measured |
| V0_OLD (A, offset −5.0) | NO_FIX | "no usable source (gps: stale (5.0 s > 3.0 s))" (5.0–5.8 s depending on the instant) |
| V0_COARSE (B, σ 40.0) | DEGRADED | "gps: σ 40.0 m > 25.0 m" |
| V0_COARSE_REASON | `gps: σ 40.0 m > 25.0 m` (exact) | the status `message` of B: only a run gives the wording |
| EXPLAIN_FIX | e.g. to_navsatfix takes frame_id from the Estimate's source and sets service 0 (or STATUS_NO_FIX when invalid, altitude NaN by default) | convert.py vs make_fix |
| EXPLAIN_JUMP | A's stamps are 5 s behind, so its first fix is stamped BEFORE the previous receiver's last trusted fix: elapsed < 0, the gate allows only the margin and refuses reachable fixes; the gate assumes stamps only move forward | `arbiter.log`: "gps fix refused: jump 90 m > 50 m in -0.1 s" (value depends on the restart delay) |
| V0_NO_SIGMA (C, σ 0.0) | FIX — **wrong** | "gps: σ 0.0 m": v0 reads √max(0, 0) and ignores type UNKNOWN |
| V0_FUTURE (D, offset +30.0) | FIX — **wrong** | "gps: σ 3.0 m", age_s ≈ −29.4 |
| AGE_FUTURE_S | about −29.5 (accepted −31.5 to −28) | −30 plus the age of the fix at the moment of the echo (0 to 1 s) |
| FROZEN_S | about 32–33 (accepted 20–45) | the last fix is stamped t_stop + 30; v0 says NO_FIX when its age passes 3.0 s, at the next 5 Hz tick. Measured: 32.0 s and 35 s |
| Step 6 hand trace | dt 0, 0.47, 0.59 s; moved 0, 4.7, 5.9 m east; stamps = the three instants | 2 Hz, 10 m/s, heading 90°, ticks at 0.00, 0.47, 1.06 s |
| Lesson ✏️ §3 | speeds 8.0, 5.0, 20.0 m/s; 6.0 m both | 2 m per fix over 0.25 / 0.40 / 0.10 s |
| Lesson ✏️ §5 | FIX "gps: σ 20.0 m"; 1 s later NO_FIX (age 3.5 s) | √max(400, 100) |

Check 6 (real dt) passes only if every pair of consecutive fixes moves 8.0 m/s ± 2 % on heading 30° ± 2°,
while the driver delays each `on_timer` call by 0–0.2 s and one call by 1.2 s (the runner's `jitter` uses
1.3 s: both are deliberate). Check 7 changes heading, speed, σ and stamp offset while the node runs and requires
all four to take effect. All live checks run ONE script in the student's Python (their node, arbiter v0 and a
listener in one process, namespace /check10): terminal tabs and the checker have separate networks. A nominal-dt node gives speeds
such as 6.6–9.5 m/s and fails with certainty.

## Rubric for written answers (the check only verifies "written and on topic")

| Item | 2 — complete | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_DRIVE | Lost ticks are never made up, so the nominal receiver adds 0.5 s of motion per call while more time passed; the missing motion is never recovered; plus the speeds between ticks swing because the intervals are not 0.5 s | Says "the dt is wrong" without the lost ticks | Restates the numbers |
| EXPLAIN_JITTER | Each fix moves speed × the real interval, measured on the same clock as the stamp, so distance ÷ stamp difference is always the true speed; a nominal node would show speeds from a few m/s to tens of m/s | One of the two halves | "It works" |
| EXPLAIN_JUMP | Negative elapsed because the new stamps are older than the last trusted one; the gate assumes stamps only increase, so it refuses reachable fixes (NAVERA now drops a late fix as old news) | "negative" without the cause | Copies the log line |
| EXPLAIN_HOLES | C: v0 takes σ from the numbers (0.0) and never reads the type UNKNOWN → a perfect FIX for "I don't know"; D: a negative age passes "age ≤ 3 s", so a dead receiver stays fresh ~33 s; names what a better judge checks (type/zero covariance; future limit) | Finds both holes without the mechanism, or one with it | Lists the four states |
| report.md | Topic, message, honest covariance and types, measured rate and std; nominal 12.48 m and 14.3 m/s vs own 10.00 m/s; the two holes with v0's reasons and the checks of mission 12 | Two sections good | Copied from the lesson |

## Difficulties expected (from 22 wrong-solution tests and 3 reviewers, round 1; pilot still to do)

The lab runs in ONE terminal tab with background jobs (`&`, `jobs`, `kill -INT %%`), as mission 09.
`run_gps.py jitter` also tests the stamp_offset_s and sigma_m knobs, so a student who forgot them finds out
before session 2 (reviewer weak1 would otherwise have concluded a "third hole" in experiment A).

All 22 mutants in `~/academy-test/review/10-publisher/build/mutants/` fail at least one check with a message
naming the mistake (full list in the build report):

- **Heading as an ENU angle / east and north swapped in `offset`** (cos for east): check 1 "north and east are
  mirrored"; check 7 "towards 90° instead of 0°". **Degrees in `math.sin`**: check 1 "right distance, wrong
  direction (292° instead of 225°)".
- **No ValueError for dt < 0**: check 2 only.
- **Ints in the covariance** (`[v, 0, 0, …]`): check 3 names them; `make_fix` then dies with the
  300-digit AssertionError — check 4 and the live checks add "write 0.0, not 0".
- **σ instead of σ², type 2, an invented σ for None**: each has its own message in check 3.
- **`int(stamp_s)`**: check 4 "nanosec=0"; the live checks see two fixes with the same stamp.
- **Start position from DEFAULTS**, **period = rate_hz**, **`self.on_timer()`**, **absolute topic name**:
  check 5 (the inspection) names each one.
- **Nominal dt** (the classic): only check 6 catches it — the reason the jitter driver exists.
- **Parameters read once** (heading, or speed/σ/offset cached at start-up, or only the offset cached),
  **no stamp offset**, **`last_t` never updated**, **σ from DEFAULTS**: checks 6–8.
- **`sigma_m <= 0` tested before `None`**: TypeError; check 3 and the runner say "your function received
  None … test `sigma_m is None` FIRST".
- Students coming from 09 run nodes in several terminals and forget them: the check runs its own nodes in the
  namespace `/check10`, so leftovers in the student's terminals do not disturb it.
- The arbiter's jump gate may log "gps fix refused: jump …" when a receiver is restarted far from the last
  trusted fix (the lab says so). After experiment D the gate holds a future fix: the lab asks to restart the
  arbiter.

## Class plan (session 1: 2 h to 2 h 30, session 2: 1 h 15 to 1 h 30, plus 1 h of reading; meta 4 h 30)

Session 1: Step 0 together on the projector (5 min, then the hook figure). 15 min on §1 with the Heartbeat
node typed live (show the `self.on_timer()` error). Students: Steps 1–5 (60–75 min). Stop at Step 3 for a
2-minute class discussion of the busy-computer figure. Step 6 trace by hand in pairs before coding TODO 6.
End with the Builder check.
Session 2: three terminals is the hard part for beginners — demonstrate Step 8 once. Collect the four
predictions on the board before anyone runs A–D; reveal D last (the 33 s of a dead receiver kept alive is the
moment of the mission). Memo in the last 20 minutes.

**Fast students:** Going further (tunnel, the bug live with a repeater on the day topic, own geo.py).
**Struggling students:** give the Step 6 hint list as a printed checklist; pair them for Steps 8–9 (one
types, one reads the status).

## Known limits

- MEASURED_RATE_HZ / MEASURED_STD_S are real measurements: graded by ranges.
- FROZEN_S depends on when the student presses Ctrl+C and reads `date`: range 20–45 s.
- `run_gps.py jitter` is random by design (its numbers are not graded); `drive` is deterministic.
- Lesson length: about 3 400 words of prose plus code and tables (≈ 4 200 counted by `wc`), above the
  3 000-word target; §3 and §4 carry the mission.

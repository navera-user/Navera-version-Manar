# Mission 13 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — Guard the knobs** (Steps 0–4, TODO 1–4, badge **Knob guard** = milestone
`knob_guard`, checks 1–7) and **Session 2 — One command** (Steps 5–10, TODO 5, badge **Integrator** when every
check passes). Rebuilt 2026-10-13 on NAVERA Lite (no NAVERA code, files or launch). The hook is NAVERA's
R-1 (review of 1 October 2026) and LOC-30 (review of 28 September 2026), in words, from ENGINEERING_BACKLOG.md;
the 4–1 890 km/h start-up range from TROUBLESHOOTING.md; "cruise + 50 %" from FIELD_TEST_PROCEDURE.md; the
day-vision 5 s (production) vs 3 s (node default) from ARCHITECTURE.md.

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Typed parameters, descriptors, validation callback; which guard acts when | §1, §2 (robot heading) | Steps 0–3 (TODO 1–3) | 1, 2, 3, 5, 6 |
| 2. Predict and measure precedence | §3 (b.yaml / c.yaml, four commands) | Steps 5–6 (my_gps.yaml, six commands incl. (f)) | 8, 9 |
| 3. A launch file: namespaces, arguments, condition, remap | §4 (judge in /test), §5 (string default, int param) | Step 7 (TODO 5) | 10, 11, 12 |
| 4. Change a setting, predict the verdict; check a whole file against the vehicle (R-1) | §6 (bridge gap, plane 80/90 m/s) | Steps 4, 8 (PREDICT_PLANE), 9 (PREDICT_SIGMA) (TODO 4) | 4, 7, 11, 13, 14, 15 |

## Answer key (measured in the sandbox, ROS 2 Humble, 2026-10-13)

- Step 0: `-p max_speed_mps:=30` → `InvalidParameterTypeException: Trying to set parameter 'max_speed_mps' to '30'
  of type 'INTEGER', expecting type 'DOUBLE'`. `ros2 param set /arbiter fix_max_sigma_m 2.0` → "Set parameter
  successful", `param get` → 2.0, the status stays `gps: σ 3.0 m` (FIX): arbiter v0 copies its settings into its
  judge at start. `SET_REPORTED_OK = True`, `STATE_AFTER_SET = "FIX"` (PREDICT_SET is asked before; the lesson's
  "Read once" answer is behind a "Read this after lab Step 0" box).
- Step 2: `ros2 param describe /fake_gps speed_mps` shows the description and Min 0.0 / Max 100.0.
  `rate_hz 5.0` → "Trying to set a read-only parameter: rate_hz." `speed_mps 500.0` → "Parameter speed_mps out of
  range Min: 0.0, Max: 100.0, value: 500.0". Start with `-p speed_mps:=150.0` → `InvalidParameterValueException`
  (traceback), the node does not start. All three False. Before TODO 3 a change that passes the descriptor is
  refused with "Callback returned an invalid type" (the stub returns None; no crash) — the lab says so.
- Step 3: `vehicle boat` accepted (10.0 ≤ 20.0), then `speed_mps 25.0` → "speed_mps 25.0 > 20.0 m/s, the top speed of
  a boat": `BOAT_25_OK = False`. Attacker: `-p vehicle:=boat -p speed_mps:=25.0` starts, `param get` → 25.0
  (`ATTACK_SPEED = 25.0`): the callback is registered after the declarations and is never called for start values;
  only type and range act at start.
- Step 4: `integrator.yaml` → 4 problems: gps_timeout_s int, gps_jump_margin_m int, night_timeout_s 0.0, max_speed_mps
  15.0 < 20.0 for a boat. `navera_lite.yaml` → 0.
- Step 6 (drone, my_gps.yaml with `/**` first and the drone at 18.0): (a) 10.0 (b) 18.0 (c) 18.0 (d) 18.0 (e) 25.0
  (f) 30.0 (fast.yaml creates the drone's row first, my_gps.yaml's `/**` row lands below it, `-p` writes that row).
  The model of lesson §3 (one row per section name, created at first appearance, overwritten in place, `-p` = the
  `/**` row, lowest matching row wins) predicted all 20 command lines measured while building, and the lesson's
  worked examples (a.yaml + -p → 180.0; a.yaml → 0.0; b.yaml, b + -p, -p + b → 45.0). Most students predict
  25.0 for (c): that is the point of the step. If a student's my_gps.yaml puts `/**` last, (c) gives 25.0 — check
  test 8 refuses that file anyway.
- Step 7: `ros2 node list` → /arbiter, /boat/fake_gps, /drone/fake_gps (≈ 2 s after the launch; first status 1.5 s).
  Default: the judge subscribes to /drone/navera_lite/fix/gps, status `gps: σ 3.0 m`, longitude grows (east 12 m/s).
  `gps_source:=boat`: latitude grows, longitude stays 10.6084. `use_boat:=false gps_source:=boat` → level 3,
  "no position received yet" (STARTING) forever, no error: `NO_BOAT_STATE = "STARTING"`. `--show-args` lists the
  two arguments. Ctrl+C → "process has finished cleanly" ×3, exit 0.
- Step 8: plane.yaml (vehicle plane, 30.0) + plane at 85 m/s: first fix FIX, then "jump 85 m > 80 m in 1.0 s",
  "jump 170 m > 110 m in 2.0 s"…; after 10 s NO_FIX "no usable source (gps: stale (… > 3.0 s); last fix refused:
  jump … )" (measured with 90 m/s: "jump 990 m > 380 m in 11.0 s"). `run_lab13.py settings plane.yaml` →
  "max_speed_mps must be >= 100.0 for a plane, got 30.0". With 100.0: FIX. `PLANE_STATE_30 = "NO_FIX"`,
  `PLANE_STATE_100 = "FIX"`.
- Step 9: PREDICT_SIGMA first; status level 1, `gps: σ 3.0 m > 2.0 m` (DEGRADED). `diff` shows the single
  fix_max_sigma_m line.
- Step 7: the judge also gets `-p vehicle:=<gps_source>` (TODO 5, round 1: a substitution in params, so TODO 5 is
  not a copy of the §5 example). `ros2 topic echo` prints the level as a byte (`"\x03"` = STARTING): the lab says so.
- Lesson checks: §3 b.yaml (1)(2)(3) → 45.0, c.yaml + `-p` (4) → 180.0 (the `/**` row is created BELOW the node's row:
  `-p` wins; measured in rclpy and rclcpp by the expert reviewer); §4 judge in /test → STARTING forever (measured);
  §5 `default_value` is text; `"rate": 2` crashes replay; a launch argument without a default is required ("missing
  required argument 'file'", measured); §6 bridge: boat 18 m/s, limit 10, margin 50, 7 s gap → 126 m > 120 m, locked out
  (safe gaps < 50 / 8 ≈ 6.25 s); plane 80 m/s accepted (80 ≤ 80) only without a lost fix (160 > 110), 90 m/s locked out.
  Check yourself 3 (robot heading) → starts with 270.0, set 200.0 refused.
- launch_ros `Node(parameters=[file, {dict}])` writes the dict to a temporary params file under the node's full name:
  it beats the file's node section; `fl_node`'s `-p` does not (lesson §5; launch_util docstring).

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_SILENT | the judge reads its settings once at start and builds its rules from them; the stored value changed, the used one did not; needs a restart (or read_only to say so) | "it needs a restart" without why | "ROS bug" |
| EXPLAIN_GUARDS | the callback is registered after the declarations, so start values never reach it; only type and range act at start; start values need their own check (check_settings / call the rule in declare_all) | names the start but not the registration order | "the callback is wrong" |
| EXPLAIN_PRECEDENCE | (c) `-p` writes the `/**` row, which sits above the drone's own row → 18.0; (e) fast.yaml uses the same section name → overwrites that row in place → 25.0; (f) fast.yaml created the drone row first, so the `/**` row (and the `-p`) is below → 30.0 | two of the three | "files win" |
| EXPLAIN_REMAP | the judge listens to /boat/navera_lite/fix/gps where nobody publishes → no position ever → STARTING; nothing crashes or warns, so an operator may wait or fly on a judge that never judged | the topic but not the danger | restates STARTING |
| EXPLAIN_R1 | 30 m/s + 50 m = 80 m per second < 85 m flown → the jump gate refuses real fixes, each refusal widens the gap faster than the gate → stale → NO_FIX; check_settings (or NAVERA's start-up range check) would refuse the file before take-off | the gate but not the lock-out, or no prevention | "the plane is too fast" |
| report.md | each section uses the student's own numbers and states a rule; "One setting per vehicle" links R-1 to a start-time check | numbers without the rule | template text |

## Difficulties expected (from the mutants and the sandbox runs)

- `floating_point_range = FloatingPointRange(...)` (not a list) → TypeError at message construction.
- Callback registered before the loop → the node does not start: "Callback returned an invalid type" while TODO 3 is a
  stub, `ParameterNotDeclaredException` after. run_lab13 now names the cause (weak reviewer lost 25 min on it).
- TODO 4: a text value ('fast') must give "must be a float, got 'fast'" (the docstring now numbers the six rules and
  says so); the check rejects "write fast.0" and gives the expected keys when a case fails.
- `my_gps.yaml` with `boat/fake_gps:` (no first slash) is accepted (ROS reads it as `/boat/fake_gps`); `fake_gps:` is not.
- Comparing the **current** speed instead of the new one (25.0 accepted for a boat); reading only new values
  (`KeyError: 'vehicle'` when only the speed changes, which rclpy turns into a crashed `param set`).
- `return True` from the callback → "Callback returned an invalid type".
- `-p speed_mps:=12` / `params={"speed_mps": 12}` in the launch file → the receiver dies with
  InvalidParameterTypeException, silently in launch.log while the rest runs; `run_lab13.py launch` and `test` now
  flag it (⚠), and the lab says "three nodes; only two? grep died launch.log".
- `"/" + LaunchConfiguration(...)` → TypeError when the launch file is loaded.
- Background jobs: `ros2 launch … &` in a non-interactive script ignores Ctrl+C (SIGINT); students always run it in
  its own terminal tab, so this only matters for teachers scripting demos (`set -m`, then `kill -INT -PID`).
- Discovery: the first `ros2 param get` 2 s after a cold start can say "Node not found": ask again.

## Class plan (2 × 2 h)

- Session 1: 15 min hook (R-1, LOC-30 live: Step 0 on the projector), 20 min §2 table, then Steps 1–4. Badge at the end.
- Session 2: 10 min §3 model on the board (draw the rows for one example), students predict Step 6 **before**
  running; 20 min §5 example; Steps 7–9; report at home.
- Fast students: Going further (start-time guard, third vehicle, colcon package). Struggling students: give the
  §5 example printed and let them adapt it line by line for TODO 5; pair them for Step 6 (one runs, one asks).

## Files

- `courses/13-launch-params/files/`: generated `navera_lite/` (manifest `solutions/_navera_lite/manifest.d/13-launch-params.json`),
  `navera_lite.yaml` (generated once), hand-written `run_lab13.py`, `runner_kit.py` (copy), `answers.py`,
  `my_gps.yaml` (starter comment only), `integrator.yaml`, `fast.yaml`, `report.md`.
- `solutions/13-launch-params/`: answers, my_gps.yaml, plane.yaml, navera_lite.yaml (fix_max_sigma_m 2.0) and its
  `.orig`, report.md. No dataset.
- Expected values are constants in `check.py` (computed from the reference); the check's ROS tests run the
  student's node in-process (rclpy, `set_parameters_atomically`, the same path as `ros2 param set`) and the
  student's launch file twice: a dry run (substitutions resolved for 4 argument sets) and a real `ros2 launch`
  (≈ 15 s). Whole check ≈ 30–40 s. Real time (round 1): strong ≈ 3 h 20 in all, weak ≈ 6 h (reading ≈ 100 min): meta.json says 5 h 30.

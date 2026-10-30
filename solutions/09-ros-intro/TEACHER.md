# Mission 09 — teacher notes (The ROS 2 graph: nodes, topics, discovery and QoS)

Rebuilt 2026-10-13 on NAVERA Lite (no NAVERA code, files or topics). Students run the given nodes
`navera_lite.ros.arbiter_v0` and `navera_lite.ros.replay_node`, map them with the `ros2` CLI, write **one** stack
TODO (`ros/qos.py` `incompatible_policies()`, which `compatible()` (given) wraps), repair a mission file (`imu_listener.py`, the I-F3 bug), and write TODO 2 `latched_probe.py` (a late
subscriber of a latched topic; graded since round 2: it is the only rclpy code they write from scratch and closes
the B3 loop with their own node; ≈ 15 min, inside the 5 h card).
Duration on the card: 5 h (reading 60–90 min, lab 2 h 45–3 h 45; weak reviewer measured 85 min + 3 h 20 before TODO 2 was added). Two sessions, badges **Cartographer**
(checks 1–7) and **QoS detective** (all 13).

**Platform fact the whole lab is built around:** each dashboard terminal tab (and the check) runs in its own
bubblewrap sandbox with `--unshare-net`, so ROS nodes started in one tab are invisible in another. Everything is
done in ONE tab with background jobs (`&`, `jobs`, `kill -INT %%`, `kill -INT $(jobs -p)`); the check starts its own
publishers. If the platform later shares one network per student, the lab still works; only the warning box at the
top of lab.md becomes too strong.

## Alignment

| Objective | Lesson | Lab | Check |
|---|---|---|---|
| 1. map a live graph with the `ros2` CLI | §1, §6 | Steps 2, 3, 5, 6 | 3, 4, 6, 7 |
| 2. read rclpy code → edges of the graph | §3 (Replay worked example, ✏️ logger) | Steps 1–2 (`python3 -m`, ArbiterV0.__init__), Step 4 (who calls `step()`) | 2, 3, 5 |
| 3. explain discovery, domains, localhost | §4 (WEB-12 worked example) | Steps 2 (lag, EXPLAIN_LAG), 6 | 3, 7 |
| 4. predict QoS compatibility, write it | §5 (ladders, tables, worked pairs) | Steps 7–8 | 8, 9, 10 |
| 5. diagnose and repair a QoS mismatch | §5 plain-number trap, §6 detective table | Steps 0, 9, 10 | 11, 13 |
| 4–5. latched topics, late subscribers | §5 latched (box after Step 7) | Step 7 B1–B3, Step 11 TODO 2 | 8, 12 |

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| MODULE_ERROR | ModuleNotFoundError (`No module named 'navera_lite'`) | running the file by its path |
| ARBITER_SUBSCRIBES | /navera_lite/fix/{gps,day,night,celestial}, /navera_lite/imu | `ros2 node info /arbiter` |
| ARBITER_PUBLISHES | /navera_lite/position, /navera_lite/status | idem (without /rosout, /parameter_events) |
| EXTRA_PARAMS | use_eligible (declared in ArbiterV0.__init__), use_sim_time (every rclpy node) | `ros2 param list /arbiter` (14 names) vs the 12 yaml keys |
| STATUS_NO_FIX | −1 | `ros2 interface show sensor_msgs/msg/NavSatFix` |
| DEGRADED_LEVEL | 1 (WARN) | convert.LEVELS + DiagnosticStatus constants (STARTING worked: STALE = 3); seen live in Step 4's `--field level` watch: `b'\x00'`, `b'\x01'`, `b'\x00'` (and `b'\x03'` if the watch starts before the first fix) |
| TODO 2 latched_probe.py | subscription with STATUS_QOS (RELIABLE + TRANSIENT_LOCAL), print the first `msg.message` | check: one-shot latched publisher with a random message, probe started 4 s later; VOLATILE and BEST_EFFORT+TL fail (Fast DDS) |
| STATUS_HZ | 5.4–7.5 measured (check accepts 5.2–8.0, refuses exactly 5.0) | 5 Hz tick + one decision per arriving fix (GPS 1/s + day 0.5/s ⇒ ≈ 6.5; ≈ 5.5 during the GPS gap) |
| GATE_ALLOWED_M | 950 (check 930–970) | first refusal: `jump 4990 m > 950 m in 9.0 s` (last trusted fix at t = 11 s, spoof at 20 s: 100 × 9 + 50); second `4980 m > 1050 m in 10.0 s` |
| STATUS_PUBLISHERS | 2 | `ros2 topic info /navera_lite/status`; both logs print the "2 judges" ERROR within 5 s |
| OTHER_DOMAIN_SEES_STATUS | False | the other domain lists only /parameter_events and /rosout (the CLI's own node) |
| A1 / A2 | False / True | BEST_EFFORT pub vs RELIABLE / BEST_EFFORT sub |
| B1 / B2 / B3 | True / False / False | late TL+RELIABLE gets "go"; VOLATILE gets nothing old; TL+BEST_EFFORT matched but no history (Fast DDS, Humble's default; RMW-dependent) — B3 is the intended surprise: the lesson's explanation sits in a "read after Step 7" box |
| INCOMPATIBLE_POLICY | RELIABILITY | the WARN line of A1 |
| LISTENER_REQUESTS | RELIABLE | doctor / `ros2 topic info -v` |
| incompatible_policies() | "RELIABILITY" if offer BEST_EFFORT ∧ request RELIABLE; "DURABILITY" if offer VOLATILE ∧ request TRANSIENT_LOCAL; [] otherwise | 7 of 16 combinations non-empty, 1 with both names; same names as the WARN line; for a pair where both fail the WARN line shows only RELIABILITY, the function returns both |
| imu_listener repair | `SENSOR_QOS` (or `qos_profile_sensor_data`, or any BEST_EFFORT+VOLATILE profile) | measured 27–51 msgs in 5 s after the repair (discovery eats ≈ 1–2 s) |

Step 0 / Step 9: the broken listener prints `heard 0 IMU messages in 5.0 s` and itself logs the incompatible-QoS WARN;
`ros2 topic echo` (no QoS options) prints the IMU because the CLI adapts its request to the publisher.

## Rubric for written answers (the check only verifies "written and on topic")

| Item | 2 (good) | 1 (partial) | 0 |
|---|---|---|---|
| EXPLAIN_LAG | discovery takes ~1 s and the daemon cache is cold; a node needs 3–5 s to start; waited for the log line and listed again | "it takes time" without discovery, or nothing about what to do | "the node was broken" |
| EXPLAIN_HZ | tick at 5 Hz **and** `on_fix` → `step()` on every arrival, so ≈ 5 + arrivals/s | only one of the two causes | "jitter", "ROS is imprecise" |
| EXPLAIN_GATE | gate counts from the last **trusted** fix (t = 11 s), 9 s × 100 m/s + 50 m; GPS gap 12–19 s | formula without why 9 s | 150 m / copies the log |
| EXPLAIN_TWO_JUDGES | decoupling: nothing limits publishers on a name; subscribers get two interleaved answers and cannot tell them apart | one side only | "ROS forbids it" |
| EXPLAIN_ISOLATION | a stranger in the same domain on the same network can publish fixes the judge trusts; private domain + localhost-only | one setting | vague "security" |
| EXPLAIN_TEN | a plain int is only the depth; the rest is the default profile, RELIABLE + VOLATILE | "10 is RELIABLE" | wrong |
| EXPLAIN_REPAIR | requests BEST_EFFORT (accepts both kinds); the driver/publisher belongs to someone else and other subscribers rely on it | one reason | "changed SENSOR_QOS" (wrong place) |

## Difficulties expected (from the sandbox runs and 16 wrong-solution tests; no pilot with real students yet)

- **Start-up and discovery lag:** a Python node needs 3–5 s to start here (arbiter's first log line ≈ 3–5 s);
  the lab waits for the log line (`until grep -q started arbiter.log; …`) and lists twice.
- **Job numbers:** `%N` shifts when a stopped job is not yet reaped; the lab uses `%%` (last background job) and
  `kill -INT $(jobs -rp) 2>/dev/null` (running jobs only, silent). `jobs` may show Exit 2 (ros2 topic pub) / Exit 15. A student who restarts nodes several times may stop the wrong one: `jobs` first.
- **Order in Step 4:** arbiter started after the replay, during scenario seconds 12–20, trusts the spoof first and
  logs `> 150 m in 1.0 s` (check message and hint 2 cover it).
- **Echo through a pipe** shows nothing without `PYTHONUNBUFFERED=1` (Python block-buffers into pipes): kept in the
  command with one sentence of explanation. `timeout 35` prints `Terminated`: said in the lab.
- **"A message was lost!!!"** on the latched status: harmless, said in Step 3.
- Round 1 (2026-10-13): grader tightened against the expert's misconceptions (timer jitter, "10 is RELIABLE",
  changed the publisher, "ROS should forbid it", gate formula without why 9 s) — all now refused.
- Mutants run (all caught, messages in the build report): reliability-only, durability-only, swapped arguments,
  equality instead of ladder, depth compared, string "True", one combined `and`, comparing with text, a typo crash;
  listener unchanged, explicit RELIABLE, BEST_EFFORT+TRANSIENT_LOCAL (message names DURABILITY), STATUS_QOS,
  "fixing" the publisher's SENSOR_QOS (caught by the profile check); answers: ImportError, names without `/`, a
  published topic in subscribes, WARN level 1, tick 5.0, quoted numbers/booleans, wrong observations.

## Class plan

- Session 1 (1 h 15–1 h 30): 5 min Step 0 together (project the silent listener) → students read §1–§4 (25 min) →
  Steps 1–6. Debrief: draw the graph on the board from their `node info`; ask "who stops a third judge?".
- Session 2 (1 h 15–2 h): read §5–§6 (20 min) → Step 7 predictions in pairs before running → Step 8 TODO →
  Steps 9–10 → Step 11 TODO 2. Debrief with I-F3: one line, 4/4 → 3/3 frames.
- Fast students: Going further (late joiners with depth 3 → 3 messages; namespaces `/boat`; ports with `ss -uln`).
- Struggling students: the 🧰 jobs box first; pair them for Step 7; Step 8 hints 1–5 (hint 3: print(offered.reliability) for the text-vs-constant trap).

## Known limits

- The status rate depends on the scenario phase; the accepted range is wide on purpose.
- Domain +1 for Step 6: the dashboard's sandboxes have private networks, so the next domain is always empty; with
  try_lesson's test domains (200–232) a domain 232 student would get 233 (invalid) — only the last test domain.
- NAVERA facts used (in words): acceptance findings 2026-10-03 (I-F3: 4/4 unusable → 3/3), code review 2026-09-28
  (WEB-12), ARCHITECTURE (sensors BEST_EFFORT depth 50; latched start/ready/start-position; loopback + own domain;
  status at 5 Hz).

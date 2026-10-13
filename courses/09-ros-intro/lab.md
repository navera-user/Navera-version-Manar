# Lab 9 — The silent listener: map a ROS 2 graph, then repair it

**Goal:** run NAVERA Lite's first judge and its replay node, map their graph with the `ros2` tools, read their code,
measure what the judge does, then reproduce the I-F3 bug of the brief (a listener that hears nothing), write the rule
that predicts it, and repair it.
**Time:** 2 h 30 to 3 h 30 (a student who knows Linux well: about 2 h). **Fast track:** skip the 🧰 boxes and the
"Stuck?" boxes; after Step 10, do "Going further".

Your files (📝 Code tab): [answers.py](file:./answers.py) (everything you measure and explain),
[imu_listener.py](file:./imu_listener.py) (the integrator's broken listener: **you repair it**),
[navera_lite/ros/qos.py](file:./navera_lite/ros/qos.py) (**your TODO 1**), [qos_doctor.py](file:./qos_doctor.py)
(runs your TODO on examples and on the live graph; you don't edit it), and the given nodes you read:
[arbiter_v0.py](file:./navera_lite/ros/arbiter_v0.py), [replay_node.py](file:./navera_lite/ros/replay_node.py),
[convert.py](file:./navera_lite/ros/convert.py).

| Lesson | Lab | You do |
|---|---|---|
| (nothing to read first) | Step 0 | watch a listener hear nothing |
| §1–§3 Graph, messages, nodes | Steps 1–4 | run nodes, map them, read their code, measure the judge |
| §1, §4 Decoupling, domains | Steps 5–6 | two judges; another domain |
| §5 QoS | Steps 7–8 | five experiments; TODO 1 `incompatible_policies()` |
| §5–§6 The detective's toolbox | Steps 9–10 | find the broken pair; repair `imu_listener.py` |

> [!WARNING] One terminal tab for the whole lab
> In this academy each terminal tab is a small private computer of its own: a node started in one tab **cannot be
> seen** from another tab. Run every command of this lab in the **same** tab, and start the nodes in the
> background with `&` (the 🧰 box below shows how).

<details><summary>🧰 Several programs in one terminal (open it before Step 0 if <code>&amp;</code> and <code>jobs</code> are new to you)</summary>

```bash
python3 -m http.server 8000 > web.log 2>&1 &      # & = run in the background; > web.log 2>&1 = all its output into web.log
jobs                                              # [1]+  Running   python3 -m http.server 8000 > web.log 2>&1 &
tail -n 3 web.log                                 # the last 3 lines of its log
kill -INT %1                                      # job 1 gets SIGINT, exactly what Ctrl+C sends (mission 02 §5)
jobs                                              # [1]+  Done ... (or nothing): it has stopped
```

`%1` is the **job number** that `jobs` prints in brackets, not a PID; `%%` means "my most recent background
job" (the `+` line of `jobs`). A background program cannot read your keyboard, so `Ctrl+C` does not reach it: use
`kill -INT %N`. Before you start a node, run `jobs`: never leave two copies of the same node running.

- **Forgot the `&`?** The terminal is busy with the node and does not give the prompt back: press `Ctrl+C` and type
  the command again, with `&`.
- `jobs` may show `Done`, `Interrupt`, `Exit 2` or `Exit 15` for a job you stopped: all mean "stopped"
  (`ros2 topic pub` ends with code 2 after `Ctrl+C`).
- **Retrying a step?** Stop the old copy first (`jobs`, then `kill -INT %N`): with two copies, `%%` points at the
  newest one only.
- **Stop everything** that still runs, without complaints when nothing is left (`jobs -rp` = the process numbers of
  the running jobs):
  `kill -INT $(jobs -rp) 2>/dev/null; sleep 1; jobs`
</details>

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` is written **before** you run the step. It is never marked right or
> wrong; being wrong and finding out why is the point. Text in quotes, numbers without, `True`/`False` with a
> capital letter, lists in brackets.

## Session 1 — Map the graph (about 1 h 15)

## Step 0 — The silent listener

Start the replay node in the background. It publishes a 30 s scenario of position fixes and, ten times per second,
an IMU message (a "heartbeat": the judge only checks that the IMU is alive):

```bash
python3 -m navera_lite.ros.replay_node > replay.log 2>&1 &
```

Now run the integrator's listener. It listens to the IMU topic for 5 s and says how many messages it heard:

```bash
python3 imu_listener.py
```

Is the data there? Ask ROS for one IMU message (its header only):

```bash
ros2 topic echo /navera_lite/imu sensor_msgs/msg/Imu --once --field header
```

Topic present, data present, publisher present, and the listener heard nothing. (It also printed a WARN line: keep
it in mind, you will understand every word of it in session 2.)

> [!TASK]
> `PREDICT_SILENT`: how can a listener hear nothing on a topic that exists and that `ros2 topic echo` can read? Any
> honest guess.

Stop the replay (your most recent background job, `%%`), then read the lesson's §1–§4:

```bash
kill -INT %%
```

## Step 1 — Run a node from a package

Your lesson folder holds a **package**, `navera_lite/`: a folder with an `__init__.py`, whose modules import each
other by their full names (`from navera_lite.estimate import Estimate`).

<details><summary>🧰 Packages and <code>python3 -m</code></summary>

```
lessons/09-ros-intro/              ← run commands from HERE (the folder that holds the package)
  weather/                         a package: a folder with an __init__.py
    __init__.py                    runs once, at the first `import weather…`
    units.py                       def c_to_f(c): return c * 9 / 5 + 32
    report.py                      from weather.units import c_to_f   (absolute import)
```

`python3 -m weather.report` means "run the module weather.report" (dots, no `.py`): Python puts the **current**
folder first on its search path, so `from weather.units import …` finds the package. `python3 weather/report.py`
puts only the file's own folder (`weather/`) on the path, where there is no `weather` package. And from inside
`weather/`, even `-m` fails: the package must be in the current folder.
</details>

First the wrong way, on purpose. Read the **last** line of the error:

```bash
python3 navera_lite/ros/arbiter_v0.py
```

> [!TASK]
> `MODULE_ERROR`: the error's name (the first word of the last line).

Now the right way. Start arbiter v0, the judge, with its settings file (`--ros-args` starts the ROS options;
`--params-file` gives every parameter of `navera_lite.yaml` to the node):

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml > arbiter.log 2>&1 &
```

A Python ROS node needs 3 to 5 s to start on this computer. This command waits until the log says "started" (it
checks once per second), then prints the log. If it never comes back, press `Ctrl+C` and read `cat arbiter.log`:
the node crashed.

```bash
until grep -q started arbiter.log; do sleep 1; done; cat arbiter.log
```

It says it started, and its first decision: STARTING (no position received yet). Keep it running until Step 6.

## Step 2 — Read the code, then map the node

Open [arbiter_v0.py](file:./navera_lite/ros/arbiter_v0.py) and find `class ArbiterV0(Node)` and its `__init__`
(below the line "the ROS node"). With lesson §3's table, list every `create_subscription` and
`create_publisher`. Two Python details:

- `for name in SOURCES:` creates one subscription per source; `SOURCES` is defined in
  [estimate.py](file:./navera_lite/estimate.py).
- `lambda msg, name=name: self.on_fix(name, msg)` is a one-line function: when a message arrives on that fix
  topic, ROS calls it, and it calls `on_fix` with the source's name.

> [!TASK]
> `PREDICT_SUBSCRIBES`: from the code only, which topics will `/arbiter` subscribe to? Write them before the next
> command.

```bash
ros2 node list
```

Empty, or `/arbiter` missing? Discovery (lesson §4): run it again a few seconds later. Then:

```bash
ros2 node info /arbiter
```

`/parameter_events` and `/rosout` belong to every node (parameter changes, log messages); leave them out.
Now its parameters. `navera_lite.yaml` gave it twelve; how many does it have?

```bash
ros2 param list /arbiter
```

Read one value (`ros2 param get` asks the node through one of its services):

```bash
ros2 param get /arbiter fix_max_sigma_m
```

> [!TASK]
> `ARBITER_SUBSCRIBES` and `ARBITER_PUBLISHES` (lists of full topic names, as `ros2 node info` prints them). Did
> your prediction miss one? Which line of the code was it? `EXTRA_PARAMS`: the parameters of `ros2 param list` that
> are **not** keys of [navera_lite.yaml](file:./navera_lite.yaml) (a list of names); for each, find where it comes
> from (`ArbiterV0.__init__`? every node?). `EXPLAIN_LAG`: was a listing empty or incomplete right after a start?
> Why can that happen, and what do you do (lesson §4)?

## Step 3 — Message types

The fix topics carry `sensor_msgs/msg/NavSatFix`:

```bash
ros2 interface show sensor_msgs/msg/NavSatFix
```

The indented lines under `NavSatStatus status` are the nested message, with its constants (the lines with `=`).
The judge's status is a `DiagnosticStatus`:

```bash
ros2 interface show diagnostic_msgs/msg/DiagnosticStatus
```

Which level does arbiter v0 use for each state? Open [convert.py](file:./navera_lite/ros/convert.py) and find
`LEVELS`. Now look at the judge's status right now (it is still STARTING):

```bash
ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --once
```

`level` is a byte, printed `"\x03"` for byte 3. Read it as a chain: `LEVELS["STARTING"]` in convert.py is
`DiagnosticStatus.STALE`, and the interface says `STALE=3`, hence `"\x03"`. Do the same chain for NO_FIX. (If the
echo prints *"A message was lost!!!"* first: harmless, the latched status keeps only its last message and the echo
joined late, so it sees a gap in the message numbers.)

> [!TASK]
> `STATUS_NO_FIX` (the value of that NavSatStatus constant) and `NO_FIX_LEVEL` (the level number the arbiter
> puts in its status when the state is NO_FIX).

## Step 4 — Watch the judge decide

Open [replay_node.py](file:./navera_lite/ros/replay_node.py) and read the docstring of `demo_rows()`: the 30 s
scenario, second by second. The arbiter is running and has heard nothing yet. **Start the replay now** (the order
matters for this step: the judge must hear the scenario from its first second):

```bash
python3 -m navera_lite.ros.replay_node > replay.log 2>&1 &
```

Watch the judge's reasons for 35 s. `--field message` prints only the reason of each status, `grep -v -- ---`
removes the `---` separators, `uniq` prints a line only when it changes, and `timeout 35` stops it all after
35 s (it then prints `Terminated`: expected). `PYTHONUNBUFFERED=1` makes the echo (a Python program) pass on each
line at once: into a pipe, Python would otherwise keep its output in blocks of several kilobytes, and you would see
nothing:

```bash
PYTHONUNBUFFERED=1 timeout 35 ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --field message | grep --line-buffered -v -- --- | uniq
```

Match each line with the scenario (your times may differ by a second). The spoofed GPS of 20–21 s never shows in
the status: the jump gate refused it before the judge stored it. The arbiter wrote why in its log:

```bash
grep refused arbiter.log | head -3
```

> [!TASK]
> `GATE_ALLOWED_M`: in the **first** `refused` line, the distance the gate allowed (the number after `>`).
> `EXPLAIN_GATE`: why that much, and not the 150 m of mission 01's example? (Mission 01 §5. In the scenario, when
> did the gate accept its last GPS fix before the spoof?)

How often does the judge publish its status? `navera_lite.yaml` says `tick_hz: 5.0`.

> [!TASK]
> **Predict** (`PREDICT_HZ`): how many status messages per second?

```bash
timeout 8 ros2 topic hz /navera_lite/status
```

> [!TASK]
> `STATUS_HZ`: the last `average rate`. `EXPLAIN_HZ`: why that rate? Look in `ArbiterV0` for **every** place that
> calls `self.step()`.

<details><summary>Stuck? Hints</summary>

1. No `refused` line? The replay must start **after** the arbiter, and the 30 s scenario must reach 20 s. Run the
   `grep` again after a minute.
2. Your first `refused` line says `> 150 m in 1.0 s`? The arbiter started in the middle of a scenario lap, so its
   gate trusted a spoofed fix first. Stop both (`kill -INT $(jobs -p)`), start the arbiter, then the replay, wait
   30 s, and `grep` again.
3. `ros2 topic hz` prints nothing for a few seconds: it needs a window of messages; wait for `average rate`.
</details>

## Step 5 — Two judges

What stops a second judge from publishing on the same status topic? Start one (the same code, so the same node
name):

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml > arbiter2.log 2>&1 &
```

Wait about ten seconds (the node starts, then it counts publishers every 5 s), then:

```bash
ros2 topic info /navera_lite/status
```

```bash
grep ERROR arbiter.log arbiter2.log | head -2
```

(`ros2 node list` would now also print a WARNING: two nodes share the name `/arbiter`. ROS runs both.)

Arbiter v0 counts the publishers on its own status topic every 5 s and logs an ERROR when there are more than one
(NAVERA's judge reports a second judge too; the message says "Ctrl+C in its terminal" because a judge normally
runs in a terminal of its own). Now stop the extra judge, and only that one: it is your most recent background
job (the `+` line of `jobs`, the one that ends with `arbiter2.log`):

```bash
jobs
```

```bash
kill -INT %%
```

> [!TASK]
> `STATUS_PUBLISHERS`: the publisher count you saw with two judges. `EXPLAIN_TWO_JUDGES`: why does ROS allow it
> (lesson §1), and what does a node that subscribes to the status receive then?

## Step 6 — Another domain is another world

```bash
echo "domain $ROS_DOMAIN_ID, localhost only: $ROS_LOCALHOST_ONLY"
```

List the topics from the next domain. The variable is changed for this one command only (mission 02 §4);
`--no-daemon` asks the network directly instead of the daemon's cache, during `--spin-time 3` seconds:

```bash
ROS_DOMAIN_ID=$((ROS_DOMAIN_ID + 1)) ros2 topic list --no-daemon --spin-time 3
```

Compare with your own domain:

```bash
ros2 topic list
```

(`/parameter_events` and `/rosout` exist in every domain where at least one node runs: here, the `ros2` command's
own node.)

> [!TASK]
> `OTHER_DOMAIN_SEES_STATUS` (`True` or `False`). `EXPLAIN_ISOLATION`: NAVERA's WEB-12 (lesson §4) in your words:
> what could go wrong, and which two settings prevent it?

End of session 1: stop every background job, then check that `jobs` prints nothing (or only `Done`,
`Interrupt` or `Exit` lines):

```bash
kill -INT $(jobs -rp) 2>/dev/null; sleep 1; jobs
```

Press **✔ Check my work**: checks 1–7 earn the **Cartographer** badge. Before session 2, read lesson §5–§6.

## Session 2 — The silent listener (about 1 h 15 to 2 h)

## Step 7 — Offered vs requested, by hand

Five experiments with hand-made publishers and subscribers (`ros2 topic pub` and `ros2 topic echo` take QoS options).

> [!TASK]
> **Predict** (`PREDICT_QOS`) with the two tables of lesson §5, before you run anything: in each of the five
> experiments A1, A2, B1, B2, B3 below, will at least one message arrive?

**A — reliability.** A publisher that offers BEST_EFFORT, twice per second:

```bash
ros2 topic pub -r 2 /qos_test std_msgs/msg/String "{data: hello}" --qos-reliability best_effort > /dev/null &
```

A1, a subscriber that requests RELIABLE (it stops by itself after 6 s):

```bash
timeout 6 ros2 topic echo /qos_test std_msgs/msg/String --qos-reliability reliable
```

A2, a subscriber that requests BEST_EFFORT:

```bash
timeout 6 ros2 topic echo /qos_test std_msgs/msg/String --qos-reliability best_effort
```

Read the WARN lines of A1 (the background publisher prints one too: its errors still reach your terminal). Stop
the publisher, your most recent background job:

```bash
kill -INT %%
```

**B — durability: a latched message and late subscribers.** One message, kept for late subscribers (`-w 0`: do not
wait for a subscriber; `--keep-alive 120`: stay alive 120 s to keep it):

```bash
ros2 topic pub --once -w 0 --keep-alive 120 --qos-depth 1 --qos-durability transient_local /mission_start std_msgs/msg/String "{data: go}" > /dev/null &
```

Wait a few seconds: every subscriber below arrives **late**. B1, TRANSIENT_LOCAL + RELIABLE:

```bash
timeout 8 ros2 topic echo --once /mission_start std_msgs/msg/String --qos-durability transient_local --qos-reliability reliable
```

B2, VOLATILE + RELIABLE:

```bash
timeout 8 ros2 topic echo --once /mission_start std_msgs/msg/String --qos-durability volatile --qos-reliability reliable
```

B3, TRANSIENT_LOCAL + BEST_EFFORT:

```bash
timeout 8 ros2 topic echo --once /mission_start std_msgs/msg/String --qos-durability transient_local --qos-reliability best_effort
```

Stop the latched publisher:

```bash
kill -INT %%
```

> [!TASK]
> The five booleans `BE_PUB_RELIABLE_SUB_RECEIVED` (A1), `BE_PUB_BE_SUB_RECEIVED` (A2),
> `LATE_TL_RELIABLE_RECEIVED` (B1), `LATE_VOLATILE_RECEIVED` (B2), `LATE_TL_BEST_EFFORT_RECEIVED` (B3): what you
> **saw**. `INCOMPATIBLE_POLICY`: the last word of A1's WARN line. Which of your predictions were wrong? Now open the box "Read this after
> lab Step 7" in lesson §5: does it explain the surprise?

## Step 8 — TODO 1: `incompatible_policies()`

Open [navera_lite/ros/qos.py](file:./navera_lite/ros/qos.py). The three profiles are given.
`incompatible_policies(offered, requested)` is yours: the list of the policies that stop a publisher that offers
`offered` from serving a subscriber that requests `requested`, named like ROS's WARN line (`"RELIABILITY"`,
`"DURABILITY"`), or `[]` when they connect. The given `compatible()` below it is one line on top of yours. The
docstring gives two examples.

<details><summary>🧰 QoS profiles in Python</summary>

```python
from rclpy.qos import HistoryPolicy, QoSProfile
p = QoSProfile(history=HistoryPolicy.KEEP_ALL, depth=1)
p.history                                # <HistoryPolicy.KEEP_ALL: 2>  — a named constant (an "enum")
p.history == HistoryPolicy.KEEP_ALL      # True: compare with the constant, not with the text "KEEP_ALL"
p.history.name                           # 'KEEP_ALL' — the text, for printing
```

`ReliabilityPolicy` and `DurabilityPolicy` are imported at the top of `qos.py` and work the same way
(`ReliabilityPolicy.BEST_EFFORT`, `DurabilityPolicy.VOLATILE`…). A list that grows: `bad = []`, then
`bad.append("X")`, then `return bad` (mission 03).
</details>

Test it on the docstring's examples and three more pairs:

```bash
python3 qos_doctor.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Two separate questions: can the offered reliability serve the requested one? Can the offered durability serve
   the requested one? Each "no" adds one name to the list; two "no" give two names.
2. Each table of lesson §5 has exactly **one** ✘ cell. Write down, for each, the offered and the requested value
   of that cell: those are the only two reasons to add a name.
3. Your rule looks right but the doctor never says NO CONNECTION? You probably compared with text
   (`== "BEST_EFFORT"`). Add `print(offered.reliability)` in the function and run the test again: it prints
   `ReliabilityPolicy.BEST_EFFORT`, a constant, not text. Compare with the constant (🧰 box above).
4. `FIX_QOS → SENSOR_QOS` gives NO CONNECTION and `SENSOR_QOS → FIX_QOS` gives connect? You swapped the roles: the
   **first** argument is the publisher's offer.
5. `FIX_QOS → FIX_QOS` gives NO CONNECTION? You refuse whenever the policies differ: the ✘ is one precise
   combination, not "different". `SENSOR_QOS → STATUS_QOS` must list both names.
</details>

## Step 9 — The doctor on the live graph

Start the replay, the judge and the broken listener (for 30 s), each in the background:

```bash
python3 -m navera_lite.ros.replay_node > replay.log 2>&1 &
```

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml > arbiter.log 2>&1 &
```

```bash
python3 imu_listener.py 30 > listener.log 2>&1 &
```

Wait until the judge has started (the listener was started at the same time):

```bash
until grep -q started arbiter.log; do sleep 1; done; sleep 1
```

`qos_doctor.py` asks ROS who publishes and who subscribes on a topic, prints what each endpoint offers or
requests, and judges every pair with **your** `incompatible_policies()`:

```bash
python3 qos_doctor.py /navera_lite/imu
```

Compare with what ROS itself prints (find the `Reliability:` line of each endpoint):

```bash
ros2 topic info -v /navera_lite/imu
```

After 30 s, read the listener's verdict:

```bash
cat listener.log
```

> [!TASK]
> `LISTENER_REQUESTS`: the reliability `imu_listener` requests, as printed. `EXPLAIN_TEN`: `imu_listener.py`
> never wrote "RELIABLE". Where does it come from (lesson §5)?

## Step 10 — The repair

Repair [imu_listener.py](file:./imu_listener.py): change what its subscription **requests** (one line; plus an
import if you use a profile from another module). Do not touch the given profiles of `qos.py`: in real life the
publisher is somebody else's driver. The replay still runs, so test at once:

```bash
python3 imu_listener.py
```

(Fewer than 50 messages in 5 s is normal: the first second or two go to starting the node and discovery.)
Then let it run in the background and ask the doctor again:

```bash
python3 imu_listener.py 20 > listener.log 2>&1 &
```

```bash
python3 qos_doctor.py /navera_lite/imu
```

<details><summary>Stuck? Hints</summary>

1. The bug is in the last argument of `create_subscription`.
2. NAVERA Lite already defines a profile that requests BEST_EFFORT: which one, in `qos.py`? Import it with
   `from navera_lite.ros.qos import …` (you run the listener from the lesson folder, so the package is found).
3. Still 0? Run `jobs`: is the replay still running? Did its log (`cat replay.log`) say "replaying"?
</details>

> [!TASK]
> `EXPLAIN_REPAIR`: what you changed, and why the repair belongs in the **subscriber** and not in the publisher.

Clean up, then press **✔ Check my work**. The check starts its own IMU publishers (one BEST_EFFORT, one
RELIABLE) and runs your listener against both.

```bash
kill -INT $(jobs -rp) 2>/dev/null; sleep 1; jobs
```

## Step 11 — Look back (not graded)

1. In Step 0 you guessed why the listener was silent. What would you check first today, and with which command?
2. The I-F3 fix in NAVERA requested BEST_EFFORT with depth 50 for every vehicle sensor. What does depth 50 protect
   against that BEST_EFFORT does not?
3. Arbiter v0 logs an ERROR when a second judge appears, but it keeps publishing. Should it stop? What could go
   wrong either way?

## Going further (optional)

- **Late joiners and depth.** Publish three latched messages with `--qos-depth 3`
  (`ros2 topic pub -t 3 -w 0 --keep-alive 30 --qos-depth 3 --qos-durability transient_local /hist std_msgs/msg/String "{data: x}" > /dev/null &`),
  then start a late `ros2 topic echo /hist std_msgs/msg/String --qos-durability transient_local --qos-reliability reliable --qos-depth 10`.
  How many messages arrive? Repeat with `--qos-depth 1` on the publisher and explain.
- **Namespaces.** Start a second judge in the namespace `/boat`:
  `python3 -m navera_lite.ros.arbiter_v0 --ros-args -r __ns:=/boat --params-file navera_lite.yaml > boat.log 2>&1 &`.
  What do `ros2 node list` and `ros2 topic list` show now? Does it hear the replay? Does it trigger the two-judges
  ERROR? Why (lesson §1, relative names)? Mission 13 builds on this.
- **Check your rule against ROS's.** rclpy has its own checker:
  `python3 -c "from rclpy.qos import qos_check_compatible; from navera_lite.ros.qos import *; print(qos_check_compatible(SENSOR_QOS, FIX_QOS))"`.
  Compare it with your `incompatible_policies()` on the 16 pairs of the two tables. What does a `WARNING` result
  mean (try `STATUS_QOS, SENSOR_QOS`)? Which policies does it look at that you did not?
- **A latched probe.** Write `latched_probe.py` (about 15 lines; copy `main()` from `imu_listener.py`): it subscribes
  to `/navera_lite/status` with a QoS you choose and prints the first status it gets. Start it 10 s after the
  arbiter. Which profile makes it print at once? Which never does?
- **Ports.** With a node running, `ss -uln` lists the open UDP ports. Find your domain's discovery port with the
  formula of the optional box of lesson §4 (`echo $((7400 + 250 * ROS_DOMAIN_ID))`), then the pairs of ports of
  each program.

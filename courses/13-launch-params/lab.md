# Lab 13 — Guard the knobs, then start everything with one command

**Goal:** give NAVERA Lite's fake GNSS receiver guarded parameters, write the start-time check of the
judge's settings, write a settings file for two vehicles and measure which value wins, write the stack's
launch file, and then break and repair a configuration the way R-1 did.
**Time:** 3 to 4 h in two sessions (a fast student: about 2 h 30).

Your files (📝 Code tab):
[navera_lite/ros/gps_node.py](file:./navera_lite/ros/gps_node.py) (**TODO 1–3**, at the bottom: mission 10's
`FakeGps` above them is finished), [navera_lite/settings.py](file:./navera_lite/settings.py) (**TODO 4**),
[navera_lite/ros/navera_lite_launch.py](file:./navera_lite/ros/navera_lite_launch.py) (**TODO 5**),
[my_gps.yaml](file:./my_gps.yaml) (you write it), [answers.py](file:./answers.py),
[report.md](file:./report.md). `run_lab13.py` tries your code without starting nodes by hand.

| Lesson | Lab | You write |
|---|---|---|
| §1 Types | Step 0 | nothing: two traps, live |
| §2 Guards | Steps 1–3 | `make_descriptor`, `CheckedGps.declare_all`, `CheckedGps.on_set_parameters` |
| §6 Whole-file check | Step 4 | `check_settings` |
| §3 Files, precedence | Steps 5–6 | `my_gps.yaml`, five measurements |
| §4–§5 Names, launch | Step 7 | `generate_launch_description` |
| §6, In NAVERA | Steps 8–9 | `plane.yaml`, one edit of `navera_lite.yaml` |

> [!WARNING] One terminal tab for the whole lab
> In this academy each terminal tab is a small private computer of its own: a node started in one tab **cannot be
> seen** from another tab. Run every command of this lab in the **same** tab: nodes run in the background with `&`,
> their output goes to a log file, and `kill -INT %%` stops the last one (mission 09's 🧰 box). Before you start a
> node, run `jobs`: it must not list an old copy. `kill -INT $(jobs -p)` stops them all.

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` is written **before** you run the step. It is never marked
> right or wrong. **Discovery takes a moment:** after you start a node, wait 2 s before you ask about it.
> If `ros2 param get` says `Node not found`, ask again; the first `ros2 node list` after a pause can be
> empty or incomplete.

## Session 1 — Guard the knobs (about 1 h 45)

## Step 0 — Two traps (no code)

> [!TASK]
> **Predict** (`PREDICT_INT`): the judge is started with `-p max_speed_mps:=30`. What happens?

This one runs in the foreground (it stops by itself):

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml -p max_speed_mps:=30
```

Read the **last** line of the error. Now start it correctly (`30.0`), in the background:

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml -p max_speed_mps:=30.0 > arbiter.log 2>&1 &
```

The judge needs a GPS. Your `gps_node` cannot start before TODO 2, so play the demo recording of mission 09
(after 3 s, GPS with σ 3 m for 11 s):

```bash
python3 -m navera_lite.ros.replay_node > replay.log 2>&1 &
```

Wait about 5 s for a FIX, then ask the judge to be stricter than 3 m, and read its verdict again:

```bash
ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --once --field message
```

```bash
ros2 param set /arbiter fix_max_sigma_m 2.0
```

```bash
ros2 param get /arbiter fix_max_sigma_m
```

```bash
ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --once --field message
```

(The demo repeats every 30 s: if the message does not start with `gps:`, ask again a few seconds later. `A message was lost!!!` above a message is harmless: the status is published faster than `echo` reads it.)
Stop both nodes:

```bash
kill -INT $(jobs -p)
```

> [!TASK]
> `SET_REPORTED_OK` (True / False), `STATE_AFTER_SET` ("FIX", "DEGRADED" or "NO_FIX": `gps: σ 3.0 m` with
> no "> …" is FIX) and `EXPLAIN_SILENT`: why did the verdict not follow? (Lesson §2, "Read once".)

## Step 1 — Descriptors (TODO 1)

Open [gps_node.py](file:./navera_lite/ros/gps_node.py) and scroll to **TODO 1**, `make_descriptor(name, value)`.

<details><summary>🧰 Building a message object, and an optional field (open if needed)</summary>

ROS messages are Python objects; their fields can be given by name, or set later:

```python
from rcl_interfaces.msg import IntegerRange, ParameterDescriptor
d = ParameterDescriptor(description="number of retries")
d.integer_range = [IntegerRange(from_value=0, to_value=5, step=1)]   # a LIST holding one range
print(d.integer_range[0].to_value, d.read_only)                     # 5 False
```

A field you never set keeps its default (`read_only` is `False`, a range list is empty).
</details>

```bash
python3 run_lab13.py test
```

The TODO 1 lines must be ✔. The other groups fail until you write them.

<details><summary>Stuck? Hints, one at a time</summary>

1. One descriptor with the description, then add a range only for the four names of the docstring's table.
2. A dict `{name: (low, high)}` avoids four `if`s.
3. `floating_point_range` is a **list**: `[FloatingPointRange(from_value=…, to_value=…, step=0.0)]`.
4. `AssertionError: The 'floating_point_range' field must be a set or sequence …`: you gave one range,
   not a list holding it.
</details>

## Step 2 — Declare with guards (TODO 2)

**TODO 2** `CheckedGps.declare_all`: like mission 10's `FakeGps.declare_all` (just above, finished), but
each `declare_parameter` gets a third argument, and the callback is registered after the loop.
(`on_set_parameters` is still a stub: ROS will refuse every change that reaches it with "Callback
returned an invalid type". That is expected until Step 3.)

```bash
python3 run_lab13.py test
```

The first three TODO 2–3 lines must be ✔. Then start your node in the background:

```bash
python3 -m navera_lite.ros.gps_node > gps.log 2>&1 &
```

Two seconds later, read what an integrator now sees:

```bash
ros2 param describe /fake_gps speed_mps
```

> [!TASK]
> **Predict** (`PREDICT_GUARDS`): which of the next three commands are refused, and by which guard?
> `ros2 param set /fake_gps rate_hz 5.0`, `ros2 param set /fake_gps speed_mps 500.0`, and starting the
> node with `-p speed_mps:=150.0`.

```bash
ros2 param set /fake_gps rate_hz 5.0
```

```bash
ros2 param set /fake_gps speed_mps 500.0
```

Stop it, and start it again (in the foreground) with a value out of range:

```bash
kill -INT %%
```

```bash
python3 -m navera_lite.ros.gps_node --ros-args -p speed_mps:=150.0
```

> [!TASK]
> `RATE_SET_OK`, `SPEED_500_OK`, `START_150_RUNS` (True / False each).

<details><summary>Stuck? Hints</summary>

1. `declare_parameter(name, value, descriptor)`: the descriptor comes from your TODO 1.
2. Do not forget the two lines that set `self.lat` and `self.lon` (copy them from `FakeGps.declare_all`).
3. `add_on_set_parameters_callback(self.on_set_parameters)` — the method itself, **no** brackets after
   its name.
4. The node crashes at start with `ParameterNotDeclaredException`? You registered the callback before
   the loop (lesson §2: it is then called for each declaration).
</details>

## Step 3 — A rule across two parameters (TODO 3), then attack it

**TODO 3** `CheckedGps.on_set_parameters(params)`. Its docstring gives the rule and the exact example.

<details><summary>🧰 A dict from a list, and <code>dict.get</code> with a fallback</summary>

```python
pairs = [("a", 1), ("c", 3)]
d = {k: v for k, v in pairs}          # {'a': 1, 'c': 3}
print(d.get("a", 0), d.get("b", 0))   # 1 0  — the second value is used when the key is missing
```

In the callback each item of `params` has `.name` and `.value`.
</details>

```bash
python3 run_lab13.py test
```

Then live:

```bash
python3 -m navera_lite.ros.gps_node > gps.log 2>&1 &
```


```bash
ros2 param set /fake_gps vehicle boat
```

```bash
ros2 param set /fake_gps speed_mps 25.0
```

> [!TASK]
> `BOAT_25_OK` (True / False). Stop the node: `kill -INT %%`.

<details><summary>Stuck? Hints</summary>

1. Build `new = {name: value}` from `params`; the vehicle and the speed are each the new value when it is
   there, else `self.get_parameter(…).value`.
2. The vehicle test comes first: `VEHICLES[vehicle]` of an unknown vehicle is a `KeyError`.
3. `ros2 param set … speed_mps 25.0` is accepted for the boat? You compared the **current** speed, not the
   new one. `KeyError: 'vehicle'`? You read only the new values: a change of the speed alone does not
   carry the vehicle.
4. "Callback returned an invalid type": return `SetParametersResult(successful=…, reason=…)`, not `True`.
</details>

**Now be the attacker.** Your callback guards every change. Does it guard the **start**?

```bash
python3 -m navera_lite.ros.gps_node --ros-args -p vehicle:=boat -p speed_mps:=25.0 > gps.log 2>&1 &
```

```bash
ros2 param get /fake_gps speed_mps
```

> [!TASK]
> `ATTACK_SPEED`: the value you read. `EXPLAIN_GUARDS`: why did the callback not refuse it, and which
> guard, or which check, acts at start? Stop the node (`kill -INT %%`).

## Step 4 — Check a whole settings file (TODO 4)

**TODO 4** `check_settings(cfg)` in [settings.py](file:./navera_lite/settings.py): every rule broken, as a
list of sentences, in the docstring's order. The last TODO with the least help: before you code, apply the
five rules **by hand** to [integrator.yaml](file:./integrator.yaml) and write down what you expect.

<details><summary>🧰 Types: <code>isinstance</code>, and why <code>True</code> is an int</summary>

```python
isinstance(3.0, float), isinstance(3, float), isinstance(3, int)   # True False True
isinstance(True, int)          # True!  a bool is a kind of int in Python: test bool first
[k for k in {"a_s": 1, "b": 2} if k.endswith("_s")]                 # ['a_s']
```
</details>

```bash
python3 run_lab13.py test
```

```bash
python3 run_lab13.py settings navera_lite.yaml
```

```bash
python3 run_lab13.py settings integrator.yaml
```

> [!TASK]
> `N_INTEGRATOR_PROBLEMS`: how many problems your function finds in `integrator.yaml`. Does it match
> your hand check? If not, which of you is right?

<details><summary>Stuck? Hints</summary>

1. Five loops or blocks, one per rule, each appending sentences to one list; return the list at the end.
2. Rule 1 loops over `DEFAULTS.items()`: the type of the **default** says what the value must be.
3. `max_speed_mps must be >= …` never appears? The rule needs the vehicle's limit: `VEHICLES[vehicle]`,
   and only when the vehicle is known.
4. Your count differs from your hand check? Print the list: each sentence starts with its key. One key
   can rightly appear twice (one value can break two rules); a rule that never speaks: test its
   condition by hand on that value.
</details>

> [!TIP] 🏅 End of session 1 — Knob guard
> Press **✔ Check my work**. When the checks of TODO 1–4 and Steps 0–4 pass, you earn the **Knob guard**
> badge (the other ✘ lines are session 2).

## Session 2 — One command (about 2 h)

## Step 5 — Two vehicles in one file

Complete [my_gps.yaml](file:./my_gps.yaml) with three sections, in this order:

- `/**`: `rate_hz` 1.0 and `sigma_m` 3.0 (every receiver);
- `/drone/fake_gps`: `vehicle` "drone", `speed_mps` 18.0, `heading_deg` 90.0;
- `/boat/fake_gps`: `vehicle` "boat", `speed_mps` 6.0, `heading_deg` 45.0, `start_lat` 35.7800,
  `start_lon` 10.8600 (at sea, off Monastir).

Start the boat in its namespace:

```bash
python3 -m navera_lite.ros.gps_node --ros-args -r __ns:=/boat --params-file my_gps.yaml > gps.log 2>&1 &
```

```bash
ros2 param get /boat/fake_gps start_lat
```

```bash
ros2 topic list
```

`head -1 gps.log` also says where it publishes. Stop it: `kill -INT %%`.

<details><summary>Stuck? Hints</summary>

1. Copy the lesson §3 example and change it: two levels of indentation (2 and 4 spaces).
2. `start_lat` stays 35.8256? The section name must be the full name `/boat/fake_gps`, with the first slash.
3. The node crashes with `InvalidParameterTypeException`: a number without `.0`.
</details>

## Step 6 — Who wins? Measure it

Each command below starts the **drone** in the background. After each one: wait 2 s, ask
`ros2 param get /drone/fake_gps speed_mps`, then stop it with `kill -INT %%` before the next one.
[fast.yaml](file:./fast.yaml) is given: open it.

> [!TASK]
> **Predict** (`PREDICT_PRECEDENCE`): the five values, with the lesson §3 model (rows!). Then measure.

(a)

```bash
python3 -m navera_lite.ros.gps_node --ros-args -r __ns:=/drone > gps.log 2>&1 &
```

(b)

```bash
python3 -m navera_lite.ros.gps_node --ros-args -r __ns:=/drone --params-file my_gps.yaml > gps.log 2>&1 &
```

(c)

```bash
python3 -m navera_lite.ros.gps_node --ros-args -r __ns:=/drone --params-file my_gps.yaml -p speed_mps:=25.0 > gps.log 2>&1 &
```

(d)

```bash
python3 -m navera_lite.ros.gps_node --ros-args -r __ns:=/drone -p speed_mps:=25.0 --params-file my_gps.yaml > gps.log 2>&1 &
```

(e)

```bash
python3 -m navera_lite.ros.gps_node --ros-args -r __ns:=/drone --params-file my_gps.yaml --params-file fast.yaml > gps.log 2>&1 &
```

The question, after each one, then the stop:

```bash
ros2 param get /drone/fake_gps speed_mps
```

```bash
kill -INT %%
```

> [!TASK]
> `SPEED_DEFAULT`, `SPEED_FILE`, `SPEED_FILE_THEN_P`, `SPEED_P_THEN_FILE`, `SPEED_TWO_FILES`, and
> `EXPLAIN_PRECEDENCE`: why did `-p` lose in (c), and why did `fast.yaml` win in (e)? Draw the rows of (c)
> and (e) on paper first.

## Step 7 — The launch file (TODO 5)

**TODO 5** `generate_launch_description()` in
[navera_lite_launch.py](file:./navera_lite/ros/navera_lite_launch.py). The lesson §5 example has every piece
you need; the docstring says what to start. Check what it **would** start, without starting anything:

```bash
python3 run_lab13.py launch
```

```bash
python3 run_lab13.py launch use_boat:=false gps_source:=boat
```

Read every command line: namespaces, `-p` values (with `.0`?), and the judge's remap. Then for real:

```bash
ros2 launch navera_lite/ros/navera_lite_launch.py > launch.log 2>&1 &
```

Wait 3 s; `cat launch.log` shows every process's lines, prefixed with its name. Then:

```bash
ros2 node list
```

```bash
ros2 node info /arbiter
```

```bash
ros2 topic echo /navera_lite/position sensor_msgs/msg/NavSatFix --once --field longitude
```

The drone flies east at 12 m/s: run the last command twice, a few seconds apart, and the longitude grows.
Stop the launch, then look at the end of its log: every process should end with "process has finished cleanly":

```bash
kill -INT %%
```

```bash
tail -n 4 launch.log
```

Now the boat (north, 5 m/s):

```bash
ros2 launch navera_lite/ros/navera_lite_launch.py gps_source:=boat > launch.log 2>&1 &
```

The latitude grows and the longitude stays put:

```bash
ros2 topic echo /navera_lite/position sensor_msgs/msg/NavSatFix --once
```

Stop it: `kill -INT %%`.

> [!TASK]
> **Predict** (`PREDICT_NO_BOAT`): with `use_boat:=false gps_source:=boat`, what will the judge say?

```bash
ros2 launch navera_lite/ros/navera_lite_launch.py use_boat:=false gps_source:=boat > launch.log 2>&1 &
```

```bash
ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --once
```

> [!TASK]
> `NO_BOAT_STATE` (level 0 = FIX, 1 = DEGRADED, 2 = NO_FIX, 3 = STARTING; the message says it too) and
> `EXPLAIN_REMAP`. Stop the launch (`kill -INT %%`).

<details><summary>Stuck? Hints</summary>

1. Five items in the list: two `DeclareLaunchArgument`, three `fl_node`.
2. The judge's remap target is a **list** joined at run time: `["/", gps_source, "/navera_lite/fix/gps"]`.
3. `TypeError: can only concatenate str (not "LaunchConfiguration")`: lesson §5.
4. A receiver dies with `InvalidParameterTypeException`: `speed_mps: 5` instead of `5.0` (or heading `0`).
5. The boat still starts with `use_boat:=false`? `condition=IfCondition(LaunchConfiguration("use_boat"))`
   belongs to the boat's `fl_node`.
</details>

## Step 8 — One speed for every vehicle (R-1)

An integrator installs NAVERA Lite on a fixed-wing plane. He copies the drone's settings and changes the
vehicle only. Make his file:

```bash
cp navera_lite.yaml plane.yaml
```

Open [plane.yaml](file:./plane.yaml), set `vehicle: "plane"` and `max_speed_mps: 30.0` (a drone's limit), save.

> [!TASK]
> **Predict** (`PREDICT_PLANE`): the plane flies at 85 m/s, one fix per second, judged with these
> settings. What will the judge say after 10 s?

The judge with the plane's file, and the plane:

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file plane.yaml > arbiter.log 2>&1 &
```

```bash
python3 -m navera_lite.ros.gps_node --ros-args -p vehicle:=plane -p speed_mps:=85.0 > gps.log 2>&1 &
```

Wait 10 s, read the judge's log, then its verdict:

```bash
cat arbiter.log
```


```bash
ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --once
```

Stop both (`kill -INT $(jobs -p)`). Your check would have refused the file before take-off:

```bash
python3 run_lab13.py settings plane.yaml
```

Set `max_speed_mps: 100.0` in plane.yaml, save, start the two nodes again (the same two commands), wait 10 s,
and read the verdict again.

> [!TASK]
> `PLANE_STATE_30`, `PLANE_STATE_100` and `EXPLAIN_R1`. Keep plane.yaml at 100.0. Stop both nodes:
> `kill -INT $(jobs -p)`.

## Step 9 — Change one setting of your stack

Your client demands FIX only within 2 m. Your receivers state σ 3 m. Keep a copy first:

```bash
cp navera_lite.yaml navera_lite.yaml.orig
```

In [navera_lite.yaml](file:./navera_lite.yaml) set `fix_max_sigma_m: 2.0` (keep the 4 spaces before it), save, and launch:

```bash
ros2 launch navera_lite/ros/navera_lite_launch.py > launch.log 2>&1 &
```

```bash
ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --once
```

> [!TASK]
> `SIGMA_STATE` and `SIGMA_MESSAGE` (copy the message). Stop the launch (`kill -INT %%`). Then see your change the way a
> reviewer would; only one line may differ:

```bash
diff navera_lite.yaml.orig navera_lite.yaml
```

Keep `fix_max_sigma_m: 2.0`: the check reads it.

## Step 10 — Report, check, look back

Fill [report.md](file:./report.md) (three headings, at least 40 words each, with your numbers), then press
**✔ Check my work**. It tests your functions on cases they have never seen, starts your node and your
launch file, and reads your files (about one minute). It starts its own nodes: run `jobs` first and stop
anything still running (`kill -INT $(jobs -p)`). Every check passed: **Integrator** badge.

Look back (not graded):

1. Which guard would have stopped NAVERA's R-1 before the first flight, and which would not?
2. Which of your Step 6 predictions was wrong, and what did you believe about `-p`?
3. A wrong remap gave silence, not an error. How would you make that mistake loud?

## Going further (optional)

- **Guard the start too.** In `CheckedGps.declare_all`, after declaring, call your own
  `on_set_parameters` with the start values (`[self.get_parameter(n) for n in DEFAULTS]`) and raise a
  `ValueError` with its reason when it refuses. Re-run the attacker's command of Step 3.
- **A third vehicle.** Add a robot (`VEHICLES["robot"]` = 10 m/s) in `/robot`, with a launch argument
  `use_robot`, and make `gps_source:=robot` work. How many lines did it take?
- **Your own settings file in the launch.** Give the receivers `params_file="my_gps.yaml"` and remove their
  `params`. With the §3 model, predict what changes; check with `ros2 param get`.
- **A real package.** Make `navera_lite` an `ament_python` package (`package.xml`, `setup.py` with the
  launch file in `share/`), build it with `colcon build --symlink-install` in a workspace under your home,
  and start it with `ros2 launch navera_lite navera_lite_launch.py`. Which line of the launch file is no
  longer needed?

# Lab 13 — One command for a configurable system

**Goal:** make the fake GNSS node configurable like a product node (descriptors and a validation
callback in [fake_gps_node.py](file:./fake_gps_node.py)), write a parameters file for two vehicles
([my_gps.yaml](file:./my_gps.yaml)), measure the precedence rules, write a launch file that starts a
car, a boat and NAVERA ([my_navera.launch.py](file:./my_navera.launch.py)), fall into NAVERA's order
trap on purpose, and change one of NAVERA's own settings. Record measurements in
[answers.py](file:./answers.py) and the analysis in [report.md](file:./report.md).
**Time:** about 3 h. Two terminals are enough; `Ctrl+C` stops a node or a launch.

## Step 1 — The starting point

**Terminal 1**:

```bash
python3 fake_gps_node.py
```

It logs `fake GPS (car) on /fake_gps/fix at 2.0 Hz from (23.588, 58.3829)`. **Terminal 2**:

```bash
ros2 param describe /fake_gps speed_mps
```

Only `Type: double` and an empty description: nothing tells an integrator what this number means or
which values are sensible. Stop the node.

## Step 2 — Descriptors (TODO 1)

> [!TASK]
> **TODO 1** — `make_descriptor(description, lo, hi, read_only)` returns a `ParameterDescriptor` with
> the description, the read-only flag and, when `lo` is given, a `FloatingPointRange` [lo, hi].

Start the node again (Terminal 1) and in Terminal 2:

```bash
ros2 param describe /fake_gps speed_mps
```

Now: the description and `Min value: 0.0`, `Max value: 60.0`. Try to change a read-only parameter, then
an out-of-range value:

```bash
ros2 param set /fake_gps rate_hz 5.0
```

```bash
ros2 param set /fake_gps speed_mps 500.0
```

> [!TASK]
> Fill `RATE_SET_ACCEPTED` and `SPEED_500_ACCEPTED` (`True` / `False`). Stop the node.

## Step 3 — A rule across two parameters (TODO 2)

A range cannot say "15 m/s is fine for a car but too fast for a boat". A validation callback can.

> [!TASK]
> **TODO 2a** — `check_settings(vehicle, speed_mps)` returns `""` or the exact reason of the
> docstring. **TODO 2b** — `on_set_parameters` combines the new and the current values and returns a
> `SetParametersResult`.

Test the plain function first:

```bash
python3 -c "from fake_gps_node import *; print(repr(check_settings('car', 12.0)), '|', check_settings('boat', 20.0), '|', check_settings('tank', 1.0))"
```

Expected: `'' | speed 20.0 m/s too fast for a boat (max 15.0) | unknown vehicle 'tank' (car, drone or boat)`.
Then live — start the node (Terminal 1) and in Terminal 2:

```bash
ros2 param set /fake_gps speed_mps 45.0
```

`Setting parameter failed: speed 45.0 m/s too fast for a car (max 40.0)`. Changing the vehicle is
checked against the current speed (5 m/s), so this works:

```bash
ros2 param set /fake_gps vehicle drone
```

Stop the node. Invalid settings are also refused **at start** (the node checks them in `__init__`):

```bash
python3 fake_gps_node.py --ros-args -p vehicle:=boat -p speed_mps:=20.0
```

## Step 4 — Two vehicles in one file (TODO 3)

> [!TASK]
> **TODO 3** — complete `my_gps.yaml`:
> - `/**` (first!): `rate_hz` **1.0** (like NAVERA's real receiver), `sigma_m` **3.0**;
> - `/car/fake_gps`: vehicle `"car"`, start **23.5880 / 58.3829** (Muscat), speed **12.0**, heading **90.0**;
> - `/boat/fake_gps`: vehicle `"boat"`, start **24.3500 / 56.7500** (off Sohar), speed **5.0**, heading **45.0**.

Start the boat: a namespace (`-r __ns:=/boat`), a remapping that makes the absolute topic relative
(`-r /fake_gps/fix:=fix`) and the file:

```bash
python3 fake_gps_node.py --ros-args -r __ns:=/boat -r /fake_gps/fix:=fix --params-file my_gps.yaml
```

It logs `fake GPS (boat) on /boat/fix at 1.0 Hz from (24.35, 56.75)`. In Terminal 2:

```bash
ros2 topic list
```

```bash
ros2 param get /boat/fake_gps vehicle
```

```bash
ros2 param set /boat/fake_gps speed_mps 20.0
```

> [!TASK]
> Fill `BOAT_FAST_ACCEPTED`. Stop the boat. Now start it **without** the remapping (same command
> without `-r /fake_gps/fix:=fix`) and run `ros2 topic list` again: where do the fixes go, and why?
> (Course, section 4.) Stop it.

## Step 5 — Who wins? Measure it

Run each line in **Terminal 1** (stop the previous one first), then in **Terminal 2**
`ros2 param get /car/fake_gps rate_hz` and note the value.

```bash
python3 fake_gps_node.py --ros-args -r __ns:=/car
```

```bash
python3 fake_gps_node.py --ros-args -r __ns:=/car --params-file my_gps.yaml
```

```bash
python3 fake_gps_node.py --ros-args -r __ns:=/car --params-file my_gps.yaml -p rate_hz:=4.0
```

```bash
python3 fake_gps_node.py --ros-args -r __ns:=/car -p rate_hz:=4.0 --params-file my_gps.yaml
```

The question for each, in Terminal 2:

```bash
ros2 param get /car/fake_gps rate_hz
```

> [!TASK]
> Fill `RATE_CODE_DEFAULT`, `RATE_FROM_FILE`, `RATE_FILE_THEN_P` and `RATE_P_THEN_FILE`. Stop the node.

Optional but instructive: move the `/**:` section to the **end** of `my_gps.yaml`, give `rate_hz: 3.0`
to `/car/fake_gps`, and measure again with the file alone. Then put the file back as the TODO says.

## Step 6 — The launch file (TODO 4 to 8)

Open `my_navera.launch.py`; its docstring says what it starts.

> [!TASK]
> **TODO 4** — `fake_gps(namespace, condition)` returns a `Node` for the script, with the file and
> the remapping. **TODO 5** — the launch arguments `with_boat` and `gps_source`. **TODO 6** — NAVERA's
> GNSS bridge with `fix_topic` built from `gps_source`. **TODO 7** — NAVERA's estimator launch file,
> included with `gps_timeout_s` = 2.0. **TODO 8** — the car, the boat (with its condition) and the
> final list.

**Terminal 1**:

```bash
ros2 launch ./my_navera.launch.py
```

Read the start: the warning about `NAVERA_MAX_SPEED_KMH` (not configured in the sandbox — normal),
then one line per process: `[fake_gps_node.py-1] … fake GPS (car) on /car/fix`, the boat, `GPS from
/car/fix`, and `estimator up … gps_timeout=2.0s`.

> [!NOTE]
> When you press `Ctrl+C` on `ros2 launch`, you will see Python tracebacks that end with
> `KeyboardInterrupt` (from several processes, even your `fake_gps_node.py`), and lines like
> `[ERROR] [fake_gps_node.py-1]: process has died [pid 31, exit code -2, …]`. This is **normal**
> shutdown noise: exit code -2 means "stopped by Ctrl+C" (signal 2). It is not a crash of your code.

In **Terminal 2**:

```bash
ros2 node list
```

```bash
ros2 topic echo /navera/nav_status --field reason
```

**`GPS fix`** — the same result as lesson 11, with one command. Where is NAVERA? (`Ctrl+C` after one
message.)

```bash
ros2 topic echo --once /navera/position --field latitude
```

About 23.588: the car in Muscat. Stop the launch, then try the two arguments:

```bash
ros2 launch ./my_navera.launch.py with_boat:=false
```

(`ros2 node list` in Terminal 2: no `/boat/fake_gps`.) Stop it.

```bash
ros2 launch ./my_navera.launch.py gps_source:=boat
```

`ros2 topic echo --once /navera/position --field latitude` now says about 24.35: NAVERA follows the
boat off Sohar. Stop the launch.

## Step 7 — NAVERA's order trap

Open NAVERA's settings file in **your copy**:
[estimator_params.yaml](file:navera/navera_estimator/navera_estimator/config/estimator_params.yaml).
Change `gps_timeout_s: 3.0` to `gps_timeout_s: 1.0` (keep the 4 spaces before it) and save. Start
the arbiter the product's way:

```bash
ros2 launch navera_estimator estimator.launch.py
```

```bash
ros2 param get /estimator_node gps_timeout_s
```

**3.0** — your edit is ignored: the launch file's dict comes after the YAML (course, "In NAVERA").
Stop it. Now load the same YAML directly, without the launch file:

```bash
ros2 run navera_estimator estimator_node.py --ros-args --params-file ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
```

```bash
ros2 param get /estimator_node gps_timeout_s
```

**1.0**. Stop it, **put `gps_timeout_s` back to 3.0** in the YAML and save. Your own launch passes
the value as a launch argument; start it and ask again:

```bash
ros2 launch ./my_navera.launch.py
```

```bash
ros2 param get /estimator_node gps_timeout_s
```

> [!TASK]
> Fill `GPS_TIMEOUT_YAML_1_PLAIN_LAUNCH`, `GPS_TIMEOUT_YAML_1_RUN` and `GPS_TIMEOUT_MY_LAUNCH`. Stop
> the launch.

## Step 8 — Change NAVERA itself

NAVERA reports FIX only if the stated σ is at most `fix_max_sigma_m` = 25 m; your fake receivers
state 3 m. Suppose your client demands 2 m. In the same YAML file, change the last setting to:

```yaml
    fix_max_sigma_m: 2.0
```

Save, relaunch your system, and read the verdict:

```bash
ros2 launch ./my_navera.launch.py
```

```bash
ros2 topic echo /navera/nav_status --field reason
```

**`GPS fix, uncertainty 3 m > 2 m`** — DEGRADED. One number in a text file, and NAVERA's decision
changed. See your changes the way git sees them (lesson 05) — only `fix_max_sigma_m` must differ:

```bash
git -C ~/navera diff
```

> [!NOTE]
> Keep this change for the check. Lesson 14 starts by putting NAVERA back with git (the
> **Reset my NAVERA copy** button would do it too).

Stop the launch.

## Step 9 — Write the analysis

Fill [report.md](file:./report.md) (at least 40 words per section): **Precedence**, **Validation**,
**NAVERA** — with your measured values. Press **✔ Check my work**. The checker unit-tests your
functions, runs your node with several settings, launches your system three times and reads NAVERA's
YAML. About two minutes.

## Going further (optional)

- **A group.** Rewrite the boat with `GroupAction([PushRosNamespace("boat"), Node(...)])` instead of
  `namespace=`; check that the names are the same.
- **Dynamic typing.** Replace the `speed_mps` declaration by NAVERA's `declare_float`
  (`from navera_common.params import declare_float`) and check that `-p speed_mps:=12` (an integer)
  is accepted. What do you lose? (Hint: can a descriptor with dynamic typing still have a range?)
- **A third vehicle.** Add a drone over Jebel Akhdar (about 23.07 N, 57.66 E) with one more launch
  argument `with_drone`, and make `gps_source:=drone` work. How many lines did you change?

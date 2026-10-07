# Lab 13 — One command for a whole system

**Goal:** turn the fake GPS's settings into parameters
([fake_gps_params.py](file:./fake_gps_params.py)), write them in a YAML file
([my_gps.yaml](file:./my_gps.yaml)), write a launch file that starts your GPS **and** NAVERA
([my_navera.launch.py](file:./my_navera.launch.py)), then change one of NAVERA's own settings.
**Time:** about 1 hour 30 minutes.

You need two terminals. Remember `Ctrl+C` to stop a node or a launch.

## Step 1 — Look at the parameters of a real node

Start NAVERA's arbiter the simple way, in **Terminal 1**:

```bash
ros2 run navera_estimator estimator_node.py
```

In **Terminal 2**, list its parameters and read two of them:

```bash
ros2 param list /estimator_node
```

```bash
ros2 param get /estimator_node day_timeout_s
```

```bash
ros2 param get /estimator_node fix_max_sigma_m
```

`day_timeout_s` is **3.0** — the default written in the code. Now stop the arbiter (`Ctrl+C` in
Terminal 1) and start it **the way the product does**, with its launch file:

```bash
ros2 launch navera_estimator estimator.launch.py
```

Read the first lines: the launch prints a warning about `NAVERA_MAX_SPEED_KMH` (the vehicle's maximum
speed is not configured in your sandbox — normal here), then the node's own line, prefixed with
`[estimator_node.py-1]`. Ask again in Terminal 2:

```bash
ros2 param get /estimator_node day_timeout_s
```

**5.0**: this time the value comes from the YAML file. Try to change a setting live:

```bash
ros2 param set /estimator_node fix_max_sigma_m 1.0
```

"Set parameter successful"… but the arbiter read its settings once, at start-up: its decisions will
not change until it restarts. Stop the launch with `Ctrl+C`.

## Step 2 — Parameters in your node (TODO 1)

Open `fake_gps_params.py`. It is a fake GPS like lesson 10's, but its settings are written in the
code. Run it to see the starting point:

```bash
python3 fake_gps_params.py
```

It logs `fake GPS on /fake_gps/fix at 2.0 Hz from (35.8256, 10.6084)`. Stop it.

> [!TASK]
> **TODO 1** — declare the 7 parameters (`topic`, `rate_hz`, `start_lat`, `start_lon`, `speed_mps`,
> `heading_deg`, `sigma_m`) with the defaults listed in the comment, and read `topic`, `rate_hz`,
> `start_lat`, `start_lon` and `sigma_m` with `get_parameter(...).value`.

Now start it with other settings — without changing the code:

```bash
python3 fake_gps_params.py --ros-args -p rate_hz:=5.0 -p start_lat:=36.0
```

The log says `at 5.0 Hz from (36.0, 10.6084)`. In Terminal 2, measure the rate:

```bash
ros2 topic hz /fake_gps/fix
```

About 5. Stop both. Now fall into the type trap on purpose (no `.0`):

```bash
python3 fake_gps_params.py --ros-args -p rate_hz:=5
```

Read the last line of the error: `… of type 'INTEGER', expecting type 'DOUBLE'`. Now you will
recognise it.

## Step 3 — Change the speed while it runs (TODO 2)

> [!TASK]
> **TODO 2** — in `on_timer`, read `speed_mps` and `heading_deg` with `self.get_parameter(...)` at
> every tick, instead of the fixed numbers.

Start your node with the defaults:

```bash
python3 fake_gps_params.py
```

In Terminal 2, watch the longitude grow (heading 37° is north-east):

```bash
ros2 topic echo /fake_gps/fix --field longitude
```

Stop the echo, change the speed to 20 m/s, and watch again: the longitude now grows 4 times faster.

```bash
ros2 param set /fake_gps speed_mps 20.0
```

```bash
ros2 topic echo /fake_gps/fix --field longitude
```

Turn the vehicle due north: what happens to the longitude now?

```bash
ros2 param set /fake_gps heading_deg 0.0
```

Finally, print all of the node's parameters as YAML — the format of the next step:

```bash
ros2 param dump /fake_gps
```

Stop the node.

## Step 4 — A YAML parameters file (TODO 3)

> [!TASK]
> **TODO 3** — complete `my_gps.yaml` for these settings: topic `/fake_gps/fix`, **1.0** fix per second
> (like NAVERA's real GPS receiver), start at latitude **35.8300**, longitude **10.5900**, speed
> **8.0** m/s, heading **90.0** (due east), sigma **3.0** m. Decimal numbers with a dot.

Start the node with the file:

```bash
python3 fake_gps_params.py --ros-args --params-file my_gps.yaml
```

The log must say `at 1.0 Hz from (35.83, 10.59)`. If the node ignores your file, check the first two
lines: the node name `fake_gps:`, then `ros__parameters:` (two underscores), each indented with spaces.
In Terminal 2:

```bash
ros2 topic echo /fake_gps/fix --field latitude
```

The latitude must stay the same (due east!). Stop everything.

## Step 5 — Your launch file (TODO 4 to 7)

Open `my_navera.launch.py`. Its docstring says what it must start; each TODO shows the action to use.

> [!TASK]
> **TODO 4** — an `ExecuteProcess` for your fake GPS with `--params-file my_gps.yaml`.
> **TODO 5** — a `Node` for NAVERA's `ros_gps_node.py` (package `gps_pkg`), with the parameter
> `fix_topic` set to `/fake_gps/fix`.
> **TODO 6** — an `IncludeLaunchDescription` of NAVERA's `estimator.launch.py`.
> **TODO 7** — return the three actions in the `LaunchDescription` list.

Launch the system, in **Terminal 1**:

```bash
ros2 launch ./my_navera.launch.py
```

All the outputs arrive in one terminal: `[python3-1]` (your GPS), `[ros_gps_node.py-2]`,
`[estimator_node.py-3]`. In **Terminal 2**:

```bash
ros2 node list
```

```bash
ros2 topic echo /navera/nav_status --field reason
```

**`GPS fix`** — the same result as lesson 11, with one command instead of four. Leave the launch running.

## Step 6 — Change NAVERA itself

NAVERA calls a GPS position a FIX only if the receiver states an uncertainty σ of at most
`fix_max_sigma_m` = 25 m. Your fake GPS states 3 m. Let's pretend your vehicle needs a much stricter
rule: only 2 m or better counts as FIX.

Open NAVERA's settings file in **your copy**:
[estimator_params.yaml](file:navera/navera_estimator/navera_estimator/config/estimator_params.yaml).
Find the line `fix_max_sigma_m: 25.0` (at the end), and change it to:

```yaml
    fix_max_sigma_m: 2.0
```

Keep the 4 spaces before it. Save. Look at Terminal 2: nothing changed. The arbiter read the file when
it started. Restart the launch (`Ctrl+C`, then `↑` `Enter` in Terminal 1) and watch the reason again:

```bash
ros2 topic echo /navera/nav_status --field reason
```

**`GPS fix, uncertainty 3 m > 2 m`** — DEGRADED. One number in a text file, and NAVERA's verdict
changed. Confirm what the running arbiter uses:

```bash
ros2 param get /estimator_node fix_max_sigma_m
```

And see your change the way git sees it (lesson 5):

```bash
git -C ~/navera diff
```

> [!NOTE]
> Keep this change for the check. Lesson 14 starts by showing you how to put NAVERA back exactly as it
> was, with git. (The **Reset my NAVERA copy** button would do it too.)

Stop the launch (`Ctrl+C`).

## Step 7 — Check your work

Press **✔ Check my work**. The checker starts your node several times with different parameters,
reads your YAML files, and runs your launch file. It takes about a minute.

## Going further (optional)

- **A launch argument.** Add `DeclareLaunchArgument("rate_hz", default_value="1.0")` to your launch,
  and pass `LaunchConfiguration("rate_hz")` to your GPS (`-p`, `["rate_hz:=", LaunchConfiguration("rate_hz")]`).
  Then: `ros2 launch ./my_navera.launch.py rate_hz:=4.0`.
- **The order trap.** In NAVERA's YAML, set `gps_timeout_s: 1.0` and relaunch. Does
  `ros2 param get /estimator_node gps_timeout_s` say 1.0? Read the course's "In NAVERA" again to
  explain it, then try `ros2 launch navera_estimator estimator.launch.py gps_timeout_s:=1.0`. Put it
  back to 3.0 afterwards.
- **No more type trap.** Replace `declare_parameter` by NAVERA's `declare_float` for the decimal
  parameters (`from navera_common.params import declare_float`) and check that `-p rate_hz:=5` works.

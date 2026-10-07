# Launch files and parameters

The same NAVERA software runs on a small drone, on a delivery car and on a boat. A drone may fly at
100 km/h; a boat crawls at 20 km/h. One box reads its GPS on a serial cable, another gets it from the
autopilot. Should IRIS Systems write a different program for each vehicle? Of course not. The code
stays the same; only the **settings** change. In ROS, a node's settings are called **parameters**.

And how many programs did you start by hand in lesson 11 to get a FIX? Four, in four terminals. A
real NAVERA box starts about ten, every time it boots. Nobody types ten commands: they write a
**launch file**, and start the whole system with one command.

Today you learn both: parameters, YAML files to store them, and Python launch files. And you will
change, for the first time, a setting of NAVERA itself — and watch its decisions change.

## Parameters: a node's settings

A **parameter** is a named value that belongs to one node: `rate_hz = 2.0`,
`topic = "/fake_gps/fix"`, `gps_timeout_s = 3.0`. A node **declares** each parameter with a default
value, then **reads** it:

```python
self.declare_parameter("rate_hz", 2.0)            # name, default value
rate = self.get_parameter("rate_hz").value        # the value actually in use
```

Why not just a Python variable at the top of the file, as in lesson 10? Because a parameter can be
changed **without touching the code**: when you start the node, from a file, from a launch file, or
even while it runs. The person who installs NAVERA on a boat never opens a `.py` file.

Each parameter has a **type**, fixed by its default: `2.0` makes a decimal number (a *double*),
`2` a whole number (an *integer*), `"text"` a *string*, `True` a *bool*.

### Setting parameters when you start a node

After the program's name, `--ros-args` opens the ROS options, and `-p name:=value` sets one parameter:

```bash
python3 fake_gps_params.py --ros-args -p rate_hz:=5.0 -p topic:=/test/fix
ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/fake_gps/fix
```

You already used the second one in lesson 11!

> [!WARNING]
> **The type trap.** `-p rate_hz:=5` (without `.0`) is an *integer*, and `rate_hz` was declared as a
> double: the node crashes with `InvalidParameterTypeException: … of type 'INTEGER', expecting type
> 'DOUBLE'`. Always write decimals with a dot. NAVERA's engineers met this trap too, and wrote a
> helper that accepts both — look at `declare_float` in
> [navera_common/…/params.py](file:navera/navera_common/navera_common/params.py) and its comment.

### Looking at parameters while a node runs

| Command | What it does |
|---|---|
| `ros2 param list /node` | the names of all its parameters |
| `ros2 param get /node name` | the current value |
| `ros2 param set /node name value` | change it now |
| `ros2 param dump /node` | all values, written as YAML |

A subtle point about `ros2 param set`: it changes the value stored in the node, but the node only
**uses** the new value if it reads it again. A node that reads its parameters once in `__init__`
(like NAVERA's arbiter, which copies them into variables at start-up) keeps behaving as before: you
must restart it. A node that calls `get_parameter()` at every tick (like your fake GPS will, for its
speed) changes behaviour immediately. Neither is wrong — but you must know which one you have.

## YAML parameter files

Ten parameters on a command line are unreadable. Instead, you write them in a **YAML** file. YAML
("YAML Ain't Markup Language") is a simple text format for settings: `name: value` lines, and
**indentation with spaces** to show what belongs to what. A ROS parameters file always has the same
shape:

```yaml
fake_gps:                      # the NODE name
  ros__parameters:             # always this word (two underscores!)
    rate_hz: 1.0               # name: value
    topic: "/fake_gps/fix"
```

and you give it to the node with `--params-file`:

```bash
python3 fake_gps_params.py --ros-args --params-file my_gps.yaml
```

YAML rules that bite beginners: spaces, never tabs; the same number of spaces for things at the same
level; `1.0` is a double, `1` an integer, `"text"` or `text` a string; `#` starts a comment.

## Who wins?

A parameter can get a value from several places. The rule: **the last one applied wins**.

![The layers of a parameter: code default, YAML file, command line or launch file, ros2 param set](assets/param_layers.svg)

You saw it in lesson 11 without noticing: `ros2 run navera_estimator estimator_node.py` printed
`day_timeout=3.0s`, the default **in the code**. NAVERA's real launch file loads its YAML file, which
says `day_timeout_s: 5.0` — and the YAML's comment explains why: frames come every 1–4 s under load,
and a 3 s window made NAVERA flicker between FIX and NO_FIX. The code's default and the product's
setting are different on purpose, and the YAML file documents the product's choice.

## Launch files

A **launch file** describes a set of programs to start together, with their parameters. In ROS 2 it
is a Python file with a function `generate_launch_description()` that returns a
`LaunchDescription`: a list of **actions**. You start it with `ros2 launch`:

```bash
ros2 launch navera_estimator estimator.launch.py      # a launch file installed in a package
ros2 launch ./my_navera.launch.py                     # a launch file in this folder
```

The three actions you will use:

| Action | Starts | Example |
|---|---|---|
| `Node(package=…, executable=…, parameters=[…])` | a node installed in a ROS package | NAVERA's `ros_gps_node.py` |
| `ExecuteProcess(cmd=[…])` | any command, like in a terminal | your own `python3 fake_gps_params.py` |
| `IncludeLaunchDescription(…)` | another launch file, with all its actions | NAVERA's `estimator.launch.py` |

`parameters=[…]` is a list: a YAML file path, and/or a Python dict `{"name": value}`. Later items win.

![my_navera.launch.py starts three things; one of them is NAVERA's own launch file](assets/launch_tree.svg)

When you press `Ctrl+C`, `ros2 launch` stops every process it started. All their outputs appear in
the same terminal, each line starting with the process name in brackets, like
`[estimator_node.py-1]`.

## In NAVERA

Open NAVERA's arbiter launch file,
[estimator.launch.py](file:navera/navera_estimator/navera_estimator/launch/estimator.launch.py).
Its heart:

```python
pkg_share = get_package_share_directory('navera_estimator')
cfg = os.path.join(pkg_share, 'config', 'estimator_params.yaml')
...
Node(
    package='navera_estimator',
    executable='estimator_node.py',
    name='estimator_node',
    output='screen',
    on_exit=Shutdown(reason='node exited'),
    parameters=[
        cfg,
        {
            'publish_rate_hz': LaunchConfiguration('publish_rate_hz'),
            'gps_timeout_s':   LaunchConfiguration('gps_timeout_s'),
            'imu_timeout_s':   LaunchConfiguration('imu_timeout_s'),
        },
        max_speed_params(),
        imu_topic_params(),
    ],
),
```

Read it with your new eyes:

- `get_package_share_directory('navera_estimator')` finds where the package is **installed**; the
  YAML file is installed there by `setup.py`. Because your copy was built with `--symlink-install`,
  that installed file is a **link** to the file in your source folder: edit
  `navera_estimator/navera_estimator/config/estimator_params.yaml` and the next launch uses it,
  no rebuild needed.
- `parameters=[cfg, {...}, ...]`: first the YAML file, then a dict that **overrides** three of its
  values with **launch arguments** (`DeclareLaunchArgument('gps_timeout_s', default_value='3.0')`). So
  `ros2 launch navera_estimator estimator.launch.py gps_timeout_s:=2.0` changes the GPS window — and
  a change of `gps_timeout_s` in the YAML file alone has **no effect** with this launch file, because
  the dict comes after it. Order matters!
- `max_speed_params()` reads the vehicle's maximum speed from the installation's settings
  (`NAVERA_MAX_SPEED_KMH`), so one value serves every node. When it is not set, the launch prints a
  warning — you will see it.
- `on_exit=Shutdown(...)`: if the arbiter crashes, the whole launch stops, and the system service
  restarts everything cleanly. A half-running navigation system is worse than a restart.

Now open [estimator_params.yaml](file:navera/navera_estimator/navera_estimator/config/estimator_params.yaml).
Every value has a comment explaining **why** it is what it is — sometimes with the measurement behind
it (`ros2 topic hz /navera/sensors/gps_fix = 1.000 Hz`). That is the habit of a good engineer: a
setting without a reason is a setting nobody dares to change. In the lab you will change
`fix_max_sigma_m`, the largest stated uncertainty that still counts as a FIX.

## Words to remember

| Word | Meaning |
|---|---|
| **parameter** | a named setting of a node, with a type and a value |
| **declare / get** | create a parameter with its default / read its current value |
| **`--ros-args -p name:=value`** | set a parameter when starting a node |
| **YAML** | a text format for settings, with indentation |
| **params file** | a YAML file `node: ros__parameters: name: value` |
| **launch file** | a Python file that starts several programs with their parameters |
| **action** | one thing a launch file does: `Node`, `ExecuteProcess`, `IncludeLaunchDescription` |
| **launch argument** | a setting of a launch file itself: `ros2 launch pkg file.py name:=value` |
| **share directory** | where a package's installed files (launch, config) live |

## Check what you learned

<details><summary>1. You start a node with <code>-p rate_hz:=10</code> and it crashes. Why?</summary>
<code>10</code> is an integer, and the parameter was declared with a double default (<code>2.0</code>).
Write <code>10.0</code>.
</details>

<details><summary>2. <code>ros2 param set /estimator_node fix_max_sigma_m 1.0</code> answers "Set parameter successful", but NAVERA's decisions do not change. Why?</summary>
The arbiter reads its parameters once, at start-up, into its own variables. The new value is stored
but never read again: restart the node (with the value in the YAML file or on the command line).
</details>

<details><summary>3. In a YAML params file, what are the first two levels?</summary>
The node name, then <code>ros__parameters:</code>. The parameters come under it, indented.
</details>

<details><summary>4. You change <code>gps_timeout_s</code> in estimator_params.yaml and launch NAVERA's estimator.launch.py. The value used is still 3.0. Why?</summary>
The launch file passes a dict after the YAML file, with <code>gps_timeout_s</code> taken from a launch
argument (default 3.0). Later items win. Use <code>gps_timeout_s:=…</code> on the launch command instead.
</details>

<details><summary>5. Why does your launch file include NAVERA's <code>estimator.launch.py</code> instead of starting the estimator with its own <code>Node</code> action?</summary>
To reuse everything NAVERA's own launch does: its YAML, its overrides, the vehicle speed, the
shutdown rule. Copying it would drift away from the product over time.
</details>

Now open the **🛠️ Lab** tab.

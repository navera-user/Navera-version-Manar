# Launch files and parameters: configuring a system without touching its code

![One program, two vehicles and a judge: the same fake GNSS node runs as a drone and as a boat, each in its own namespace, and one judge listens to the one chosen at launch](assets/launch_graph.svg)

> [!NOTE] Mission brief
> **1 October 2026, NAVERA review, item R-1 (severity high).** NAVERA had no setting for the vehicle's
> speed: its arbiter's jump gate used 100 m/s and its day and night vision 30 m/s, **whatever the
> vehicle**. On a fast fixed wing, real GPS fixes would be refused and every vision position rejected.
> The code was right; the **configuration** was wrong. Days earlier (LOC-30), a launch override written
> `1` instead of `1.0` had crashed a node at start.
>
> You met R-1 in mission 03. Today you fix NAVERA Lite's version of it. **Session 1 — Guard the
> knobs:** your fake GNSS receiver learns to refuse impossible settings, and you check a whole settings
> file. **Session 2 — One command:** two vehicles and the judge from one launch file, then the integrator
> who copied the drone's settings onto a plane. Badges: **Knob guard**, then **Integrator**.

**Objectives.** After this mission you can:

1. declare typed parameters with **descriptors** (range, read-only) and a **validation callback**, and
   say which mistakes each guard catches, at start or at run time;
2. predict, then measure, which value a node gets when a default, files and the command line all give
   one (**precedence**);
3. write a **launch file** that starts two vehicles in **namespaces** and one judge, with launch
   arguments, a condition and a **remap**;
4. change one setting of the stack, predict the judge's new verdict, and check a whole settings file
   against the vehicle it is for (R-1).

**You need:** missions 03 (`VEHICLES`), 09 (nodes, topics, background jobs), 10 (`declare_parameter`,
`-p`, `ros2 param set`). ⏱ Reading: about 85 minutes with the ✏️ checks. Lab: 3 to 4 h in two sessions
(up to 5 h if ROS is still new to you).

**Before you start** — three questions from earlier missions. If you miss two, reread lesson 10 §3.

<details><summary>1. Your fake GPS reads <code>speed_mps</code> at every tick. What happens 1 s after <code>ros2 param set /fake_gps speed_mps 20.0</code>?</summary>
It moves at 20 m/s: the node reads the value again at the next tick. A node that read it once in
<code>__init__</code> would keep its old speed.
</details>

<details><summary>2. What is the type of <code>-p speed_mps:=12</code>, and why does it matter?</summary>
An integer. <code>speed_mps</code> was declared with the default <code>10.0</code>, a double, so the node stops with
<code>InvalidParameterTypeException</code>. Write <code>12.0</code>.
</details>

<details><summary>3. In <code>navera_lite/vehicle.py</code> (mission 03), what is <code>VEHICLES["boat"]</code>, and what is it for?</summary>
20.0: the top speed of a boat, in m/s. A speed limit belongs to the vehicle, not to the software.
</details>

<details><summary>Workspace and words (open if you need them)</summary>

Your files are in `~/lessons/13-launch-params/`. The lab runs in **one** terminal tab: nodes in the
background (`&`, as in mission 09), questions (`ros2 param get`, `ros2 topic echo`) in the same tab, and
`kill -INT %%` to stop the last node.

| Word | Meaning | Français |
|---|---|---|
| **parameter** | a named, typed setting of a node, given from outside | paramètre |
| **descriptor** | the description and limits of a parameter (range, read-only) | descripteur |
| **validation callback** | your function that ROS calls before a parameter changes; it may refuse | fonction de validation |
| **parameters file** | a YAML file of sections `node name: ros__parameters: …` | fichier de paramètres |
| **fully qualified name** | namespace + name: `/boat/fake_gps`, `/boat/navera_lite/fix/gps` | nom complet |
| **namespace** | a prefix that keeps the nodes and topics of one subsystem apart | espace de noms |
| **remap** | replacing one name by another when a node starts (`-r from:=to`) | remappage |
| **launch file** | a Python file that describes which processes `ros2 launch` starts, and how | fichier de lancement |
| **launch argument** | a value given to a launch file: `ros2 launch file.py name:=value` | argument de lancement |
| **substitution** | a value that the launch system computes later, when it runs | substitution |
| **precedence** | which value wins when several places give one | priorité |
</details>

## 1. A parameter has a type, fixed by its default

In mission 10 you declared `self.declare_parameter("speed_mps", 10.0)`. The default does two jobs: it
gives the value, and it fixes the **type** for the life of the node. `10.0` makes a double, `10` an
integer, `"drone"` a string, `True` a bool. A later value of another type is refused, at start or at
run time. The replay node of mission 09 declares `imu_hz` with `10.0`. Started with `-p imu_hz:=5`, it
stops before it publishes anything:

```
rclpy.exceptions.InvalidParameterTypeException: Trying to set parameter 'imu_hz' to '5' of type
'INTEGER', expecting type 'DOUBLE'
```

This is NAVERA's LOC-30. Stopping is better than a silent conversion, but the person who wrote `5` was
an integrator on a test site, far from the code. Write every decimal with a dot, in YAML too (`30` is an
integer, `30.0` a double). (`ParameterDescriptor(dynamic_typing=True)` lets a node accept both and
convert the value itself, at the price of the type check.)

## 2. Three guards on a parameter

A type is not enough: `speed_mps: 500.0` is a perfectly good double. ROS gives you three guards.

**A descriptor** is the third argument of `declare_parameter`:

```python
from rcl_interfaces.msg import FloatingPointRange, ParameterDescriptor

d = ParameterDescriptor(description="direction of motion, degrees clockwise from north",
                        floating_point_range=[FloatingPointRange(from_value=0.0, to_value=360.0, step=0.0)])
self.declare_parameter("heading_deg", 90.0, d)
```

`ros2 param describe /fake_gps heading_deg` prints the description and the limits for the integrator.
`floating_point_range` is a **list** holding one range (`step=0.0`: any value in between); `read_only=True`
is another field.

**A validation callback** checks rules that one range cannot express, because they link several
parameters: 25 m/s is fine for a drone (`VEHICLES["drone"]` = 30) and impossible for a boat (20). You
register a method; ROS calls it with the list of parameters **about to change**, and applies the
change only if it returns `successful=True`:

```python
from rcl_interfaces.msg import SetParametersResult

self.add_on_set_parameters_callback(self.on_set_parameters)      # after the declarations

def on_set_parameters(self, params):          # params: a list of rclpy Parameter (.name, .value)
    new = {p.name: p.value for p in params}   # {"heading_deg": 400.0}: only what is changing
    ...
    return SetParametersResult(successful=False, reason="heading_deg 400.0 is not a heading")
```

The list holds only the parameters that change. When the rule needs another parameter, take its new
value if it is in the list, else its current one (`self.get_parameter(name).value`). Register the
callback **after** the declarations: registered before them, ROS calls it once for each parameter it
declares, while the others do not exist yet, and your `get_parameter` fails.

**Read-only.** A timer's period is fixed when the timer is created. If `rate_hz` could be changed while
the node runs, `ros2 param set` would answer "successful" and nothing would change: a lie. Declared
`read_only=True`, it can be given at start only, and a change is refused with a clear message.

Measured on the course's fake GNSS (Humble), the first three guards act like this:

| Guard | at start (`-p`, a file) | while it runs (`ros2 param set`) |
|---|---|---|
| type (the default) | ✘ node stops | ✘ "Wrong parameter type" |
| range (descriptor) | ✘ node stops | ✘ "out of range Min … Max …" |
| read-only (descriptor) | ✔ allowed | ✘ "Trying to set a read-only parameter" |

And the callback? You will find out in lab Step 3, as an attacker.

<details><summary>Read this after lab Step 3: the callback, and the attacker's door</summary>

| Guard | at start (`-p`, a file) | while it runs (`ros2 param set`) |
|---|---|---|
| callback, registered after the declarations | **not called** | ✘ your reason |

Values given at start never pass through a callback registered after the declarations. So a careful
node checks its **start** values too, in one place: §6.
</details>

**Read once, or read every time?** `ros2 param set` changes the **stored** value. A node uses it only if
it reads it again. A node that copies its settings into its own variables when it starts follows no
later change; a node that reads them at every tick does. Which one is NAVERA Lite's judge? Lab Step 0.

<details><summary>Read this after lab Step 0</summary>
NAVERA Lite's judge reads its settings once, when it starts, and builds its rules from them: a
<code>ros2 param set</code> is stored, reported "successful", and changes no verdict until the judge restarts.
Neither design is wrong; a node must say which one it is, and <code>read_only</code> is the honest way to say
"restart me".
</details>

## 3. Settings files, and which value wins

Twenty `-p` on one command line are unreadable. A **parameters file** is YAML, made of **sections**.
A section's key is a node's **fully qualified name** (namespace + name), or a wildcard:

```yaml
/**:                      # every node
  ros__parameters:        # always this key, two underscores
    sigma_m: 3.0
/boat/fake_gps:           # only the node fake_gps in the namespace /boat
  ros__parameters:
    vehicle: "boat"
    heading_deg: 45.0
```

`/**` matches every node; `/boat/*` every node directly in `/boat`. A key without the first slash is
read as if it had one: `boat/fake_gps:` means `/boat/fake_gps`, but `fake_gps:` means `/fake_gps`, and
does **not** match the same node started in `/boat` (measured: the node keeps its code default, with
no warning). Write full names. You load the file at start: `--ros-args --params-file my_file.yaml`.
Your `navera_lite.yaml` is such a file: one `/**` section.

**Who wins?** The code's default loses to anything given at start; `ros2 param set` comes last (if a
guard accepts it). Between files and `-p`, ROS 2 Humble follows a rule that surprises most people. In
short: everything goes into one list of sections, and `-p` does not add a line at the bottom: it changes
the `/**` line wherever that line already is. Precisely (measured on 25 command lines, Python and C++
nodes; this model predicts them all):

![The table of sections: each section name gets one row, created where it first appears; a later value for the same name overwrites its row in place; -p writes in the /** row; the node applies its matching rows from top to bottom, so the lowest matching row wins](assets/precedence_table.svg)

1. Everything given at start goes into **one table**, with **one row per section name**.
2. A row is created where its name **first** appears, reading the command line from left to right
   (and each file from top to bottom).
3. A later value for the same section name **overwrites that row in place**: the row does not move.
4. `-p name:=value` writes into the **`/**` row** (and creates it if it does not exist yet).
5. The node applies its matching rows **from top to bottom**: the **lowest** matching row wins.

**Worked example.** `/boat/fake_gps` is started with `--params-file a.yaml -p heading_deg:=180.0`, where
`a.yaml` holds `/boat/fake_gps: heading_deg 45.0` and then `/**: heading_deg 0.0`.
Rows: `/boat/fake_gps` (45.0), then `/**` (0.0); `-p` overwrites the `/**` row with 180.0, which stays
second. Both rows match; the lowest wins: **180.0**. Without the `-p`: **0.0**, because the file put
its wildcard *after* the specific section. Put `/**` first in a file, always.

> [!QUESTION] ✏️ Check
> `b.yaml` holds `/**: heading_deg 0.0`, then `/boat/fake_gps: heading_deg 45.0`. `c.yaml` holds only
> `/boat/fake_gps: heading_deg 45.0`. Predict `heading_deg` of `/boat/fake_gps` for
> (1) `--params-file b.yaml`, (2) `--params-file b.yaml -p heading_deg:=180.0`,
> (3) `-p heading_deg:=180.0 --params-file b.yaml`, (4) `--params-file c.yaml -p heading_deg:=180.0`.
> Draw the rows for each.

<details><summary>Answer</summary>
(1) 45.0: rows <code>/**</code>, <code>/boat/fake_gps</code>; the lower one wins. (2) 45.0: <code>-p</code> overwrites the
<code>/**</code> row, which is still above. (3) 45.0: <code>-p</code> creates the <code>/**</code> row first, the file
overwrites it and adds <code>/boat/fake_gps</code> below. (4) <b>180.0</b>: c.yaml creates only the boat's row, and
<code>-p</code> creates the <code>/**</code> row <i>below</i> it. A <code>-p</code> loses to a node's own section only when a
<code>/**</code> row sits above that section (here, created by b.yaml's first section). Do not learn a slogan:
draw the rows.
</details>

The practical rule: give each value in **one** place, put `/**` first, override a node's own section
with a later file that uses the same section name **and has no `/**` section after it**, and **always
check** with `ros2 param get`.

## 4. Names: namespaces and remaps

Every node and topic name is **resolved** into a fully qualified name. A name that starts with `/` is
**absolute** and stays as it is. A name without it is **relative**: the node's namespace is put in
front. NAVERA Lite's nodes use relative topic names on purpose (`navera_lite/fix/gps`):

| Node started with | Node's full name | It publishes on |
|---|---|---|
| no namespace | `/fake_gps` | `/navera_lite/fix/gps` |
| `-r __ns:=/drone` | `/drone/fake_gps` | `/drone/navera_lite/fix/gps` |
| `-r __ns:=/boat` | `/boat/fake_gps` | `/boat/navera_lite/fix/gps` |

Two identical receivers run side by side without mixing their fixes. The judge, without a namespace,
subscribes to `/navera_lite/fix/gps`, where nobody publishes any more. A **remap** tells one node, at
start, to use another name: `-r navera_lite/fix/gps:=/boat/navera_lite/fix/gps`, and the unchanged judge
listens to the boat. `-r __ns:=…` and `-r __node:=…` are remaps too.

> [!QUESTION] ✏️ Check
> The judge is started with `-r __ns:=/test`, no other remap, next to the two receivers above. Which
> topic does it read, and what does it say?

<details><summary>Answer</summary>
<code>/test/navera_lite/fix/gps</code>, where nobody publishes. It never receives a position and stays
STARTING, "no position received yet", forever, without an error. A wrong name is not a crash: it is
silence. <code>ros2 node info /test/arbiter</code> shows what it really subscribes to.
</details>

## 5. Launch files

NAVERA starts about ten programs at every boot, each with its namespace, settings and remaps. Nobody
types those command lines: each of NAVERA's services runs `ros2 launch`, and the service manager
restarts a program that stops. A **launch file** is a Python file whose `generate_launch_description()`
returns a `LaunchDescription`, a **list of actions**. It starts nothing; it *describes*. `ros2 launch`
does it, prefixes each output line with the process name, and stops them all when it is stopped.

Product packages are built with **colcon** (lab "Going further") and started with
`launch_ros.actions.Node(package=…, executable=…)`. NAVERA Lite is not built, so `fl_node()` (in
`navera_lite/ros/launch_util.py`) builds the command line you would type. The two look alike, but differ
in one detail that §3 makes important:

```python
Node(package="pkg", executable="gps_node", name="fake_gps", namespace="boat",
     parameters=["file.yaml", {"speed_mps": 5.0}], remappings=[("from", "to")])
# starts: ... --ros-args -r __node:=fake_gps -r __ns:=/boat --params-file file.yaml
#             --params-file /tmp/launch_params_xxxx -r from:=to
#   (the dict goes into a temporary file, in a section named /boat/fake_gps)
fl_node("gps_node", "fake_gps", namespace="boat",
        params_file="file.yaml", params={"speed_mps": 5.0}, remaps=[("from", "to")])
# starts: ... --ros-args -r __node:=fake_gps -r __ns:=/boat --params-file file.yaml
#             -p speed_mps:=5.0 -r from:=to
```

If file.yaml starts with `/**` and has its own `/boat/fake_gps: speed_mps`, `Node`'s dict wins (same
section name: it overwrites that row) and `fl_node`'s `-p` loses (the `/**` row, above). NAVERA Lite's
launch file never gives a key twice, so the lab does not show it.

**A complete example** (not the one you write): replay a CSV file into a judge, with a launch argument
`file` and a switch `with_judge`.

```python
import os, sys                                                         # 1
from launch import LaunchDescription                                  # 2
from launch.actions import DeclareLaunchArgument                      # 3
from launch.conditions import IfCondition                             # 4
from launch.substitutions import LaunchConfiguration                  # 5
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # 6
from navera_lite.ros.launch_util import fl_node                       # 7

def generate_launch_description():                                    # 8
    log = LaunchConfiguration("file")         # a substitution: known only when it runs  # 9
    return LaunchDescription([                                        # 10
        DeclareLaunchArgument("file", description="CSV to replay"),   # 11 (no default: required)
        DeclareLaunchArgument("with_judge", default_value="true"),    # 12
        fl_node("replay_node", "replay", namespace="test", params={"file": log, "loop": False}),  # 13
        fl_node("arbiter_v0", "arbiter", params_file="navera_lite.yaml",                        # 14
                remaps=[("navera_lite/fix/gps", "/test/navera_lite/fix/gps")],                  # 15
                condition=IfCondition(LaunchConfiguration("with_judge"))),                      # 16
    ])
```

`ros2 launch replay_launch.py file:=attack.csv with_judge:=false` would start the replay only. Three
ideas in it:

- **Launch arguments** (lines 11–12): set with `name:=value`, listed by `ros2 launch <file> --show-args`.
  Without a `default_value` an argument is **required**: `ros2 launch` refuses to start and names it.
- **Substitutions.** `LaunchConfiguration("file")` is not a string: it is an object that `ros2 launch`
  replaces by the value when it runs (line 13 puts one in `params`). A **list** of text and substitutions
  is joined at run time: `["/", LaunchConfiguration("gps_source"), "/navera_lite/fix/gps"]` becomes
  `/boat/navera_lite/fix/gps`. `"/" + LaunchConfiguration("gps_source")` fails at once (`TypeError: can
  only concatenate str (not "LaunchConfiguration") to str`): the value does not exist yet.
- **Conditions** (line 16): `IfCondition(…)` starts the action only when the value is true.

> [!NOTE]
> **Why line 6?** `ros2 launch` loads a launch file by its **path**, so without it line 7 fails with
> `ModuleNotFoundError: No module named 'navera_lite'`. Line 6 finds the lesson folder three folders up
> from the file; your launch file already has it. (The name ends in `_launch.py`: a module name cannot
> contain a dot.)

> [!QUESTION] ✏️ Check
> 1. In the example, why is `default_value="true"` a string and not `True`?
> 2. Someone writes `params={"loop": False, "rate": 2}`. What happens when `replay` starts?

<details><summary>Answer</summary>
1. Launch arguments are text, like everything typed on a command line; <code>IfCondition</code> reads
"true"/"false" (also "1"/"0").<br>
2. <code>fl_node</code> writes <code>-p rate:=2</code>, an integer, and <code>rate</code> was declared as a double
(1.0): the node stops with <code>InvalidParameterTypeException</code>. LOC-30 again, now hidden in a launch
file, and the other processes keep running. Write <code>2.0</code>.
</details>

## 6. Checking a whole settings file at start: one speed per vehicle

The judge's twelve settings must agree with each other and with the vehicle: positive timeouts, a FIX
limit above the smallest stated σ, and `max_speed_mps`, the jump gate's speed (mission 01), at least the
vehicle's top speed.

**Worked example.** A robot's limit (10 m/s) is left in the settings of a boat cruising at 18 m/s, one
fix per second, margin 50 m. Each fix: 18 m ≤ 10 × 1 + 50 = 60 m, fine. Then a bridge hides GPS for 7 s:
the next fix is 18 × 7 = 126 m from the last trusted one, the gate 10 × 7 + 50 = 120 m: **refused**. The
gap now grows 18 m per second, the gate only 10: every later fix is refused, and the judge loses GPS for
good on a healthy boat. A vehicle faster than `max_speed_mps` survives only gaps shorter than
margin / (speed − max_speed_mps), here 50 / 8 ≈ 6 s, and GPS gaps are what NAVERA is built for. That is
R-1 (lab Step 8 shows the faster case: locked out at the second fix). The rule: `max_speed_mps` ≥ the
vehicle's top speed, so that no healthy vehicle depends on the margin.

So the rules are checked **once, at start, on the whole file**: your `check_settings(cfg)` (TODO 4)
returns every rule broken, as sentences, not just the first (an integrator fixing one mistake per
restart loses an afternoon), with the fix where there is one (`write 3.0, not 3`).

> [!QUESTION] ✏️ Check
> `max_speed_mps` is 30.0 (a drone), the vehicle is a plane at 80 m/s, one fix per second, margin
> 50 m. Is its second fix refused? And with 90 m/s?

<details><summary>Answer</summary>
80 m/s: 80 m ≤ 30 × 1 + 50 = 80 m, accepted, and every fix after it too, just, and only while no fix is
lost: one lost fix gives 160 m > 110 m, locked out. 90 m/s: 90 m > 80 m, refused; 2 s after the last
trusted fix the gap is 180 m and the gate 110 m; it never catches up. The judge loses GPS for good, on a
healthy plane.
</details>

> [!WARNING] Common wrong ideas
> - "`-p` on the command line always wins." Not when a `/**` row was created before the node's own
>   section, for example by a file that starts with `/**` (§3: draw the rows).
> - "If `ros2 param set` says *successful*, the node uses the value." Only if it reads it again (§2).
> - "A margin of 50 m covers a slightly wrong speed limit." Until the first GPS gap (§6).
> - "The launch file failed, I would have seen an error." A wrong remap or namespace starts everything
>   and connects nothing: the judge just waits (§4).
> - "`LaunchConfiguration("x")` is the argument's value." It is a promise of it, kept when the launch runs (§5).

## In NAVERA

From NAVERA's engineering backlog and architecture notes (in words; its code is not part of the course):

- **One speed per installation (R-1, fixed after the review of 1 October 2026).** The installer gives
  the maximum speed **once, in km/h** (settings file or mission page); it is converted to m/s and fed to
  the jump gate and both vision motion gates. The field test procedure suggests cruise + 50 %. A value
  outside 4–1 890 km/h stops NAVERA at start with a message naming the setting: §6's start-time check.
- **LOC-30 (review of 28 September 2026, low severity, fixed):** integer launch overrides crashed float
  parameters (§1).
- **A default is not a setting.** The production configuration keeps a day-vision position fresh for
  5 s (frames come every 1–4 s under load); the node's code default is 3 s. A section name that does not
  match (§3) would leave it on 3 s without a word, and the arbiter flickering to NO_FIX between frames.
- NAVERA's programs read their settings when they start. After a change, the installer restarts NAVERA's
  services; its mission page refuses to apply settings while the vehicle is armed.

## In NAVERA Lite

You write three parts of the stack you build: in [navera_lite/ros/gps_node.py](file:./navera_lite/ros/gps_node.py)
the descriptors and the callback of `CheckedGps` (TODO 1–3: a subclass of mission 10's `FakeGps`; from
now on `python3 -m navera_lite.ros.gps_node` starts the checked node); in
[navera_lite/settings.py](file:./navera_lite/settings.py) `check_settings` (TODO 4); and
[navera_lite/ros/navera_lite_launch.py](file:./navera_lite/ros/navera_lite_launch.py), the stack's launch file
(TODO 5), where the judge is also told which vehicle it judges. `launch_util.fl_node` is given. Mission 14
tests the whole stack, launch file included.

## 🐦 How birds do it

Blackcaps from southern Germany migrate far; blackcaps from the Canary Islands hardly migrate. Crossed
by Peter Berthold and Ulrich Querner (published 1981), their young showed a migratory restlessness **in
between**. Same species, same body: different inherited **settings**, and a setting from the wrong
population sends a bird the wrong way.

## Summary

1. A parameter's **type** is fixed by its default: write `30.0`, not `30`, everywhere.
2. **Descriptors** (range, read-only) and a **callback** guard a node; a whole settings file is checked
   **at start**, against the vehicle.
3. Precedence: one row per section name, created where it first appears; `-p` writes the `/**` row; **the
   lowest matching row wins**. Draw the rows; check with `ros2 param get`.
4. **Namespaces** keep identical nodes apart; a **remap** reconnects one; a wrong name gives silence.
5. A **launch file** describes processes, arguments, conditions and substitutions. R-1 is a configuration
   bug that waits for the first GPS gap: `max_speed_mps` ≥ the vehicle's top speed.

**Next mission:** testing, so that a wrong change, in the code or in a launch file, is caught before it flies.

## Check yourself

Answer without scrolling up.

<details><summary>1. Name one mistake each guard catches: range, read-only, callback, check_settings.</summary>
Range: <code>speed_mps 500.0</code>. Read-only: changing <code>rate_hz</code> while running. Callback: 25 m/s for a
boat, while running. check_settings: a whole file at start (a zero timeout, an int, a drone's limit for a
plane).
</details>

<details><summary>2. A file has <code>/boat/fake_gps: speed_mps 4.0</code> and then <code>/**: speed_mps 7.0</code>. You add <code>-p speed_mps:=9.0</code> after it. Value for <code>/boat/fake_gps</code>?</summary>
9.0: rows boat (4.0), then <code>/**</code> (7.0, overwritten with 9.0); the lowest matching row wins.
</details>

<details><summary>3. A node declares <code>heading_deg</code> with the range 0.0 … 360.0 and a callback that refuses more than 180.0 for a robot. Started with <code>-p vehicle:=robot -p heading_deg:=270.0</code>: does it start? Then <code>ros2 param set … heading_deg 200.0</code>?</summary>
It starts with 270.0: the range allows it, and the callback is not called for start values. The set to
200.0 is refused by the callback. The node holds a value its own rule forbids: start values need a
check of their own.
</details>

<details><summary>4. Node <code>fake_gps</code> in namespace <code>/boat</code> publishes on <code>navera_lite/fix/gps</code>. Full topic name? And if the code had written <code>/navera_lite/fix/gps</code>?</summary>
<code>/boat/navera_lite/fix/gps</code>. With the leading slash the name is absolute: the namespace is ignored and
both vehicles would publish on the same topic.
</details>

<details><summary>5. (Mission 01) Jump gate: v_max 20 m/s, margin 50 m, 1 fix/s, a vehicle at 75 m/s. Why is it never accepted again after its first refused fix?</summary>
Each second the gap from the last trusted fix grows by 75 m and the gate by only 20 m: the gate falls
further behind every second (75 m > 70 m after 1 s, 150 m > 90 m after 2 s…).
</details>

Now open the **🛠️ Lab** tab.

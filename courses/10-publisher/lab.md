# Lab 10 — Build a fake GNSS receiver, then sabotage it

**Goal:** write NAVERA Lite's fake GNSS receiver (`navera_lite/ros/gps_node.py`): motion with the real time
between ticks, an honest NavSatFix, and the node around them. Measure it live, then turn its knobs to find
what arbiter v0 believes that it should not.
**Time:** 2 h 30 to 4 h (a strong programmer: about 2 h).
**Fast track:** if you know Python and rclpy, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further".

Your files (📝 Code tab): [navera_lite/ros/gps_node.py](file:./navera_lite/ros/gps_node.py) (**your code**:
`TODO 1–6`), [answers.py](file:./answers.py), [report.md](file:./report.md), and the runner
[run_gps.py](file:./run_gps.py), which runs your code on the lab's situations (you only run it). The other
parts in `navera_lite/` are finished: `vehicle.py` (mission 03), `geo.py` (06), and the ROS layer of mission 09
(`convert.py`, `qos.py`, `runner.py`, `arbiter_v0.py`, …). [navera_lite/PARTS.md](file:./navera_lite/PARTS.md)
lists them.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | nothing: you watch the bug |
| §1 | Step 1 | nothing: you read and run the starter |
| §3 the real dt | Steps 2–3 | `step` (TODO 1), two numbers |
| §4 NavSatFix | Step 4 | `covariance_from_sigma`, `make_fix` (TODO 2–3) |
| §1–§2 node, parameters | Step 5 | `FakeGps.declare_all`, `FakeGps.start` (TODO 4–5) |
| §3 | Steps 6–7 | `FakeGps.on_timer` (TODO 6), measurements |
| §5 the judge | Steps 8–9 | experiments, four verdicts |
| all | Step 10 | the memo |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is never
> marked right or wrong. A node needs about 2 s to be seen by the `ros2` tools: if one says "Node not found"
> or prints nothing, wait and run it again. A line "A message was lost!!!" from `ros2 topic echo` is harmless.

> [!WARNING] One terminal tab for the whole lab (as in mission 09)
> Each terminal tab is a small private computer of its own: a node started in one tab **cannot be seen** from
> another tab. Run every command in the **same** tab, and start nodes in the background with `&`, their output
> going to a log file. `jobs` lists them; `kill -INT %%` stops the most recent one (what Ctrl+C would send);
> `kill -INT $(jobs -p)` stops them all. Before you start a node, run `jobs`: never two copies of one node.

## Session 1 — Build (about 2 h 30)

## Step 0 — The bug

```bash
python3 run_gps.py bug
```

A GPS measures one position per second on a vehicle at 10 m/s, and a forwarder re-sends the latest one five
times per second, stamped when it **sends** it. Read the right-hand column, then open `out/bug.png`.

> [!TASK]
> `BUG_SPEED_10HZ_MPS`: a faster forwarder re-sends 10 times per second. Work out the largest speed the
> listener computes **before** you run it, then check:

```bash
python3 run_gps.py bug --rate 10
```

## Step 1 — Read your file, run the starter

Open [gps_node.py](file:./navera_lite/ros/gps_node.py). Top to bottom: `TOPIC`, `ALTITUDE_M`, `DEFAULTS` (the
eight parameters), your three functions, the class `FakeGps` (its `__init__` is finished: it calls your
`declare_all()` and `start()`), and `main()`. Each TODO's docstring gives its goal and one example with the
result. Now run the node:

```bash
python3 -m navera_lite.ros.gps_node
```

It stops at once with a traceback. Read its **last** line: `NotImplementedError: TODO 4`. Python stops at the
first TODO it meets, in `__init__`. (`python3 -m navera_lite.ros.gps_node` runs the module `gps_node` of the
package; mission 09 showed why we start nodes this way.)

## Step 2 — One step of motion (TODO 1)

<details><summary>🧰 Two Python tools for TODO 1</summary>

```python
def ratio(a, b):
    if b == 0:
        raise ValueError(f"b must not be 0, got {b}")    # stops the function with a clear error
    return a / b

x, y = (3.0, 4.0)        # unpacking: a function returning (e, n) gives two variables in one line
```
</details>

**TODO 1** `step(lat, lon, speed_mps, heading_deg, dt_s)`: lesson §3, "One step of motion" (it is the lesson's
worked example). `vehicle.ground_velocity` and `geo.offset` are already imported at the top of the file.

```bash
python3 run_gps.py test
```

The two `TODO 1` lines must be ✔ (the others come later).

<details><summary>Stuck? Hints, one at a time</summary>

1. Three lines: the velocity (east, north), the move in metres (velocity × dt), the new position.
2. Moved towards 0° instead of 90°? `geo.offset` takes east **first**: `offset(lat, lon, e_m, n_m)`. Or you
   wrote your own sin/cos with the ENU angle (from east): a heading is from north, clockwise.
3. Always 10.00 m whatever dt? You forgot to multiply by `dt_s`.
4. The ValueError line is ✘: test `dt_s < 0` **before** computing anything, and `raise ValueError(...)`.
</details>

## Step 3 — Real dt or nominal dt?

A survey boat leaves Singapore's harbour at 12 m/s, heading 45°, with a 2 Hz timer on a busy computer. The
runner has the real instants of the calls. It moves one receiver with **your** `step()` and the real dt, and
another with the nominal 0.5 s, and compares both with where the boat really was at each stamp.

> [!TASK]
> **Predict** (`PREDICT_DRIVE`): one gap between the ticks will be long. After the last tick, will the nominal
> receiver be ahead of the truth, behind it, or on it? And yours?

```bash
python3 run_gps.py drive
```

The NOMINAL columns are hidden (`?`). Compute them yourself from the `stamp` column: after the first tick, the
nominal receiver adds 12 m/s × 0.5 s at every tick, while the boat really moves 12 m/s × (stamp − first stamp).
The speed a listener computes is the distance between two fixes ÷ the difference of their stamps. Then reveal:

```bash
python3 run_gps.py drive --reveal
```

Open `out/drive.png`.

> [!TASK]
> `NOMINAL_ERROR_M` (the nominal receiver's distance from the truth at the **last** stamp, one decimal) and
> `NOMINAL_SPEED_MAX_MPS` (the largest speed a listener computes from it, one decimal), computed by you and
> confirmed by `--reveal`. `EXPLAIN_DRIVE`: why is the nominal receiver wrong, and why does its error not
> shrink again after the busy second? (Lesson §3, the figure of the busy timer.)

## Step 4 — An honest NavSatFix (TODO 2 and 3)

<details><summary>🧰 None, nan, and filling a message</summary>

```python
import math
for v in (None, 2.0, float("nan"), -1.0):
    print(v is None, v is not None and math.isfinite(v))   # test None FIRST: math.isfinite(None) crashes

from std_msgs.msg import Header
h = Header()
h.frame_id = "camera"             # a field of a message is set like an attribute
h.stamp.sec = 12                  # a nested field: two dots
```
</details>

**TODO 2** `covariance_from_sigma(sigma_m)` and **TODO 3** `make_fix(lat, lon, alt_m, sigma_m, stamp_s)`:
lesson §4 (the table, the worked example and the warning box). In TODO 3 use your TODO 2 and the given
`convert.s_to_stamp` (already imported). Mission 09's `convert.to_navsatfix` fills the same message from an
Estimate: write yours **without** looking at it first. The constants are on the message classes, e.g.
`NavSatStatus.STATUS_FIX`; this prints them all:

```bash
ros2 interface show sensor_msgs/msg/NavSatFix
```

```bash
python3 run_gps.py test
```

All TODO 1–3 lines must be ✔. Now open [convert.py](file:./navera_lite/ros/convert.py) and compare
`to_navsatfix` with your `make_fix`, field by field.

> [!TASK]
> `EXPLAIN_FIX` (one sentence): one field that `to_navsatfix` fills differently from your `make_fix`, and why.

<details><summary>Stuck? Hints, one at a time</summary>

1. TODO 2 has two cases. Decide first whether σ is "stated" (a number, finite, > 0); otherwise return the
   unknown case at once.
2. `[9, 0, 0, …]` or "each value of type 'float'": write `0.0`, and square `float(sigma_m)`.
3. Type 2 instead of 1: a stated σ is `COV_APPROXIMATED` (imported from `navera_lite.estimate`).
4. TODO 3: the stamp shows `nanosec=0`? You wrote `int(stamp_s)`: use `s_to_stamp(stamp_s)`. `service is 0`?
   Set `msg.status.service`.
5. `make_fix(36, 10, 40, …)` crashes: `msg.latitude = float(lat)`, and the same for longitude and altitude.
</details>

## Step 5 — The node: parameters, publisher, timer (TODO 4 and 5)

<details><summary>🧰 Walking through a dictionary</summary>

```python
limits = {"speed_mps": 30.0, "altitude_m": 120.0}
for name, value in limits.items():      # each key with its value
    print(name, value)
```
</details>

**TODO 4** `declare_all(self)` and **TODO 5** `start(self)`: lesson §1 (the Heartbeat node) and §2. Use
`TOPIC` and `qos.FIX_QOS` (imported as `FIX_QOS`). The runner builds your node and inspects it, without ever
letting its timer fire (your `on_timer` is still a stub):

```bash
python3 run_gps.py node
```

Now with parameters from the command line, as a user would start it:

```bash
python3 run_gps.py node -p rate_hz:=4.0 -p start_lat:=-33.9249 -p start_lon:=18.4241
```

Every line must be ✔: the start is Cape Town and the timer period 0.250 s.

<details><summary>Stuck? Hints, one at a time</summary>

1. TODO 4: one `declare_parameter` per item of `DEFAULTS` (name and default value), in a loop. Then read
   `start_lat` and `start_lon` back **from the parameters**: `-p` must win over the defaults.
2. The start is still Sousse with `-p start_lat:=…`? You copied `DEFAULTS["start_lat"]` instead of reading
   the parameter.
3. TODO 5: `self.pub = …` (the given `__init__` and your `on_timer` use `self.pub`). Period = 1 / rate.
4. "on_timer was CALLED while the node was built": you wrote `self.on_timer()`. Give `self.on_timer`.
</details>

## Step 6 — Every tick (TODO 6), live

**TODO 6** `on_timer(self)` is the least guided TODO: its docstring says what one tick does. Before you code,
**trace it by hand**: rate 2 Hz, 10 m/s, heading 90°, ticks really at 0.00, 0.47 and 1.06 s. What are dt,
the distance moved and the stamp at each of the three ticks? (Lesson §3.)

<details><summary>Check your trace</summary>
dt = 0.00, 0.47, 0.59 s; moved 0.0, 4.7, 5.9 m east; stamps 0.00, 0.47, 1.06 s (the instants of the ticks,
since stamp_offset_s is 0.0). If you wrote 5.0 m at each tick, you used the nominal dt.
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. Order: read the clock once (`self.now_s()`); compute dt from `self.last_t` (0.0 when it is `None`); store
   the clock in `self.last_t`; read the parameters; move with `step()`; publish.
2. Read `speed_mps`, `heading_deg`, `sigma_m` and `stamp_offset_s` **inside** `on_timer`, with
   `self.get_parameter(name).value`: values read once never follow `ros2 param set`.
3. The stamp is the clock you read + `stamp_offset_s`; the altitude is `ALTITUDE_M`.
4. `TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'`: the first tick has no previous one.
5. The vehicle speeds up and up? `self.last_t` must change at **every** tick.
</details>

Start your receiver in the background, its log in `gps.log`:

```bash
python3 -m navera_lite.ros.gps_node > gps.log 2>&1 &
```

```bash
cat gps.log
```

It logs `fake GPS on /navera_lite/fix/gps from (35.8256, 10.6084)` and then nothing more: a silent node is
normal (you may add a log line every 10 fixes with `self.get_logger().info(…)` and `self.count`, as the
course's reference does). A traceback in `gps.log` means your on_timer crashed: read its last line. Now one
message (the type is given, so it waits for your node):

```bash
ros2 topic echo /navera_lite/fix/gps sensor_msgs/msg/NavSatFix --once
```

Check every field against lesson §4. Now drive it: turn north, and watch the latitude grow (Ctrl+C stops the
echo, which runs in the foreground):

```bash
ros2 param set /fake_gps heading_deg 0.0
```

```bash
ros2 topic echo /navera_lite/fix/gps sensor_msgs/msg/NavSatFix --field latitude
```

Fall into the type trap on purpose, then do it right:

```bash
ros2 param set /fake_gps speed_mps 20
```

```bash
ros2 param set /fake_gps speed_mps 20.0
```

Now measure the rate. Wait for at least 5 blocks, then Ctrl+C:

```bash
ros2 topic hz /navera_lite/fix/gps
```

(A first line "WARNING: topic … does not appear to be published yet" only means the tool has not discovered
your node yet: the rates follow.)

> [!TASK]
> `MEASURED_RATE_HZ` (the last "average rate") and `MEASURED_STD_S` (the last "std dev", in seconds).
> Then stop the receiver:

```bash
kill -INT %%
```

An idle Jetson hardly jitters. Optional: restart it in the background with `--ros-args -p rate_hz:=50.0`,
measure again, and stop it. What fraction of the 0.020 s period is the std now?

## Step 7 — Your node on a busy computer

The runner starts **your** node at 2 Hz, 10 m/s east, and makes every call of your `on_timer` start 0–0.2 s
late, and one call 1.3 s late. It listens to your fixes and compares each with where the vehicle really was at
its stamp.

> [!TASK]
> **Predict** (`PREDICT_JITTER`): what speeds will a listener compute from your fixes?

```bash
python3 run_gps.py jitter
```

Open `out/jitter.png`. The last lines compare your node with a nominal-dt node at the same instants, and test
two of your knobs (`stamp_offset_s` −2.0, `sigma_m` 1.5): both must be ✔ before session 2. (Your error column
is 0.00 m by construction when dt is real: the truth and your node use the same clock reading. The column that
tests you is "speed seen".)

> [!TASK]
> `EXPLAIN_JITTER`: why do your fixes stay right although the intervals vary so much, and what would a
> nominal-dt node show at the same instants?

> [!TIP] 🏅 End of session 1 — Builder
> Press **✔ Check my work**. It runs its own copy of your node (in the namespace `/check10`, so your
> background nodes do not disturb it), with random delays, a turn by `ros2 param set`, a stamp offset and no σ, on positions it has
> never seen. When every check of TODO 1–6, "The judge", Steps 0 and 3 and Steps 6–7 passes, you earn the
> **Builder** badge (about 1 minute).

## Session 2 — Sabotage (about 1 h 30)

## Step 8 — Meet the judge

Run `jobs` first: nothing should be running. Start arbiter v0 with your settings file (mission 09), then your
receiver, both in the background:

```bash
python3 -m navera_lite.ros.arbiter_v0 --ros-args --params-file navera_lite.yaml > arbiter.log 2>&1 &
```

```bash
python3 -m navera_lite.ros.gps_node > gps.log 2>&1 &
```

Now the judge's latest decision (latched, so it arrives at once):

```bash
ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --once
```

Find `message` (the reason), the value of `state`, `sigma_m` and `age_s`. Run it a few times, at irregular
moments a few seconds apart: `age_s` moves between about 0 and 1 s. Why? (Your receiver publishes once per
second; the judge decides five times per second.) The judge's own log is in `arbiter.log`: it writes a line
each time its state changes, or when it refuses a fix.

## Step 9 — The saboteur

Your receiver has two knobs that a real fault can turn: `stamp_offset_s` (header.stamp = now + offset) and
`sigma_m` (0.0 = the receiver states no accuracy). Before you start, two things about the judge:

- **The jump gate (mission 01) also watches your restarts.** A new receiver starts again at the start point,
  far from the last trusted fix, so `arbiter.log` may get `WARN … gps fix refused: jump … m > … m in … s` for
  15 s to about a minute (the longer the previous receiver flew, the farther it is from the start point). Keep an eye on these lines: one of the experiments gives a strange one.
- **Check your knob first.** In A, the status must end up saying `gps: stale (5.x s > 3.0 s)` about YOUR fix
  (between 5 and 6 s: the offset plus the time since the last fix; not a stale fix of 10 s or more: that one is
  still Step 8's receiver, so wait).
  If the judge says FIX with an age of 0–1 s instead, your on_timer ignores `stamp_offset_s` (Step 6, hint 3):
  fix it before B, C and D.

Four experiments, **in this order**:

| | Restart your receiver with | What it imitates |
|---|---|---|
| A | `-p stamp_offset_s:=-5.0` | a receiver whose clock is 5 s slow (for the judge's age test: a fix delivered 5 s late) |
| B | `-p sigma_m:=40.0` | a receiver that sees few satellites |
| C | `-p sigma_m:=0.0` | a receiver that states no accuracy |
| D | `-p stamp_offset_s:=30.0` | a receiver whose clock is 30 s fast |

> [!TASK]
> **Predict** (`PREDICT_SABOTAGE`) the state v0 shows in A, B, C and D. Use lesson §5's rules only (do not read
> `arbiter_v0.py` first: you are the attacker, you only see the judge from outside).

For each experiment, stop the receiver (your most recent job) and start it again with the knob **in one line**,
so the new receiver starts within 2 s (press ↑ to get the line back and edit the knob for B, C, D).
Experiment A:

```bash
kill -INT %%; python3 -m navera_lite.ros.gps_node --ros-args -p stamp_offset_s:=-5.0 > gps.log 2>&1 &
```

Wait until the status `message` no longer says `last fix refused` (15 s to about a minute: the longer your
Step 8 receiver flew, the farther it is from the start point), then read the status (`state`, `message`,
`age_s`):

```bash
ros2 topic echo /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus --once
```

and the gate's lines in the judge's log:

```bash
grep "refused" arbiter.log | head -n 4
```

When A started, the gate's first refusal lines say `… in -… s`, a **negative** time (Step 8 has no refusals,
so `head` shows A's first ones).

Then B, C, D the same way, one line each
(`kill -INT %%; python3 -m navera_lite.ros.gps_node --ros-args -p sigma_m:=40.0 > gps.log 2>&1 &`, …). In B,
copy the `message` exactly. In D, read `age_s` too. Then, still in D, stop your receiver and print the clock at
once (seconds since 1970), in one line:

```bash
kill -INT %%; date +%s
```

Wait a minute, then find the judge's **last** `NO_FIX` line in its log (the one stamped after the `date` you
printed; an earlier NO_FIX can come from the gap while you restarted a receiver). The first number in brackets
is the time in the same seconds.

```bash
grep NO_FIX arbiter.log | tail -n 1
```

The difference is how long the judge kept a dead receiver alive.

> [!TASK]
> `V0_OLD`, `V0_COARSE`, `V0_NO_SIGMA`, `V0_FUTURE` (each `"FIX"`, `"DEGRADED"` or `"NO_FIX"`),
> `V0_COARSE_REASON` (B's `message`, exactly), `AGE_FUTURE_S` (the `age_s` of D) and `FROZEN_S` (after you
> stopped the receiver in D, how many seconds v0 still said FIX). `EXPLAIN_HOLES`: which verdicts are wrong, and
> why does v0 make each mistake? (Lesson §5's rules: what does v0 compute, and what does it never ask?)
> `EXPLAIN_JUMP`: in A, why was the gate's elapsed time negative, and what does the gate assume about stamps?
> (Mission 01: elapsed = the new fix's stamp − the stamp of the last trusted fix.) Then read lesson §5's box
> "Read this after lab Step 9".

When you are done, stop everything (after D, the arbiter's jump gate remembers a fix from the future), and
check that `jobs` prints nothing:

```bash
kill -INT $(jobs -p); sleep 1; jobs
```

## Step 10 — The memo

Fill [report.md](file:./report.md): three short sections, at least 150 words of your own, for a teammate
who will use your receiver to test their nodes. Quote your measured rate, the nominal receiver's error of Step
3, and the two verdicts of Step 9 that are wrong.

## Step 11 — Check, then look back

Press **✔ Check my work**. When every check passes you earn the **Saboteur** badge. Then, without the lesson:

1. Explain to a teammate, in three sentences, how "stopped, then jumped" happens and how a stamp prevents it.
2. Which of your predictions was the most wrong, and why?
3. A real receiver measures a fix at 12:00:00.000 and its serial line delivers it at 12:00:00.180. Which
   instant goes in `header.stamp`, and what would a judge get wrong with the other one?

## Going further (optional)

- **A tunnel.** Add a parameter `outage` (default `False`): while it is `True`, publish `STATUS_NO_FIX`, NaN
  latitude and longitude and type UNKNOWN. Turn it on with `ros2 param set /fake_gps outage true` and watch
  arbiter v0's reason.
- **The bug, live.** Write `repeater.py`, a node that subscribes to `navera_lite/fix/gps` and re-publishes
  the latest fix at 5 Hz on `navera_lite/fix/day` with a fresh stamp each time. Stop your receiver: what does
  the judge do with the day source? What would a listener computing speeds see?
- **Fly your own parts.** `cp ../06-coordinates/navera_lite/geo.py navera_lite/` replaces the course's
  `geo.py` with your mission 06 version; run `python3 run_gps.py drive` again. Same numbers?

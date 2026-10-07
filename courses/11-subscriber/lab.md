# Lab 11 — A trip computer, then NAVERA's verdict

**Goal:** finish two subscriber nodes. [gps_listener.py](file:./gps_listener.py) computes the distance
and speed of a GPS track. [status_listener.py](file:./status_listener.py) prints, in words, what
NAVERA's real arbiter decides — and you watch it change when the GPS stops.
**Time:** about 1 hour 15 minutes.

Your lab folder also contains [gps_track_player.py](file:./gps_track_player.py): a ready-made GPS
source that drives along a small route in Sousse at **6 m/s** and publishes on `/fake_gps/fix`, the
same topic as your fake GPS of lesson 10. You don't need to change it. (You may use your own
`~/lessons/10-publisher/fake_gps.py` instead in steps 3 and 6 — but the checker uses the player,
because it knows its exact speed.)

You will need **four terminals** in step 6: open them with **＋ new** when needed.

## Part A — The trip computer

### Step 1 — Write the memory (TODO 1)

Open `gps_listener.py`. The class `Tracker` is plain Python: no ROS inside.

> [!TASK]
> **TODO 1** — complete `Tracker.update(lat, lon, t)`: count the fix, add the step since the previous
> fix to `self.distance_m`, compute the speed when `dt > 0`, remember the fix in `self.last`, and
> return the speed (or `None`). The comments in the file list every action.

Test it **without ROS**. This command imports your file, creates a tracker, gives it 3 fixes 0.001°
of latitude apart (about 111 m) and 10 s apart, and prints what it returns:

```bash
python3 -c "from gps_listener import Tracker; t = Tracker(); print(t.update(35.8, 10.6, 0), t.update(35.801, 10.6, 10), t.update(35.802, 10.6, 20)); print(t.count, round(t.distance_m, 1))"
```

You must see `None 11.119… 11.119…` then `3 222.4`. If not, fix TODO 1 before going on: the ROS
part cannot be right if the logic is wrong.

### Step 2 — Subscribe and log (TODO 2 and 3)

> [!TASK]
> **TODO 2** — in `GpsListener.__init__`, subscribe to `NavSatFix` on `TOPIC`, with the callback
> `self.on_fix` and a queue depth of 10.
> **TODO 3** — in `on_fix(msg)`, compute `t` from `msg.header.stamp`, call
> `self.tracker.update(...)`, and log exactly one line per fix in this format:
> `fix 12: distance 66.0 m, speed 6.0 m/s` (with `?` for an unknown speed).

### Step 3 — Run the chain

In **Terminal 1**, start the GPS source:

```bash
python3 gps_track_player.py
```

In **Terminal 2**, start your listener:

```bash
python3 gps_listener.py
```

A line every 0.5 s: the fix number grows by 1, the distance by about 3 m, the speed stays near 6 m/s.
At a corner of the route, the speed dips a little for one fix — the straight line between two fixes
"cuts the corner", so the step is a bit shorter than the real path. Real GPS trip computers have
the same small error.

Stop the listener (`Ctrl+C`) and start it again: the distance starts from 0 again — the state lives
in the running program, not on disk. Leave the player running.

## Part B — Listen to NAVERA

### Step 4 — Name the states (TODO 4)

Open `status_listener.py`. The function `describe(msg)` is given; it needs `state_name()`.

> [!TASK]
> **TODO 4** — complete `state_name(state)` so that it returns `"INITIALIZING"`, `"NO_FIX"`, `"FIX"` or
> `"DEGRADED"`, using the constants `NavStatus.STATE_…`, and `f"UNKNOWN STATE {state}"` for anything else.

Test it without ROS:

```bash
python3 -c "from status_listener import *; print([state_name(n) for n in range(5)])"
```

Expected: `['INITIALIZING', 'NO_FIX', 'FIX', 'DEGRADED', 'UNKNOWN STATE 4']`.

### Step 5 — Subscribe, but don't chatter (TODO 5 and 6)

The arbiter publishes 5 status messages per second. Printing all of them would flood the screen
with identical lines. A good listener prints only when something **changes** — that needs state again.

> [!TASK]
> **TODO 5** — subscribe to `NavStatus` on `TOPIC` with the callback `self.on_status`.
> **TODO 6** — in `on_status`, log `describe(msg)` only when `(msg.state, msg.active_source)` is
> different from `self.last_key`, then store the new key in `self.last_key`.

### Step 6 — Plug your GPS into NAVERA

Keep the track player running in **Terminal 1**. Stop the gps_listener in Terminal 2 (`Ctrl+C`) and
start NAVERA's arbiter there:

```bash
ros2 run navera_estimator estimator_node.py
```

In **Terminal 3**, start your status listener:

```bash
python3 status_listener.py
```

It prints `INITIALIZING | source: none | waiting for first source message` — the arbiter runs, but
no source has ever talked to it: the player publishes NavSatFix on `/fake_gps/fix`, and the arbiter only reads
PositionEstimate on `/navera/estimate/…`. Let's connect them. In **Terminal 4**, start NAVERA's GPS
bridge, listening to the player's topic:

```bash
ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/fake_gps/fix
```

It logs `GPS from /fake_gps/fix`. Look at Terminal 3: a new line,
**`FIX | source: GPS | GPS fix`**. NAVERA trusts your GPS! (If you start the listener before the arbiter, it
prints nothing until the arbiter starts: no message, no callback.)

### Step 7 — Look at the whole chain

Use any free terminal (stop nothing). First the nodes:

```bash
ros2 node list
```

You see `/gps_track_player`, `/estimator_node`, `/ros_gps`, `/status_listener`. Now NAVERA's
output position:

```bash
ros2 topic echo --once /navera/position
```

It is the player's position, turned into NAVERA's contract: `source: 1` (GPS), `mode: 0` (measured),
`valid: true`, `producer: navera_estimator`. Compare its rate with the GPS:

```bash
ros2 topic hz /navera/position
```

About 2 Hz (ignore a first `WARNING: … does not appear to be published yet`: the rates follow). The
arbiter publishes **once per new measurement**, never the same position twice.

### Step 8 — Switch the GPS off

Go to **Terminal 1** and stop the track player with `Ctrl+C`. Watch Terminal 3. After about
3 seconds:

```
NO_FIX | source: none | GPS: stale (3.0s>3.0s); day: none received; night: none received; cn: none received
```

The last GPS fix became too old (`gps_timeout_s` = 3 s), and NAVERA says so, with the reason. It does
**not** keep publishing the last position on `/navera/position` — check it: `ros2 topic echo --once
/navera/position` now waits forever (`Ctrl+C`). Start the player again: back to `FIX` within a second.

> [!QUESTION]
> Why does NAVERA wait 3 seconds instead of saying NO_FIX as soon as one fix is late? Think of a real
> GPS that sends one fix per second and sometimes loses one. (The comment above `gps_timeout_s` in
> `navera_estimator/navera_estimator/config/estimator_params.yaml` gives NAVERA's answer.)

Stop everything with `Ctrl+C` in each terminal.

### Step 9 — Check your work

Press **✔ Check my work**. The checker runs the player with your gps_listener, then the whole NAVERA
chain with your status_listener — including switching the GPS off. It takes about 40 seconds.

## Going further (optional)

- **Your own GPS.** Redo step 6 with your fake GPS of lesson 10 instead of the player:
  `python3 ~/lessons/10-publisher/fake_gps.py`. It must reach `FIX` too.
- **A tunnel.** In your fake GPS, publish `status.status = NavSatStatus.STATUS_NO_FIX` for a few
  seconds. What does `ros2 topic echo /navera/estimate/gps --field valid` show? And the arbiter?
- **Maximum speed.** Add to `Tracker` a `max_speed_mps` that remembers the highest speed seen, and log
  it. Then think: the arbiter refuses a GPS that "jumps" faster than the vehicle can move
  (its parameter `max_speed_mps`; lesson 25 explains it) — a trip computer is the first step towards
  that check.

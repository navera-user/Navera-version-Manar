# Lab 11 — A filtering trip computer, an executor experiment, and NAVERA's verdict

**Goal:** finish three subscriber programs and measure what they do:
[gps_listener.py](file:./gps_listener.py) (filter fixes, distance and speed),
[executor_demo.py](file:./executor_demo.py) (single- versus multi-threaded executor) and
[status_listener.py](file:./status_listener.py) (NAVERA's real arbiter, including how fast it detects
a silent GNSS). You write the analysis in [report.md](file:./report.md).
**Time:** about 3 h. You need up to **four terminals** (**＋ new**); `Ctrl+C` stops a node.

Your folder also contains [gps_track_player.py](file:./gps_track_player.py), a ready-made GNSS source
that drives a loop near the Ribat of Sousse (NAVERA's test area) at **6 m/s** and publishes on `/fake_gps/fix` at
2 Hz. You don't need to change it. Its parameters `noise_m` and `faults` add Gaussian noise or bad
fixes on purpose. (Your own `~/lessons/10-publisher/fake_gps.py` publishes on the same topic and also
works — but the checker uses the player, because it knows its exact behaviour.)

## Part A — The trip computer

### Step 1 — Filtering (TODO 1)

Open `gps_listener.py`. The class `Tracker` contains no ROS: you can test it with one line.

> [!TASK]
> **TODO 1** — `Tracker.check(lat, lon, t, status)` returns `""` for a usable fix, or the first
> reason that applies, in this order: `NO_FIX`, `NOT_FINITE`, `NULL_ISLAND`, `NOT_NEWER`.

```bash
python3 -c "from gps_listener import *; t = Tracker(); print(repr(t.check(35.8, 10.6, 10.0)), t.check(35.8, 10.6, 10.0, -1), t.check(float('nan'), 10.6, 10.0), t.check(0.0, 0.0, 10.0))"
```

Expected: `'' no fix not finite null island`. (`NOT_NEWER` needs a previous fix: step 2 tests it.)

### Step 2 — Distance and speeds (TODO 2)

> [!TASK]
> **TODO 2** — `Tracker.update(...)`: for an accepted fix, count it, add the step, compute the
> instantaneous speed and the window speed, and remember the fix.

Three fixes 0.001° of latitude apart (111.2 m) and 10 s apart, then two bad ones:

```bash
python3 -c "from gps_listener import *; t = Tracker(); print(t.update(35.828, 10.64, 0), t.update(35.829, 10.64, 10), t.update(35.830, 10.64, 20)); print(t.update(35.831, 10.64, 15), t.update(0.0, 0.0, 30)); w = t.window_speed_mps; print(t.count, round(t.distance_m, 1), w if w is None else round(w, 3), t.rejected)"
```

Expected: `None 11.119… 11.119…`, then `None None`, then `3 222.4 11.119 {'not newer': 1, 'null island': 1}`.

### Step 3 — What noise does (no ROS)

`noise_study.py` replays 2 minutes of the player's drive through **your** `Tracker`, without noise and
with σ = 3 m (fixed random seed), and writes `results.json`:

```bash
python3 noise_study.py
```

Compare with the course (section 4). What you should see with σ = 3 m:

| Number | Expected | Why |
|---|---|---|
| distance ratio | about 2.1 | each noisy step is longer than the true 3 m step (the Rayleigh bias) |
| instantaneous speed: mean | about 12.6 m/s, not 6 | the same bias: the length of a noisy step is never negative |
| instantaneous speed: std | about **6.1 m/s**, not 8.5 | see below |
| window speed: mean ± std | about 6.0 ± **1.0** m/s | close to the prediction √2·σ/4.5 s ≈ 0.94 m/s |

**Why 6.1 and not 8.5 m/s?** The formula √2·σ/dt = 8.5 m/s is the spread of each **component**
(east, north) of the speed vector. It is only the spread of the speed **length** when the noise is
small compared with the step. Here the noise (4.2 m per axis) is bigger than the step (3 m). A length
cannot be negative, so the negative side is "folded" onto the positive side: the mean goes up (12.6)
and the spread goes down. For pure noise (a parked car), the spread of the length is
√(2 − π/2) ≈ 0.66 times the per-axis value: 0.66 × 8.5 ≈ 5.6 m/s. With a real 3 m step it is a
little larger: 6.1 m/s. So 6.1 is the correct result, not a bug.

**Without noise**, the instantaneous std is about 0.14 m/s, not 0, and the window speed is a little
below 6 m/s on average (about 5.92). The reason is the **corners** of the route: in a turn, the
straight line between two fixes (the chord) is shorter than the curved path (the arc), so the
computed speed drops a little. A long window cuts more of the corner than one step, so the window
speed drops more.

### Step 4 — Subscribe and log (TODO 3)

> [!TASK]
> **TODO 3** — in `GpsListener`, subscribe with `qos_profile_sensor_data` (3a) and, in `on_fix`, log
> exactly one line per message (3b): `fix 12: distance 66.0 m, speed 6.0 m/s, window 6.0 m/s` or
> `rejected (no fix), 3 so far` (3 = the number of fixes rejected so far **for this reason**).

**Terminal 1** — start the player:

```bash
python3 gps_track_player.py
```

**Terminal 2** — start your listener:

```bash
python3 gps_listener.py
```

A line every 0.5 s: the distance grows by about 3 m, both speeds stay near 6 m/s; at a corner the
window speed dips for a few seconds. Stop both (`Ctrl+C`). Now a **faulty** receiver, in Terminal 1:

```bash
python3 gps_track_player.py --ros-args -p faults:=true
```

and your listener again in Terminal 2:

```bash
python3 gps_listener.py
```

Every 6 s you see `rejected (no fix)`, `rejected (null island)` and `rejected (not newer)`, and the
distance and speeds stay correct. Stop both. Finally a **noisy** receiver, in Terminal 1:

```bash
python3 gps_track_player.py --ros-args -p noise_m:=3.0
```

Restart your listener in Terminal 2 and watch the two speeds for 20 seconds: the instantaneous speed
jumps between a few m/s and more than 20 m/s, the window speed stays within about ±2 m/s of 6. Stop the listener;
**restart the player without parameters** (as at the beginning of this step) and leave it running.

## Part B — Executors

### Step 5 — Measure the waiting timer (TODO 4)

`executor_demo.py` has a 10 Hz timer and a fix callback that works for 0.3 s. With the player running
in Terminal 1, run the single-threaded version in Terminal 2 (it stops by itself after 8 s):

```bash
python3 executor_demo.py single
```

Read `ticks` (out of `expected_ticks` = 80) and `max_gap_ms`. The result is also saved in
`executor_single.json`.

> [!TASK]
> **TODO 4** — when `separate_groups` is true, give the timer and the subscription their own
> `MutuallyExclusiveCallbackGroup` (4a), and return a `MultiThreadedExecutor(num_threads=2)` for
> `"multi"` (4b).

```bash
python3 executor_demo.py multi
```

Now about 80 ticks and a maximum gap close to 100 ms. Try one variant to understand groups: put
**both** callbacks in the **same** group (the same `MutuallyExclusiveCallbackGroup` object) and run
`multi` again — explain the result in your report. Put the two groups back afterwards.

## Part C — Listen to NAVERA

### Step 6 — Names and silence (TODO 5 and 6)

Open `status_listener.py`.

> [!TASK]
> **TODO 5** — `state_name(state)` with the `NavStatus.STATE_…` constants.
> **TODO 6** — `gps_silence_s(msg)`: `header.stamp − last_seen` of the GPS entry of `msg.sources`,
> or `None` when GPS was never heard.

```bash
python3 -c "from status_listener import *; print([state_name(n) for n in range(5)])"
```

Expected: `['INITIALIZING', 'NO_FIX', 'FIX', 'DEGRADED', 'UNKNOWN STATE 4']`.

```bash
python3 -c "from status_listener import *; from builtin_interfaces.msg import Time; m = NavStatus(); m.header.stamp = Time(sec=100, nanosec=500000000); m.sources = [SourceHealth(source=SourceHealth.SOURCE_GPS, last_seen=Time(sec=97, nanosec=300000000))]; s = gps_silence_s(m); print(s if s is None else round(s, 3))"
```

Expected: `3.2`. (`None` means TODO 6 is not done yet.)

### Step 7 — Plug your GNSS into NAVERA (TODO 7)

> [!TASK]
> **TODO 7** — subscribe to `NavStatus` (7a) and, in `on_status` (7b), log `describe(msg)` only when
> `(state, active_source)` changes; on a change to `NO_FIX`, also log `GPS silent for 3.12 s`.

Keep the player running in **Terminal 1**. In **Terminal 2**, start NAVERA's arbiter:

```bash
ros2 run navera_estimator estimator_node.py
```

In **Terminal 3**, your status listener:

```bash
python3 status_listener.py
```

It prints `INITIALIZING | source: none | waiting for first source message`: the player publishes
`NavSatFix` on `/fake_gps/fix`, but the arbiter reads `PositionEstimate` on `/navera/estimate/…`. In
**Terminal 4**, start NAVERA's GNSS bridge, listening to the player's topic:

```bash
ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/fake_gps/fix
```

Terminal 3 prints **`FIX | source: GPS | GPS fix`**. NAVERA trusts your receiver.

### Step 8 — Look at the whole chain

Open a **fifth** terminal (**＋ new**) and stop nothing. The nodes:

```bash
ros2 node list
```

`/gps_track_player`, `/estimator_node`, `/ros_gps`, `/status_listener`. NAVERA's output position:

```bash
ros2 topic echo --once /navera/position
```

`source: 1` (GPS), `mode: 0` (measured), `valid: true`, `producer: navera_estimator`, and the
covariance of your receiver (9.0 = 3 m squared). Its rate (`Ctrl+C` after a few lines; ignore a first
`does not appear to be published yet`):

```bash
ros2 topic hz /navera/position
```

About 2 Hz: the arbiter publishes **once per new measurement**, never the same position twice.

### Step 9 — Switch the receiver off

Stop the player in **Terminal 1** (`Ctrl+C`) and watch Terminal 3. About 3 seconds later:

```
NO_FIX | source: none | GPS: stale (3.1s>3.0s); day: none received; night: none received; cn: none received
GPS silent for 3.13 s
```

Run it twice or three times (start the player, wait for `FIX`, stop it) and note the silence values.
The course predicts between 3.0 and about 3.2 s: the window `gps_timeout_s` plus at most one 5 Hz tick
(plus the time a stamp travels). NAVERA does **not** keep publishing the last position — check it:

```bash
ros2 topic echo --once /navera/position
```

It waits forever (`Ctrl+C`). Stop everything with `Ctrl+C` in each terminal.

## Step 10 — Write the analysis

Fill [report.md](file:./report.md) (at least 40 words per section):

- **Noise** — your numbers from `results.json` (distance ratio, both speed standard deviations) and
  the comparison with √2·σ/dt and √2·σ/((N−1)·dt); why the instantaneous mean is not 6 m/s.
- **Executors** — your `ticks` and `max_gap_ms` for single and multi, the utilisation ρ of this demo,
  and what happened with one shared group.
- **NAVERA** — the silence values you measured and why they are between 3.0 and 3.2 s; why the
  arbiter needs a timer and not only subscriptions.

Press **✔ Check my work**. The checker tests your classes, runs your listener with a normal and a
faulty player, runs the executor demo twice, then the whole NAVERA chain with your status listener —
including switching the GNSS off. It takes about 2 minutes.

## Going further (optional)

- **A smarter speed.** Replace the chord by a least-squares fit of position versus time over the window
  (`numpy.polyfit` on north and east separately). Compare its standard deviation with the chord's in
  `noise_study.py`. Which is better, and why (how many fixes does each method really use)?
- **Your own receiver.** Redo step 7 with `python3 ~/lessons/10-publisher/fake_gps.py` instead of the
  player. Then `ros2 param set /fake_gps heading_deg 90.0` while NAVERA is in FIX: does anything change
  in the arbiter's state? Why not?
- **Reentrant.** In `executor_demo.py`, use one `ReentrantCallbackGroup` for both callbacks and three
  threads. Count `fixes`: can two `on_fix` run at once now? What would that mean for a shared
  `self.count += 1`?

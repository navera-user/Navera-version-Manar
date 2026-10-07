# Lab 12 — Face the jury

**Goal:** fill a complete `PositionEstimate` in [my_source.py](file:./my_source.py), publish it to
NAVERA's real arbiter, then break it on purpose in six different ways and record each verdict in
[verdicts.py](file:./verdicts.py).
**Time:** about 1 hour 15 minutes.

Your source publishes on `/navera/estimate/day`, the arbiter's **day-vision mailbox**: the arbiter has
exactly four mailboxes (gps, day, night, cn) and no day vision runs in your sandbox, so we borrow
that one. (On a real box, two programs publishing on the same estimate topic would be a serious
mistake — the arbiter would mix their positions.)

You need **three terminals**. Keep them organised like this for the whole lab:

| Terminal | Runs |
|---|---|
| 1 | NAVERA's arbiter (start it once, leave it running) |
| 2 | your source (you will restart it many times) |
| 3 | the arbiter's verdict |

## Step 1 — The starter faces the jury

**Terminal 1** — start the arbiter of your NAVERA copy:

```bash
ros2 run navera_estimator estimator_node.py
```

**Terminal 2** — start your source as it is:

```bash
python3 my_source.py
```

**Terminal 3** — watch the verdict (5 lines per second; `Ctrl+C` to stop):

```bash
ros2 topic echo /navera/nav_status --field reason
```

You read something like `GPS: none received; day: stale (1791367701.9s>3.0s); night: …`. Stale by
**1.7 billion seconds**? The starter never fills the stamps, so they are 0 — and time 0 in ROS is
1 January 1970. The arbiter judged your position to be 56 years old! Every empty field has a value,
and the jury takes it seriously. Stop it with `Ctrl+C` in Terminal 3.

## Step 2 — Fill the form (TODO 1)

> [!TASK]
> **TODO 1** — complete `build_estimate(lat, lon, sigma_m, stamp)`. The comment lists every field and
> its value; the course explains why. Both stamps get `stamp`, the altitude is `math.nan`, and the
> covariance holds `sigma_m ** 2` at places 0 and 4.

Print one message without ROS, and read every field:

```bash
python3 -c "from my_source import *; from builtin_interfaces.msg import Time; print(build_estimate(35.8, 10.6, 15.0, Time(sec=100)))"
```

Now ask **NAVERA's own code** what it thinks of your message. This imports the arbiter's class from
your NAVERA copy and calls two of its rules, `_sane()` and `_stated_sigma()`:

```bash
python3 -c "from my_source import *; from builtin_interfaces.msg import Time; from navera_estimator.nodes.estimator_node import EstimatorNode as E; m = build_estimate(35.8, 10.6, 15.0, Time(sec=100)); print(E._sane(m), E._stated_sigma(m))"
```

You want `True 15.0`: a sane message, with a stated accuracy of 15 m.

## Step 3 — Accepted!

Restart your source in **Terminal 2** (`Ctrl+C`, then the up arrow `↑` and `Enter` to repeat the
command):

```bash
python3 my_source.py
```

and in **Terminal 3**:

```bash
ros2 topic echo /navera/nav_status --field reason
```

**`day vision fix`**. The jury accepted you! Stop the echo, and check the state number and the
position that NAVERA now publishes:

```bash
ros2 topic echo --once /navera/nav_status --field state
```

```bash
ros2 topic echo --once /navera/position
```

`state` is 2 (FIX). In `/navera/position`, find your latitude, `source: 2`, and
`producer: navera_estimator` — the arbiter re-signs the winning estimate, but it keeps your
`sensor_stamp`, `model_id` and `frame_index`: traceability.

> [!TASK]
> In `verdicts.py`, write the reason you saw in `REASON_GOOD`.

## Step 4 — Six ways to be refused (TODO 2)

> [!TASK]
> **TODO 2** — complete `apply_fault(est, fault)`: one `if` / `elif` per fault, each changing **only**
> what the comment says. The program reads the fault from the command line: `python3 my_source.py nan`.

Now play the jury game. For each fault: in **Terminal 2**, stop your source and start it with the
fault; in **Terminal 3**, read the verdict (`Ctrl+C` after a few lines). Copy the part about `day` into
`verdicts.py`.

```bash
python3 my_source.py nan
```

```bash
python3 my_source.py bad_cov
```

```bash
python3 my_source.py stale
```

```bash
python3 my_source.py invalid
```

```bash
python3 my_source.py replayed
```

```bash
python3 my_source.py unknown_cov
```

The verdict command, in Terminal 3 each time:

```bash
ros2 topic echo /navera/nav_status --field reason
```

> [!NOTE]
> After you switch faults, the first lines may still show the previous verdict for up to 3 s: the
> arbiter keeps the last message of each source until it becomes stale. Wait a moment.

Look at what each one teaches:

- `nan` and `bad_cov` → `non-finite position or covariance`: the arbiter's `_sane()` refused them.
  Even a message that says `valid: true` is checked.
- `stale` → `stale (11.0s>3.0s)`: the age is computed from `sensor_stamp`.
- `invalid` → `invalid (lens covered)`: your own `reason` is shown to the operator.
- `replayed` → `replayed not usable`: test data can never become a position.
- `unknown_cov` → **accepted, but DEGRADED**: `day vision fix, uncertainty unknown`. Check it with
  `ros2 topic echo --once /navera/nav_status --field state` → 3.

> [!TASK]
> Fill `REASON_NAN`, `REASON_BAD_COV`, `REASON_STALE`, `REASON_INVALID`, `REASON_REPLAYED` and
> `REASON_UNKNOWN_COV` in `verdicts.py`.

## Step 5 — Too uncertain for a FIX

In `my_source.py`, change `SIGMA_M = 15.0` to `SIGMA_M = 40.0`, save, and restart the source with no
fault:

```bash
python3 my_source.py
```

The verdict becomes `day vision fix, uncertainty 40 m > 25 m` — DEGRADED: the position is used, but
the arbiter tells everyone not to rely on it like on a GPS. The limit, 25 m, is the parameter
`fix_max_sigma_m` (you will change it in lesson 13).

> [!TASK]
> Write that reason in `REASON_SIGMA_40`, then **put `SIGMA_M` back to `15.0`** and save. Answer `Q1`
> and `Q2` at the bottom of `verdicts.py`.

Stop everything (`Ctrl+C` in each terminal).

## Step 6 — Check your work

Press **✔ Check my work**. The checker tests your two functions with NAVERA's own rules, then starts
the arbiter and runs your source four times (good, `stale`, `nan`, `unknown_cov`). About 30 seconds.

## Going further (optional)

- **A message from the future.** Add a fault `"future"` that puts both stamps 5 s **ahead** of now.
  What does the arbiter say? Find the parameter `future_tolerance_s` in
  `navera_estimator/navera_estimator/config/estimator_params.yaml` and read its comment.
- **GPS beats you.** Keep your good source running, and start lesson 11's track player
  (`python3 ~/lessons/11-subscriber/gps_track_player.py`) plus NAVERA's GPS bridge (`ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/fake_gps/fix`). Which source
  does the arbiter choose? Watch `--field active_source` for a few seconds: the switch is not
  immediate — find `switch_holdoff_s` in the YAML file to know why.
- **Propagated.** Add a fault that sets `mode = MODE_PROPAGATED`. Accepted? With which state and
  reason?

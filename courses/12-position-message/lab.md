# Lab 12 — Fill the contract, then let the arbiter judge it

**Goal:** implement the covariance mathematics of the course in [my_source.py](file:./my_source.py)
and [probability.py](file:./probability.py), publish a complete `PositionEstimate` to NAVERA's real
arbiter, inject twelve faults and record each verdict in [verdicts.py](file:./verdicts.py), then
argue a design question in [report.md](file:./report.md).
**Time:** about 3 h.

Your source publishes on `/navera/estimate/day`, the arbiter's **day-vision mailbox**: the arbiter has
four mailboxes (gps, day, night, cn) and no day vision runs in your sandbox, so we borrow that one.
(On a real box, two programs publishing on the same estimate topic would be a serious mistake.)

You need **three terminals** for Part B. Keep them organised:

| Terminal | Runs |
|---|---|
| 1 | NAVERA's arbiter (start it once, leave it running) |
| 2 | your source (you will restart it many times) |
| 3 | the arbiter's verdict |

## Part A — The mathematics, without ROS

### Step 1 — Build a covariance (TODO 1)

> [!TASK]
> **TODO 1** — `enu_covariance(sigma_along, sigma_cross, heading_deg, sigma_up)` returns the nine
> floats of Σ = R·diag(σ_a², σ_c²)·Rᵀ (course, section 2), plus σ_up² at index 8.

```bash
python3 -c "from my_source import *; print([round(x, 2) for x in enu_covariance(15, 6, 30, 6)]); print(enu_covariance(10, 2, 0))"
```

Expected: `[83.25, 81.84, 0.0, 81.84, 177.75, 0.0, 0.0, 0.0, 36.0]` — the course's worked example —
and for heading 0° (along = north): `[4.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0]`.

### Step 2 — Is it a covariance? Which ellipse? (TODO 2 and 3)

> [!TASK]
> **TODO 2** — `is_psd_2x2(cov)`: finite, symmetric, non-negative variances, non-negative determinant.
> **TODO 3** — `error_ellipse(cov)`: semi-axes from the eigenvalues, heading of the major axis.

```bash
python3 -c "from my_source import *; c = enu_covariance(15, 6, 30, 6); print(is_psd_2x2(c), error_ellipse(c)); print(is_psd_2x2([100, 120, 0, 120, 100, 0, 0, 0, 0]), is_psd_2x2([4, 1, 0, 2, 4, 0, 0, 0, 0]))"
```

Expected: `True (15.0, 6.0, 30.0)` (with tiny rounding), then `False False` — the first is not PSD
(determinant 10 000 − 14 400 < 0), the second not symmetric. Now compare your rule with **NAVERA's
own** `_sane` (imported from your NAVERA copy) on the same matrix:

```bash
python3 -c "from navera_estimator.nodes.estimator_node import EstimatorNode as E; from navera_msgs.msg import PositionEstimate as P; m = P(latitude=35.8277, longitude=10.6388, position_covariance=[100.0, 120.0, 0.0, 120.0, 100.0, 0.0, 0.0, 0.0, 0.0]); print(E._sane(m))"
```

`False`: the arbiter applies exactly the criterion of the course.

### Step 3 — Probability inside the ellipse (TODO 6 and 7)

> [!TASK]
> **TODO 6** — `mahalanobis2(e_east, e_north, cov)` in `probability.py`: d² = eᵀ Σ⁻¹ e. Invert the
> 2 × 2 block by hand and expand the product (course, section 3).
> **TODO 7** — `p_inside(k)`: the 2-D probability law of course section 3.

```bash
python3 probability.py
```

It samples 100 000 errors from your covariance and prints the fractions inside the 1, 2 and
2.448-sigma ellipses next to the theory, the 1-D fraction for the east error, and — part 2 — NAVERA's
**stated σ** next to your ellipse's largest σ for the default and the "tilted" covariance. Everything
is saved in `results.json`. The sampled values must agree with the theory to about ±0.006.

## Part B — The arbiter's verdict

### Step 4 — Fill the form (TODO 4)

First, see how the arbiter judges the starter. **Terminal 1**:

```bash
ros2 run navera_estimator estimator_node.py
```

**Terminal 2**:

```bash
python3 my_source.py
```

**Terminal 3** (5 lines per second; `Ctrl+C` to stop):

```bash
ros2 topic echo /navera/nav_status --field reason
```

You read something like `day: stale (1791…s>3.0s)`. The starter never fills the stamps, so they are 0
— 1 January 1970 — and the arbiter judged your position to be 56 years old. Every empty field has a
value, and the jury takes it seriously. Stop the echo.

> [!TASK]
> **TODO 4** — complete `build_estimate(lat, lon, cov, cov_type, stamp)`: every field of the contract.

Ask NAVERA's code what it thinks of your message, without ROS running:

```bash
python3 -c "from my_source import *; from builtin_interfaces.msg import Time; from navera_estimator.nodes.estimator_node import EstimatorNode as E; m = build_estimate(LAT, LON, enu_covariance(15, 6, 30, 6), PositionEstimate.COVARIANCE_TYPE_APPROXIMATED, Time(sec=100)); print(E._sane(m), E._stated_sigma(m))"
```

You want `True 13.33…`: a sane message whose stated σ is √177.75 (course, section 6). Restart your
source in **Terminal 2** (`Ctrl+C`, then `↑` and `Enter`):

```bash
python3 my_source.py
```

and read the verdict in **Terminal 3**:

```bash
ros2 topic echo /navera/nav_status --field reason
```

**`day vision fix`** — accepted. Check the state and the position NAVERA now publishes:

```bash
ros2 topic echo --once /navera/nav_status --field state
```

```bash
ros2 topic echo --once /navera/position
```

`state` 2 (FIX). In `/navera/position`: your latitude, `source: 2`, your covariance, and
`producer: navera_estimator` — the arbiter writes its own name in `producer` (it "signs" the
output), but it keeps your `sensor_stamp`, `model_id` and `frame_index`: traceability.

> [!TIP]
> `ros2 topic echo --once` sometimes prints nothing for a few seconds: it must first discover the
> topic. Wait about 5 s. If it still prints nothing, press `Ctrl+C` and run it again.

### Step 5 — Twelve faults for the jury (TODO 5)

> [!TASK]
> **TODO 5** — complete `apply_fault(est, fault)`: one `if` / `elif` per fault, each changing
> **only** what its comment says.

For each fault: in **Terminal 2**, stop your source and start it with the fault; in **Terminal 3**,
read the reason (`Ctrl+C` after a few lines) and the state, then write both into `VERDICTS` in
`verdicts.py`. The first one:

```bash
python3 my_source.py nan
```

The verdict commands, in Terminal 3 each time:

```bash
ros2 topic echo /navera/nav_status --field reason
```

```bash
ros2 topic echo --once /navera/nav_status --field state
```

Then the same with each of: `not_psd`, `stale`, `latency`, `future`, `invalid`, `replayed`, `held`,
`propagated`, `unknown_cov`, `big_sigma`, `tilted` — for example:

```bash
python3 my_source.py stale
```

> [!NOTE]
> Your source publishes once per second and the arbiter keeps the last message of each source, so
> the first line after a switch may still show the previous verdict. Wait two seconds.

When the state is **NO_FIX**, the reason has one part per source, for example
`GPS: none received; day: stale (10.0s>3.0s); night: none received; cn: none received`. Copy only the
`day: …` part. When the state is **FIX** or **DEGRADED**, the reason is one short sentence about the
winning source (for example `day vision fix, uncertainty unknown`): copy all of it.

What each one teaches (the exact texts printed by the arbiter):

- `nan`, `not_psd` → `day: non-finite position or covariance`: `_sane()` refused them, even with
  `valid` true. (The wording also covers a non-PSD matrix.)
- `stale` → `day: stale (10.0s>3.0s)` although **published now**: freshness is judged on
  `sensor_stamp`. You will see between 10.0 and about 11.0 s: your source publishes once per second,
  so the last message is up to 1 s older when the arbiter judges it.
- `latency` → still `day vision fix` (FIX): the photo is 2 s old, inside the 3 s window. Latency is
  allowed; staleness is not.
- `future` → `day: timestamp 4.5s in the future (clock problem)`. The number is between about 4.0
  and 5.0 s, not exactly 5.0, for the same reason: time passes between publication and judgement.
- `invalid` → `day: invalid (lens covered)`: your own `reason` reaches the operator.
  `replayed`, `held` → `day: replayed not usable`, `day: held not usable`.
- `propagated` → used, but DEGRADED: `day vision solution is propagated (dead-reckoned)`.
- `unknown_cov` → used, DEGRADED: `day vision fix, uncertainty unknown`.
- `big_sigma` → DEGRADED: `day vision fix, uncertainty 30 m > 25 m`.
- `tilted` → **FIX** (`day vision fix`) — although its ellipse is 30 m long. Compare with
  `big_sigma` and with your `results.json` (`stated_vs_max`): this is the design question of the
  report.

The checker only looks for the key words (for example `stale` and `>3.0s`), so 10.1 s or 4.5 s is
correct.

Stop everything (`Ctrl+C` in each terminal) and answer `Q1` and `Q2` in `verdicts.py`.

## Step 6 — Write the analysis

Fill [report.md](file:./report.md) (at least 40 words per section): **Covariance** (your matrix,
determinant, ellipse; what a non-PSD matrix would mean), **Probability** (sampled versus theory, 1-D
versus 2-D, what "σ = 15 m" means for an operator), **Stated sigma** (tilted versus big_sigma, and
your argued design choice).

Press **✔ Check my work**. The checker tests your functions against NAVERA's own rules, then starts
the arbiter and runs your source with seven faults. About a minute and a half.

## Going further (optional)

- **The 3-D ellipsoid.** Write `ellipsoid_axes(cov)` with `numpy.linalg.eigh` on the full 3 × 3 matrix
  and check it against your 2-D formula when the up terms are uncorrelated.
- **Correlated up.** Set Σ_EU = Σ_UE to a value that makes the 3 × 3 matrix non-PSD but keeps the
  horizontal block PSD. Does NAVERA's `_sane` notice? Read its docstring: what does it promise to check?
- **GPS beats you.** Keep your good source running, then start lesson 11's player
  (`python3 ~/lessons/11-subscriber/gps_track_player.py`) and NAVERA's bridge
  (`ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/fake_gps/fix`). Watch `--field
  active_source`: the switch to GPS is not immediate. Find `switch_holdoff_s` in
  `navera_estimator/navera_estimator/config/estimator_params.yaml` to know why.

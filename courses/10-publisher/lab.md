# Lab 10 — Build a fake GNSS receiver, measure it, and test the flat Earth

**Goal:** complete [fake_gps.py](file:./fake_gps.py), a node that publishes a `NavSatFix` on
`/fake_gps/fix` for a vehicle driving from Sousse with a speed and a heading you can change while it
runs; measure its timing and message size; then compute, with NAVERA's own spherical code, how wrong
the flat-Earth conversion becomes with distance ([analysis.py](file:./analysis.py),
[report.md](file:./report.md)).
**Time:** about 2 h 30. You need two terminals (**＋ new** in the Terminal tab); `Ctrl+C` stops a node.

## Step 1 — Read and run the starter

Read `fake_gps.py` from top to bottom: settings, four plain functions, the `FakeGps` class, `main()`.
Then run it:

```bash
python3 fake_gps.py
```

It logs `fake GPS on /fake_gps/fix at 2.0 Hz from (35.8277, 10.6388)` and then nothing. In
**Terminal 2**:

```bash
ros2 node list
```

The node `/fake_gps` exists, but it publishes nothing: no publisher and no timer yet. Stop it
(`Ctrl+C` in Terminal 1).

## Step 2 — The plain functions (TODO 1 to 4)

These four functions contain no ROS: you can test each one directly. The command imports your file
without starting the node (`main()` only runs when the file is the main program).

> [!TASK]
> **TODO 1** — `velocity_ne(speed_mps, heading_deg)` returns `(v_north, v_east)`.
> **TODO 2** — `offset_to_latlon(lat0, lon0, north_m, east_m)` returns `(lat, lon)` with the
> equirectangular formulas of the course.

```bash
python3 -c "from fake_gps import *; print(velocity_ne(10, 0), velocity_ne(10, 90), velocity_ne(5, 30))"
```

Expected: about `(10.0, 0.0)`, `(0.0, 10.0)` (a tiny `6e-16` instead of 0 is normal rounding) and
`(4.33, 2.5)`.

```bash
python3 -c "from fake_gps import *; print(offset_to_latlon(35.8277, 10.6388, 111195, 0)); print(offset_to_latlon(35.8277, 10.6388, 0, 90155))"
```

Expected: about `(36.8277, 10.6388)` — one degree north — and `(35.8277, 11.6388)`: in Sousse one
degree of longitude is only 90 155 m (cos 35.8277° = 0.8108).

> [!TASK]
> **TODO 3** — `make_covariance(sigma_h_m, sigma_v_m)` returns the 9 **floats** of the ENU,
> row-major covariance. **TODO 4** — `make_fix(...)` fills a complete `NavSatFix`.

```bash
python3 -c "from fake_gps import *; print(make_covariance(3.0, 6.0))"
```

```bash
python3 -c "from fake_gps import *; from builtin_interfaces.msg import Time; print(make_fix(35.8277, 10.6388, 40.0, 3.0, Time()))"
```

(`Time()` is an empty stamp, good enough to print.) Find `status=…status=0, service=1`, your
latitude and longitude, and the covariance `[9.0, 0.0, … 36.0]`. If you see the long
`AssertionError … each value of type 'float'`, you put an `int` in a float field — read the course's
warning box.

## Step 3 — Parameters, publisher, timer (TODO 5 and 6)

> [!TASK]
> **TODO 5** — declare the 6 parameters of `DEFAULTS` and read `rate_hz`, `start_lat`, `start_lon`
> from them. **TODO 6** — create `self.pub` and the timer.

Run the node:

```bash
python3 fake_gps.py
```

Every 5 seconds it logs `fix 11: lat … lon …` — always the same position for now, because the motion
is TODO 7. In Terminal 2, list its parameters:

```bash
ros2 param list /fake_gps
```

If it says `Node not found`, wait two seconds and run it again: a new node needs a moment to be
discovered (discovery, lesson 9, section 3). Besides your six parameters you see `use_sim_time`: every
node has it (course, section 2). Stop the node.

## Step 4 — Make it move (TODO 7)

> [!TASK]
> **TODO 7** — in `on_timer`, compute `dt` from the clock, read `speed_mps` and `heading_deg` at
> every tick, and integrate `north_m` and `east_m` with `velocity_ne()`.

Start it again in Terminal 1:

```bash
python3 fake_gps.py
```

In Terminal 2, print only the latitude, as it changes (`Ctrl+C` to stop):

```bash
ros2 topic echo /fake_gps/fix --field latitude
```

(If it prints `Could not determine the type for the passed topic`, the tool has not discovered your
node yet: wait two seconds and run it again — lesson 09, section 3.) At 5 m/s on heading 30°, the vehicle moves 5 × cos 30° × 0.5 = 2.17 m north per message, so the
latitude grows by about 0.0000195° each time. Now drive it from the terminal — turn due east:

```bash
ros2 param set /fake_gps heading_deg 90.0
```

```bash
ros2 topic echo /fake_gps/fix --field latitude
```

The latitude stops changing: you drive along the parallel. Try a faster speed — and fall into the type
trap on purpose:

```bash
ros2 param set /fake_gps speed_mps 20
```

The answer is `Setting parameter failed: Wrong parameter type, expected 'Type.DOUBLE' got
'Type.INTEGER'`. Now the right way:

```bash
ros2 param set /fake_gps speed_mps 20.0
```

Keep the node running for the next step, but put the defaults back first:

```bash
ros2 param set /fake_gps speed_mps 5.0
```

```bash
ros2 param set /fake_gps heading_deg 30.0
```

## Step 5 — Look at the messages

Still in Terminal 2:

```bash
ros2 topic info -v /fake_gps/fix
```

Your publisher: RELIABLE, VOLATILE — the default profile of the `10` you passed. One full message:

```bash
ros2 topic echo --once /fake_gps/fix
```

Check every field against the course's table: the stamp (seconds since 1970), `status: 0`,
`service: 1`, latitude, longitude, altitude 40.0, the covariance and its type 2.

## Step 6 — Measure timing and size

Measure the rate. Wait for at least 5 `average rate:` blocks, then `Ctrl+C`:

```bash
ros2 topic hz /fake_gps/fix
```

Note the last `average rate`, `min`, `max` and `std dev` (in seconds). Then the bandwidth (a few
lines, then `Ctrl+C`):

```bash
ros2 topic bw /fake_gps/fix
```

`Message size mean` is the serialised size of one `NavSatFix`. You should read about **128 B**, more
than the 96 B of its 12 float64 (latitude, longitude, altitude and the 9 covariance values). The
other bytes are the rest of the message: the time stamp of the header (8 B), the `frame_id` string
`"gps"` (4 B for its length + 4 B for the text and its end byte), `status` (4 B), `covariance_type`
(1 B), a 4 B header that DDS puts in front of every message, and a few **padding** bytes (empty bytes
that keep every float64 at an address that is a multiple of 8). That makes 125 B; the tool reports
the size rounded up to 128 B. Stop the node in Terminal 1.

> [!TASK]
> Copy the five numbers into `MEASURED` at the top of `analysis.py`.

## Step 7 — How flat is the Earth? (TODO 8 and 9)

`analysis.py` imports NAVERA's spherical `dead_reckon` and `haversine_m` from **your NAVERA copy**
([geo.py](file:navera/navera_common/navera_common/geo.py)) — read `dead_reckon` first: it computes
the end point of a great circle from a start, a heading, a speed and a duration.

> [!TASK]
> **TODO 8** — `flat_error_m(distance_m, heading_deg)`: distance between your flat-Earth end point
> and NAVERA's great-circle end point. **TODO 9** — `predicted_due_east_m(distance_m, lat_deg)`:
> the course's formula d² tan φ / (2R).

```bash
python3 analysis.py
```

It prints a table for 1, 10 and 100 km, and writes `results.json`. Check yourself: for 10 km due
east, your error and the formula must agree to about 0.01 m (the course computed 5.7 m). If the
"heading 30" and "due east" columns are identical, look at how you computed the offset.

## Step 8 — Write the analysis

Fill the two sections of [report.md](file:./report.md) (at least 40 words each): **Timing** (your
measurements and why the node integrates with the measured dt) and **Flat Earth** (your three
errors for heading 30°, the d² growth, the formula, and the largest distance you would accept for a
bench test, with a reason).

Press **✔ Check my work**. The checker runs your node twice (defaults, then with parameters on the
command line), changes `heading_deg` while it runs, and recomputes your analysis. About a minute.

> [!WARNING]
> If the checker says "only 0 messages arrived", run `python3 fake_gps.py` yourself and read the
> terminal: an error inside `on_timer` appears only when the timer fires, as a Python traceback.

## Going further (optional)

- **A square route.** Write a small script that calls `ros2 param set /fake_gps heading_deg …` every
  60 s to drive a 300 m square around the Grand Mosque (use `subprocess` and `time.sleep`). Where does
  the vehicle end, and why not exactly at the start? (Hint: the timer and the 60 s are not
  synchronised.)
- **A tunnel.** Add a parameter `outage` (bool, default `False`): while it is true, publish
  `STATUS_NO_FIX` with NaN latitude and longitude and covariance type UNKNOWN. In lesson 11 you will see
  what NAVERA does with it.
- **Spherical motion.** Replace the flat integration by NAVERA's `dead_reckon` applied at each tick
  from the last position. Measure the difference with your flat version after 100 km — and explain
  why repeated small great-circle steps are not one big great circle when the heading is kept
  constant (rhumb line).

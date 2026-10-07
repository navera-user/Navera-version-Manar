# Lab 16 — Reading an IMU

**Goal:** turn quaternions into angles a human understands, check your answers against NAVERA's own
code, find true north with the World Magnetic Model, and watch a gyroscope drift.
**Time:** about 1 hour.

The IMU of the NAVERA box (a BNO085) is not connected at the moment, so you will work with a
**recorded log**: 5 minutes of a drone flight, 50 samples per second, exactly the numbers
`imu_node` would publish. The log is **simulated**: that is a good thing here, because we also know
the **true** heading at every instant and can measure each method's error.

## Step 1 — Look at the log

```bash
head -3 /data/academy/16-imu/imu_log.csv
```

You see a header and two samples. The columns are:

| Column | Meaning |
|---|---|
| `t_s` | time in seconds |
| `qx, qy, qz, qw` | the fused attitude quaternion given by the chip (magnetic north) |
| `gx, gy, gz` | the gyroscope: rotation speed around the body x, y, z axes, in **rad/s** |
| `true_heading_deg` | the truth (only a simulation can give it!) |

```bash
wc -l /data/academy/16-imu/imu_log.csv
```

15 002 lines: one header + 15 001 samples = 300 s × 50 per second + 1.

> [!QUESTION]
> Look at the first sample: x ≈ 0, y ≈ 0, z ≈ 0.4994, w ≈ 0.8664. It is a rotation around z only
> (the vertical). w = cos(θ/2) = 0.866 means θ/2 = 30°, so θ = 60°: the yaw is 60°. What is the heading?
> (Answer: 90 − 60 = 30°, and the last column says 30.000. ✔)

## Step 2 — From a quaternion to roll, pitch and yaw

Open [attitude.py](file:./attitude.py). Run it first, as it is:

```bash
python3 attitude.py
```

It says `TODO 1: quat_to_euler() returns None` for each sample. Your job is to fill the TODOs.

> [!TASK]
> **TODO 1** — write `quat_to_euler(q)`. It receives a tuple `(x, y, z, w)` and returns a tuple
> `(roll, pitch, yaw)` **in degrees**, with the three formulas of the course:
>
> ```
> roll  = atan2(2(w·x + y·z), 1 − 2(x² + y²))
> pitch = asin (2(w·y − z·x))
> yaw   = atan2(2(w·z + x·y), 1 − 2(y² + z²))
> ```
>
> In Python: `math.atan2(a, b)`, `math.asin(s)`, `x * x` for x², and `math.degrees(...)` to convert.

> [!WARNING]
> Rounding errors can make `2(w·y − z·x)` equal to `1.0000000002` when the nose points straight up,
> and `math.asin` then crashes with `ValueError: math domain error`. Protect it:
> `s = max(-1.0, min(1.0, s))` before `math.asin(s)`.

Run it again. The roll, pitch and yaw columns are filled. Check the second row: "nose to the east"
must give yaw 0, and "nose to the north" yaw 90.

## Step 3 — From yaw to compass heading, and NAVERA's opinion

> [!TASK]
> **TODO 2** — write `heading_from_yaw(yaw_deg)`: `(90 − yaw) % 360`. The result must always be
> between 0 and 360.

```bash
python3 attitude.py
```

Now look at the last two columns: **heading** is yours, **NAVERA** is the answer of NAVERA's own
`heading_deg()` from your copy, [imu_pkg/imu_pkg/orientation.py](file:navera/imu_pkg/imu_pkg/orientation.py).
They must be equal on every line. You can also ask NAVERA directly:

```bash
python3 -c "from imu_pkg.orientation import heading_deg; print(heading_deg((0, 0, 0.7071, 0.7071)))"
```

It prints about `0.001`: the nose points north (0.7071 is a rounded √½, hence the tiny 0.001).

> [!NOTE]
> Look at the last sample, "banked, nose up, to the SSW": your pitch is **−5**. In ROS a positive
> pitch is nose **down**, so −5 means nose up 5°. NAVERA's `body_rpy_enu()` in `camera_model.py`
> reports the same attitude as pitch **+5** because it counts "nose up" as positive, like pilots do.
> Same attitude, two conventions: that is why every angle in NAVERA's code has a comment saying how it
> is counted.

## Step 4 — True north

The heading in the log is **magnetic** (the BNO085 uses its magnetometer). NAVERA turns it into a
**true** heading with the declination from the World Magnetic Model.

> [!TASK]
> **TODO 3** — write `true_heading(magnetic_heading_deg, declination_deg)`: add them, and keep the
> result between 0 and 360.
>
> **TODO 4** — write `declination_at(lat, lon, year)` with the pygeomag library, exactly like
> NAVERA's class `Declination`:
>
> ```python
> from pygeomag import GeoMag
> return GeoMag().calculate(glat=lat, glon=lon, alt=0, time=year).d
> ```

```bash
python3 attitude.py
```

You should read a declination of about **+3.33°** in Sousse in October 2026 — the value written in
NAVERA's [imu_params.yaml](file:navera/imu_pkg/imu_pkg/config/imu_params.yaml) — and see that a
compass reading of 358° is in fact a true heading of 1.3°: just east of north, not west of it!

Try other places (any latitude/longitude you like):

```bash
python3 -c "from attitude import declination_at; print(declination_at(64.1, -21.9, 2026.5), declination_at(-33.9, 151.2, 2026.5))"
```

Reykjavik (Iceland) about −11°, Sydney about +13°: much bigger than in Tunisia.

## Step 5 — Why the tilt matters

> [!TASK]
> **TODO 5** — write `ground_offset_m(height_m, tilt_deg)`: the distance between the point under the
> drone and the centre of a photo taken with the camera tilted by `tilt_deg`: `height × tan(tilt)`.
> Careful: `math.tan` wants radians.

```bash
python3 attitude.py
```

At 150 m with 10° of tilt, the photo centre is **26.4 m** away from the drone — the number written in
NAVERA's `camera_model.py`. That is why NAVERA straightens every photo with the attitude before
comparing it with the map.

## Step 6 — Count turns blindfolded: the gyroscope

Open [gyro_drift.py](file:./gyro_drift.py). It reads the log and compares three headings: the truth,
the one from the fused quaternion (your functions from steps 2 and 3), and one computed **only from
the gyroscope**.

> [!TASK]
> **TODO 6** — write `integrate_gyro(times, rates)`. Start a list with `0.0`; for each next sample,
> add `rates[i] × (times[i] − times[i-1])` to the previous angle, converted to degrees. Return the list
> (one angle per sample).

```bash
python3 gyro_drift.py
```

You should see something like:

```
15001 samples, 300 s at 50 Hz
total turn measured by the gyroscope: -350.3 deg (counter-clockwise +)
after    60 s  gyroscope heading error   -2.1 deg   fused quaternion error  +0.1 deg
after   120 s  gyroscope heading error   -4.1 deg   fused quaternion error  -0.1 deg
after   300 s  gyroscope heading error   -9.7 deg   fused quaternion error  -0.0 deg
```

The drone made a full turn to the right (30° → 120° → 300° → 210° → 30°), so the true total is
−360°. The gyroscope says −350.3°: almost **10°** lost in 5 minutes. Click **drift.png** in the file list
to open the plot: the red error line keeps walking down, while the fused quaternion stays around 0.

> [!QUESTION]
> The gyroscope of this simulated log has a bias of 0.03 °/s on z. How much drift do you expect after
> 300 s? (0.03 × 300 = 9°. The extra 0.7° comes from the noise and from the small roll and pitch
> wobbles of the drone.)

## Step 7 — Run NAVERA's own tests

NAVERA has automatic tests for these conversions (lesson 14). Run them on your copy:

```bash
python3 -m pytest -q -p no:cacheprovider ~/navera/imu_pkg/test/test_orientation.py
```

All pass (`11 passed`). Open [test_orientation.py](file:navera/imu_pkg/test/test_orientation.py) and
find the test that checks `true heading = magnetic heading + declination`: it is the same rule as your
TODO 3.

## Step 8 — Quiz and check

> [!TASK]
> Answer the three questions in [answers.py](file:./answers.py).

Press **✔ Check my work**. The checker compares your functions with NAVERA's on many random
attitudes, with the World Magnetic Model at three places, and runs `gyro_drift.py`.

## Going further (optional)

- **A simple fusion.** In `gyro_drift.py`, make a third heading: at each step, take the gyroscope
  heading, then pull it 1 % of the way towards the heading from the quaternion
  (`h = h + 0.01 * wrap180(h_quat - h)`). This is a **complementary filter**, the simplest sensor fusion.
  Plot it: is it smooth *and* drift-free?
- **Declination over time.** Print the declination in Sousse for 2025, 2026 … 2029. How fast does the
  magnetic north move here?
- **The ROS message.** Run `ros2 interface show sensor_msgs/msg/Imu` and find the orientation, the
  angular velocity and their covariances — what `imu_node` fills with the `*_stddev` parameters.

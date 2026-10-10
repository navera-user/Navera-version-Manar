# Lab 16 — From raw IMU samples to an attitude

**Goal:** implement the rotation toolbox of the course (Euler angles, quaternions, SLERP), then
estimate the attitude of a drone from raw gyroscope, accelerometer and magnetometer samples:
integrate the gyroscope, compute the tilt from gravity, fuse both with a complementary filter, read
a tilt-compensated compass and correct it to true north with the World Magnetic Model. You compare
your code with NAVERA's and write a short report.
**Time:** about 3 hours for this lab (about 4 h for the whole mission with the lesson).

**Files:** [quaternions.py](file:./quaternions.py) (TODOs 1–7),
[imu_filters.py](file:./imu_filters.py) (TODOs 8–12), [report.md](file:./report.md).

> [!NOTE]
> The BNO085 of the NAVERA box is **not connected**, so you work on a **simulated** 5-minute log of a
> flight near Monastir, in NAVERA's test area in Tunisia (50 Hz). Simulated data has one big advantage: it contains the **true** attitude,
> so every method can be measured. The numbers of the sensor model (bias, noise) are chosen for
> teaching; they are not measurements of NAVERA hardware.

## Step 1 — Look at the data

```bash
head -3 /data/academy/16-rotations/imu_log.csv
```

| Columns | Meaning |
|---|---|
| `t_s` | time (s) |
| `qx, qy, qz, qw` | the BNO085's fused orientation, **ROS order (x, y, z, w)**, referenced to **magnetic** north |
| `gx, gy, gz` | gyroscope, body frame (x forward, y left, z up), **rad/s** |
| `ax, ay, az` | accelerometer (specific force), body frame, **m/s²** — about +9.81 on z when level |
| `mx, my, mz` | magnetometer, body frame, **µT** |
| `true_roll_deg, true_pitch_deg, true_heading_deg` | the truth (ROS signs; heading from **true** north) |

```bash
cat /data/academy/16-rotations/imu_log_meta.json
```

The place (lat 35.76, lon 10.75), the date (decimal year 2026.79) and the sensor model.

> [!QUESTION]
> In the first row, `az` ≈ 9.81 and `ax`, `ay` ≈ 0. What does this say about the attitude? And
> `qz` ≈ 0.525, `qw` ≈ 0.851: what is the yaw? (2·acos(0.851) ≈ 63.4°, so the **magnetic** heading
> is 90 − 63.4 = 26.6°. The true heading column says 30.0°. The difference, 3.4°, is the declination
> near Monastir — you will compute it in Step 7.)

## Step 2 — Euler angles and rotation matrices

Open [quaternions.py](file:./quaternions.py). Read the conventions at the top: angles in
**radians**, quaternions as numpy arrays **(w, x, y, z)**. `rot_x`, `rot_y`, `rot_z` are given.

> [!TASK]
> **TODO 1** — `euler_to_matrix(roll, pitch, yaw)` returns `Rz(yaw) @ Ry(pitch) @ Rx(roll)` (3×3).
>
> **TODO 2** — `matrix_to_euler(R)` returns `(roll, pitch, yaw)` in radians with the formulas of
> section 4 of the course. Clamp `R[2,0]` into [−1, 1] before `asin`. At gimbal lock
> (|R[2,0]| > 1 − 1e−9) return roll = 0 and yaw = atan2(−R[0,1], R[1,1]).

```bash
python3 quaternions.py
```

Part 1 of the output must show the matrix of the worked example of the course, `R^T R = I ? True`,
`det(R) = 1.000000`, and the angles (10, 5, 60) back. Part 2 shows gimbal lock: two different
(roll, yaw) pairs give the same matrix, and your function returns (0, 90, 20).

> [!WARNING]
> `ValueError: math domain error` means `asin` received 1.0000000002: you forgot the clamp.
> Getting 572.96 instead of 10? You converted to degrees twice (or not at all).

## Step 3 — Quaternion algebra

> [!TASK]
> **TODO 3** — `quat_mul(p, q)`: the Hamilton product (scalar first). `np.dot` and `np.cross` help.
>
> **TODO 4** — `quat_from_axis_angle(axis, angle)`: the unit quaternion of section 5. The axis
> may have any length.
>
> **TODO 5** — `quat_rotate(q, v)`: q ⊗ (0, v) ⊗ q*, return the 3 last numbers.
>
> **TODO 6** — `quat_to_matrix(q)`: the matrix of section 5 (normalise q first).

```bash
python3 quaternions.py
```

Part 3 must print `i*j = [0. 0. 0. 1.]` and `j*i = [ 0. 0. 0. -1.]`, rotate (1, 0, 0) into
(0, 1, 0), and answer `True` twice: your `quat_to_matrix(quat_from_euler(...))` equals your
`euler_to_matrix(...)`, and NAVERA's own `quat_to_matrix` (from
[camera_model.py](file:navera/navera_common/navera_common/camera_model.py)) agrees once the order is
converted with `wxyz_to_xyzw`. Look at `quat_from_euler` below the line: it builds q_z ⊗ q_y ⊗ q_x
from **your** functions, the same composition as Rz Ry Rx.

Check the order trap yourself. NAVERA's `heading_deg` takes **(x, y, z, w)**:

```bash
python3 -c "from imu_pkg.orientation import heading_deg; print(heading_deg((0.0, 0.0, 0.3827, 0.9239)), heading_deg((0.9239, 0.0, 0.0, 0.3827)))"
```

It prints about `45.0` and `90.0`. The first call is yaw 45° → heading 45°. The second puts w in
the first slot by mistake: NAVERA reads it as a 135° roll about the nose, an attitude that has nothing
to do with the first — and there is no error message.

## Step 4 — SLERP

> [!TASK]
> **TODO 7** — `slerp(q0, q1, t)` from section 6 of the course. Before you code, answer the three
> questions above TODO 7 in the file (the angle θ, the shortest path, the case θ ≈ 0). Return a
> unit quaternion. **Lesson 20 uses this function** to get the attitude at the exposure instant.

```bash
python3 quaternions.py
```

Part 4 interpolates from heading 0° to heading 90°: at t = 0.25, 0.5, 0.75 you must read 22.50,
45.00, 67.50 — equal angles for equal steps. Try what linear interpolation would give:

```bash
python3 -c "import numpy as np, quaternions as Q; q0=Q.quat_from_euler(0,0,np.radians(90)); q1=Q.quat_from_euler(0,0,0); l=q0+0.25*(q1-q0); print(np.linalg.norm(l), Q.heading_deg(l/np.linalg.norm(l)), Q.heading_deg(Q.slerp(q0,q1,0.25)))"
```

The raw average has a norm of 0.943 (not a rotation), and once normalised it gives a heading of 21.6° at t = 0.25 instead of 22.5°: the interpolated attitude does not turn at a constant rate. The error grows with the angle between q0 and q1.

## Step 5 — Integrate the gyroscope

Open [imu_filters.py](file:./imu_filters.py). It imports your functions from `quaternions.py`.

> [!TASK]
> **TODO 8** — `integrate_gyro(t, gyro, q0)` returns an (N, 4) array of quaternions, starting with
> q0. Section 7 of the course gives the update of one step. Use the rate of sample k−1 for the step
> from k−1 to k, and re-normalise at each step.

```bash
python3 imu_filters.py
```

You see the first line, `gyro only: heading error … after 60 s, … after 300 s`, then the program
stops at TODO 9. Before you continue: the z bias is 0.03 °/s. Which error do you predict after
300 s? Compare.

> [!NOTE]
> **Why is the error negative?** A positive z bias makes the gyro report a turn to the **left**
> (counter-clockwise seen from above), so the integrated **yaw** grows too fast. The compass heading
> is `90° − yaw` (yaw from east, counter-clockwise; heading from north, clockwise). So the heading
> becomes too **small**, and the error (gyro − truth) is negative: about −9°. The size is not exactly
> 9.0°: the noise and the small x and y biases add a little during the turns.

## Step 6 — Tilt: accelerometer and complementary filter

> [!TASK]
> **TODO 9** — `accel_roll_pitch(acc)` returns `(roll, pitch)` arrays (radians), with the tilt
> formulas of section 8. Use numpy on whole columns.
>
> **TODO 10** — `complementary_tilt(t, gyro, acc, tau)`: start from the accelerometer angles of
> sample 0; at each step predict with the Euler-angle kinematics (gyro of sample k−1), then blend
> with α = τ/(τ + dt). Return `(roll, pitch)` arrays.

```bash
python3 imu_filters.py
```

The program prints the accelerometer-only errors and a **sweep** of τ from 0.1 s to 30 s. Open
**attitude.png** after Step 7 (top panel): during the four turns the drone banks to about ±14°,
while the accelerometer alone stays near 0°. Why? (Section 8 of the course.) The four turns are
centred near **t = 35, 100, 165 and 240 s** (each lasts about 10–15 s). You need these times for
section 2 of the report.

> [!NOTE]
> **The best τ is 30 s, the last value of the sweep.** When the best value is at the **edge** of a
> sweep, you do not know yet if a larger value is even better. The rule: extend the sweep until the
> error grows again. Try τ = 100 s and 300 s (this takes a few seconds):
>
> ```bash
> python3 -c "import numpy as np, imu_filters as F; L = F.load_log(); t = L['t_s']; g = np.stack([L['gx'], L['gy'], L['gz']], 1); a = np.stack([L['ax'], L['ay'], L['az']], 1); [print(tau, [round(F.rms(np.degrees(x) - L[k]), 2) for x, k in zip(F.complementary_tilt(t, g, a, tau), ('true_roll_deg', 'true_pitch_deg'))]) for tau in (30.0, 100.0, 300.0)]"
> ```
>
> Where is the minimum now? Why does a very large τ fail in the end (think of the gyro bias)?
> Keep `TAUS` unchanged in the file: the check expects the original sweep. Write your answer in
> section 2 of the report.

> [!QUESTION]
> The roll error falls steadily as τ grows, but the pitch error does not: it gets worse from
> τ = 0.3 s to τ = 3 s, then better again. The accelerometer pitch is wrong while the drone speeds up
> (t = 10–20 s) and slows down (t = 280–290 s): a forward acceleration of 1 m/s² looks like a tilt
> of atan(1/9.81) ≈ 6°. How long does each τ "remember" such an error, compared with the 10 s it
> lasts?

## Step 7 — Compass and true north

> [!TASK]
> **TODO 11** — `mag_heading(mag, roll, pitch)`: the tilt-compensated heading of section 10, for
> each sample, in degrees in [0, 360). Return an array.
>
> **TODO 12** — `declination_at(lat, lon, year)`: the World Magnetic Model through pygeomag,
> exactly like NAVERA's class `Declination` in
> [orientation.py](file:navera/imu_pkg/imu_pkg/orientation.py). Read how NAVERA calls it, and use
> altitude 0.

```bash
python3 imu_filters.py
```

The program now runs to the end. It prints the declination at the place of the log (≈ +3.35°),
the mean error of the magnetic heading (≈ −D: the compass is "wrong" by exactly the declination),
the RMS error of your true heading with and without tilt compensation, the error of the BNO085's own
fused quaternion, and the declination of five places around the world (London, Reykjavik, Cape Town, Sydney,
Singapore). It saves **results.json** and
**attitude.png** — click them in the file list.

```bash
cat results.json
```

Try a place of your choice (lat, lon, decimal year), e.g. New York and Quito (on the equator):

```bash
python3 -c "from imu_filters import declination_at; print(declination_at(40.71, -74.01, 2026.79), declination_at(-0.18, -78.47, 2026.79))"
```

## Step 8 — NAVERA's tests

NAVERA's orientation code has unit tests (lesson 14). Run them on your copy:

```bash
python3 -m pytest -q -p no:cacheprovider ~/navera/imu_pkg/test/test_orientation.py
```

All must pass. Open [test_orientation.py](file:navera/imu_pkg/test/test_orientation.py) and find the
test that checks *true heading = magnetic heading + declination*, and the one for the mounting
rotation. Then read `OrientationCorrector.apply()`: the declination multiplies on the **left**, your
gyro step on the **right**. Make sure you can explain why.

## Step 9 — Report

> [!TASK]
> Fill [report.md](file:./report.md): five sections, at least 30 words each, no `TODO` left, with
> these numbers (from your output / results.json):
> 1. the gyro heading error after 300 s and your bias × time prediction (9.0°), and why the sign
>    is negative;
> 2. the largest accelerometer roll error and when it happens, the best τ of the sweep (30 s), the
>    τ trade-off, and what you found when you extended the sweep;
> 3. the declination at the log's place, the true-heading RMS with and without tilt compensation;
> 4. a table of the declination in London, Reykjavik, Cape Town, Sydney and Singapore (2 decimals),
>    and the side error after 10 km from London if D is ignored (in metres);
> 5. the NAVERA functions equivalent to your `quat_to_matrix` and `slerp` (file names), and the
>    quaternion order difference.

Press **✔ Check my work**. The checker tests every function against NAVERA's own code and against
known cases (random rotations, gimbal lock, body-frame integration, static tilts, a tilted compass),
re-runs `imu_filters.py`, and reads your report.

## Going further (optional)

- **Heading filter.** Fuse the gyro yaw rate ψ̇ = (q sin φ + r cos φ)/cos θ with your compass heading
  in a second complementary filter. Careful with the wrap-around: blend with
  `h + (1 − α)·wrap180(h_mag − h)`. What τ gives the lowest heading RMS?
- **Hard-iron calibration.** A magnetised part on the drone adds a constant offset to the
  magnetometer. Add (5, −3, 2) µT to the log's `mx, my, mz`, see the heading error, then estimate the
  offset back by fitting a sphere to the samples (least squares: |m − c|² = r²).
- **Allan-style test.** Integrate only the gyro noise part (subtract the true rate; the log
  gives it indirectly through the truth columns) for many 30 s windows and check that the spread
  grows like √t.
- **The ROS message.** `ros2 interface show sensor_msgs/msg/Imu`: find where `imu_node` puts the
  quaternion, the rates and the covariances built from the `*_stddev` parameters.

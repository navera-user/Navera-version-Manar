# Lab 16 — Build the rotation toolbox, then find the bug that gives no error

**Goal:** write NAVERA Lite's rotation part (`navera_lite/rotations.py`), watch gimbal lock happen in your
own code, check your functions against an independent library, and solve a real-looking convention bug in
a colleague's attitude table.
**Time:** 3 to 5 h (a strong programmer: about 2 h 30; 5 h if matrices or numpy are rusty).
**Fast track:** if you know numpy, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further" at the end.

Your files (📝 Code tab): [navera_lite/rotations.py](file:./navera_lite/rotations.py) (**your code**: eleven
functions, `TODO 1–11`), [detective.py](file:./detective.py) (**your code**: `TODO A`, `TODO B`),
[answers.py](file:./answers.py), [report.md](file:./report.md), and two tools you only run:
[run_rotations.py](file:./run_rotations.py) (runs your functions on the lab's situations and draws them) and
[compare_oracle.py](file:./compare_oracle.py) (compares them with SciPy).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1–§2 frames, matrices | Steps 1–2 | `rot_y`, `rot_z`, `euler_zyx_to_matrix` |
| §3 Euler angles, gimbal lock | Step 3 | `matrix_to_euler_zyx` |
| §4 quaternions | Steps 4–5 | `q_mul`, `q_conj`, `q_from_axis_angle`, `q_rotate`, `q_to_matrix` |
| §5 slerp | Step 6 | `slerp`, `q_angle_deg` |
| all | Steps 7–9 | the oracle; `misread`, `tilt_deg` (TODO A, B); the bug memo |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is
> never marked right or wrong. Each function's docstring says its goal, its units and gives one example with
> its result; `python3 run_rotations.py test` tries every example. The lesson shows how; the code is yours.
> All the matrix and quaternion functions take **radians**; write `math.radians(30)` in your own tests.

## Session 1 — Attitude reader (about 1 h 30; 2 h if numpy is new to you)

## Step 0 — Which way is "positive pitch"?

No code, no lesson yet. A ROS message from a drone's IMU says roll 0, **pitch +10°**, yaw 0.

> [!TASK]
> **Predict** (`PREDICT_PITCH` in `answers.py`): is the nose above or below the horizon? Write one reason.
> Save the file (`Ctrl+S`). Then read lesson §1–§3 (§3 is for Step 3).

## Step 1 — The elementary rotations (TODO 1, TODO 2)

Open the 📝 Code tab, then `navera_lite/rotations.py`. Read the conventions at the top of the file, then the
given `rot_x`: it is the pattern for your two functions. Each `TODO` function keeps its docstring and ends
with `return None   # TODO…`: replace that line with your code.

<details><summary>🧰 numpy: build a matrix, multiply, check it</summary>

```python
import math
import numpy as np
c, s = math.cos(math.radians(90)), math.sin(math.radians(90))
M = np.array([[c, -s], [s, c]])          # a 2 × 2 matrix, row by row
M @ np.array([2.0, 1.0])                 # array([-1.,  2.]) — matrix × vector (up to rounding: 1e-16 ≈ 0)
M @ M.T                                  # the identity: M is a rotation
round(float(np.linalg.det(M)), 6)        # 1.0 (−1.0 would be a mirror)
M[:, 0]                                  # the first COLUMN
```
</details>

**TODO 1** `rot_y(angle_rad)` and **TODO 2** `rot_z(angle_rad)`: lesson §2. Watch where the minus sign goes
in `rot_y`.

```bash
python3 run_rotations.py test
```

The two lines of TODO 1 and 2 must be ✔ (the other TODOs show "not written yet").

```bash
python3 run_rotations.py pitch
```

> [!TASK]
> `PITCH_UP_DEG`: the ROS message says pitch = +0.12 rad. What pitch does a pilot read (positive nose up),
> in degrees? `EXPLAIN_PITCH`: why does a positive ROS pitch move the nose that way? Compare with your
> `PREDICT_PITCH`.

<details><summary>Stuck? Hints, one at a time</summary>

1. Copy the shape of `rot_x`: `c, s = math.cos(angle_rad), math.sin(angle_rad)`, then `np.array([[…], […], […]])`.
   The axis of the rotation keeps its 1 on the diagonal (row 1, column 1 for y; row 2, column 2 for z).
2. `rot_y`: ✘ "the nose went UP" means the minus sign is in the top-right corner (as in `rot_x`). For y
   it sits in row 2, column 0: the third row is `[-s, 0.0, c]`.
3. `rot_z`: ✘ "east was carried towards SOUTH" means you wrote the transpose: the first row is `[c, -s, 0.0]`.
4. `pitch` prints the nose (east, north, up). Its up component is −sin(0.12): a pilot's pitch is
   `math.degrees(asin(up))`, and its sign says above or below.
</details>

## Step 2 — Euler angles, and the order of rotations (TODO 3)

**TODO 3** `euler_zyx_to_matrix(roll_rad, pitch_rad, yaw_rad)`: lesson §3, one line with your three
functions and `@`.

```bash
python3 run_rotations.py test
```

> [!TASK]
> **Predict** (`PREDICT_ORDER`) on paper, before running: with A = rot_z(90°) @ rot_x(90°) and
> B = rot_x(90°) @ rot_z(90°), where does the drone's **left wing** (0, 1, 0) point in A, and in B? Work from
> the right, as in the lesson's ✏️ check of §2.

```bash
python3 run_rotations.py order
```

Open `out/order.png`: two drones, three views each.

> [!TASK]
> `EXPLAIN_ORDER`: are A and B the same attitude? Which of them is "yaw 90° first, then roll 90° about the
> drone's **new** nose"? Say why, with the two ways of reading a product of lesson §2. Start with "A is …" or
> "B is …".

<details><summary>Stuck? Hints</summary>

1. `return rot_z(yaw_rad) @ rot_y(pitch_rad) @ rot_x(roll_rad)`-shaped: the yaw matrix on the **left**.
2. ✘ "wrong ORDER": you wrote `rot_x(…) @ rot_y(…) @ rot_z(…)`. ✘ "`*` multiplies element by element": use `@`.
3. ✘ "the nose points DOWN for a negative ROS pitch": go back to TODO 1, your `rot_y` sign.
4. For A: rot_x(90°) first sends (0, 1, 0) to (0, 0, 1); then rot_z(90°) leaves (0, 0, 1) where it is.
</details>

## Step 3 — Back to angles, and gimbal lock (TODO 4)

**TODO 4** `matrix_to_euler_zyx(R)`: lesson §3. Return **four** values: `(roll, pitch, yaw, locked)`.
Clamp before `asin`. Test for the lock with |cos(pitch)| < 1e-6, which you can compute without dividing:
cos θ = √(R[0][0]² + R[1][0]²) (`math.hypot`).

<details><summary>🧰 Python: returning several values, and a guard first</summary>

```python
def sign_and_size(x):
    if abs(x) < 1e-9:                    # the special case first, and leave at once
        return 0, 0.0, True
    return (1 if x > 0 else -1), abs(x), False

s, size, tiny = sign_and_size(-2.5)      # (-1, 2.5, False)
R = np.eye(3); R[2, 0], R[2][0]          # both index row 2, column 0 of a numpy array
max(-1.0, min(1.0, 1.0000000002))        # 1.0 — a clamp
```
</details>

```bash
python3 run_rotations.py test
```

> [!TASK]
> **Predict** (`PREDICT_LOCK`): `gimbal` feeds four (roll, yaw) pairs at ROS pitch +90° to your
> `euler_zyx_to_matrix`, then to your `matrix_to_euler_zyx`. What will come back? Then run:

```bash
python3 run_rotations.py gimbal
```

> [!TASK]
> 1. `LOCK_UP_YAW_DEG`: with your own functions (a `python3 -c "…"` line), the yaw that
>    `matrix_to_euler_zyx` returns for roll 30°, ROS pitch **−90°** (nose straight up), yaw 50°, in degrees.
> 2. `NEAR_LOCK_YAW_JUMP_DEG`: from the second part of `gimbal`, how much the yaw changed (degrees).
> 3. `EXPLAIN_LOCK`: why do roll and yaw become one angle at ±90°, and what did Apollo's crews and engineers do
>    about it (mission brief)?

<details><summary>Stuck? Hints</summary>

1. Three lines for the usual case: `pitch = math.asin(clamped)`, `roll = math.atan2(R[2][1], R[2][2])`,
   `yaw = math.atan2(R[1][0], R[0][0])`; return them with `False`.
2. ✘ "the pitch sign is wrong": pitch = asin(**−**R[2][0]). ✘ "DEGREES": the function returns radians.
3. ✘ at the lock, the idea: there cos θ = 0, so roll and yaw cannot both be found, and the convention fixes
   roll = 0. Which entries of R still contain the surviving angle? (Lesson §3, "See it in the matrix".)
4. ✘ at the lock, the code: the guard comes **first**: `if math.hypot(R[0][0], R[1][0]) < 1e-6: return 0.0, pitch, math.atan2(-R[0][1], R[1][1]), True`.
5. `ValueError: math domain error` in `asin`: you forgot the clamp.
6. `LOCK_UP_YAW_DEG`:
   `python3 -c "import math; from navera_lite.rotations import *; print([math.degrees(v) for v in matrix_to_euler_zyx(euler_zyx_to_matrix(math.radians(30), -math.pi/2, math.radians(50)))[:3]])"`.
   About 50 with roll about 30 and `locked` False? Your guard is missing: the numbers are rounding noise.
</details>

> [!TIP] 🏅 End of session 1 — Attitude reader
> Press **✔ Check my work**. When the checks of TODO 1–4 and Steps 1–3 pass (checks 1–7; the others are
> session 2), you earn the **Attitude reader** badge. If the class session ends here, stop here.

## Session 2 — Quaternion detective (about 2 h; 2 h 30 if numpy is new to you)

Read lesson §4–§5 first.

## Step 4 — The Hamilton product and the conjugate (TODO 5, TODO 6)

<details><summary>🧰 numpy: dot, cross, slicing, joining</summary>

```python
a = np.array([1.0, 2.0, 3.0]); b = np.array([0.0, 1.0, 0.0])
float(a @ b)                              # 2.0 — the dot product
np.cross(a, b)                            # array([-3.,  0.,  1.]) — the cross product (order matters!)
q = np.array([0.1, 0.2, 0.3, 0.9])
q[:3], q[3]                               # array([0.1, 0.2, 0.3]) and 0.9: vector part and w, in ROS order
np.append(np.array([1.0, 2.0, 3.0]), 4.0) # array([1., 2., 3., 4.]) — join a vector and a scalar
x, y, z, w = q                            # unpacking also works
```
</details>

**TODO 5** `q_mul(p, q)`: lesson §4, the vector part and the scalar part, returned in the order (x, y, z, w).
**TODO 6** `q_conj(q)`.

```bash
python3 run_rotations.py test
```

<details><summary>Stuck? Hints</summary>

1. Split each input: `pv, pw = np.asarray(p[:3], dtype=float), float(p[3])`, the same for q.
2. Translate lesson §4 term by term: the vector part is three terms (two scalings and one `np.cross`), the
   scalar part is a product minus a dot product (`@`). Join them with `np.append(vector, scalar)`.
3. ✘ "a cross-product term has the wrong sign": `np.cross(qv, pv)` instead of `np.cross(pv, qv)`.
   ✘ "w is not LAST": you unpacked as `w, x, y, z = p`.
4. `q_conj`: ✘ "you negated w": the conjugate keeps w.
</details>

## Step 5 — Axis-angle, rotating a vector, the matrix (TODO 7–9)

**TODO 7** `q_from_axis_angle(axis, angle_rad)`: normalise the axis, then the half angle (lesson §4); raise
`ValueError` for a zero axis. **TODO 8** `q_rotate(q, v)`: q ⊗ (v, 0) ⊗ q* with your `q_mul` and `q_conj`.
**TODO 9** `q_to_matrix(q)`: normalise first (`q_normalize` is given), then the matrix of lesson §4.

```bash
python3 run_rotations.py test
```

A drone sends this `sensor_msgs/Imu` orientation (ROS order x, y, z, w): **(−0.1245, 0.0134, −0.8834, 0.4516)**.

```bash
python3 run_rotations.py pose -0.1245 0.0134 -0.8834 0.4516
```

It prints the drone's axes, then `rpy_human`, the given function that uses your `q_to_matrix` and
`matrix_to_euler_zyx`. Open `out/pose.png`.

> [!TASK]
> Write `POSE_PITCH_UP_DEG` and `POSE_HEADING_DEG` (one decimal). Then `Q360_W`: the w of your
> `q_from_axis_angle((0, 0, 1), 2 * math.pi)`. Lesson §4 says why it is not +1.

<details><summary>Stuck? Hints</summary>

1. `q_from_axis_angle`: `u = a / np.linalg.norm(a)`; then `np.append(u * math.sin(h), math.cos(h))` with
   `h = angle_rad / 2`.
2. ✘ "the FULL angle was used": h = angle / 2. ✘ "the axis was not normalised". ✘ "w is FIRST".
3. `q_rotate`: `q_mul(q_mul(q, p), q_conj(q))[:3]` with `p = np.append(v, 0.0)`. ✘ "turned the WRONG way":
   you wrote q* ⊗ v ⊗ q.
4. `q_to_matrix`: ✘ "this is the TRANSPOSE": compare the signs of the 2·w·… terms with lesson §4 one by one.
   ✘ "has length 2: normalise q first": `x, y, z, w = q_normalize(q)`.
5. `pose` stops with "rpy_human() … not written yet"? It needs your TODO 4 and TODO 9.
</details>

## Step 6 — Between two attitudes (TODO 10, TODO 11)

**TODO 10** `slerp(q0, q1, t)`: lesson §5, all four lines of the recipe. **TODO 11** `q_angle_deg(q0, q1)`:
the least guided function. Its docstring gives the goal and two examples; the lesson gives the formula.
First check by hand: for q0 = (0, 0, 0, 1) and q1 = (0, 0, −0.2588, −0.9659), what must it return, and
what would `2·acos(q0 · q1)` without the absolute value give?

```bash
python3 run_rotations.py test
```

> [!TASK]
> **Predict** (`PREDICT_LERP`): `slerp` interpolates a level turn from heading 10° to heading 170° two ways.
> The lesson's 20° turn gave a lag of about 0.01° at t = 0.25. For this 160° turn, at t = 0.2, how many
> degrees will the normalised linear interpolation lag behind slerp: about 0.1°, 1°, 5° or 20°? Why? Then:

```bash
python3 run_rotations.py slerp
```

> [!TASK]
> `LERP_ERR_DEG`: at t = 0.2, slerp's heading − the linear heading (degrees, with its sign; open
> `out/slerp.png`). `EXPLAIN_SLERP`: why does linear interpolation not turn at a constant rate?

<details><summary>Stuck? Hints</summary>

1. `a = np.asarray(q0, dtype=float)`, same for b; `d = float(a @ b)`; if `d < 0`: `b, d = -b, -d`.
2. The small-angle case first: `if d > 0.9995: return q_normalize(a + t * (b - a))`.
3. Then `th = math.acos(d)` and the formula; return it normalised. ✘ "went the LONG way round": the
   `if d < 0` step is missing.
4. `q_angle_deg`: the hand check gives 30°, and 330° without `abs`. ✘ "half the right angle": the factor 2.
   ✘ "q and −q are the SAME attitude": `abs(…)`. `math domain error`: clamp the dot product to at most 1.
</details>

## Step 7 — The oracle: an independent library

Your code passes its own examples, but you also chose how to read the examples. An **oracle** is an answer
you did not compute: SciPy's `Rotation`, written by other people, tested by thousands of users.

```bash
python3 compare_oracle.py
```

Read the top of `compare_oracle.py` before the output: SciPy's quaternions are (x, y, z, w) like ROS, and its
`"ZYX"` Euler sequence takes the angles **yaw first**. The last part shows SciPy's own behaviour at gimbal
lock.

> [!TASK]
> `EXPLAIN_ORACLE`: why is agreement with SciPy on 500 random cases stronger evidence than your own docstring
> examples? Which conventions did the comparison have to translate?

## Step 8 — The detective: a bug with no error message

A colleague recorded a flight's attitude from ROS (`/data/academy/16-rotations/attitude_log.csv`, columns
`t_s, qx, qy, qz, qw`) and printed it as a pilot would read it (`colleague_attitude.csv`). Their table says
the drone sat on the pad **rolled over**, and later flew **upside down**. The pilot says the flight was
normal. Nobody saw an error message.

```bash
head -4 /data/academy/16-rotations/attitude_log.csv /data/academy/16-rotations/colleague_attitude.csv
```

Three suspects, all from this lesson:

- **(a)** the pitch sign: the script printed the ROS pitch where a pilot expects pitch_up;
- **(b)** R vs Rᵀ: the script used the conjugate q* (the inverse rotation) instead of q;
- **(c)** the order trap: the script read the four numbers (x, y, z, w) as (w, x, y, z).

On the pad the drone is level, heading 30°. Look at the colleague's pad row in the `head -4` output above.

> [!TASK]
> **Predict** (`PREDICT_SUSPECT`), before you write any code: for each suspect, what would the pad row show
> (roll, pitch_up, heading)? Which suspect can explain the real row? Think, or try a line of `python3 -c` with
> your functions.

A suspicion is not a proof: you will now **reproduce** the colleague's table exactly from the log, then list
the symptoms. Open [detective.py](file:./detective.py).

**TODO A** `misread(q_ros)`: what the colleague's script really used. **TODO B** `tilt_deg(q)`: how far an
attitude is from level. Trace TODO B by hand first: for a drone on its back, where does its "up" axis point,
and what angle should come out?

```bash
python3 detective.py
```

Line 0 must say ✔ reproduced. Open `out/detective.png`.

> [!TASK]
> Write `PAD_HEADING_DEG`, `COLLEAGUE_PAD_ROLL_DEG`, `COLLEAGUE_MAX_TILT_DEG` (one decimal) and `FLIP_T_S` (the
> first of the two times of line 5). `EXPLAIN_DETECTIVE`: the cause; the symptoms — what looks wrong in the
> colleague's table, and which checks (lengths, rotation between samples) do **not** see the bug, and why;
> and why the sign change of line 5 is **not** a bug (lesson §4–§5).

<details><summary>Stuck? Hints</summary>

1. Suspects: on a level pad (a) changes nothing (pitch 0 either way); (b) turns the yaw the other way
   (heading 150°, still level). Only one suspect can make a level drone look rolled.
2. TODO A, the idea: which of the four file numbers did the script call w? Write down the four names it
   believed, then give them back in OUR order (x, y, z, w).
3. TODO A, the code: `w, x, y, z = q_ros` (the script's belief), then `np.array([x, y, z, w])`. Line 0 says ✘
   with a large difference: you returned the colleague's order, or shifted the other way
   (`[q[3], q[0], q[1], q[2]]` is the opposite conversion).
4. TODO B: turn the body's up (0, 0, 1) with your `rot.q_rotate`; its world "up" component is cos(tilt).
   Clamp before `math.acos`, return degrees. `math domain error` in q_angle_deg: clamp there too (TODO 11).
5. Why does line 4 show identical numbers? Swapping the four numbers in the same way for every sample does not
   change the 4-D dot product of two samples.
</details>

<details><summary>Read this after you wrote EXPLAIN_DETECTIVE</summary>
For a level drone, q = (0, 0, sin(ψ/2), cos(ψ/2)). Read as (w, x, y, z), the scalar is 0: every attitude
becomes a <b>180° turn</b> about the axis (0, sin(ψ/2), cos(ψ/2)), which tips the drone's top over by the
yaw angle ψ. On the pad (heading 30°, yaw 60°) it shows a 60° roll; flying west (yaw near ±180°) it shows the
drone upside down. The length stays 1, and the rotation between two samples is unchanged, because the swap
is the same for every sample. Checks of "is this a valid quaternion" and "is the turn rate plausible" pass.
What catches it: a known attitude (on the pad the drone is level), a comparison with an independent source
(the compass, the camera), or a test with a non-trivial quaternion at the boundary where the data enters.
Line 5 is not a bug: the recorder keeps w ≥ 0, so when the rotation angle passes 180° all four numbers change
sign; q and −q are the same attitude, and q_angle_deg (with its absolute value) sees only 0.36°.
</details>

## Step 9 — The bug memo

Write [report.md](file:./report.md) (150–350 words, your own words, keep the three headings): what the
colleague saw, the cause and how you proved it, and how to catch this kind of bug next time (one test you
would write, mission 14 style). Quote your numbers with their units.

> [!TASK]
> report.md has the three headings, 150–350 words, and quotes the pad heading and the colleague's pad roll
> (or largest tilt), in degrees.

## Step 10 — Check, then look back

Press **✔ Check my work**: it tests your functions on attitudes they have never seen, and against SciPy.
When every check passes, you earn the **Quaternion detective** badge. Then look back, without the lesson:

1. Explain to a colleague, in three sentences, why Euler angles are fine on a display but not inside a filter.
2. Which of your predictions was the most wrong? What did you assume?
3. Name the three convention questions you will now ask about any attitude data you receive.

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Prove it.** Multiply out Rz(ψ)·Ry(−90°)·Rx(φ) by hand and show that only ψ + φ appears (Step 3 found it
  numerically). Then derive the matrix of lesson §4: apply q ⊗ v ⊗ q* to (1, 0, 0) symbolically and recover
  its first column.
- **Too fast for the camera?** From detective line 4, the largest turn rate of the flight in °/s (per 0.1 s
  → per second). Would NAVERA refuse a photo from a fixed camera for turning too fast (In NAVERA: 30°/s)?
- **A fourth gimbal.** Write `matrix_to_euler_xyz` (another sequence). Where is *its* lock? Why can't any
  three-angle sequence avoid a lock?
- **Error budget.** NAVERA's celestial fix loses ~111 km per degree of attitude error (lesson, In NAVERA).
  Rotate the "up" vector by small random errors (`q_from_axis_angle` with a random axis, angle 0.3°) and
  histogram the tilt error with your `tilt_deg`.
- **Fly your own parts.** Mission 17 ships the course's `rotations.py`. Copy yours over it
  (`cp ../16-rotations/navera_lite/rotations.py navera_lite/`) and run that mission's tests.

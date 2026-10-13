# Course conventions (one page, for authors)

Every mission uses these conventions. When a mission must use another one (a library, a paper, a
rule NAVERA uses), it says so in one line where it happens and converts explicitly.
The values are described from NAVERA's documentation (checked 2026-10-10); the code is NAVERA Lite's,
the course's own stack (`navera_lite/`). Each rule names the NAVERA Lite part that applies it.

## 1. Frames

| Frame | Axes | Used for | NAVERA Lite part |
|---|---|---|---|
| **World ENU** | x = East, y = North, z = Up | positions on a local flat map, velocities, attitude quaternions | `geo.py` (06), `rotations.py` (16) |
| **Body FLU** (ROS REP-103) | x = Forward (nose), y = Left, z = Up | the vehicle | `rotations.py` (16), `imu.py` (17) |
| **Camera (OpenCV)** | x = image right, y = image down, z = optical axis (out of the lens) | pixels, K, homographies | `camera.py` (18); a nadir camera with no mount offset has the image top towards the nose (`R_BODY_NADIR_CAM`) |

Rotation matrices are named `R_<to>_<from>`: `R_world_cam @ v_cam = v_world` (NAVERA uses the same rule).

## 2. Quaternions: (x, y, z, w)

- ROS messages (`sensor_msgs/Imu`, `geometry_msgs/Quaternion`) store a quaternion as
  **(x, y, z, w)** — the scalar part **last**. NAVERA does the same everywhere (in its words).
- **Course rule:** course code (NAVERA Lite's `rotations.py`, `imu.py`, `camera.py`) stores
  quaternions as (x, y, z, w) too. Maths text may write
  q = w + x i + y j + z k, but every function's docstring names the order.
- A 90° turn to the left (yaw +90° about Up) is q = (0, 0, 0.7071, 0.7071); it turns (1, 0, 0) into (0, 1, 0).
- Known gap: missions 17 and 20 currently use w-first numpy arrays internally; their batch switches them to
  this rule (16 is done: NAVERA Lite `rotations.py`, and it teaches the (w, x, y, z) trap as its detective step).

## 3. Heading vs ENU yaw

| Angle | Zero | Positive direction | Range |
|---|---|---|---|
| **Heading** (navigation, NAVERA's outputs) | North | **clockwise** (east = 90°) | [0°, 360°) |
| **ENU yaw** (ROS, maths) | East | **counter-clockwise** (north = 90°) | (−180°, 180°] |

`heading = (90° − yaw_enu) mod 360°` and back `yaw_enu = 90° − heading` (NAVERA Lite:
`rotations.heading_deg_from_q`, `rotations.rpy_human`; `vehicle.heading_vector` and `geo.bearing_deg` use a
heading clockwise from true north, as NAVERA does; `geo.offset(lat, lon, e_m, n_m)` takes east and north metres). Check: yaw_enu = 0° (nose east) → heading 90°.
A compass gives `atan2(east, north)` for a heading, **not** `atan2(north, east)` (that is the ENU yaw).

## 4. Pitch sign: ROS vs NAVERA's "human" angles

- **ROS (REP-103, fixed axes, `R = Rz(yaw) · Ry(pitch) · Rx(roll)`, NAVERA Lite `rotations.euler_zyx_to_matrix`):**
  pitch is a rotation about body **+y = left**. By the right-hand rule a **positive** ROS pitch
  turns the nose **down** (`Ry(θ)·(1,0,0) = (cos θ, 0, −sin θ)`).
- **"Human" angles** (what NAVERA reports, and NAVERA Lite's `rotations.rpy_human(q)`), in degrees:
  roll positive **right wing down**, pitch positive **nose up**, heading clockwise from north.
  `−asin(R[2,0])` is the ROS pitch; the human pitch is its opposite.
- So a drone 5° nose-down has ROS pitch **+5°** and human pitch **−5°**. Every mission that
  prints a pitch says which one it is ("ROS pitch" or "pitch, nose up").

## 5. Covariance notation (horizontal 2 × 2 block)

```
P = | a  b |     a = σE²       (East variance, m²)        = position_covariance[0]
    | b  c |     b = cov(E, N) (East-North covariance, m²) = position_covariance[1] = [3]
                 c = σN²       (North variance, m²)       = position_covariance[4]
```

- `position_covariance` is 9 numbers, ENU, row-major, m², as in `sensor_msgs/NavSatFix` (and in
  NAVERA Lite's `estimate.Estimate.cov`); index 8 = σU².
- Eigenvalues (ellipse axes²): `λ = (a + c)/2 ± sqrt(((a − c)/2)² + b²)`; PSD ⇔ a ≥ 0, c ≥ 0,
  `a·c − b² ≥ 0` up to a small tolerance (NAVERA Lite `estimate.is_covariance`; NAVERA's judge applies
  the same test, in its words).
- Correlation `ρ = b / (σE σN)`. The single "stated σ" is `sqrt(max(a, c))` (NAVERA Lite
  `estimate.stated_sigma`; NAVERA's judge and day vision use the same rule).
- Known gap: mission 12 uses this notation; mission 29 (old 25) writes b = σN², c = cov — fixed in its batch.

## 6. Percentiles

- **Course rule:** `np.percentile(x, q)` with numpy's default **linear** interpolation (median,
  p90, p95, CEP50 = median radial error, CEP95 = p95). NAVERA Lite's `stats.percentile` (32)
  reimplements it.
- **Named contrast:** NAVERA's evaluation tool (described in words) takes the sorted sample at index
  `round(q/100 · (n − 1))` — no interpolation, a nearest-sample ("nearest-rank") rule, identical to
  `np.percentile(x, q, method="nearest")`. NAVERA Lite's `stats.pct_nearest` (given in 32) applies
  that rule so mission 32 can compare the two, and says so.
- Example, x = 1…10: p50 linear = 5.5, nearest = 5; p95 linear = 9.55, nearest = 10.

## 7. Units and names (short)

Angles in **degrees** at interfaces and in prints, **radians** inside `math`/`numpy` trig calls
(convert at the boundary, names end in `_deg` / `_rad`). Distances in metres (`_m`), times in seconds
(`_s`), ROS float fields get floats (`9.0`, not `9`). Latitude before longitude, always.

## 8. NAVERA Lite (the course's stack)

Package `navera_lite/` in each lesson folder, settings in `navera_lite.yaml` (ROS 2 params-file
format), ROS topics `/navera_lite/*` (fixes `NavSatFix` on `/navera_lite/fix/<source>`, the judge's
`/navera_lite/position` and `/navera_lite/status`). Import absolutely (`from navera_lite.geo import
haversine_m`) and run nodes with `python3 -m navera_lite.ros.<node>` from the lesson folder.
Lessons say "In NAVERA" (the product, in words and numbers only) and then "In NAVERA Lite" (where the
idea lives in the student's own code). Design: `reviews/fledgling-design.md` (read Fledgling as NAVERA Lite).

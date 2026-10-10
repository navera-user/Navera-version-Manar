# Course conventions (one page, for authors)

Every mission uses these conventions. When a mission must use another one (a library, a paper,
NAVERA's own tool), it says so in one line where it happens and converts explicitly.
Each rule was checked against NAVERA's code in `base/` (2026-10-10); the file is named after each rule.

## 1. Frames

| Frame | Axes | Used for | NAVERA source |
|---|---|---|---|
| **World ENU** | x = East, y = North, z = Up | positions on a local flat map, velocities, attitude quaternions | `navera_common/camera_model.py` (module docstring) |
| **Body FLU** (ROS REP-103) | x = Forward (nose), y = Left, z = Up | the vehicle | same file; `imu_pkg/orientation.py` |
| **Camera (OpenCV)** | x = image right, y = image down, z = optical axis (out of the lens) | pixels, K, homographies | same file; a nadir camera with no mount offset has the image top towards the nose (`R_BODY_NADIR_CAM`) |

Rotation matrices are named `R_<to>_<from>`: `R_world_cam @ v_cam = v_world`, as in NAVERA.

## 2. Quaternions: (x, y, z, w)

- ROS messages (`sensor_msgs/Imu`, `geometry_msgs/Quaternion`) and every NAVERA function
  (`quat_to_matrix`, `body_rpy_enu`, `orientation.quat_mul`, `sensor_history.slerp`) store a
  quaternion as **(x, y, z, w)** — the scalar part **last**.
- **Course rule:** course code stores quaternions as (x, y, z, w) too. Maths text may write
  q = w + x i + y j + z k, but every function's docstring names the order.
- A 90° turn to the left (yaw +90° about Up) is q = (0, 0, 0.7071, 0.7071); it turns (1, 0, 0) into (0, 1, 0).
- Known gap: missions 16, 17 and 20 currently use w-first numpy arrays internally. Their batch
  switches them to this rule (and teaches the (w, x, y, z) trap as the "detective" role of 16).

## 3. Heading vs ENU yaw

| Angle | Zero | Positive direction | Range |
|---|---|---|---|
| **Heading** (navigation, NAVERA's outputs) | North | **clockwise** (east = 90°) | [0°, 360°) |
| **ENU yaw** (ROS, maths) | East | **counter-clockwise** (north = 90°) | (−180°, 180°] |

`heading = (90° − yaw_enu) mod 360°` and back `yaw_enu = 90° − heading` (NAVERA:
`imu_pkg/orientation.py heading_deg`, `camera_model.body_rpy_enu`; `geo.dead_reckon` takes a heading
clockwise from true north). Check: yaw_enu = 0° (nose east) → heading 90°.
A compass gives `atan2(east, north)` for a heading, **not** `atan2(north, east)` (that is the ENU yaw).

## 4. Pitch sign: ROS vs NAVERA's "human" angles

- **ROS (REP-103, fixed axes, `R = Rz(yaw) · Ry(pitch) · Rx(roll)`, `camera_model.rpy_to_matrix`):**
  pitch is a rotation about body **+y = left**. By the right-hand rule a **positive** ROS pitch
  turns the nose **down** (`Ry(θ)·(1,0,0) = (cos θ, 0, −sin θ)`).
- **NAVERA's `body_rpy_enu(q)` reports human angles** in degrees: roll positive **right wing down**,
  pitch positive **nose up**, heading clockwise from north. In the code:
  `pitch = −asin(R[2,0])` is the ROS pitch, and the function returns `−pitch`.
- So a drone 5° nose-down has ROS pitch **+5°** and `body_rpy_enu` pitch **−5°**. Every mission that
  prints a pitch says which one it is ("ROS pitch" or "pitch, nose up").

## 5. Covariance notation (horizontal 2 × 2 block)

```
P = | a  b |     a = σE²       (East variance, m²)        = position_covariance[0]
    | b  c |     b = cov(E, N) (East-North covariance, m²) = position_covariance[1] = [3]
                 c = σN²       (North variance, m²)       = position_covariance[4]
```

- `position_covariance` is 9 numbers, ENU, row-major, m² (`navera_msgs/PositionEstimate.msg`, as
  `sensor_msgs/NavSatFix`); index 8 = σU².
- Eigenvalues (ellipse axes²): `λ = (a + c)/2 ± sqrt(((a − c)/2)² + b²)`; PSD ⇔ a ≥ 0, c ≥ 0,
  `a·c − b² ≥ 0` (NAVERA's `estimator_node._sane()` tests `cov[0]*cov[4] − cov[1]*cov[3] ≥ −tol`).
- Correlation `ρ = b / (σE σN)`. NAVERA's single "stated σ" is `sqrt(max(a, c))` (estimator, day vision).
- Known gap: mission 12 uses this notation; mission 29 (old 25) writes b = σN², c = cov — fixed in its batch.

## 6. Percentiles

- **Course rule:** `np.percentile(x, q)` with numpy's default **linear** interpolation (median,
  p90, p95, CEP50 = median radial error, CEP95 = p95). Missions 23 and 33 use it; `stats_tools.percentile`
  in 33 reimplements it.
- **Named contrast:** NAVERA's `navera_tools/evaluate_session.py pct(v, q)` takes the sorted sample
  at index `round(q/100 · (n − 1))` — no interpolation, a nearest-sample ("nearest-rank") rule,
  identical to `np.percentile(x, q, method="nearest")` (checked on 20 000 random cases). Mission 32
  uses `pct()` only to reproduce NAVERA's tables, and says so.
- Example, x = 1…10: p50 linear = 5.5, `pct` = 5; p95 linear = 9.55, `pct` = 10.

## 7. Units and names (short)

Angles in **degrees** at interfaces and in prints, **radians** inside `math`/`numpy` trig calls
(convert at the boundary, names end in `_deg` / `_rad`). Distances in metres (`_m`), times in seconds
(`_s`), ROS float fields get floats (`9.0`, not `9`). Latitude before longitude, always.

# Fledgling — the course's own navigation stack (design)

Status: design for review (2026-10-12). Nothing in `courses/`, `solutions/`, `server/` or `datasets/` was edited.
Sources: `reviews/rebuild-plan-02-30.md` (the plan this document amends), mission 01 (the template), `AUTHORING.md`,
`courses/_lib/*`, every mission 02–33 (lesson, lab, check, files, solutions, datasets), `server/simlite.py`,
`server/static/simlite/*`, `server/{config,sandbox,workspaces,app}.py`, and NAVERA's base (read only, for concepts).

**The rule this design serves.** Students never see, run, import, grep or edit NAVERA's code or files. Lessons may
describe NAVERA in words and numbers (design, rules, settings values, measured results with dates). Everything a
student runs is course-written code: **Fledgling**.

---

## 1. Overview

### 1.1 Purpose

Fledgling is a small GPS-denied navigation stack for a drone, written for the course and **completed by the
students, one part per mission**. It has the same *shape* as NAVERA as lesson 1 §5 describes it in words
(witnesses → judge → messenger), so every "In NAVERA" paragraph can point at the Fledgling part that does the same
job. It is deliberately smaller: pure Python + numpy + OpenCV, a thin rclpy layer on standard messages, no custom
messages, no colcon build in any required step, CPU only.

It replaces three things at once: the student's `~/navera` copy (reading, editing, running), every
"compare with NAVERA" script (the oracle becomes the course's reference values or a third-party library), and
NAVERA's estimator inside Sim Lite (the browser now flies the student's own arbiter).

Naming in lessons: "Fledgling, your stack" vs "NAVERA, IRIS's product". A one-paragraph box in mission 02 says:
"NAVERA's code is IRIS's property and is not part of the course. You build Fledgling, which works on the same ideas.
When a lesson says *In NAVERA*, it describes the product in words; *In Fledgling* shows where the idea lives in your
own code."

### 1.2 Architecture

```
 DATA / SENSORS                 SOURCES (one Estimate each)                 JUDGE                       MESSENGER
 NMEA lines ──► gnss (15) ─────────────────────────► gps  ──┐
 camera frame ─► camera (18-20) ─► features/match (21-22)    │
               ─► locate (23) ─────────────────────► day  ──┤   estimate.eligible (12)
 thermal frame ► night (25) ───────────────────────► night ─┼─► guard: jump gate (01), ──► arbiter (29) ──► /fledgling/position
 star photo ───► stars (26) ───────────────────────► star ──┘   cross-check (30)          state machine     /fledgling/status
 IMU ──────────► imu (17) ──► attitude ──► used by camera (20) and stars (26)              │                 output (31): GPS_INPUT bytes
 frames ───────► vo (24) ──► drift + σ growth (project source in 33)                       └ uncertainty.fuse (27), kalman (28): the
                                                                                             "selection vs fusion" experiment and smoothing
 toolkit: vehicle/track (03) · logbook (04) · geo (06) · tiles (07) · image (08) · rotations (16)
 ROS layer (09-14): qos · gps_node · trip_node · convert · replay_node · arbiter_v0 → arbiter_node (29) · launch
 proving it: tests/ (14) · sim/ headless world = Sim Lite's world (31) · stats (32) · tools/evaluate_bag (32)
```

The arbiter exists in two generations. **Arbiter v0** (`fledgling/ros/arbiter_v0.py`, given, ~90 lines) is naive on
purpose: freshness + priority + the jump gate from mission 01, FIX if a stated σ ≤ 25 m. Students read it in 09,
watch it in 11, attack it in 12, launch it in 13, launch-test it in 14. In 29 they write the real arbiter that
replaces it (eligibility, hold-off, honest states, reasons), and in 30 they add the cross-check. This gives the ROS
missions a live judge without giving away mission 29.

### 1.3 Package layout (complete stack, as in the reference)

```
fledgling/
  __init__.py        PARTS: dict part → mission; __version__ = "course-2026.1"
  settings.py        load/validate fledgling.yaml                       (values 01, code 13)
  vehicle.py         Vehicle classes, wind triangle, VEHICLES table     (03)
  track.py           Track (time-ordered positions)                     (03)
  logbook.py         pandas flight-log cleaning and outages             (04)
  geo.py             sphere + WGS84, ENU, haversine, bearing            (06)
  tiles.py           Web Mercator, MBTiles, map_patch                   (07)
  image.py           dtype, filters, affine warp, like_map              (08)
  estimate.py        Estimate contract + covariance/eligibility checks  (12)
  guard.py           jump gate (01), cross-check (30)
  gnss.py            NMEA, DOP, receiver decision, σ from HDOP          (15)
  rotations.py       matrices, Euler, quaternions (x,y,z,w), slerp      (16)
  imu.py             gyro integration, tilt, complementary, declination (17)
  camera.py          pinhole/K, ground projection, GSD, homography (18), fisheye (19), timing/attitude (20)
  features.py        gradients, Harris, repeatability, matchability     (21)
  match.py           ratio test, similarity fit, RANSAC, gates          (22)
  locate.py          photo → lat/lon, error budget                      (23)
  vo.py              phase correlation, drift, blend                    (24)
  night.py           NCC, coverage, prepare, motion gate                (25)
  stars.py           time, alt/az, Polaris, two roots                   (26)
  uncertainty.py     ellipse, propagate, Mahalanobis, gate, fuse        (27)
  kalman.py          predict/update, NEES, Height1D                     (28)
  arbiter.py         the judge                                          (29)
  output.py          GPS_INPUT encode (given) / decode (student)        (31)
  stats.py           errors, percentiles, availability, bootstrap, Wilson (32)
  ros/
    qos.py  convert.py  gps_node.py  trip_node.py  replay_node.py  nmea_node.py
    arbiter_v0.py  arbiter_node.py  camera_node.py  launch_util.py  fledgling.launch.py
  sim/               world.py (same file as Sim Lite's), sensors.py, run.py, _lite/ (rclpy stand-in)  (31)
  tools/             evaluate_bag.py (32), init_repo.sh (14, 33)
  tests/             test_<part>.py for every finished part             (14 onward)
fledgling.yaml       settings, ROS params-file format (§2.2)
```

### 1.4 Coding style (binding for authors)

- Python 3.10, numpy < 2, OpenCV, pandas only in `logbook.py`/`stats.py` callers; scipy only as a test oracle.
- Mission 01 style: every student function has a docstring with the **goal, inputs/outputs with units, and one
  `Example:` call with its result**, never the algorithm. Stubs end with
  `return None   # TODO: write your code above, and return the result` (runner_kit's STUB_MARKS);
  methods that must return nothing use `raise NotImplementedError("TODO 3")`.
- Units in names (`_m`, `_s`, `_deg`, `_rad`, `_mps`); degrees at interfaces; latitude before longitude;
  quaternions (x, y, z, w); covariance a/b/c notation; percentiles linear — all as `courses/_lib/CONVENTIONS.md`.
- Pure functions in parts; I/O only in `ros/`, `sim/`, `tools/` and mission runners. No globals except constants.
- Absolute imports inside the package (`from fledgling.geo import haversine_m`), so a file runs the same from the
  runner, from `python3 -m`, from check.py and in Pyodide.
- Errors: impossible input raises `ValueError("<what> must be <rule>, got <value>")`; "no answer" returns `None`
  plus a reason where the contract says `(value, reason)`.
- Every file starts with: `"""fledgling/<part>.py — <one line>. Part of Fledgling, the course's teaching stack
  (mission NN). Written for the course; it is not NAVERA code."""`. Finished functions carry
  `# from mission NN — finished: read it, use it, do not change it`.
- Line length ≤ 110; no Python feature before the mission that teaches it (classes from 03, pandas 04,
  rclpy 10, dataclasses 12 with a 🧰 box).
- **Originality:** the reference is written from the lesson texts and this document, never by copying NAVERA. A
  release gate (§5, `fledgling_lint.py`) refuses any 6-line normalised span identical to `base/`, and any banned
  identifier (`navera_`, `estimator_node`, `/navera/`, `PositionEstimate`, `NavStatus`, `cn_pkg`, `day_pkg`…).

### 1.5 Delivery inside `~/lessons/<id>/`

Each mission ships only the parts it needs (the import closure of its TODO parts and runners), never the whole stack
(except 33). Layout, example mission 29:

```
~/lessons/29-arbiter/
  fledgling/
    __init__.py            PARTS lists what this copy holds
    PARTS.md               table: part · mission · status (given / ✏️ YOUR TODOs 1–6)
    settings.py geo.py estimate.py guard.py uncertainty.py      given, finished
    arbiter.py             ✏️ this mission (TODO stubs + small finished helpers)
    ros/__init__.py convert.py qos.py replay_node.py arbiter_node.py arbiter_v0.py   given
    tests/test_estimate.py tests/test_guard.py                  given (they pass)
  fledgling.yaml           the student's settings (they may edit it)
  run_arbiter.py           the runner (mission 01 style, imports runner_kit)
  runner_kit.py            copy of courses/_lib/runner_kit.py
  play_scenario.py         mission-specific given tools
  answers.py  report.md
```

- **Earlier parts are the course's reference versions**, not the student's own: a weak mission-06 `geo.py` must not
  sink mission 23. Going further, every mission from 07 on offers "fly your own parts":
  `cp ../06-coordinates/fledgling/geo.py fledgling/ && python3 -m pytest fledgling/tests -q`
  (all lesson folders live in the same `~/lessons`, so no server change is needed).
- Functions introduced in **later** missions are cut out of a part, not stubbed: mission 18's `camera.py` has only
  the 18 functions; 19 adds fisheye; 20 adds timing. A part grows; it never shows a future TODO.
- Data never goes into `fledgling/`; it stays in `/data/academy/<id>/`.

### 1.6 One source, generated starters and solutions

- **Single source of truth:** `solutions/_fledgling/` (teacher only, never mounted): the complete reference stack,
  its tests, and `manifest.json`. Each top-level function/class in the reference is preceded by one tag line:
  `# @part 29 todo 4` (introduced in 29, stubbed there as TODO 4) or `# @part 12` (introduced in 12, never a TODO —
  a given helper). A function's student-facing docstring is written once, in the reference.
- **`manifest.json`:** per mission: `parts` (module list; closure is computed and checked), `todo_missions`
  (normally `[NN]`), `tests` (which test files to ship), `extra` (e.g. `sim/` in 31, everything in 33).
- **`tools/fledgling_build.py <id> | --all`** writes:
  - `courses/<id>/files/fledgling/…`: each part with functions tagged ≤ NN; tagged == NN replaced by signature +
    docstring + stub; tagged > NN removed; header comment "generated — edit solutions/_fledgling".
  - `solutions/<id>/fledgling/…`: the same parts, complete.
  - It then verifies: the starter imports; `pytest` of the shipped tests passes on the solution; the starter's
    TODO functions are stubs; every TODO docstring has an `Example:`; `fledgling_lint.py` passes.
- Mission-specific files (runner, answers.py, report.md, play tools) stay hand-written in `courses/<id>/files/`
  as today. `tools/try_lesson.py --solution` already copies `solutions/<id>/` over the lesson folder; it must copy
  sub-folders (one-line check, §5).
- Expected values in check.py are computed **once** by the builder from the reference on the check's unseen inputs
  and pasted as numbers (`solutions/_fledgling/expected/<id>.json` → check.py constants). check.py never imports the
  reference.

---

## 2. Module-by-module specification

Format: `signature` — contract. **Intro** = mission that introduces it (TODO there unless marked *given*).
**Reuse** = later missions that ship it finished.

### 2.1 Seeds from mission 01 (done, unchanged)

Mission 01's `beacons.py` stays as it is. Its gate functions are re-born in `guard.py` and credited
("you wrote this in mission 01"): `gate_ok`, `count_refused`, `first_disagreement` (the last becomes the starting
point of the cross-check in 30). `navera_settings.yaml` stays the description of NAVERA's values; `fledgling.yaml`
takes the same numbers.

### 2.2 `fledgling.yaml` and `settings.py`

`fledgling.yaml` is a **ROS 2 params file** (`/**: ros__parameters:`), so one file feeds `--params-file`, launch,
and `settings.load()`. Values = mission 01's sheet + lesson 1 §5 (described NAVERA values):

```yaml
/**:
  ros__parameters:
    gps_timeout_s: 3.0        day_timeout_s: 5.0     night_timeout_s: 5.0   celestial_timeout_s: 45.0
    future_tolerance_s: 0.5   fix_max_sigma_m: 25.0  min_stated_sigma_m: 0.01
    switch_holdoff_s: 2.0     tick_hz: 5.0
    max_speed_mps: 100.0      gps_jump_margin_m: 50.0
    xcheck_gap_k: 5.0  xcheck_margin_m: 50.0  xcheck_gap_hold_s: 3.0
    xcheck_streak_k: 3.0  xcheck_streak_n: 5  xcheck_doubt_n: 2  xcheck_return_n: 2
    vehicle: "drone"
```
(one key per line in the real file, each with a comment.)

- `DEFAULTS: dict` — the values above (*given*, 12).
- `load(path="fledgling.yaml") -> dict` — DEFAULTS updated by the file's `/**` block; unknown keys raise (*given*, 12).
- `check_settings(cfg) -> list[str]` — every rule broken, as sentences: timeouts > 0, `0 < fix_max_sigma_m`,
  `max_speed_mps` within the vehicle's range, ints are ints (the LOC-30 trap). **Intro 13** (TODO). Reuse 29–33.

### 2.3 Toolkit parts

`vehicle.py` — **intro 03**; reuse 13 (vehicle → max speed), 31, 33.
- `heading_vector(heading_deg) -> (e, n)`; `ground_velocity(airspeed_mps, heading_deg, wind_e=0.0, wind_n=0.0) -> (ve, vn)`;
  `wind_components(track_deg, wind_e, wind_n) -> (along, cross)`;
  `heading_for_track(track_deg, tas_mps, wind_e, wind_n) -> (heading_deg, gs_mps)` (ValueError if crosswind > TAS);
  `endurance_s(battery_wh, power_w, reserve=0.2)`.
- `class Vehicle(name, cruise_mps, max_speed_mps, battery_wh, power_w)`: `endurance_s()`, `range_m(wind_along_mps=0)`;
  `Multirotor`, `FixedWing(stall_mps)` with `turn_radius_m(bank_deg=30)` (optional).
- `VEHICLES = {"drone": 30.0, "plane": 100.0, "boat": 20.0, "robot": 10.0}` max speeds m/s (*given*; same as Sim Lite).

`track.py` — **intro 03**; reuse 04, 11, 24, 31, 32.
- `class Track`: `add(t_s, e_m, n_m)` (ValueError if t not increasing), `__len__`, `arrays() -> (t, e, n)`,
  `length_m()`, `speeds_mps() -> np.ndarray`, `glitches(max_mps) -> list[int]`. `load_track(path) -> Track` (*given*).

`logbook.py` — **intro 04**; reuse 31, 32.
- `clean(df) -> (df, removed: dict)`, `add_motion(df) -> df`, `outage_runs(valid: np.ndarray) -> list[(i0, i1)]`,
  `outage_table(df, dt_s) -> df`, `state_shares(df) -> dict`, `noise_by_source(df) -> df`.

`geo.py` — **intro 06**; reuse 07–33 (everything that touches lat/lon). R = 6 371 000 m for the sphere functions.
- `haversine_m(lat1, lon1, lat2, lon2) -> float` (numpy-broadcastable); `bearing_deg(lat1, lon1, lat2, lon2)`;
  `enu_flat(lat0, lon0, lat, lon) -> (e_m, n_m)` (cos of mean latitude); `offset(lat, lon, e_m, n_m) -> (lat, lon)`;
  `great_circle_points(p1, p2, n) -> list[(lat, lon)]`; `max_offset_km(p1, p2)`.
- WGS84 (06, Going further level in the lesson, but TODOs): `radii(lat)`, `geodetic_to_ecef(lat, lon, h=0)`,
  `ecef_to_geodetic(x, y, z)`, `geodetic_to_enu(lat, lon, h, lat0, lon0, h0)`, `enu_to_geodetic(...)`.
- `is_finite_latlon(lat, lon) -> bool` (*given* 06: finite, in range, not (0, 0)).

`tiles.py` — **intro 07**; reuse 08, 18, 21–25 (replaces the four copies of `navmap.py`).
- `tile_xy(lat, lon, z) -> (x, y)` fractional; `tile_to_latlon(x, y, z)`; `m_per_px(lat, z)`;
  `best_zoom(gsd_m, lat, zmin=13, zmax=19)`; `read_tile(db, z, x, y) -> bytes | None` (placeholders, TMS flip);
  `pixel_to_latlon(px, py, z, x0, y0)`, `latlon_to_pixel(lat, lon, z, x0, y0)`.
- *Given* from 07 on: `MAP_PATH` (env `FLEDGLING_MAP`, default `/data/map.mbtiles`, fallback
  `/data/academy/07-map-tiles/sousse_small.mbtiles`), `map_patch(lat, lon, z, width_px, height_px) -> np.ndarray`.

`image.py` — **intro 08**; reuse 18, 21–25.
- `to_uint8(a)`, `to_float01(a)`, `to_gray(img)`, `histogram(gray)`, `normalise(gray)`, `convolve2d(img, k)`,
  `gaussian_kernel(k, sigma)`, `sobel(gray)` (one normalisation course-wide, /8), `affine_matrix(angle_deg, scale, centre)`,
  `warp_affine(img, M, size)` (bilinear), `like_map(photo, heading_deg, gsd_photo_m, gsd_map_m)`.

### 2.4 The position contract: `estimate.py` (intro 12)

```python
@dataclass
class Estimate:                       # one position from ONE source
    source: str                       # "gps" | "day" | "night" | "star"
    lat: float; lon: float; alt_m: float = math.nan
    t_meas_s: float = 0.0             # measurement instant (header.stamp), s
    cov: tuple | None = None          # 9 floats ENU m², row-major; None = unknown
    cov_type: int = 0                 # 0 UNKNOWN, 1 APPROXIMATED, 2 DIAGONAL_KNOWN, 3 KNOWN (NavSatFix values)
    valid: bool = True                # False = the source is alive but has no position
    reason: str = ""
    t_recv_s: float | None = None     # when the judge received it
```

- `PRIORITY = ("gps", "day", "night", "star")`, `TIMEOUT_KEY = {"gps": "gps_timeout_s", …}` (*given*).
- `is_covariance(cov9, tol=1e-9) -> (ok, reason)` — finite, symmetric, a ≥ 0, c ≥ 0, ac − b² ≥ −tol. **TODO**.
- `stated_sigma(est, cfg) -> float | None` — √max(a, c) when the type is not UNKNOWN and the matrix is a covariance;
  None if unknown, invalid, or below `min_stated_sigma_m` (an invented zero). **TODO**.
- `staleness_m(speed_mps, age_s) -> float`. **TODO**.
- `eligible(est, now_s, cfg) -> (bool, reason)` — valid; `is_finite_latlon`; covariance sane when stated; not from the
  future beyond `future_tolerance_s`; fresh (age ≤ the source's timeout). Reasons are short fixed phrases
  (`"stale (3.4 s > 3.0 s)"`, `"from the future"`, `"not a covariance"`, `"no position"`, `"null island"`). **TODO**.
- `classify(est, cfg) -> (state, reason)` — `"FIX"` if a stated σ ≤ `fix_max_sigma_m`, else `"DEGRADED"`. *Given* 12
  (it is lesson 1's table); reused by v0 and 29.
- Reuse: 13, 14, 27–33, Sim Lite.

On the wire (`ros/convert.py`, *given* 12): `to_navsatfix(est) -> NavSatFix`, `from_navsatfix(msg, source, now_s) -> Estimate`.
Mapping: `header.stamp` = measurement instant (ROS convention; lesson 12 teaches "stamp = when measured", and that
NAVERA carries a second stamp for the publication instant, in words); `header.frame_id` = source;
`status.status = -1` ⇔ `valid=False`, else 0; `position_covariance(_type)` copied. A fix topic carries measurements
only: Fledgling never re-publishes an old or dead-reckoned position on a fix topic ("one topic, one meaning").

### 2.5 `guard.py` (seed 01, given 12, intro of the cross-check 30)

- `gate_ok(last_xy, new_xy, elapsed_s, v_max_mps, margin_m) -> bool` (01, *given* from 12).
- `class JumpGate(cfg)`: `check(est) -> (ok, reason)` keeps the last trusted GPS fix (lat/lon via `geo.enu_flat`);
  refused fixes never become trusted (*given* 12; lesson 1's table is its test).
- 30 TODOs:
  - `allowed_m(sigma_m, dt_s, k, cfg) -> float` = k·σ + margin + v_max·|dt| (the "what the vehicle can fly between the two" term).
  - `crosscheck(gps_est, vis_est, cfg) -> ("agree" | "far" | "gap", distance_m)`.
  - `persistent(flags, n) -> bool` (last n flags all True).
  - `class CrossCheck(cfg)`: `on_vision(est)`, `on_gps(est) -> ("TRUSTED" | "IN_DOUBT" | "REFUSED", reason)`:
    gap beyond `xcheck_gap_k`σ + margin held `xcheck_gap_hold_s` → REFUSED; `xcheck_streak_n` vision fixes in a
    row beyond `xcheck_streak_k`σ → REFUSED; from `xcheck_doubt_n` → IN_DOUBT; back to TRUSTED after
    `xcheck_return_n` agreeing vision fixes; no σ-stating vision → no verdict (the stated limit).
  - `patient_accept_time(offset_m, drift_mps, cfg) -> float` (jump gate alone; `inf` when drift = 0 and offset > margin
    — fixes the old TODO 7 ZeroDivisionError).
  - `p_exceed(k, sigma_ref_m, sigma_gps_m)`, `p_streak(k, n, …)`, `roc_point(z_h0, z_h1, k, n)` stay in the mission's
    `detection.py` (analysis, not stack).
- Reuse: 31 (sim), 33.

### 2.6 Sensor parts

`gnss.py` — **intro 15**; reuse 31, 33.
- `nmea_checksum(body) -> str`, `is_valid(line) -> bool`, `dm_to_deg(value, hemi) -> float`,
  `parse_gga(line) -> dict | None` (keys t_utc_s, lat, lon, qual, sats, hdop, alt_msl_m, geoid_m),
  `parse_gsa`, `parse_gsv`; `geometry_matrix(az_deg, el_deg)`, `dops(az_deg, el_deg) -> dict | None` (None when singular).
- `fix_decision(gga) -> (valid, reason)` — qualities {1, 2, 4, 5} measured; 6 (receiver's own dead reckoning) and 0
  refused; reasons are Fledgling's own phrases. `covariance_from_hdop(hdop) -> (cov9, cov_type)` — σ = 2·HDOP m
  (lesson states this is NAVERA's rule too), Up 2σ; HDOP None → UNKNOWN. `to_estimate(gga, t_s) -> Estimate`.
- `ros/nmea_node.py` (*given* 15): reads a file or a pty, publishes `/fledgling/fix/gps`, counts published/valid/invalid.

`rotations.py` — **intro 16**; reuse 17–20, 26.
`rot_x/rot_y/rot_z(angle_rad)`, `euler_zyx_to_matrix(roll, pitch, yaw)` (ROS pitch), `matrix_to_euler_zyx(R) -> (r, p, y, locked)`,
`q_mul(p, q)`, `q_conj(q)`, `q_from_axis_angle(axis, angle_rad)`, `q_rotate(q, v)`, `q_to_matrix(q)`, `slerp(q0, q1, t)`,
`q_angle_deg(q0, q1)`, *given*: `heading_deg_from_q(q)`, `rpy_human(q) -> (roll, pitch_up, heading)` (the conventions-sheet
"human angles", pitch positive nose-up). All quaternions (x, y, z, w).

`imu.py` — **intro 17**; reuse 20, 26.
`integrate_gyro(q0, t_s, gyro_rad_s) -> np.ndarray`, `tilt_from_accel(ax, ay, az) -> (roll, pitch)`,
`complementary(t_s, gyro, accel, tau_s) -> np.ndarray`, `mag_heading(mag, roll, pitch)`, `true_heading(mag_deg, decl_deg)`,
`declination_deg(lat, lon, year)` (*given*, pygeomag), `class StaleDetector(max_repeat)`: `update(sample) -> bool`.

`camera.py` — **intro 18** (pinhole), **19** (fisheye), **20** (time); reuse 21–26.
- 18: `focal_px(hfov_deg, width_px)`, `K_from_hfov(hfov_deg, w, h)`, `project(K, R_wc, C, X)`, `backproject_ground(K, R_wc, C, u, v)`,
  `footprint(K, R_wc, C, w, h)`, `gsd(h_m, hfov_deg, w_px)`, `tilt_position_error(h_m, tilt_deg, dtilt_deg)`,
  `nadir_homography(K, R_cam_nadir)`; *given*: `R_BODY_NADIR_CAM`, `camera_rotation(q_body, R_body_cam)`.
- 19: `load_calibration(path) -> dict`, `fisheye_project(X_cam, K, D)`, `theta_from_theta_d(theta_d, D)`,
  `reprojection_rms(...)`, `straight_K(hfov_deg, size)`, `undistort(img, K, D, K_new)`, `stretch_at(theta_deg)`.
- 20: `frame_stats(stamps_s) -> dict`, `exposure_time(grab_s, latency_s)`, `delay_from_flashes(flash_t, frame_t, brightness)`,
  `attitude_at(t, imu_t, imu_q, max_gap_s=0.2) -> q | None`, `usable(meta, cfg) -> (bool, reason)` (no attitude within
  0.2 s, rate > 30°/s, tilt > 45° refused).
- `ros/camera_node.py` (*given* 20): OpenCV V4L2 capture (or replay of recorded frames when the camera is not booked),
  publishes `/fledgling/camera/image` (`sensor_msgs/Image`, top half, straightened with the student's calibration) and
  `/fledgling/camera/meta` (`diagnostic_msgs/DiagnosticStatus` key/values: exposure_s, attitude, usable, reason).

### 2.7 Vision and sky parts

`features.py` — **intro 21**; reuse 22–25. `gradients(gray)`, `structure_tensor(gx, gy, sigma)`, `harris(gray, k=0.04)`,
`harris_corners(gray, n, …)`, `repeatability(kp1, kp2, H, tol_px)`, `hamming(d1, d2)`, `spread(kps, shape, grid)`,
`matchability(gray) -> (score, reason)`; *given*: `detect(gray, method="orb"|"sift", n)` (OpenCV wrapper).

`match.py` — **intro 22**; reuse 23–25. `ratio_test(knn, ratio=0.8)`, `fit_similarity(src, dst) -> (s, theta_deg, tx, ty)`,
`ransac_iterations(p=0.99, w, s=2)`, `ransac_similarity(src, dst, thr_px, iters, rng) -> (fit, inlier_mask)`,
`gates(fit, inliers, predicted_scale, cfg) -> (ok, reason)` (≥ 6 inliers, scale within ±15 %, spread).
DLT/homography: optional `dlt_homography`, *given* in Going further.

`locate.py` — **intro 23**; reuse 24, 31 (σ profile), 33. `photo_gsd(alt_m, hfov_deg, w_px)`,
`search_patch(prior_lat, prior_lon, radius_m, z) -> (patch, x0, y0)`,
`locate(photo, meta, prior, cfg) -> (lat, lon, reason)` (lat/lon None when refused), `budget(terms) -> float` (RSS),
`evaluate(results, truth) -> dict` (availability, median, p90, wrong_accepted), `to_estimate(lat, lon, sigma_m, t_s) -> Estimate`
(*given*: day source, σ stated 30 m like NAVERA's conservative value, or UNKNOWN).

`vo.py` — **intro 24**; reuse 33. `phase_shift(a, b) -> (dx, dy, response)`, `px_to_en(dx, dy, m_per_px, heading_deg)`,
`integrate(steps, start) -> np.ndarray`, `drift_sigma(n, sigma_step_m, bias_m)`, `blend(x1, v1, x2, v2) -> (x, v)`,
`vo_gate(v_vo, v_ref, sigma)`; *given*: `frame_m_per_px`.

`night.py` — **intro 25**; reuse 33. `ncc(a, b) -> float`, `footprint_m(alt_m, hfov_deg)`,
`coverage(w_px, h_px, alt_m, hfov_deg, heading_deg, ref_m) -> float`, `prepare(frame, alt_m, hfov_deg, heading_deg, map_gsd)`,
`motion_gate(anchor, t_anchor, fix, t, v_max_mps=30.0, margin_m=…) -> (ok, reason)`, `ncc_locate(prepared, patch) -> (dx, dy, score)`.

`stars.py` — **intro 26**; reuse 33. `julian_date(y, mo, d, h=0, mi=0, s=0.0)`, `gmst_deg(jd)`,
`altaz(ra_deg, dec_deg, lat, lon, gst_deg) -> (alt, az)` (vectorised), `lat_from_polaris(alt_deg, ha_deg=None)`,
`both_roots(alt, az, ra, dec, gst) -> [(lat, lon), (lat, lon)]`, `choose(roots, prior) -> (lat, lon) | None`,
`error_km(att_err_deg)`; *given*: `precess(ra, dec, jd)` (Meeus low-precision, course-written), `load_bsc(path, mag_max)`,
`local_to_radec(alt, az, lat, lon, gst)` (the oracle the old lab took from NAVERA).

### 2.8 Fusion parts

`uncertainty.py` — **intro 27**; reuse 28–33.
`sample_cov(points)`, `ellipse(P, k=1.0) -> (a_m, b_m, angle_deg)`, `chi2_threshold(p, dof=2)`, `propagate(J, P)`,
`polar_to_en(r, bearing_deg, sr, sb_deg)`, `mahalanobis2(r, S)`, `gate(r, S, p=0.99) -> bool`,
`fuse(x1, P1, x2, P2) -> (x, P)`, `make_covariance(P2, sigma_up_m=None) -> (cov9, cov_type)`.

`kalman.py` — **intro 28**; reuse 33. `cv_model(dt, q, dims=2) -> (F, Q)`, `kf_predict(x, P, F, Q)`,
`kf_update(x, P, z, H, R) -> (x, P, nis)`, `nees(err, P)`, `run_filter(times, zs, sigma_z, q, gate_p=None)`,
`class Height1D(climb_accel=0.5)`: `update(t, h, sigma)` — the model lesson 28 describes as NAVERA's height filter (in
words: q from 0.5 m/s² climb acceleration, start P = diag(σ², 4)); the "race" is against the course's reference outputs.

### 2.9 The judge: `arbiter.py` (intro 29) and the ROS nodes

Mirrors NAVERA's rules as lesson 1 §5 and `navera_settings.yaml` describe them; names and code are Fledgling's.

```python
@dataclass
class Decision:
    state: str            # "STARTING" | "NO_FIX" | "FIX" | "DEGRADED"
    source: str | None    # winning source or None
    estimate: Estimate | None
    reason: str           # one sentence, e.g. "day: σ unknown → DEGRADED; gps: stale (3.4 s > 3.0 s)"
    switched: bool = False
```

- `why_not(name, est, now_s, cfg) -> str` — *given* (reason wording, so the race compares words).
- TODO 1 `candidates(latest, now_s, cfg) -> list[str]` — eligible sources (via `estimate.eligible`) in priority order.
- TODO 2 `pick(cands, current, since, now_s, cfg) -> (source, since)` — the hold-off: a higher-priority source takes
  over only after being eligible `switch_holdoff_s` while the current one is still eligible; if the current one is
  lost, switch immediately; `since` maps source → first eligible time.
- TODO 3 `decide(latest, now_s, mem, cfg) -> Decision` — STARTING before any estimate; NO_FIX with every source's
  `why_not`; else `classify` the winner.
- `class Arbiter(cfg)`: *given* skeleton; TODO 4 `receive(est, now_s)` (GPS through `JumpGate`, and in 30 through
  `CrossCheck`; drop an estimate not newer than the stored one); TODO 5 `step(now_s) -> Decision` (decide on every
  arrival and at `tick_hz`, record switches).
- Hooks for 30: `Arbiter.gps_filters: list` (JumpGate in 29; JumpGate + CrossCheck in 30). An IN_DOUBT GPS
  is classified DEGRADED.
- Rules in one table (lesson 29 §1 reproduces it): priority GPS > day > night > star; fresh = age ≤ 3/5/5/45 s;
  FIX iff stated σ ≤ 25 m, else DEGRADED; hold-off 2 s; jump gate v_max·Δt + 50 m from the last trusted fix;
  cross-check 5σ + 50 m for 3 s, streak 5 beyond 3σ, doubt from 2, return after 2; an old position is never
  re-sent as new.

ROS layer (all run with `python3 -m fledgling.ros.<node>` from the lesson folder; no build):

| Node (module) | Mission | Subscribes | Publishes | Parameters |
|---|---|---|---|---|
| `fake_gps` (`ros.gps_node`) | 10 (TODO), 13 (descriptors TODO) | — | `/fledgling/fix/gps` NavSatFix | rate_hz (read-only), speed_mps, heading_deg, start_lat, start_lon, sigma_m, vehicle |
| `trip_computer` (`ros.trip_node`) | 11 (TODO) | `/fledgling/fix/gps` | `/fledgling/trip` DiagnosticStatus | window_s, silence_s |
| `replay` (`ros.replay_node`) | 11 *given* | — | `/fledgling/fix/<src>` NavSatFix, `/fledgling/imu` Imu | file, rate, faults, loop |
| `nmea` (`ros.nmea_node`) | 15 *given* | — | `/fledgling/fix/gps` | port or file |
| `fledgling_arbiter` (`ros.arbiter_v0`) | 09 *given* | `/fledgling/fix/{gps,day,night,star}`, `/fledgling/imu` | `/fledgling/position` NavSatFix, `/fledgling/status` DiagnosticStatus | all of fledgling.yaml; `use_eligible` (12: plug the student's `eligible`) |
| `fledgling_arbiter` (`ros.arbiter_node`) | 29 *given wrapper* of the student's `Arbiter` | same | same | same |
| `camera` (`ros.camera_node`) | 20 *given* | `/fledgling/imu` | `/fledgling/camera/image`, `/fledgling/camera/meta` | device, calibration_file, replay_dir |

- **Message types:** only `sensor_msgs/NavSatFix`, `sensor_msgs/Imu`, `sensor_msgs/Image`,
  `diagnostic_msgs/DiagnosticStatus` (+ `KeyValue`). Status mapping: level OK = FIX, WARN = DEGRADED, ERROR = NO_FIX,
  STALE = STARTING; `name` = "fledgling/arbiter"; `message` = reason; `values` = state, source, sigma_m, age_s,
  and one `src.<name>` entry per source ("fresh, eligible", "stale 4.1 s", "refused: jump"). The lesson states the
  trade-off: NAVERA uses typed custom messages (described in words); Fledgling avoids a build and pays with
  string values, so the key list is a written contract (`ros/convert.py STATUS_KEYS`).
- **QoS** (`ros/qos.py`, `compatible()` is a 09 TODO): fixes RELIABLE/KEEP_LAST 10/VOLATILE; IMU sensor-data
  (BEST_EFFORT) — the 09 bug is a listener that requests RELIABLE from it; status RELIABLE + TRANSIENT_LOCAL depth 1
  ("latched", so a late `ros2 topic echo` sees the current state).
- **Rates:** arbiter decides on each arrival and at 5 Hz; position published only when a winner exists (never in NO_FIX).
- **Single judge:** the arbiter counts publishers on `/fledgling/status` at start and every 5 s and logs an ERROR
  when > 1 (the R-12 "two arbiters" story of 02, now in Fledgling). `academy_check.publishers_ok` defaults to this topic.
- **Launch** (`ros/launch_util.py`, *given* 13): `fl_node(module, name, namespace="", params_file=None, params=None,
  remaps=None) -> ExecuteProcess` builds `python3 -m fledgling.ros.<module> --ros-args -r __node:=… -r __ns:=…
  --params-file … -p k:=v -r from:=to`. `fledgling.launch.py` (13 TODO) = two vehicles' `fake_gps` in namespaces
  `/car`, `/boat` + one arbiter, with `use_boat` and `gps_source` launch arguments. The lesson shows the one-to-one
  mapping to `launch_ros.actions.Node(package=…)`, which product packages use; building `fledgling_ros` as an
  ament_python package with colcon is a Going further of 13 (justified: it teaches `share/` and
  `--symlink-install` for students who want it, and costs ~1 min; never required).

### 2.10 Messenger, simulator, measurement

`output.py` — **intro 31**. *Given* `encode_gps_input(decision, t_unix_s, seq) -> bytes` (MAVLink 2 GPS_INPUT, course
code using `struct` and a given `crc_x25`; pymavlink only as the test oracle). TODOs: `crc_x25(data, crc=0xFFFF)`,
`parse_frames(data) -> list[dict]`, `decode_gps_input(payload) -> dict`, `ignored(flags) -> list[str]`,
`gps_time_to_utc(week, ms)`. Rules (in words, from lesson 1/31): NO_FIX → fix_type 0, never an old position;
DEGRADED → 2D/accuracy fields honest; velocity sent (OUT-1 lesson).

`sim/` — **intro 31** (*given* except `sensors.py` TODOs). `world.py` is **the same file** as Sim Lite's world
(§4); `_lite/` holds the rclpy stand-in so `python3 -m fledgling.sim.run my_scenario.json` flies the student's arbiter
headless in seconds and writes `my_runs/<name>.csv` + `_events.log` with Sim Lite's columns. `sensors.py` TODOs:
`gauss_markov(n, dt=0.2, tau_s=20, q=0.6, rng)`, `stationary_sigma(q, tau_s)`, `autocorrelation(x, lag)`,
`rayleigh_quantile(sigma, p)`, `sigma_for_median(m)`.

`stats.py` — **intro 32**; reuse 33. `errors_m(rows) -> np.ndarray`, `percentile(v, q)` (linear),
`summary(errs) -> dict` (n, mean, median, p90, p95, max, rmse), `availability(rows, state_ok=("FIX","DEGRADED"))`,
`longest_gap_s(rows)`, `bootstrap_ci(x, stat, B=2000, alpha=0.05, rng=None, block=1)`, `paired_diff_ci(a, b, …)`,
`wilson(k, n, z=1.96)`, `coverage_experiment(...)`. *Given*: `pct_nearest(v, q)` — the nearest-sample rule, named in
the lesson as the rule NAVERA's evaluation tool uses (in words), to contrast.
`tools/evaluate_bag.py` (*given* 32): reads a rosbag2 of `/fledgling/fix/*` NavSatFix + truth CSV, prints
per-source error vs stated σ (replaces running NAVERA's evaluation script).

`tools/init_repo.sh` (*given* 14, 33): `git init` the lesson's `fledgling/` folder, one commit, tag `base`.

---

## 3. Per-mission replacement table (02–33)

Columns: **Old NAVERA use → Fledgling replacement · Students write (TODOs) · Given · Data · Resources · Risks.**
Brief changes to `rebuild-plan-02-30.md`: wherever a brief says "Data: `<NAVERA file>`", read the Fledgling part in
this table; hooks keep their NAVERA stories in words and numbers.

| # | Old NAVERA use → Fledgling replacement | Students write | Given | Data | Res. | Risks |
|---|---|---|---|---|---|---|
| 02 | `cd/find/grep/du ~/navera`, copy `gps_params.yaml`, `env \| grep NAVERA_`, systemd unit, preflight tests `PositionEstimate.msg`; check reads NAVERA's git tree → a **Fledgling skeleton tree** (`/data/academy/02-terminal/fledgling_tree/`: the full §1.3 layout with headers/docstrings only, `deploy/systemd/fledgling-gps.service`, `fledgling.env.example`, `config/gps.yaml`, a fake `build/ install/`); `env \| grep ^FLEDGLING_`; "two arbiters" = two `fledgling_arbiter` processes from `fake_node.sh` | `log_report.sh`; answers E1–E2, Q1–Q9 recomputed on the tree | fake_node.sh, preflight.sh (tests the map and the tree) | new tree (≈200 kB) built by `make_dataset.py`; logs stay; **3 inbox photos** (real NAVERA frames, no provenance) → replace with map crops | — | the tree must not contain solution bodies (builder emits stubs only) |
| 03 | lesson quotes `vehicle.py`, `TrackVelocity`, `EstimatorNode(Node)` → `fledgling/vehicle.py`, `track.py`; NAVERA's speed setting story (R-1) in words | wind/vehicle/track TODOs (brief) | `Multirotor`, `load_track` | unchanged | — | none (no NAVERA dependency today) |
| 04 | lesson quotes `day_localizer`, evaluation `pct()` → `fledgling/logbook.py`; nearest-rank named in words | `clean`, `add_motion`, `outage_runs`, `outage_table`, `state_shares`, `noise_by_source` | `load_log`, plots | unchanged + brief's offset clock | — | none |
| 05 | whole lab inside `~/navera` (edit `gps_node.py`, `geo.py`, `ACADEMY_README.md`; patch on NAVERA's `geo.py` + `estimator_params.yaml`; answer = NAVERA commit hash) → **Fledgling history repo** made by `datasets/05-git/make_repo.sh` into `~/lessons/05-git/fledgling-history` (~40 commits: geo.py, guard.py with mission 01's gate, fledgling.yaml, README); seeded regression in `guard.py` (elapsed reset / `>=`→`>`); `review_me.patch` against Fledgling files (`gps_jump_margin_m` 50→5000 + a radius constant change) | `first_bad()`, `bisect_test.sh`, `review.md`, commits on `my-first-change` | make_repo.sh run in Step 0 | `datasets/05-git/make_repo.sh` (new) | — | repo must be rebuilt identically (fixed dates/identities) so hashes in check are stable |
| 06 | `compare_navera.py` imports NAVERA `haversine_m`, `dead_reckon`, `_en`, `_move`; check skips → compare against **Vincenty** (`geodesic_ref.py`, course) and against the student's own spherical vs flat functions; NAVERA's 111 320 m/° shortcut and its 0.33 % error stated in words with numbers | `geo.py` TODOs (§2.3) | `is_finite_latlon`, `geodesic_ref.vincenty`, error_study | none | — | lesson must not show NAVERA's formula as code |
| 07 | `compare_navera.py` (local_matcher, prepare_area, day_localizer, MBTilesReader) → compare against `sousse_small.mbtiles` md5s and hard-coded expected tiles; the 175 m corner bug kept as a NAVERA story | `tiles.py` TODOs | `map_patch`, mosaic tools | `/data/map.mbtiles` (stays: map data) + `sousse_small.mbtiles` | — | quiz values tied to the 10 GB file: keep, or recompute on the small file if the map is withdrawn (Q1) |
| 08 | real frame `/data/navera_data/.../day/frame_0005.jpeg` (explore, demo, analysis; check depends on it) → `datasets/08-images/real_frame.jpg` **copy** (data) — or a map-made "camera-like" frame if the owner refuses | `image.py` TODOs | `similarity`, `difference` | +1 file (≈300 kB) | — | Q2 below |
| 09 | `ros2 interface show navera_msgs/...`, run `estimator_node`, echo `/navera/nav_status`, get `fix_max_sigma_m` → run **arbiter v0** (`python3 -m fledgling.ros.arbiter_v0`), `ros2 node info /fledgling_arbiter`, echo `/fledgling/status`, `ros2 param get … fix_max_sigma_m`; `ros2 interface show sensor_msgs/msg/NavSatFix`, `diagnostic_msgs/msg/DiagnosticStatus` | `qos.compatible()`, repair `imu_listener.py`, answers | arbiter_v0, convert, qos profiles | none | — | discovery lag (2 s warning stays) |
| 10 | `analysis.py`/check import NAVERA `dead_reckon` → `geo.offset` + haversine (the student's 06 work, given finished) | `velocity_ne`, `step`, `covariance_from_hdop`, `FakeGps` (rate, real dt) | geo | none | — | — |
| 11 | runs `estimator_node` + `ros_gps_node` bridge, `NavStatus` listener → `fake_gps` (10, given) feeds **arbiter v0** directly (same NavSatFix, no bridge); student's `status_listener` reads `/fledgling/status`; silence 3 s → NO_FIX "gps: stale" | `Tracker.check/update`, `speed_window`, `Watchdog.silent`, `make_executor`, `status_listener` | gps_track_player → `replay_node`, arbiter_v0 | none | — | expected silence 2.9–3.6 s now depends on v0's 5 Hz tick: measure |
| 12 | `PositionEstimate` fields, NAVERA private `_sane/_stated_sigma`, live estimator verdicts with NAVERA reason texts → `estimate.py` + `convert.py`; `my_source.py` publishes NavSatFix on `/fledgling/fix/day`; **attacker role vs arbiter v0** (zero covariance shown as FIX, non-PSD accepted…), then relaunch v0 with `-p use_eligible:=true` to plug in the student's `eligible` and see the attacks refused; check compares the student's verdicts with expected values on 13 unseen faults | `is_covariance`, `stated_sigma`, `staleness_m`, `eligible`, `apply_fault`, `mahalanobis2`/`p_inside` move to 27 per brief | Estimate, convert, arbiter_v0, classify, JumpGate | none | — | the "two stamps" idea becomes words (NavSatFix has one); keep lesson honest about it |
| 13 | includes NAVERA's launch, edits `estimator_params.yaml` (check reads it), `declare_float` → `fledgling.launch.py` with `fl_node`; edit **the student's own** `fledgling.yaml` (`fix_max_sigma_m: 2.0` → "gps: σ 3 m > 2 m → DEGRADED"); `git diff` replaced by `diff fledgling.yaml fledgling.yaml.orig` | `make_descriptor`, `check_settings`, `on_set_parameters`, `my_gps.yaml`, `fledgling.launch.py` | launch_util, arbiter_v0, gps_node | none | — | ExecuteProcess vs Node(package) must be explained once, clearly |
| 14 | NAVERA's 359-test suite, break/restore `geo.py` with git, mutants of NAVERA's `geo.py`, launch test of `estimator_node` → `tools/init_repo.sh` makes `fledgling/` a git repo; run the **Fledgling suite** (`pytest fledgling/tests`, count re-measured at build); break/restore `fledgling/geo.py`; check's mutants are string replacements in Fledgling's `geo.py`; `test_arbiter_launch.py` launches arbiter v0 and asserts a 5 km jump is refused, NaN fix gives NO_FIX | test files TODO 1–7 | geo_tools, init_repo.sh, pytest.ini | none | — | mutants must be re-validated whenever geo.py's text changes (builder runs them) |
| 15 | `gps_filter.py` copies `gps_node` decisions/reason texts; `play_to_gps_node.py` runs `gps_pkg gps_node` on a pty; `/navera/estimate/gps` → `gnss.fix_decision`, `covariance_from_hdop`; `play_to_nmea_node.py` replays into **`fledgling.ros.nmea_node`** (uses the student's parser) and writes `nmea_node_counts.json`; numbers (1066/1007/59) recomputed | `gnss.py` TODOs (§2.6) | nmea_node, `fields`, `read_log` | unchanged (synthetic) | — | rename `navera_decision` → `fix_decision`; expected counts change |
| 16 | check imports `camera_model.rpy_to_matrix/quat_to_matrix`, `orientation.quat_mul`, `sensor_history.slerp`; lab runs `imu_pkg` | `rotations.py` TODOs | oracle = `scipy.spatial.transform.Rotation` in check (x,y,z,w native) + expected values | rename dataset folder only | — | scipy present? (verify at build; else expected values) |
| 17 | `Declination` in `imu_pkg`, NAVERA's orientation tests → `imu.py`; pygeomag directly; "In NAVERA" in words (BNO085, 50 Hz) | `imu.py` TODOs | rotations (16) | `datasets/17-imu` (dedupe 16) | — | — |
| 18 | `compare_with_navera.py` (camera_model, LocalMatcher) graded "ALL MATCH" → `compare_with_opencv.py` (`cv2.projectPoints`, `cv2.warpPerspective`) + expected values | `camera.py` 18 TODOs, `measure_pad` | rotations, R_BODY_NADIR_CAM, experiments | unchanged (map renders) | — | — |
| 19 | runs `~/navera/navera_tools/calibrate_camera.py`; `compare_navera.py` uses `CameraModel` → `calibrate_lab.py` (student's `calibrate_fisheye`) with a given CLI `fledgling/tools/calibrate.py` writing `my_calib.yaml`; comparison picture with OpenCV only | `camera.py` 19 TODOs, calibrate_lab TODOs | lens_curve, detect_all | unchanged — **real bench views + `insta360_top.yaml`** (data) | — | Q2 below |
| 20 | `GstCapture`, `sensor_history.History`, `ros2 run camera_pkg live_camera.py`, `/day/*` topics → **`fledgling.ros.camera_node`** (OpenCV V4L2, replay fallback) + student's `attitude_at`/`usable`; GStreamer part becomes plain `gst-launch-1.0 videotestsrc` timing (optional) | `camera.py` 20 TODOs | camera_node, FrameSource, capture/analyse | unchanged (bench frames + synthetic) | camera (`c.skip` without) | camera_node must stay simple; booking path unchanged |
| 21 | lesson quotes `local_matcher` settings; `navmap.py` → `tiles.map_patch`; NAVERA settings (CLAHE 2.0/8×8, contrast 0.02) as numbers | `features.py` TODOs | detect, peek/scale/clahe demos | unchanged (`real_aerial_frame.jpeg` already copied) | — | — |
| 22 | lab Step 12 greps `local_matcher.py`/`vision_nav.py` → "In NAVERA" in words; brief's similarity core | `match.py` TODOs | features (21), inlier_spread, draw helpers | unchanged (Wayback tiles = map data) | — | — |
| 23 | `evaluate.py` runs NAVERA `LocalMatcher` on 719 tiles; report "mine vs NAVERA" → compare with (a) the student's own no-scale-gate variant and (b) NAVERA's published bench numbers (30/33, median 4 m, worst 5 m, dated) in words; drop `images/` (21 MB) | `locate.py` TODOs, `budget`, `evaluate` | match/features/camera/tiles | `photos/`, `truth.csv` kept; `images/` deleted | — | auditor role weaker (no product run): replace with "which gate refused p13" on their own pipeline |
| 24 | `FrameOdometry`, `VisionNavigator` imported and graded (3.57 m/100 m) → student's `vo.py` vs **reference results** `reference_steps.csv` (course reference, min_response 0.15 stated as NAVERA's value in words); `navera_nav.py` → `fuse_run.py` using `vo.blend` + `vo_gate` | `vo.py` TODOs, drift_sim | geo, camera.frame_m_per_px | unchanged + `reference_steps.csv` | — | — |
| 25 | `normalize_query`, STHN (described), `/data/navera_data/.../thermal` and `/day` frames read live → `night.py` with NCC on CPU; thermal + day frames **copied** into `datasets/25-thermal-night/` (≈15 MB) — or synthetic "thermal-like" map renders if refused | `night.py` TODOs, `find_day_twin` | `parse_thermal_name`, `min_altitude`, `fake_thermal` | **new** dataset | — | Q2; STHN story stays words only |
| 26 | `cn_pkg.celestial_math` (gast, apparent_radec via astropy, local_to_radec, observer_candidates, choose_candidate) run and graded → `stars.py` with course-written `precess` and `local_to_radec` given; expected values from the course reference | `stars.py` TODOs | load_bsc, sky_plot, precess | **new** `datasets/26-stars/bsc5.dat` (public Yale BSC, 1.7 MB) | — | GMST vs GAST: state the ≤ 1″ nutation term as ignored |
| 27 | `estimate_message()` fills `PositionEstimate`; check calls `EstimatorNode._sane/_stated_sigma` → `uncertainty.make_covariance` + `estimate.is_covariance/stated_sigma` (given from 12) | `uncertainty.py` TODOs | estimate | `datasets/27-uncertainty` | — | — |
| 28 | race against `VisionNavigator` heights (1e-6) → race against `reference_heights.csv` from `kalman.Height1D` (the model is described as NAVERA's in words) | `kalman.py` TODOs | uncertainty | `datasets/28-kalman` (dedupe) + reference CSV | — | race loses "the product" feeling; say plainly it's the same model |
| 29 | `compare_real.py` runs `estimator_node` with NAVERA params, races 11 decisions; answers read NAVERA's code → `play_scenario.py` replays the same 31 s scenario **over ROS into the student's `arbiter_node`** and records `my_run.json`; race against `reference_decisions.json` (course reference, same scenario); code-reading answers are about arbiter_v0 vs theirs | `arbiter.py` TODOs 1–5, experiment.py (holdoff/freshness metrics, fuse) | estimate, guard.JumpGate, uncertainty, arbiter_node, arbiter_v0 | `reference_decisions.json` | — | ROS run needs publisher guard; reason words fixed by `why_not` |
| 30 | `spoof_real.py` runs `estimator_node` (3 scenarios), check reads its transcripts; constants mirror its methods → `spoof_run.py` runs **the student's arbiter_node with CrossCheck**; REAL_* offsets measured on their own run (±2 m of reference); Sim Lite red/blue team on their arbiter | `guard.py` 30 TODOs, detection.py | arbiter (29 reference), scenarios.py | none | simlite (optional) | — |
| 31 | `sim_ctl.py` drives NAVERA's full simulator (run_sim.sh, ArduPilot SITL); datasets recorded on it (logs contain NAVERA output and paths); `gps_input.bin` packed by NAVERA's mavlink_out; Part E Sim Lite flies student's NAVERA → **headless Fledgling sim** (`python3 -m fledgling.sim.run`) + Sim Lite, both flying the 30 reference arbiter by default and the student's with `--mine`; campaign regenerated; `gps_input.bin` regenerated by `output.encode_gps_input`; SITL described in words | `output.py` TODOs, `sim/sensors.py` TODOs, campaign.py (R1–R7) | sim/world, `_lite`, encode, scenarios | **regenerate** whole `datasets/31-simulator` | simlite | the "one run FAILS" must be engineered in the sim (e.g. measured vision + drift) |
| 32 | runs `evaluate_session.py` on a `navera_msgs` bag; flights recorded on NAVERA's sim → `tools/evaluate_bag.py` on a **regenerated** NavSatFix bag; flights regenerated with the headless sim; Q6/Q7 recomputed; nearest-rank as words + `pct_nearest` | `stats.py` TODOs, measure.py, bootstrap.py | evaluate_bag, pct_nearest | **regenerate** flights + bag | — | numbers in the lesson move: rerun provenance |
| 33 | branch, failing test, change and patch in `~/navera` (`gps_node.fix_problem` example; 10 NAVERA project ideas) → full Fledgling stack in `~/lessons/33-final-project/fledgling` (`init_repo.sh`, branch `project/<name>` from `base`); measure with headless sim campaigns or `gnss` on `nmea_bench.txt`; example project = min-satellites rule in `gnss.fix_decision`; project menu: DR drift alarm (vo), vision-σ honesty (NEES), slow-spoof with VO, IMU dead reckoning source, HDOP-aware jump margin, frozen-GPS detector, freshness windows | project change + test, PROJECT.md | everything finished, stats (32) | unchanged (`nmea_bench.txt`) | simlite (optional) | the full stack = every solution visible; fine at the end, but see Q3 |

Missions **01, 03, 04, 21, 22** had no NAVERA runtime dependency; only their "In NAVERA" text changes to words.

**`/data/navera_data` users** (all must stop): **08** (frame_0005), **25/26** (thermal + day frames, read live).
Indirect (author scripts on the host, data already copied): 19, 20 (bench calibration views and yaml from
`~/.navera_sim/bench_2026-10-06`), 21 (frame_0010), 22/23 (Wayback tiles from the same bench folder).
No lab uses STHN weights, DINOv2 or `TORCH_HOME` at runtime: they only appear as words (25, 32 hook) and in
sandbox env vars to delete. Recordings from NAVERA's simulator/nodes: **31, 32** → regenerate.

---

## 4. Sim Lite on Fledgling

### 4.1 What changes, what stays

Stays: Pyodide in a worker, the world (vehicle kinematics, GPS noise/jam/spoof, vision profiles "measured" ≈ 440 m
median and "target" 15/25 m, IMU liveness, autopilot fed only by the arbiter's output), map tiles, flight scripts,
`my_scenario.json` → `my_runs/` for mission 31, the 1-row-per-second CSV.

Changes: the browser loads **Fledgling files from a lesson folder** instead of NAVERA files from `~/navera`; the world
talks standard messages on `/fledgling/*`; no `navera_msgs` build step.

### 4.2 Server API (`server/simlite.py`)

`GET /api/simlite/code?src=mine|v0|reference&lesson=<id>` →
`{"origin": "mine"|"v0"|"reference", "lesson": "29-arbiter", "entry": "fledgling.ros.arbiter_node:ArbiterNode",
  "files": {"fledgling/__init__.py": "…", …, "fledgling.yaml": "…"}, "missing": [...]}`

- `FLY_FILES` (allow-list, nothing else is ever read): `fledgling/{__init__,settings,geo,estimate,guard,uncertainty,arbiter}.py`,
  `fledgling/ros/{__init__,convert,qos,arbiter_node,arbiter_v0}.py`, `fledgling.yaml`. Each ≤ 400 kB (as today).
- `src=mine`: from `students/<name>/home/lessons/<L>/` where `L` = the `lesson` argument if that folder has
  `fledgling/arbiter.py`, else the newest installed of `FLYABLE = ("33-final-project", "31-simulator",
  "30-spoofing", "29-arbiter")`. If none: 404 with "Finish mission 29's arbiter to fly your own; meanwhile fly v0".
  If `arbiter.py` still has stubs, the page says which TODO and offers v0.
- `src=v0`: `server/static/simlite/py/fledgling_v0/` — the built-in naive arbiter (same file as `ros/arbiter_v0.py` +
  its imports). Everyone.
- `src=reference`: the 30 reference closure from `solutions/30-spoofing/` — **staff only** (`is_staff`); students
  never receive solution code in the browser. (Option: also students who passed 30 — owner Q3.)
- `entry`: `arbiter_v0:ArbiterV0Node` for v0, `arbiter_node:ArbiterNode` otherwise.
- Remove `_root`, `navera_allowed` and the "original NAVERA" path entirely. `scenario`, `save_flight`, `script`,
  tiles: unchanged.

### 4.3 Browser (`server/static/simlite/`)

- `worker.js`: `load` → `world.install_fledgling(_files, '/fledgling')` and remember `args.entry`; error filtering
  unchanged (it already hides `/lite/` frames and shows the student's file and line).
- `py/world.py`:
  - `install_fledgling(files, root)`: purge `sys.modules` entries starting with `fledgling`, write files, compile each
    `.py` (SyntaxError → "fledgling/arbiter.py, line 12: …"), add root to `sys.path`. No message generation.
  - `World`: publishes `NavSatFix` on `/fledgling/fix/gps` (jammed: `status.status=-1`, NaN lat/lon),
    `/fledgling/fix/day|night` (covariance type UNKNOWN for "measured", DIAGONAL_KNOWN σ for "target"), `Imu` on
    `/fledgling/imu`; subscribes `/fledgling/position` (NavSatFix; source from `header.frame_id`) and
    `/fledgling/status` (DiagnosticStatus; state from `level`/`values["state"]`, source from `values["source"]`,
    reason from `message`). SRC/STATE tables become name-based.
  - `Run`: `BUS.params["fledgling_arbiter"] = {**settings, "max_speed_mps": …}`; imports the `entry` class and
    instantiates it (its node name is `fledgling_arbiter`).
  - CSV columns: `navera_state/source/lat/lon/err_m` → `fl_state/fl_source/fl_lat/fl_lon/fl_err_m`; mission 31's
    `campaign.py` and check use the new names (31 is rebuilt anyway).
  - Flight-script API: `sim.nav` (state, source, error_m, position, reason); keep `sim.navera` as a hidden alias for one
    term so saved scripts do not break; `DEFAULT_SCRIPT` and `_OLD_DEFAULT` migration updated.
- `py/diagnostic_msgs/{__init__,msg/__init__}.py`: new shim (`DiagnosticStatus` with OK/WARN/ERROR/STALE,
  `KeyValue`) via `_rosmsg.define`; add to `manifest.json`. `sensor_msgs` already has NavSatFix/NavSatStatus/Imu.
- `py/fledgling_v0/…`: the v0 closure (copied by the builder from `solutions/_fledgling`, same bytes as courses).
- `simlite.js` / `index.html`: title "Fledgling Sim Lite" (keep "by IRIS"); source selector "My Fledgling
  (lessons/29-arbiter)" / "Arbiter v0" / "Reference (staff)"; file line `📄 fledgling/arbiter.py`; console text "Edit
  fledgling/arbiter.py in the lesson's 📝 Code tab, press ↻ reload, then ▶ Fly"; card label "Fledgling — your
  code"; tooltips quote NAVERA's measured day-vision accuracy with its date (numbers only); "NAVERA max m/s" →
  "max speed m/s".
- **The same `world.py` is shipped in mission 31 as `fledgling/sim/world.py`** with `_lite/` (copies of `rclpy/`,
  `_rosmsg.py` and message shims). `fledgling.sim.run` puts `_lite` first on `sys.path` only in that process, so the
  sandbox's real rclpy is untouched, and browser and headless runs give identical CSVs for the same seed (a builder
  test).

---

## 5. Shared changes (server/, courses/_lib, tools, docs)

**Server**
1. `sandbox.py` env: delete `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS`, `DAY_DATASET_DIR`, `NAVERA_DAY_IMAGES_DIR`,
   `NAVERA_DAY_CSV`, `TORCH_HOME` (or point it at an empty cache), `NAVERA_STATE_DIR`, `NAVERA_ARDUPILOT`,
   `NAVERA_SIM_DOMAIN` for students; rename `NAVERA_MBTILES` → `FLEDGLING_MAP`. Hostname/PS1 `navera` → `academy`.
2. `config.data_mounts`: `~/navera_data` only for staff (already gated: keep, and stop mentioning it in
   `missing_data()` for students); `/data/bsc5.dat` and `/data/ardupilot` only for staff (26 gets its own copy);
   `missing_data()` text: map only.
3. `workspaces.py`: `BASHRC` without `source ~/navera/install/setup.bash` for students (keep for staff with access);
   `ACADEMY_README`/clone/reset stay staff-only; `install_lesson` unchanged (sub-folders already copied by `copytree`).
4. `app.py`: hide "♻️ Reset my NAVERA copy" and `file:navera/…` links for students (refuse in the file API too);
   the Code tab tree never lists `~/navera` for students.
5. Sim Lite: §4 (simlite.py `code()`, `FLY_FILES`, `FLYABLE`, permissions; worker/world/shims/JS/HTML).
6. Optional (Q3): `"requires": "<previous id>"` in meta.json so a mission installs only after the previous one is
   passed, which keeps later missions' finished parts out of reach.

**courses/_lib**
7. `academy_check.py`: `sh()`/`Background()` source only `/opt/ros/humble/setup.bash`; `load_student()` accepts
   dotted names and package paths (`"fledgling.arbiter"`, `"fledgling/arbiter.py"`), puts the lesson folder first on
   `sys.path`, and reloads `fledgling.*` on `fresh=True`; `publishers_ok(topic="/fledgling/status")`; new
   `is_stub(func)` helper shared with runner_kit.
8. `runner_kit.py`: `load_student("fledgling.arbiter")` (existence check on the module path); error locations name
   `fledgling/arbiter.py line N`; version bump.
9. `CONVENTIONS.md`: "NAVERA source" column → "Fledgling part"; §5 index mapping refers to NavSatFix and
   `fledgling.estimate`; §6 nearest-rank contrast in words; the "checked against NAVERA's code" line becomes "values
   described from NAVERA's documentation; code is Fledgling's".
10. `TOOLBOX.md`: add "Python 6 — dataclasses" (12) and "Python 7 — packages and `python3 -m`" (09).

**tools/**
11. `fledgling_build.py` (§1.6) and `fledgling_lint.py` (ban list: `navera_`, `~/navera`, `/data/navera_data`,
    `/navera/`, `estimator_node`, `PositionEstimate`, `NavStatus`, `cn_pkg`, `day_pkg`, `gps_pkg`, `imu_pkg`,
    `camera_pkg`, `night_pkg`, `navera_tools`; scanned in `courses/` and `datasets/` except quoted words in
    lesson prose whitelisted as "NAVERA" alone; plus the 6-line copy check against `base/`).
12. `try_lesson.py`: confirm `--solution` copies sub-folders (`fledgling/`) and that a solution with no `_apply.sh`
    needs none (every current `_apply.sh` touching `~/navera` disappears).
13. Number-provenance script: unchanged scope (NAVERA numbers quoted in words must be in VALIDATION_STATUS/BACKLOG).

**Docs**
14. `AUTHORING.md`: remove "own copy of NAVERA", `file:navera/…`, the `/data/navera_data` rows, the `~/navera`
    colcon line and `_apply.sh` on `~/navera`; "In NAVERA" becomes words-only and is followed by "In Fledgling";
    add the Fledgling section (layout, builder, style) pointing here.
15. `rebuild-plan-02-30.md`: add a header line "Data/code references to NAVERA are superseded by
    reviews/fledgling-design.md §3"; Batch 0 gains: write `solutions/_fledgling` parts needed by Batch 1–2, the
    builder, the lint, the 02 tree and the 05 repo; Batch 3 needs arbiter_v0 + convert + replay_node first; Batch 6
    needs the arbiter reference before 29's race file; Batch 7 needs the headless sim before 31/32 datasets.

**Datasets to build or change** (all by `make_dataset.py` on the host, ≤ 50 MB each)
- New: `02-terminal/fledgling_tree/`, `05-git/make_repo.sh`, `25-thermal-night/` (copied frames or synthetic),
  `26-stars/bsc5.dat`, `24`/`28`/`29` reference CSV/JSON, `31-simulator/` (regenerated), `32-measuring/`
  (regenerated flights + NavSatFix bag).
- Change: `08-images/real_frame.jpg` (+1), `23-locate-on-map/images/` (delete), `02-terminal/inbox` photos
  (replace), dedupe `16/17` and `27/28` when those missions are split.

---

## 6. Open questions for the owner

1. **NAVERA data copies** (data, not code; each one is a yes/no). (a) Real aerial frames: `08` (1 frame), `21`
   (1, already copied), `02` inbox (3, provenance unknown — I propose to replace them by map crops anyway).
   (b) Real thermal + day frames for `25` (≈15 MB). (c) The Insta360 bench calibration views and
   `insta360_top.yaml` in `19`/`20` (IRIS's own camera recording and its calibration result). (d) Wayback 2017/2022
   tiles in `22`/`23`. If (b) is refused, 25 uses synthetic thermal-like renders and loses the "is this dataset real?"
   exercise.
2. **The satellite map** `/data/map.mbtiles` (Sousse z13–19, 10 GB) is data and stays mounted, but its imagery
   licence should be confirmed for teaching use (it also feeds 07, 08, 18, 21–24 datasets and Sim Lite).
3. **Spoilers between missions.** Mission N ships finished parts of N−1, so a student who opens mission 07 early
   can read mission 06's solution. Accept (as today, within an open leg), or add the `requires` gate (§5.6)?
   Same question for "Reference arbiter" in Sim Lite: staff only (my default) or also after passing 30?
4. **Name and branding.** "Fledgling" in code, topics (`/fledgling/*`) and the Sim Lite title — confirm. Sim Lite
   would no longer say "NAVERA SIM".
5. **ArduPilot SITL** leaves the student path (31 describes it in words). Keep `/data/ardupilot` mounted for a
   staff demo only, or drop it?

## 7. Owner decisions (2026-10-12)

1. **Name:** keep the NAVERA name. The students' stack is **NAVERA Lite**, Python package `navera_lite`
   (read every "Fledgling"/`fledgling` above as NAVERA Lite/`navera_lite`; topics `/navera_lite/*`,
   settings file `navera_lite.yaml`). Lessons: "NAVERA Lite, the stack you build" vs "NAVERA, IRIS's product".
   The lint blocks the real product's identifiers (navera_common, navera_estimator, navera_msgs, *_pkg names,
   estimator_node…) and any 6-line span copied from base/, not the word "navera".
2. **NAVERA data** (photos, frames, calibration views): yes, copies may go into datasets/. Never code.
3. **Map:** switch from the Esri Wayback satellite map to OpenStreetMap-based tiles (open licence, attribution
   "© OpenStreetMap contributors" shown wherever a tile is shown). Do not bulk-download from tile.openstreetmap.org
   (its usage policy forbids it): tiles must come from a source whose licence and usage policy allow it, or be
   rendered from OSM data. Vision missions that matched real photos to the satellite map (22, 23, Sim Lite day
   vision) use camera views rendered from the same OSM map (synthetic, with noise, blur, rotation and scale), or
   pairs of real frames (photo↔photo) where a map is not required.
4. **Mission order:** a mission opens only when the previous one is passed; the teacher can open any mission for
   a student (server change).

## 8. Interfaces as built (overrides §2 where they differ)
- **tiles.py (07):** `open_map(path=None)` → connection; `read_tile(conn, z, x, y)` raises ValueError for impossible
  addresses (z checked before 2**z); `mercator_y` is a TODO; given `map_patch(..., path=None)`, `patch_origin`,
  `decode_tile`, `stamp_attribution`; `MAP_PATH` from env `NAVERA_LITE_MAP` (not FLEDGLING_MAP). Missions 21–25 build
  on `map_patch` + `patch_origin`.
- **geo.py (06):** `offset(lat, lon, e_m, n_m)` takes east/north metres.
- **vehicle.py (03):** `Multirotor` has no own `__init__` (adds `hover_s`); `Vehicle.endurance_s(reserve)` is a method.
- **settings:** `navera_lite.yaml` key `celestial_timeout_s`.
- **gnss.py (15):** pure Python, no ROS. `to_estimate()` and `ros/nmea_node.py` are DEFERRED to the 09–14 rebuild
  (they need estimate.py from 12 and the ROS layer). `dops` returns None for rank < 4. GSV parsing is given.
- **rotations.py (16):** radians in, numpy out. TODOs rot_y, rot_z, euler_zyx_to_matrix, matrix_to_euler_zyx →
  (roll, pitch, yaw, locked), q_mul, q_conj, q_from_axis_angle, q_rotate, q_to_matrix, slerp, q_angle_deg; given
  rot_x, q_normalize, q_from_euler_zyx, heading_deg_from_q, rpy_human (pitch_up = −ROS pitch), IDENTITY_Q.

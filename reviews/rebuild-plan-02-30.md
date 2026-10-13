# NAVERA Academy: redesign briefs for missions 02–30

> **Superseded in part (2026-10-13):** every data/code reference to NAVERA here is replaced by `reviews/fledgling-design.md` §3 (per-mission NAVERA Lite table), and §7 of that file (owner decisions: NAVERA Lite / `navera_lite`, OpenStreetMap map, missions open in order) overrides both documents.

I only read files; nothing was edited. Sources: AUTHORING.md; mission 01 (lesson, lab, beacons.py, where_am_i.py, TEACHER.md); meta.json and lesson/lab outlines for 02–30; the 10 student-sim reports; base/docs (VALIDATION_STATUS, ARCHITECTURE, ENGINEERING_BACKLOG, ACCEPTANCE_FINDINGS); the server code (app.py, orgs.py, simlite.py).

## A. Structure decision

**What the server does today, and why it matters**
- `lesson_ids()` treats every course folder that has a meta.json as a mission.
- The certificate unlocks only when *every* mission is passed (`_course_facts`). The hours printed on it are the sum of the meta durations.
- Progress is stored per folder id.
- A class opens its "legs" by **module index** (`orgs.leg_open_from`, keys "0".."6").
- Current live state (`~/navera-academy/state`): `progress.json` is empty, `classes.json` is `{}`, and one certificate has already been issued. Renumbering is therefore cheap **now** and expensive later.
- There is no "optional mission" in the server. An advanced track would need a new `"optional": true` flag in meta.json that `_course_facts` and the course list respect.

**Recommendation: split only 16, 24 and 26; trim the others.**
- **Split 16, 24 and 26.** Each holds two core ideas that both need a worked example and a lab. The reports measured 16 at 7–9 h and 24 at 7 h 30.
- **Trim 06, 08, 15, 20 and 28.** Move derivations and trivia to `<details class="further">` and "Going further".
- **Lighten 11 and 12** by moving ellipses, χ² and Rayleigh into the new 27.
- **Do not create optional missions.** Under the server rules above they would still block the certificate.
- **Result:** 33 missions and the same 7 modules, so class leg keys do not change.
- **Hours:** about 33 × 4 h 30 ≈ 150 h on the certificate (today about 130 h). Confirm this with the owner.
- **Fallback if 30 missions must be kept:** trim 16, 24 and 26 instead of splitting them. Missions would then run 6–9 h. Not recommended.

**Renumber everything in one commit before authoring (Batch 0).** That commit covers:
- course folders, solutions/ and datasets/;
- the `number` field in every meta.json;
- modules.json;
- cross-references, e.g. 01's lab says "mission 27 adds that", which must become 30.

Missions 01–15 keep their numbers.

| New | Folder id | From old | Module (leg) |
|---|---|---|---|
| 01–05 | welcome, terminal, python-basics, python-data, git | same | 1 Foundations |
| 06–08 | coordinates, map-tiles, images | same | 2 Geodesy |
| 09–14 | ros-intro, publisher, subscriber, position-message, launch-params, testing | same | 3 ROS 2 |
| 15 | gps-nmea | 15 | 4 Sensors |
| 16 | rotations | 16 (part 1) | 4 |
| 17 | imu | 16 (part 2) | 4 |
| 18 | camera-model | 17 | 4 |
| 19 | calibration | 18 | 4 |
| 20 | live-camera | 19 | 4 |
| 21 | features | 20 | 5 Vision |
| 22 | matching | 21 | 5 |
| 23 | locate-on-map | 22 | 5 |
| 24 | visual-odometry | 23 | 5 |
| 25 | thermal-night | 24 (part 1) | 5 |
| 26 | stars | 24 (part 2) | 5 |
| 27 | uncertainty | 26 (part 1) | 6 Fusion |
| 28 | kalman | 26 (part 2) | 6 |
| 29 | arbiter | 25 (moved after fusion: its "selection vs fusion" section needs inverse-variance fusion first) | 6 |
| 30 | spoofing | 27 | 6 |
| 31 | simulator | 28 | 7 System |
| 32 | measuring | 29 | 7 |
| 33 | final-project | 30 | 7 |

**Course-wide fixes, done once in Batch 0 and used by every mission**

1. **Conventions sheet (one page).**
   - Frames: ENU world, FLU body, OpenCV camera.
   - Quaternions are stored as (x, y, z, w) in ROS.
   - Heading is clockwise from north; ENU yaw is counter-clockwise from east.
   - A ROS rotation about +y (left) is nose-down. NAVERA's `body_rpy_enu` *reports* pitch positive nose-up. This fixes the 16/17 pitch bug.
   - One covariance notation: a = σE², b = cov(E,N), c = σN². Today 12 and 25 swap b and c.
   - One percentile rule: `np.percentile` linear. NAVERA's `evaluate_session.pct()` is nearest-rank; teach it as a contrast in 32.
2. **Maths & Python toolbox page.** A box is reused by the missions that need it.
3. **Runner kit** copied from `where_am_i.py`: `call()` turns a crash, `None` or a stub into one plain sentence.
4. **checker helpers.** A ROS guard that counts publishers on `/navera/nav_status` and aborts if there is not exactly one. A PREDICT/EXPLAIN "written and on-topic" helper.
5. **Number-provenance script.** Every NAVERA figure quoted in a lesson must appear in VALIDATION_STATUS / BACKLOG, with its date.
6. **Ban list**, applied everywhere:
   - multiple-choice questions whose right answer is the longest option;
   - "Expected:" values printed before a run;
   - algorithms written in TODO comments;
   - answers sitting directly under the question;
   - "In NAVERA" code that uses syntax not yet taught.

## B. Mission briefs (old number → new number)

### 02 → 02 Terminal — KEEP, cut the lesson by ~40 % (command tables become a cheat sheet)
- **Hook:** two real product bugs (ENGINEERING_BACKLOG):
  - DEP-2: the GPS service lacked the `dialout` group, so the serial port gave "Permission denied".
  - R-12 / EST-10: an orphan estimator left by the simulator ran beside the real one, "two arbiters, decisions interleaved" (fixed 6bff3d6).
- **Objectives:**
  1. Diagnose and fix a permission error (`ls -l`, octal modes, groups).
  2. Find, identify and stop a process cleanly (PID/PPID, TERM then KILL).
  3. Answer log questions with pipelines.
  4. Write a bash script that passes on an unseen log.
- **Hardest idea:** a pipeline is a chain of filters on one stream; stderr is a separate stream.
  - Worked example on a *different* log: "which node wrote most WARN lines", shown stage by stage: `grep` → `cut` → `sort` → `uniq -c` → `sort -rn`.
- **Student codes:** `log_report.sh` (spec plus a hidden log). Going further: `watchdog.sh`, which restarts a crashing node and gives up after N tries (the DEP-1 mechanism).
- **Role:** detective. `fake_node.sh` starts two "arbiters"; find the orphan by start time and parent, and stop it with TERM.
- **Prereqs:** 01 (arbiter states). 🧰 serial port and baud; `sort -u`; exit codes and `set -e`; systemd in 5 lines.
- **Data:** `datasets/02-terminal/make_dataset.py`, `files/fake_node.sh`, `inbox/`. **Build:** the orphan scenario and a new worked-example log.
- **Fix:**
  - The lesson gives away lab Q6 (61 day_subscriber) and Q7 (08:45:24).
  - `sort -u` is needed but never taught.
  - The preflight check shows ✘ when the map disk is absent → use `c.skip`.
  - Explain "CET" vs UTC+1.
  - Remove `mapfile`, `-prune` and the DDS port formula from "In NAVERA".

### 03 → 03 Python for engineers — KEEP (turn radius becomes optional)
- **Hook:**
  - Mars Climate Orbiter, lost September 1999: one team's software output impulse in pound-force·s, the navigation software expected newton·s (NASA MCO Mishap Investigation Board, Phase I report, Nov 1999).
  - NAVERA LOC-11: the camera node invented speed 5 m/s, heading 0 and altitude 400 m when they were unknown. `geo.dead_reckon` now returns None instead.
- **Objectives:**
  1. Write functions with explicit units that raise on impossible input.
  2. Derive and code the wind triangle by projection.
  3. Build `Vehicle` → `Drone`/`Boat` classes with `super()`.
  4. Vectorise a track with NumPy (diff, hypot, masks).
- **Hardest idea:** wind components are dot products with the track's unit vectors.
  - Worked example: track 090°, wind 5 m/s blowing towards 225° → w = (−3.54, −3.54) m/s.
  - Along-track −3.54, cross-track +3.54 (to the right).
  - True airspeed 12 m/s → crab 17.1° to the left, heading 072.9°, ground speed 11.47 − 3.54 = 7.93 m/s.
  - The lab uses track 030°, so the example cannot be copied.
- **Student codes:**
  - `wind_components(track_deg, wind_e, wind_n) -> (along, cross)`
  - `heading_for_track(track_deg, tas, wind_e, wind_n) -> (heading_deg, gs)`, raising ValueError when the crosswind exceeds the airspeed
  - `endurance_s(wh, w, reserve=0.2)`
  - `Vehicle` / `Drone` classes
  - `Track.speeds()`, `Track.glitches(max_mps)`
- **Runner:** go/no-go mission planner, plus the harbour track with its glitch at index 149/150.
- **Roles:** engineer (go/no-go) and detective (the glitch). Going further: a "unit saboteur" module (one function in knots) to expose with tests.
- **Prereqs:** 01 (unit vectors). 🧰 radians; 2-D dot product.
- **Data:** `datasets/03-python-basics/make_track.py`; `navera_common/track.py` (TrackVelocity), ≤ 15 lines.
- **Fix:**
  - Replace the NAVERA list-comprehension example (`*_en(p[:2])`).
  - TODO 3 currently gives the algorithm.
  - Grade the inheritance question (`WHERE_ENDURANCE_FROM`).
  - Add `UnboundLocalError` to the error table.

### 04 → 04 Data analysis — KEEP (haversine, error propagation and 2-D broadcasting move to 06; give `haversine_m`)
- **Hook:**
  - VALIDATION_STATUS: "The replay frames in camera_pkg/data/day do not show the places their CSV labels say. Earlier accuracy figures computed on them are not valid."
  - RTC-2: a real-time clock kept in local time gives a 1 h error.
- **Objectives:**
  1. Clean a campaign with stated rules and count what each rule removed.
  2. Summarise each flight with `groupby`.
  3. Detect outages by run-length.
  4. Choose mean/σ or median/MAD and justify the choice.
- **Hardest idea:** robust statistics.
  - Worked example: errors [2,3,3,4,4,5,5,6,250] m → mean 31.3, σ 77.3, median 4, MAD 1 (×1.4826 ≈ 1.5).
  - One glitch multiplies the mean by 8; the median does not move.
- **Student codes:**
  - `clean(df) -> (df, removed: dict)`
  - `add_speeds(df)`
  - `outages(df, min_gap_s) -> [(t0, t1)]`
  - `noise_by_source(df)`
- **Runner:** figures plus `results.json`.
- **Role:** data detective. One flight's clock is 1 h off and one column is mislabelled; find both *before* computing any statistic.
- **Prereqs:** 02, 03. 🧰 variance vs σ; the percentile rule; boolean masks.
- **Data:** `datasets/04-python-data/make_dataset.py`. **Build:** add the offset clock and the mislabelled column.
- **Fix:**
  - φ/λ, σ, crosstab and reindex are used before they are taught.
  - The Step 8 median vs σ gap (0.77 vs 1.1) is unexplained.
  - Predictions must be graded only as "written".
  - Silence the Axes3D warning.
  - London–Paris 343 556 vs 343 479.8 is unexplained → move to 06.

### 05 → 05 Git — KEEP (workflow first; objects, DAG and SHA move to optional)
- **Hook:** NAVERA EST-9: "refused GPS re-accepted once reachable by time alone: a patient spoofer gets in, then the true GPS is locked out". It is a regression that only history and tests catch. Keep the existing frame: a colleague's change "to stop false refusals".
- **Objectives:**
  1. Make small, well-described commits on a branch.
  2. Review a patch hunk by hunk and justify each verdict.
  3. Find a regression with `git bisect run`.
  4. Recover lost work (restore, reflog).
- **Hardest idea:** bisect is binary search.
  - Worked: a 16-commit toy needs 4 tests (8, 4, 2, 1).
  - The lab history has about 40 commits, so ⌈log₂ 40⌉ = 6 tests.
- **Student codes:**
  - `first_bad(commits, is_bad)`, a Python binary search checked on unseen lists
  - `bisect_test.sh` (exit codes from 02)
  - `review.md` with a verdict per hunk
- **Roles:** reviewer vs saboteur (the patch hides a `>=`→`>` or an elapsed-reset change in the gate, subtler than "5000"); detective (bisect).
- **Prereqs:** 01 (gate), 02 (scripts, exit codes).
- **Data — must build:** the student's `~/navera` has **one squashed commit** (b0e06dc), so real hashes are not there. Build `datasets/05-git/make_repo.sh`, a teaching repo of about 40 commits with a seeded regression, and update `review_me.patch`.
- **Fix:**
  - Remote/tag "base" is ambiguous → rename the remote "academy".
  - Two- and three-dot diffs give the same output → make the difference visible or drop it.
  - Step 9 gives the review verdict away.

### 06 → 06 Coordinates — KEEP, refocus
NAVERA's `geo.py` is spherical (R = 6 371 000 m). Exact WGS84/ECEF move to optional, which replaces the "6b" split the report suggested.
- **Hook:** two NAVERA bugs:
  - R-6: route length computed with a flat approximation, 1 750 instead of 1 768 km.
  - R-2: the map corridor followed the straight lat/lon line, "~17 km" from the great-circle path flown Paris→Tunisia (871 of 20 675 tiles on the real path).
- **Objectives:**
  1. Convert lat/lon differences to east/north metres and state the error.
  2. Compute haversine distance and initial bearing.
  3. Compute a great-circle path and its offset from the straight lat/lon line.
  4. Tell ellipsoidal height from sea-level height (GPS-4).
- **Hardest idea:** where you take cos φ matters.
  - Worked: London→Paris haversine 343 556 m.
  - Flat-Earth with cos(start latitude): 341 088 m (−2.5 km). With cos(mean latitude): 343 603 m (+47 m).
- **Student codes:**
  - `enu_flat(lat0, lon0, lat, lon) -> (e, n)`
  - `haversine_m`
  - `bearing_deg`
  - `great_circle_points(p1, p2, n)`
  - `max_offset_km(p1, p2)`
  - the error-study loop, written by the student after a prediction
- **Role:** auditor. Re-compute R-2. My computation for Paris (48.857, 2.352) → Tunis (36.807, 10.182) gives about 31 km, not 17 km; the doc's figure used other endpoints or legs. The student must reconcile the two, and the lesson must not quote 17 km unless it is reproduced.
- **Prereqs:** 03, 04. 🧰 radians; vectors in 10 minutes (dot, cross).
- **Data:** `geo_lab.py`, `compare_navera.py`; `navera_common/geo.py`.
- **Fix:**
  - Symbol clashes e/E, N, R.
  - Two flat formulas (R = 6 371 000 vs 111 320 m/°) are unexplained → keep one.
  - Formulas are written in starter comments.
  - Geoid/NMEA moves to 15.

### 07 → 07 Map tiles — KEEP
- **Hook:** NAVERA LOC-1: day vision published the tile's NW corner as the position, a 175 m bias (fixed e725928). The student proves that 175 m is half the diagonal of a z17 tile at Sousse: 256 × 0.969 m / √2 = 175.3 m.
- **Objectives:**
  1. Compute tile x/y and the pixel offset from lat/lon, and back.
  2. Compute m/px at any latitude and choose a zoom.
  3. Read a tile with parameterised SQL and handle TMS rows.
  4. Convert a mosaic pixel to lat/lon.
- **Hardest idea:** the y formula and the TMS flip.
  - Worked: m/px at z17 is 1.194 in Quito, 0.969 in Sousse and 0.521 in Reykjavik.
- **Student codes:**
  - `tile_xy(lat, lon, z)` (fractional)
  - `tile_to_latlon(x, y, z)`
  - `m_per_px(lat, z)`
  - `best_zoom(gsd_m, lat)`
  - `read_tile(db, z, x, y)`
  - `pixel_to_latlon(...)`
- **Runner:** mosaic.png with a corner-vs-centre overlay.
- **Roles:** bug hunter (reproduce LOC-1 and measure 175 m); attacker (an SQL injection against a string-formatted query, to show why `?` placeholders exist).
- **Prereqs:** 06. 🧰 SQL in 10 minutes; log₂; sinh/atan.
- **Data:** `datasets/07-map-tiles/sousse_small.mbtiles`; `web_common.MBTilesReader`; `local_matcher.tile_xy`.
- **Fix:**
  - 7 of 10 TODOs give the formula.
  - Add a 3-line derivation of y.
  - EPSG:3395 and the Gudermannian move to optional.
  - The radius r in (2r+1)² is undefined.
  - GSD is circular between 07 and 08 → 07 owns map GSD, 18 owns camera GSD.

### 08 → 08 Images — KEEP, trim (Canny, HSV and CLAHE detail move to 21 or optional)
- **Hook:** NAVERA LOC-24: thermal mono16 converted to bgr8 without scaling. LOC-7: the night inputs were double-normalised.
  - Worked: uint16 7 500 cast to uint8 gives 76 (7 500 mod 256); clipped it gives 255; min-max scaling is the right fix.
- **Objectives:**
  1. Predict and avoid dtype wrap and overflow.
  2. Convolve by hand and in code (Gaussian, Sobel) and explain the kernel flip.
  3. Build a 2×3 affine for rotation about the centre plus scale.
  4. Bring a drone photo to the map's heading and GSD.
- **Hardest idea:** the affine matrix about the image centre.
  - Worked: 1-D [1,2,1]/4 on [0,0,4,0,0] gives [0,1,2,1,0]; then the matrix for 30°, s = 0.5, centre (100, 50).
- **Student codes:**
  - `to_float01`, `to_uint8`
  - `convolve2d(img, k)`
  - `affine_matrix(angle_deg, scale, centre)`
  - `warp_affine(img, M, size)` (bilinear)
  - `like_map(photo, heading_deg, gsd_photo, gsd_map)`
- **Runner:** NCC heading sweep, 25–45°.
- **Role:** engineer. Maximise NCC (defined once in the lesson) against `map_patch.png`.
- **Prereqs:** 04, 07. 🧰 matrix × vector; a 2×2 `np.mgrid` warm-up.
- **Data:** `datasets/08-images/*`; the night frame preparation (≤ 15 lines).
- **Fix:**
  - Sobel is /4 here but /8 in 20 → choose one.
  - Add a drawing for the heading sign.
  - Remove the ±35° TIP giveaway and the matrix written in TODO 9.

### 09 → 09 ROS graph — KEEP, add real code
- **Hook:**
  - I-F3: an integrator's IMU published BEST_EFFORT; NAVERA asked for RELIABLE → 4/4 frames had "no attitude" (3/3 usable after the fix).
  - WEB-12: DDS was open to the network and simulators could hijack the estimator; the fix was ROS_LOCALHOST_ONLY.
- **Objectives:**
  1. Map a live graph with the `ros2` CLI.
  2. Predict from QoS whether a publisher/subscriber pair connects.
  3. Repair a QoS mismatch in code.
  4. Explain domains and localhost isolation.
- **Hardest idea:** QoS is "offered vs requested".
  - Worked table: BEST_EFFORT publisher + RELIABLE subscriber → no connection; RELIABLE + BEST_EFFORT → yes. Latched = TRANSIENT_LOCAL + RELIABLE.
- **Student codes:** `compatible(pub_qos, sub_qos) -> bool`, checked on unseen combinations. Repair `imu_listener.py`, replacing the Fibonacci and add_two_ints demos.
- **Role:** detective. "Topic present, node present, no data": diagnose with `ros2 topic info -v`. Predict before each QoS experiment.
- **Prereqs:** 02. 🧰 IP, port, UDP and 127.0.0.1 in 5 lines.
- **Data:** demo nodes; `navera_common/qos.py`.
- **Fix:**
  - SPDP/SEDP and the port formula move to optional.
  - Define QoS before asymmetric discovery.
  - Make "latched needs RELIABLE" prominent.
  - Add a "wait 2 s" discovery-lag warning.
  - Staff note: high domain numbers give a port error.

### 10 → 10 Publisher — KEEP (flat Earth removed: taught in 06)
- **Hook:**
  - EST-1 / OUT-3: the same fix was re-published at 5 Hz with fresh stamps, and ArduPilot saw "stopped, then jumped".
  - GPS-5: HDOP invented when it was missing.
  - `estimator_params.yaml` records the GPS rate as measured: 1.000 Hz, std 0.148 s.
- **Objectives:**
  1. Write an rclpy node class with parameters, a timer and a publisher.
  2. Integrate motion with the real dt.
  3. Fill NavSatFix honestly: floats, m², UNKNOWN when unknown, σ = 2·HDOP as in `gps_node`.
  4. Measure rate and jitter.
- **Hardest idea:** integrate with the real dt.
  - Worked: real dt [0.50, 0.62, 0.41, 0.55] s at 10 m/s gives 20.8 m, not the 20.0 m that a nominal 0.5 s assumes.
- **Student codes:**
  - `velocity_ne(speed, hdg)`, e.g. (10, 90) → (0, 10)
  - `step(lat, lon, vn, ve, dt)`
  - `covariance_from_hdop(hdop)` (HDOP 1.2 → 5.76 m²; None → UNKNOWN)
  - the `FakeGps` node
- **Runner/check:** the runner injects a random 0–0.2 s sleep; the check verifies true-dt integration.
- **Role:** saboteur. Publish a stale fix with a fresh stamp (sets up 12).
- **Prereqs:** 03, 06, 09. 🧰 inheriting from Node; float vs int.
- **Data:** `navera_tools/sensor_sim.py`; `gps_node.py`.
- **Fix:**
  - TODO comments are the code.
  - Jitter is invisible and unchecked (a hard-coded dt = 0.5 passes).
  - `publisher_node.svg` is orphaned.
  - E[·] is used untaught.
  - The sin-for-east / cos-for-north choice is unexplained.
  - Say "Depth UNKNOWN is normal".

### 11 → 11 Subscriber — KEEP, trim (Rayleigh moves to 27; the executor core is one blocking-callback demo)
- **Hook:**
  - EST-13: the estimator decided only on its 5 Hz tick, adding up to 200 ms and skipping measurements.
  - OUT-5: the output polled at 5 Hz while positions also arrived at 5 Hz, so messages were dropped or doubled. ArduPilot then reported "GPS not healthy" and refused to arm (SITL).
- **Objectives:**
  1. Write a stateful subscriber that refuses bad fixes and says why.
  2. Predict the noise of a speed derived from positions and reduce it with a window.
  3. Detect silence with a timer.
  4. Explain on-arrival vs polling.
- **Hardest idea:** the noise of a derived speed.
  - Worked: σ 3 m per fix → speed over 1 s has σ ≈ 4.2 m/s; over 10 s, 0.42 m/s.
- **Student codes:**
  - `TripComputer.update(fix) -> (ok, reason)` (this fixes TODO 3b's dead end)
  - `speed_window(fixes, window_s)`
  - `Watchdog.silent(now)`
  - a pure-Python polling simulation that counts drops and doubles
- **Role:** engineer. Reproduce OUT-5 in pure Python, then watch NAVERA's arbiter detect a GPS that has been switched off.
- **Prereqs:** 10, 04. 🧰 what a thread is (kitchen analogy).
- **Data:** `gps_track_player.py`, `status_listener.py`; `estimator_node.py`.
- **Fix:**
  - Define "thread".
  - Remove the Step 3 "Expected" table.
  - Explain the covariance_type 2→1 change.
  - Explain the 17 vs 13 fixes oddity.

### 12 → 12 Position contract — KEEP, lighten (eigen, ellipse probabilities and χ² move to 27)
- **Hook:** ACCEPTANCE_FINDINGS 2026-10-03:
  - Q-F1/F3/F4: an all-zero covariance was shown as FIX with accuracy 0; an undefined covariance type was treated as bounded; a non-PSD covariance was republished.
  - O-F2: vision fixes 1–2.5 s old, plane at 40 m/s → output error 83 m median, 0 % within the stated σ.
- **Objectives:**
  1. Fill a PositionEstimate correctly.
  2. Test whether a 2×2 matrix is a covariance (a ≥ 0, c ≥ 0, ac − b² ≥ 0).
  3. Distinguish `sensor_stamp` from `header.stamp` and compute the staleness error.
  4. Predict the arbiter's verdict.
- **Hardest idea:** what makes nine numbers a covariance.
  - Worked: [[25, 30], [30, 16]] → 400 − 900 < 0 → impossible (correlation 1.5) → not used.
- **Student codes:**
  - `is_covariance(cov9) -> (ok, reason)`
  - `stated_sigma(cov9, type)` (the ≥ 1 cm rule)
  - `staleness_m(speed, age)`
  - `verdict(est, now)` for 12 injected faults
- **Check:** compares the predicted verdicts with the live arbiter automatically.
- **Role:** attacker. Craft estimates that fool a naive arbiter, then test NAVERA's.
- **Prereqs:** 10, 11. 🧰 correlation ρ; symmetry.
- **Data:** `PositionEstimate.msg`; the eligibility code in `estimator_node.py`.
- **Fix:**
  - Use the single covariance notation.
  - Remove the multiple-choice question (right answer always the longest).
  - Define hold-off.
  - Drop σ_max/√2.

### 13 → 13 Launch & parameters — KEEP (cut GroupAction, PushRosNamespace, TimerAction and `~` private names)
- **Hook:**
  - R-1: the box had no vehicle-speed setting. The estimator used 100 m/s and the vision gates 30 m/s whatever the vehicle, so a fixed-wing's real GPS would be refused and every vision fix rejected. Now one setting, NAVERA_MAX_SPEED_KMH, feeds all three.
  - LOC-30: the integer override `conf_threshold:=1` crashed a float parameter.
- **Objectives:**
  1. Declare typed parameters with descriptors and a validation callback.
  2. Predict and measure precedence.
  3. Write one launch file (namespaces, remaps) for two vehicles plus NAVERA.
  4. Change a NAVERA setting and observe the verdict change.
- **Hardest idea:** precedence.
  - Worked: default 30.0 < YAML 15.0 < launch 20.0 < CLI 25.0 → 25.0. Then `param set 40` is refused by the validator.
- **Student codes:** a descriptor plus a callback (min_speed < max_speed); `my_gps.yaml`; `my_navera.launch.py`, after a complete annotated 15-line example.
- **Role:** configuration attacker. Find a value that passes the descriptor but breaks behaviour (int vs float, km/h vs m/s).
- **Prereqs:** 10, 11. 🧰 package, colcon, share, `--symlink-install` (promised in 02 but never taught).
- **Data:** `estimator_params.yaml`; the `simulation_web/launch` files.
- **Fix:**
  - Expected values (3.0, 1.0) are printed in bold before the run.
  - The quiz answers the lab.
  - TODO 3 keys should be start_lat/start_lon.
  - Warn about the cold-daemon timeout on `ros2 param describe`.

### 14 → 14 Testing — KEEP
- **Hook:**
  - Ariane 5 flight 501, 4 June 1996: reused Ariane 4 code converted a 64-bit float to a 16-bit integer, which overflowed. It had never been tested with Ariane 5 trajectory data (Inquiry Board report, J.-L. Lions, July 1996).
  - NAVERA: `is_finite_latlon` refuses (0, 0), "Null Island".
- **Objectives:**
  1. Write parametrised example tests that pin a bug.
  2. Write property tests and read their counterexamples.
  3. Measure test quality with mutants.
  4. Run NAVERA's suite and a launch test of the real arbiter.
- **Hardest idea:** properties vs examples.
  - Worked: haversine properties (symmetric, ≥ 0, d(a,a) = 0, ≤ πR). The mutant `cos(p1)²` survives 5 example tests and is killed by symmetry.
- **Student codes:** `test_geo_tools.py`, `test_properties.py`, `test_estimator_launch.py` (a 5 km jump must be refused).
- **Role:** mutant hunter. The check runs hidden mutants; pairs play saboteur rounds.
- **Prereqs:** 03, 06, 13. 🧰 decorators; `yield` fixtures.
- **Data:** `geo_tools.py`; `run_tests.sh`; `geo.py`.
- **Fix:**
  - The hypothesis counterexample is latitude > 90 (lat0 = 89.55, north = 49 751), but the text explains longitude > 180 → explain both and let the check accept the student's own.
  - The hint uses rel = 1e-6, which fails correct code (55 596.93 vs 55 597.46) → use 1e-3 and say why.
  - Add a pytest.ini to filter warnings.
  - The checker uses the ambiguous ref `refs/tags/base`.
  - "359 unit tests" must be re-measured at build time: grep finds 262 test functions, and the parametrised count differs. State the date.
  - `run_tests.sh` takes 53 s, not "~1 min 20".

### 15 → 15 GNSS & NMEA — KEEP, trim (UERE, DRMS and CEP statistics move to 32; GSV kept light)
- **Hook:**
  - GPS-1: the checksum was not verified.
  - GPS-2: GGA quality 6 (the receiver's own dead reckoning) was accepted as a fix.
  - GPS-4: MSL altitude was used instead of ellipsoidal.
  - The real line from the project report, `$GNRMC,141621.00,A,3544.04006,N,01034.55091,E`, decodes to 35.73400 N, 10.57585 E (M'saken).
- **Objectives:**
  1. Parse GGA/RMC/GSA with the checksum and refuse what must be refused.
  2. Convert ddmm.mmmm to degrees.
  3. Compute DOP from (GᵀG)⁻¹ and explain what it means.
  4. Turn HDOP into NAVERA's σ (2·HDOP) and say FIX or DEGRADED (HDOP > 12.5 → DEGRADED).
- **Hardest idea:** DOP.
  - Worked with mission 01's beacons, receiver at (3, 4), rows [uₓ, u_y, 1]: HDOP 1.22. Adding beacon D (10, 10) gives 1.02.
- **Student codes:**
  - `checksum_ok`
  - `parse_gga -> dict | None`
  - `dm_to_deg("3544.04006", "N")`
  - `dops(unit_vectors)`, with a specified behaviour on singular geometry
  - `sigma_from_hdop`
- **Role:** attacker. Craft lines that pass a naive parser: the bit flip 3547→3574 is 50 km, and swapped characters keep the XOR. Replay them into the real `gps_node`.
- **Prereqs:** 01 (H), 02 (serial). 🧰 XOR and hex; bytes vs str; `np.linalg.inv`.
- **Data:** `datasets/15-gps-nmea/*`; `gps_node.py`; `play_to_gps_node.py`.
- **Fix:**
  - `dops()` raises LinAlgError on singular geometry, and the solution crashes too.
  - The demo says "47", the course uses 32.
  - drive.png is all yellow.
  - "How conservative is NAVERA" is untaught.
  - Predictions must come before `dop.py`.

### 16 (part 1) → 16 Rotations & quaternions — SPLIT
- **Hook:**
  - Apollo 11's three-gimbal IMU could gimbal-lock. Michael Collins asked for "a fourth gimbal for Christmas" (NASA Apollo 11 Flight Journal — verify the wording before release).
  - NAVERA stores quaternions as (x, y, z, w) (`camera_model.quat_to_matrix`).
- **Objectives:**
  1. Compose and invert rotations in the right order.
  2. Convert ZYX Euler angles ↔ matrix and show gimbal lock.
  3. Use quaternion product, conjugate, vector rotation and slerp.
  4. Read NAVERA's frame conventions.
- **Hardest idea:** a quaternion is a half-angle rotation about an axis.
  - Bridge from e^{iα} in 2-D.
  - Worked: a 90° yaw is q = (0, 0, 0.7071, 0.7071), which turns (1, 0, 0) into (0, 1, 0).
- **Student codes:** `rot_x`/`rot_y`/`rot_z`, `euler_zyx_to_matrix`, `matrix_to_euler_zyx` (flags lock), `q_mul`, `q_conj`, `q_rotate`, `slerp`.
- **Runner:** draws an aircraft attitude.
- **Role:** detective. A colleague read ROS data as (w, x, y, z); find its four symptoms and check against `body_rpy_enu`.
- **Prereqs:** 03. 🧰 matrix × matrix; complex numbers in 5 lines.
- **Data:** `camera_model.py`, `sensor_history.slerp`.
- **Fix:**
  - **Pitch-sign bug** between old 16 and 17 → conventions sheet.
  - Heading `atan2(my, mx)` clockwise-from-north vs counter-clockwise-from-east.
  - Delete SO(3) and spherical harmonics.

### 16 (part 2) → 17 IMU & attitude estimation — SPLIT
- **Hook:**
  - IMU-3: heading was magnetic, not true; now corrected with WMM declination (still to confirm on the BNO085).
  - IMU-1: the library cached the last report, so stale data was published forever.
  - VALIDATION: celestial error is about 111 km per degree of attitude; a BNO085-class IMU (0.3°/1.5°) gives 24–119 km.
- **Objectives:**
  1. Integrate a gyro and predict drift from its bias.
  2. Get tilt from gravity and say when it fails.
  3. Fuse with a complementary filter and choose τ.
  4. Convert magnetic heading to true heading.
- **Hardest idea:** the complementary filter as a time constant.
  - Worked: a 0.01°/s bias gives 6° after 10 min; τ = 1 s, dt = 0.02 s → α = 0.980.
- **Student codes:**
  - `integrate_gyro(q0, rates, dt)`
  - `tilt_from_accel(ax, ay, az)`
  - `complementary(...)`
  - `true_heading(mag, decl)`
  - a stale-sensor detector (IMU-1)
- **Runner:** simulated flight near Monastir.
- **Role:** engineer. Tune τ over a coordinated turn, where the accelerometer is fooled.
- **Prereqs:** 16, 04. 🧰 small angles; rates.
- **Data:** `datasets/16-imu/imu_log.csv` (rename to 17-imu); `imu_pkg/orientation.py`, `imu_node.py`.
- **Fix:**
  - "Best τ 30 s" and "9.0° drift" are printed in brackets (spoilers).
  - Explain why the accelerometer reads +9.81 upward.
  - Show plots after TODO 8/9.
  - TODO 7 slerp is printed in "In NAVERA".
  - Real time 7–9 h vs 4 h claimed.

### 17 → 18 Camera model — KEEP (general-plane [R|t], oblique GSD and scale-gate statistics move to optional)
- **Hook:**
  - `camera_model.py` docstring: "150 m altitude, 10 deg pitch: 26 m apart".
  - VALIDATION: straightened 33/33 within 2.6 m; without straightening, median 28 m and 1 wrong.
  - Altitude +40 %: 0/33 before the altitude window, 27/33 after.
- **Objectives:**
  1. Project with K and back-project a pixel onto the ground.
  2. Compute footprint and GSD.
  3. Quantify height error → scale error and tilt → position error.
  4. Straighten a view with K R K⁻¹. Teach it here: report 22 found it taught nowhere.
- **Hardest idea:** homogeneous projection.
  - Worked: (30, −45, 150) m, f = 800, centre (640, 360) → pixel (800, 120).
- **Student codes:**
  - `K_from_hfov`
  - `project`
  - `backproject_ground(K, R, h, u, v)`
  - `footprint`
  - `gsd(h, hfov, w)`
  - `nadir_homography(K, R)`
- **Roles:** measurer (size of a landing pad in photos); attacker (what tilt pushes the photo centre outside σ 30 m).
- **Prereqs:** 16, 07. 🧰 homogeneous coordinates; matrix inverse.
- **Data:** `datasets/17-camera-model/*`; `camera_model.py`; `bench/camera_chain.py`.
- **Fix:**
  - R_body→camera is undefined → add an axes figure.
  - Add a prediction before Step 4.
  - Replace the report table with 3–4 explain questions.

### 18 → 19 Calibration — KEEP (Zhang derivation moves to optional; keep the intuition and figure)
- **Hook:** the live camera refuses a calibration made at another resolution, or with another USB camera (ARCHITECTURE §5). The Insta360 top lens sees about 166°, but NAVERA keeps only the central 111°.
- **Objectives:**
  1. Implement the equidistant fisheye model.
  2. Measure reprojection error and say where it is valid.
  3. Calibrate, then test on held-out views.
  4. Justify 111° with numbers.
- **Hardest idea:** pinhole vs fisheye radius.
  - Worked: tan 55.5° = 1.46 but tan 83° = 8.14, so the edge of a 166° view would be stretched 5.6× more.
- **Student codes:**
  - `fisheye_project(K, D, X)`
  - `reprojection_rms`
  - `calibrate(views)` (OpenCV)
  - `holdout_error`
  - `stretch_at(theta)`
- **Roles:** trade-off engineer (choose the output FOV); detective (why views f0023 and f0208 fail).
- **Prereqs:** 18. 🧰 RMS; the idea of a Taylor series.
- **Data:** `datasets/18-calibration/*`; `calibrate_camera.py`.
- **Fix:**
  - The lab contradicts the lesson: fx 670.3 vs 660.5 ± 2; 110.2° vs 111°; Brown–Conrady ≈ fisheye on hold-out (0.570 vs 0.567) → add a graded "3 reasons" step.
  - Use a strongly distorted view for before_after.
  - Real time 6–7 h vs 4 h claimed.

### 19 → 20 Live camera — KEEP (V4L2 and GStreamer jargon move to optional)
- **Hook:**
  - O-F2 (VALIDATION 2026-10-03): vision fixes 1–2.5 s old while stating ±30 m → 83 m median output error at 40 m/s.
  - CN-2: the celestial attitude was read at processing time, degrees off in flight.
- **Objectives:**
  1. Describe frame timing (rate, jitter, median vs minimum delay).
  2. Measure delay from flash frames.
  3. Turn delay × rotation rate into ground error.
  4. Interpolate the attitude at the exposure and refuse frames (no attitude within 0.2 s, rate > 30°/s).
- **Hardest idea:** a time error becomes metres.
  - Worked: 25°/s × 0.14 s = 3.5° → 150 m × tan 3.5° = 9.2 m.
- **Student codes:**
  - `frame_stats(stamps)`
  - `delay_from_flashes(...)`
  - `attitude_at(t, history)` (slerp given from 16)
  - `usable(meta) -> (bool, reason)`
- **Role:** engineer. Choose the latency setting from the data, and explain why NAVERA uses the median (0.138 s).
- **Prereqs:** 16, 18, 19, 04. 🧰 ddof; bisect; log scale.
- **Data:** `datasets/19-live-camera/*`; `live_camera.py`; `resources: ["camera"]`, with `c.skip` when the camera is absent.
- **Fix:**
  - Algorithms sit in the docstrings.
  - The median vs minimum contradiction.
  - `watch_live.py` says step 6, the demo is step 8.
  - Remind students of the half angle (yaw 20° → Ω = 10°).
  - Delete the falcon.

### 20 → 21 Features — KEEP, trim (SIFT internals, BRIEF and the pyramid move to optional)
- **Hook:**
  - NASA/JPL on Ingenuity's final flight 72 (18 Jan 2024): its navigation tracked surface features and lost them over featureless sand ripples; the landing damaged the rotor (JPL news release, Dec 2024 — verify the wording).
  - NAVERA: day vision is unreliable over uniform terrain (Gabès desert, the sea).
- **Objectives:**
  1. Compute gradients and the structure tensor.
  2. Classify flat, edge or corner from its eigenvalues (Harris).
  3. Measure repeatability.
  4. Predict and test how matchable a terrain is.
- **Hardest idea:** the structure tensor.
  - Worked: Sxx = Syy = 200, Sxy = 0 → λ = 200, 200 → a corner, R = 40 000 − 0.04·400² = 33 600.
  - Sxx = 200, Syy = 2 → an edge.
- **Student codes:**
  - `gradients`
  - `structure_tensor(gx, gy, sigma)`
  - `harris(img, k)`
  - `repeatability(kp1, kp2, H, tol)`
  - `hamming(d1, d2)`
  - `matchability(img)`
- **Role:** scout. Rank city, olives, hills and sea before measuring, then confront the surprise (olives 1.00 > city 0.94).
- **Prereqs:** 08 (same Sobel normalisation). 🧰 eigenvalues of a 2×2; `np.unpackbits`.
- **Data:** `datasets/20-features/*`; `local_matcher.py`.
- **Fix:**
  - σ² and r/√2 are asserted without reason.
  - Harris crosses on the dense medina cannot be judged → use a synthetic house.
  - The results table spoils the prediction.
  - "~16 min" reading is really 60–90 min.

### 21 → 22 Matching — KEEP, refocus
Similarity fit becomes the core, because NAVERA uses `estimateAffinePartial2D`. DLT, homography and SVD move to optional.
- **Hook:** VALIDATION day-vision table. A prototype with no scale check and ≥ 12 inliers accepted 10/33 frames, worst 1 097 m, 1 wrong. Adding the scale check: 21/33, worst 5 m, 0 wrong.
- **Objectives:**
  1. Apply and explain the ratio test.
  2. Fit a similarity by least squares.
  3. Compute the RANSAC iteration count and implement RANSAC.
  4. Apply the gates (≥ 6 inliers, scale within ±15 %).
- **Hardest idea:** the RANSAC sample count.
  - Worked: w = 0.3, s = 2, p = 0.99 → 49 iterations; a 4-point homography would need 567.
- **Student codes:**
  - `ratio_test(d, 0.8)`
  - `fit_similarity(src, dst)`
  - `ransac_similarity(src, dst, thr, iters, rng)`
  - `gates(fit, predicted_scale)`
- **Roles:** attacker (the other-date and sea pairs); defender (show the scale gate refusing — today no gate is ever seen refusing).
- **Prereqs:** 01 (lstsq), 21. 🧰 2×2 rotation.
- **Data:** `datasets/21-matching/*`; `local_matcher.py`.
- **Fix:**
  - TODOs 1, 2, 3b, 6 and 9 dictate the code.
  - Do degenerate samples count as iterations?
  - `experiments.py` takes 6 s, not 30 s.
  - Use one p course-wide (today 0.99 here and 0.999 in 22).

### 22 → 23 Locate on the map — KEEP
- **Hook:**
  - LocalMatcher: 30/33 frames, median 4 m, worst 5 m, 0 wrong, 0.11 s (bench; aerial frames, not NAVERA's camera).
  - Gabès long route with retrieval: median 351 m, p90 853 m, autopilot LAND after 45 s.
- **Objectives:**
  1. Run the full chain from photo to lat/lon.
  2. Build an RSS error budget.
  3. Evaluate with four numbers (availability, median, p90, wrong accepted) against a baseline.
- **Hardest idea:** the error budget.
  - Worked: tilt 1° at 250 m → 4.4 m; lag 0.14 s × 20 m/s → 2.8 m; map 3 m. RSS ≈ 6.0 m, against a plain sum of 10.2 m.
- **Student codes:**
  - `photo_gsd`
  - `search_patch(prior, radius_m)`
  - `locate(photo, patch, meta) -> (lat, lon, reason)`
  - `budget(terms)`
  - `evaluate(results, truth)`
- **Role:** auditor. Run NAVERA's LocalMatcher on the same 13 photos; explain (graded) which gate refused p13.
- **Prereqs:** 07, 18, 22. 🧰 RSS; clamp.
- **Data:** `datasets/22-locate-on-map/*`; `bench/day_wrong_altitude.py`.
- **Fix:**
  - The p01 worked example (384.3, 424.9) is not reproducible.
  - Bangkok 10.9 vs 10.8.
  - "Wrong height costs availability, not accuracy" becomes core content with a figure.
  - Add a picture for clockwise θ.
  - Predict before `budget.py`.

### 23 → 24 Visual odometry — KEEP (the DFT primer becomes core; fusion reduced to a 1-D variance blend; the full Kalman filter moves to 28)
- **Hook:**
  - VALIDATION (simulator only): dead reckoning carried 90 s over a bay stating ±300 m, true error ≤ 146 m.
  - `frame_odometry.py`: VO cannot work over open water.
  - The Mars Exploration Rovers used visual odometry where their wheels slipped (Maimone, Cheng & Matthies, J. Field Robotics, 2007).
- **Objectives:**
  1. Measure a shift by phase correlation.
  2. Convert pixels to east/north metres.
  3. Model drift as random walk plus bias.
  4. Bound the drift with map fixes.
- **Hardest idea:** the Fourier shift theorem.
  - Worked in 1-D numpy: a shift of 2 gives a peak at 2; a shift of 2.5 gives a split peak.
- **Student codes:**
  - `phase_shift(a, b) -> (dx, dy, response)`
  - `px_to_en(dx, dy, gsd, hdg)`
  - `integrate`
  - `drift_sigma(n, σ, bias)`
  - `blend(x1, v1, x2, v2)`
- **Role:** navigator over 80 frames. Choose the response threshold, then compare with FrameOdometry (min_response 0.15).
- **Prereqs:** 17, 18, 04. 🧰 e^{iωt}; FFT; variances add.
- **Data:** `datasets/23-visual-odometry/*`; `frame_odometry.py`, `vision_nav.py`, `track.py`.
- **Fix:**
  - The R (std) vs P (variance) trap.
  - "σ grows linearly" contradicts "variances add".
  - 2σ is about 86 % in 2-D, not 95 %.
  - Step 6 spoils 114.25 m and 2°.
  - Monte Carlo and N(0, σ) are undefined.

### 24 (part 1) → 25 Night vision (thermal) — SPLIT
- **Hook:** LOC-6: until 2026-09-28 the STHN model ran with **random weights**, because the checkpoint keys never matched (`strict=False`). It now refuses to start if the weights do not load. Night vision is still not validated on real thermal images.
- **Objectives:**
  1. Explain what a thermal camera sees and why SIFT fails across modalities.
  2. Compute NCC and show its limits.
  3. Prepare a frame (scale, north-up, coverage ≥ 85 %).
  4. Apply the motion gate and state the honest limits.
- **Hardest idea:** coverage of a rotated footprint.
  - Worked: an 84° camera at 400 m sees about 720 m; a frame rotated 45° covers a smaller fraction of the reference. The student reproduces the docs' ~350 m minimum altitude.
- **Student codes:**
  - `ncc`
  - `footprint_m`
  - `coverage(frame, heading, ref)`
  - `prepare(frame, h, hfov, heading)`
  - `motion_gate(prev, new, dt, vmax=30)`
- **Roles:** defender (a wrong match with consistency 0.93 — the doc's 320 m shift with 238 m error — which check catches it?); saboteur (load the weights with `strict=False`).
- **Prereqs:** 08, 18, 22. 🧰 mean/std normalisation.
- **Data:** `/data/navera_data/.../thermal/`; `night_subscriber.py`. **Build:** `datasets/25-thermal-night` (grey map renders).
- **Fix:**
  - NCC is taught nowhere.
  - The "no sun shadows" clue becomes core.
  - Stop the program printing "[8]".

### 24 (part 2) → 26 Stars — SPLIT
- **Hook:** CN-1 / LOC-10:
  - The latitude formula took a single asin root; a southern sky gave errors of 100–1000s of km.
  - The plate-solver fit was anchored at an image edge: about 1° off, i.e. 111 km.
  - The first real sky photo solved 1.7′ from Siril.
- **Objectives:**
  1. Convert time to GMST and hour angle.
  2. Compute altitude/azimuth from RA, Dec, latitude, longitude and time.
  3. Get latitude from Polaris and resolve the two roots with a prior.
  4. Budget position error from attitude error.
- **Hardest idea:** angles on the sky become distance.
  - Worked: 1′ = 1 852 m, so 1° = 111.1 km; a 0.5° tilt error gives about 55 km (53 km measured).
- **Student codes:**
  - `julian_date`
  - `gmst_deg`
  - `altaz(ra, dec, lat, lon, t)`
  - `lat_from_polaris`
  - `both_roots` + choose with the prior
  - `error_km(att_err)`
- **Roles:** navigator (latitude from a solved star photo plus attitude); attacker (what attitude bias stays inside ±55 km).
- **Prereqs:** 16, 17, 06. 🧰 a sky-basics page (celestial sphere figure, 15°/h, 23 h 56 min); spherical trigonometry in 3 formulas; ′ and ″.
- **Data:** `/data/bsc5.dat`, `etoiles.jpeg`; `cn_pkg/nodes/celestial_math.py`.
- **Fix:**
  - TODOs 1–3 dictate Meeus, GMST and alt-az → present the constants as an honest "recipe".
  - Median vs RMS (55 km RMS vs 47.4 km median).
  - The Polaris RA question gets no feedback.
  - sky.png is unused.

### 26 (part 1) → 27 Uncertainty: covariance, gating, fusion — SPLIT
- **Hook:**
  - QA-2 / OUT-6: a ±55 km celestial fix was forwarded as ±300 m, and the autopilot's position jumped 125 km.
  - R-10: vision forwarded at ±300 m while its measured median was 442 m → EKF failsafe. An honest σ is a safety property.
- **Objectives:**
  1. Draw an error ellipse (eigen-decomposition).
  2. Propagate a covariance with J P Jᵀ.
  3. Gate with Mahalanobis d² and χ².
  4. Fuse two estimates by inverse variance.
- **Hardest idea:** χ² learned by simulation.
  - Worked: square and add two N(0, 1) variables, 10 000 times: 95 % fall below 5.99. The 1σ ellipse holds only 39 %.
- **Student codes:**
  - `ellipse(cov)`
  - `propagate(J, P)`
  - `mahalanobis2(r, S)`
  - `gate(r, S, p)`
  - `fuse(x1, P1, x2, P2)`
- **Roles:** judge (a fix 150 m off after a 40 s jam: plausible?); attacker (the smallest offset that passes your gate).
- **Prereqs:** 12, 04. 🧰 λ = (a+c)/2 ± √(((a−c)/2)² + b²); transpose.
- **Data:** `datasets/26-uncertainty/*` (rename).
- **Fix:**
  - Show the d² = 8.17 arithmetic.
  - Show the eigenvector angle θ.
  - Generalise λ = 9 ± √(81 − 47).
  - Rayleigh moves here (from 11 and 30).

### 26 (part 2) → 28 Kalman filter — SPLIT
- **Hook:**
  - The Kalman filter's first practical use was Apollo navigation (McGee & Schmidt, NASA TM-86847, 1985).
  - NAVERA's own 1-D height filter: a race where the student must produce identical outputs.
- **Objectives:**
  1. Predict and update in 1-D by hand and in code.
  2. Give Q and R meaning with numbers.
  3. Write a 2-D constant-velocity filter with a gate.
  4. Test honesty with NEES.
- **Hardest idea:** the gain.
  - Worked: P = 100, R = 25 → K = 0.8, P⁺ = 20; after 1 s with q = 1, P⁻ = 21.
- **Student codes:**
  - `kf_predict(x, P, F, Q)`
  - `kf_update(x, P, z, H, R) -> (x, P, nis)`
  - `nees(err, P)`
  - `q_sweep`
- **Role:** tuner, plus the "same filter" race against NAVERA.
- **Prereqs:** 27. 🧰 2×2 inverse.
- **Data:** `heights.csv`, `track.csv`; `race_navera.py`.
- **Fix:**
  - K = P Hᵀ S⁻¹ is unmotivated → derive it from 1-D.
  - The NEES band [1.80, 2.21] appears from nowhere → get it by simulation.
  - The q-sweep answer sits under its question.
  - track.png uses an 8 km scale; nees.png uses a log axis.
  - **check.py skips tests 7 and 12 when NAVERA is not importable yet still says 14/15** → make them fail with a "source" hint.

### 25 → 29 Arbiter — KEEP, moved after 27/28
- **Hook:**
  - O-F8: with a 3 s window under load, NAVERA flickered between FIX and NO_FIX on 20–60 % of samples, and the autopilot landed during a 6.7–9.2 s gap.
  - EST-3: GPS/vision zig-zag before the hold-off existed.
- **Objectives:**
  1. Code eligibility and priority.
  2. Implement hysteresis and measure its cost.
  3. Map the winner to FIX/DEGRADED/NO_FIX.
  4. Argue selection vs fusion with numbers from 27.
- **Hardest idea:** what hysteresis costs.
  - Worked (from the current lab dataset; re-measure): a 2 s hold-off cut switches from 27.1 to 12.7 per minute but threw away 200.8 s of 600 s of good GPS.
- **Student codes:** `eligible(est, now, cfg) -> (bool, reason)`; `decide(estimates, now, state)`.
- **Roles:** race the real `estimator_node` (same decisions, or explain why not); designer (hold-off and freshness for a plane vs a boat).
- **Prereqs:** 12, 27, 11. 🧰 a state table instead of "Mealy" jargon.
- **Data:** `arbiter.py`, `compare_real.py`; `estimator_params.yaml`.
- **Fix:**
  - k and y_k are undefined; the eigen formula is unused.
  - The 1/3 availability factor needs a timeline figure.
  - exp(−h/μ) is underived; EKF is undefined.
  - Add a `source ~/navera/install/setup.bash` line.
  - Use the single covariance notation.

### 27 → 30 Spoofing — KEEP
- **Hook:**
  - June 2013: UT Austin's Radionavigation Lab (Humphreys) spoofed the yacht *White Rose of Drachs* off course in the Mediterranean, with no alarm on the bridge.
  - NAVERA EST-9 and EST-11 ("jam, then spoof") were found in the simulator.
  - Limitation 7: without an independent source, a patient spoofer is not caught.
- **Objectives:**
  1. Treat detection as a hypothesis test (P_FA, P_D).
  2. Implement the kinematic gate and the cross-check with persistence.
  3. Compute the detection delay for a drift.
  4. Measure a ROC by Monte Carlo and choose an operating point.
- **Hardest idea:** persistence vs correlated errors.
  - Worked: P_FA 0.05 with 3 independent tests in a row → 1.25 × 10⁻⁴. Correlation ρ = 0.9 breaks this (lab: 0.004 → 0.28).
- **Student codes:**
  - `gate_ok`
  - `crosscheck(gps, vis, σ, k)`
  - `persistent(flags, n)`
  - `patient_accept_time`
  - `roc`
- **Role:** red team vs blue team, on Sim Lite (the estimator runs in the browser) and on the real estimator.
- **Prereqs:** 01, 27, 29. 🧰 conditional probability.
- **Data:** `spoof.py`, `detection.py`, `scenarios.py`, `spoof_real.py`.
- **Fix:**
  - **Bug in TODO 7:** the docstring says a == 0 → return −c/b, but the check calls `(2000, 30, 30, 0)` expecting inf → ZeroDivisionError.
  - `spoof_real.py` must count publishers and abort if ≠ 1.
  - The 33 s quote vs the 74.8 s example.
  - Add a TRUSTED → IN DOUBT → REFUSED flowchart.
  - ROC name clash.

### 28 → 31 Simulator — KEEP, trim (a struct/bits primer box; CRC_EXTRA derivation optional; Sim Lite Part E optional)
- **Hook:**
  - Integration defects found only in SITL: OUT-1 (no velocity → EKF failsafe at take-off), OUT-2 (fixes sent as 2D → ignored), OUT-5 (drops/doubles → "GPS not healthy").
  - The GPS week rollover of 6 April 2019 (10-bit week number) broke older receivers; GPS_INPUT carries `time_week`.
- **Objectives:**
  1. Decode GPS_INPUT with `struct` and check its CRC with a given function.
  2. Simulate Gauss–Markov noise and verify its statistics.
  3. Derive expected values from NAVERA's rules and give PASS/FAIL.
  4. State what a simulation proves and what it does not.
- **Hardest idea:** an expected value from a rule.
  - Worked: drift 4 m/s, σ 30 m, rule 5σ + 50 m held for 3 s → refused near 212 m (doc: ~160–200 m; discuss the gap).
- **Student codes:**
  - `decode_gps_input(frame)`
  - `gauss_markov(n, σ, τ, dt, rng)`
  - `verdict(run, expect) -> (PASS/FAIL, why)`
- **Role:** test engineer. One campaign run FAILS; diagnose it.
- **Prereqs:** 15, 29, 30. 🧰 bytes; little-endian; GPS week.
- **Data:** `datasets/28-simulator/*` (rename); `mavlink_out.py`; Sim Lite.
- **Fix:**
  - The data shows "FIX — DAY VISION" while "today only GPS reaches FIX" → label it as the simulated target σ 15 m.
  - Gate 100 m/s with Δt 1 s (01) vs 30 m/s with Δt 0.2 s → explain the per-vehicle NAVERA_MAX_SPEED_KMH.
  - Observation (b): drift 72.8 m vs the doc's 160–200 m is unexplained.
  - All 22 runs PASS → add a FAIL.
  - Remove the longest-answer multiple-choice question.

### 29 → 32 Measuring — KEEP
- **Hook:** VALIDATION: DINOv2 retrieval median 442 m, against the baselines "repeat the previous position" 480 m and "random tile" 536 m. "32/33 within 9 m" needs an interval.
- **Objectives:**
  1. Compute CEP50/95 and RMSE with a stated percentile rule.
  2. Report availability and continuity.
  3. Beat a baseline.
  4. Give bootstrap (iid and block) and Wilson intervals and explain coverage.
- **Hardest idea:** what a confidence interval means.
  - Worked: Wilson for 32/33 → [84.7 %, 99.5 %]; the naive ±1.96 SE gives [91.1 %, 102.8 %], which is impossible.
- **Student codes:**
  - `errors_m`
  - `summary(errs)`
  - `availability`
  - `bootstrap_ci(x, stat, B, rng, block=None)`
  - `wilson(k, n)`
  - `coverage_experiment`
- **Role:** buyer's auditor. Turn the five questions about the trade-fair "4 m" claim into code checks.
- **Prereqs:** 04, 06, 27. 🧰 resampling; s vs σ; 1.96.
- **Data:** `datasets/29-measuring/*`; `evaluate_session.py` (`pct` is nearest-rank: contrast it).
- **Fix:**
  - The percentile rule differs across 22/28/29/30 (fixed in Batch 0).
  - The `flight_selective` block CI [−308, −5] → print "n/a".
  - The report asks for an iid CI but `measure.py` computes block.
  - The multiple-choice answers are all the longest option.

### 30 → 33 Final project — KEEP, refocus on GPS-denied navigation
- **Hook:** NAVERA's open backlog:
  - EST-8 / QA-8: a slow spoof is undetected without vision of stated accuracy.
  - FEAT-2: IMU dead reckoning is not implemented.
  - R-9: never tested above ~400 m.
  - O-F9: vision σ 30 m is not yet measured.
- **Objectives:**
  1. Write a pre-registered proposal with a decision rule.
  2. Write a failing test first.
  3. Measure before/after paired, with block bootstrap.
  4. Decide accept / reject / inconclusive and deliver branch, patch and report.
- **Hardest idea:** pre-registration.
  - Worked rule: "accept if p90 drops ≥ 10 %, the CI excludes 0, and availability loss ≤ 0.10 (a fraction, not points)".
- **Student codes:** their change in `~/navera` plus a test. `stats_tools` is **given** (from 32).
- **Guided example:** replace the satellite-count filter with a dead-reckoning drift alarm or a vision-σ honesty check (NEES).
- **Challenge:** teams on the same idea compare results.
- **Prereqs:** 05, 14, 32.
- **Data:** `datasets/30-final-project`; `track.py`; `evaluate_session.py`.
- **Fix:**
  - `measure_project.py` hides the ImportError behind "fix_problem missing" → print the real exception.
  - Remove the "garden of forking paths" idiom.
  - Define scalar Cov.
  - Explain `git apply --check -R`.
  - Add an end-to-end NAVERA recap.
  - Course-wide: say "dead-reckoned along the measured track", never inertial; vision in 31–33 is truth + noise — say so.

## C. Build plan

Each batch can be built in parallel. Interfaces are fixed by Batch 0 and by the function signatures above.

- **Batch 0 (one person, serial):**
  - renumbering, modules.json and meta;
  - conventions sheet and toolbox page;
  - runner kit and checker helpers (ROS publisher guard, PREDICT/EXPLAIN);
  - number-provenance script;
  - one canonical `navmap.py` to copy into 22–25;
  - `datasets/05-git/make_repo.sh`.
- **Batch 1:** 02, 03, 04, 05, 06. No ROS. **Then pilot 02 and 06 with simulated B2/B1 students and adjust the template before going on.**
- **Batch 2:** 07, 08, 15, 16, 18. Non-ROS. 16 and 18 depend only on the conventions sheet; 15 replays into `gps_node`.
- **Batch 3 (ROS sandbox):** 09, 10, 11, 12, 13. `try_lesson` gives each lesson its own ROS domain, so they can be tested in parallel.
- **Batch 4:** 14, 17, 19, 20, 21. 20 needs the camera booking path plus `c.skip`.
- **Batch 5:** 22, 23, 24, 25, 26. Each keeps its own copy of `navmap.py`; 25 needs a new dataset.
- **Batch 6:** 27, 28, 29, 30. 28 and 30 use 27's API; 29 uses 27's `fuse`.
- **Batch 7:** 31, 32, 33. Freeze 32's `stats_tools` API (`bootstrap_ci`, `wilson`) before starting 33.
- **After each batch:** `try_lesson` (starter fails cleanly, solution passes, every lab command run with `--shell`); simulated B2/B1 students; expert review of every number and analogy.

## D. Risks

1. **ROS missions (09–14, 20, 29–31).** They only work in the sandbox.
   - Discovery lag; cold-daemon timeouts.
   - Leftover nodes on the student's domain (seen in 27) → publisher-count guard.
   - rclpy float typing.
   - `base/install/setup.bash` is broken from a plain host shell.
2. **Shared resources.** The camera (20) and the full simulator (31) must teach and pass without them; prefer Sim Lite, which runs in the browser.
3. **Jetson load (8 GB, one vision pipeline at a time).**
   - 25 STHN and 22/23 SIFT run while several sandboxes share the GPU.
   - Prefer CPU or pre-computed outputs, and keep `check_timeout_s` well under budget.
4. **Maths-heavy missions (16, 17, 18, 22, 26, 27, 28, 30).** These are the ones at risk with B1 readers.
   - Each needs a 🧰 box and one numeric worked example checked by a second reviewer.
   - Teach χ² and CIs by simulation first.
   - Expect them to drift over budget.
5. **Product drift.** NAVERA is Release 0.2 and its figures are dated 2026-10-03. Quote with dates and run the provenance check at release.
6. **Git history.** The student's NAVERA copy has one squashed commit, so no real hashes can be used in labs.
7. **Renumbering.** Do it now, while progress is empty and no class exists.
   - Datasets and solutions folders, `/data/academy/<id>` paths and cross-references all move.
   - The existing certificate stays valid (it is a signed record).
   - Class legs are unaffected (7 modules kept).
8. **Time inflation.** About 150 h total, and the reports found today's times about 2× optimistic. State honest durations and get the owner's sign-off.
9. **Anti-copy and grading.** Checks can only grade values and "written" answers; reasoning needs the TEACHER.md rubrics. Tell students. Use unseen numbers in every check.
10. **Public incidents.** Verify the Apollo 11 gimbal quote and the Ingenuity flight-72 wording before release.
11. **Paris→Tunisia offset.** My computation for Paris→Tunis gives ≈ 31 km, not the backlog's 17 km. Do not quote 17 km unless it is reproduced.
12. **Data access.** `/data` is root-only on the host, so authors need the `datasets/` copies. Real frames' `flight_log.csv` positions are wrong and must never be used as ground truth.

### Critical files for implementation
- /home/shadow-team/navera-academy-v2/AUTHORING.md
- /home/shadow-team/navera-academy-v2/courses/01-welcome/files/where_am_i.py (runner template) and /home/shadow-team/navera-academy-v2/solutions/01-welcome/TEACHER.md (teacher-notes template)
- /home/shadow-team/navera-academy-v2/courses/modules.json and /home/shadow-team/navera-academy-v2/server/app.py (`lesson_ids`, `_course_facts`, `lesson_leg`)
- /home/shadow-team/navera-academy/base/docs/VALIDATION_STATUS.md and /home/shadow-team/navera-academy/base/docs/ENGINEERING_BACKLOG.md (the only allowed source of product numbers)
- /home/shadow-team/navera-academy-v2/courses/_lib/academy_check.py

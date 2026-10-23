# day_pkg — day visual localization

`day_subscriber` estimates the position by matching the camera frame against the satellite
map around the prior position, with **local feature matching** (`local_matcher.py`): the frame
is scaled to the map's resolution (frame altitude + `camera_hfov_deg`), its SIFT features are
matched to those of the map tiles in the search circle (GPU nearest neighbours), and a rotation
+ scale + translation is fitted with RANSAC. A match is accepted only with ≥ `local_min_inliers`
inliers **and** the fitted scale within `local_scale_tol` of the one the altitude predicts.

> Benchmark: 32/33 labelled frames within 9 m (median 4 m), no wrong position accepted,
> 0.11–0.16 s/frame — aerial frames from another source, **not yet NAVERA's camera**. The
> former method, DINOv2 tile retrieval (`day_localizer.py`, median 442 m), is the fallback
> when the frame scale is unknown. See [docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md).

## Behaviour
- While live GPS is valid, no inference: the last GPS fix is the prior.
- While GPS is valid, the map features around the position are computed in the background
  (and, after each match, ahead along the track), so frames never wait for new tiles.
- Without GPS, the search is limited to a 400–600 m circle around the prior (last GPS fix or
  last accepted match). Local matching widens it by `max_speed_mps` × the time since its last
  match, up to `local_max_radius_m`, instead of dropping the prior; retrieval needs a score
  ≥ `conf_threshold`. After a gap the circle (3 σ of the carried position) can be far wider than
  one window can match (a 600 m window: 0–11 matches where 150 m windows gave 90–170 inliers):
  it is covered with small windows, nearest the carried position first, up to
  `reacquire_max_radius_m` (re-acquisition, F32). Visual odometry that disagrees with the track's
  velocity is used when two clear consecutive steps agree (the vehicle turned round or stopped).
- Local matches are published with a stated accuracy of `local_sigma_m` (30 m, conservative
  until measured with the real camera); retrieval positions with an unknown one.
- No match: dead-reckoning from measured heading/speed only, for at most `max_dead_reckon_s`
  and while its stated accuracy stays under `dead_reckon_max_sigma_m`; otherwise an explicit
  "no position". The stated accuracy grows with the time *since the last measured fix* —
  velocity error × t + 5° heading error × distance + ½ × `dead_reckon_accel_mps2` × t² (unseen
  acceleration; quadratic, so after ~40 s it passes 500 m and the position is withdrawn) —
  not step by step (that sum was linear and 5× too small after 100 s, simulator 2026-10-15).
  Visual-odometry steps grow it by max(10 %, the frame height's own relative uncertainty) of
  the distance, and are used only when the previous frame's position was published. With retrieval, after `max_consecutive_rejects` the
  prior is dropped.
- Gyro heading carry (`gyro_heading`, day_pkg/gyro_heading.py): for frames without a heading in
  their meta (no attitude at the exposure), the heading vision measures on a good fix (the
  matcher's fitted rotation, ≥ `gyro_heading_min_inliers`; also on the GPS-check matches) is
  carried on by integrating the gyro's rate about the vertical (`gyro_imu_topic`, empty = the IMU
  of `NAVERA_SENSOR_SOURCE`). The carry then follows the path that heading draws, from the
  instant the track's velocity was fitted at (on a turn the fit is a chord, tens of degrees
  behind), instead of straight on. Its 1 σ grows from `gyro_heading_reset_sigma_deg` with
  `gyro_heading_bias_dps` × t and the rate noise; past `gyro_heading_max_sigma_deg` (or across a
  gap in the gyro samples) there is no heading and the carry goes straight on as before. A vision
  heading more than 3 σ from a valid carried one is not taken. A frame meta heading (IMU
  attitude) always has priority. Replay of the screen bench's real recorded frames through this
  node (`navera_tools/bench/replay_gyro_heading.py`, 900 m circuit, GPS denied from 30 s, gyro
  simulated: route rate + 0.05 deg/s bias + noise; vision heading = route + the real fitted-rotation
  error), output error median / p90 / max (m), off → on: heavy rain 60 m/s 6.5/61/210 → 5.1/14/54
  (dead-reckoned max 210 → 23; the 54 m is a wrong fix both have), clouds 60 m/s 27.5/92/340 →
  27.5/54/75 (5 → 0 outputs beyond 3 σ), heavy rain 20 m/s 4.5/11/20 → 4.1/7.8/15; clear, flare,
  vibration, wind unchanged within ±2 m. Wrong fixes (> 50 m): identical frames in both arms in all
  9 conditions (0 new). Gyro bias 0.5 deg/s: same results. Not yet measured on a real gyro in flight.
- GPS course reset (`gyro_course_reset`, `gyro_heading.CourseReset`): while the GPS is trusted, on
  each arbiter GPS position above `gyro_course_min_speed_mps` on a steady course (the gyro turned
  < 3° over the 2 s chord), the gyro heading is reset to the course + the camera's offset from it
  (learned from ≥ 3 vision headings measured while the course was known, else `-mount_yaw_deg`
  from the frame meta: a downward camera on a vehicle flying nose first, σ
  `gyro_course_crab_sigma_deg`), never over a fresher more certain heading. Frames without
  attitude then give the matcher the gyro-carried heading (tolerance max(`local_heading_tol_deg`,
  3 σ)): the learned matcher needs a heading. Results: `docs/VALIDATION_STATUS.md` ("Day: a real
  flight replayed").
- Map zoom (`day_pkg/map_levels.py`): read from the area (`area.json` `zoom`, `zooms`; an area
  without it is zoom 17). With several zooms (`prepare_area.py --extra-zoom 18`) each frame is
  matched against the finest zoom at least `map_zoom_min_ratio` times coarser than the frame's
  ground resolution, else the coarsest; the finer matcher shares the networks.
- Whole-map search (no prior) is disabled by default (`allow_global_search`): its score does
  not separate good from bad matches.
- Visual odometry while GPS is trusted (`gps_vo_enabled`, default true): at most once per
  `gps_vo_period_s` (1 s) the frame is phase-correlated with the previous one given
  (`frame_odometry.FrameOdometry`, frames reduced to `gps_vo_width_px` 1280 px at most, ~0.14 s
  of CPU per 1200 × 900 frame on the Orin), with the frame's heading (attitude, else the gyro
  carry) and its height smoothed over `gps_vo_height_tau_s` (60 s), and the step is published on
  `gps_vo_topic` (`/navera/vision/odometry`, std_msgs/String JSON: `t0`, `t1` frame instants s,
  `east_m`, `north_m`, `quality`). No GPS enters the step (no prediction). The estimator compares
  it with the GPS displacement over the same instants (`navera_common.gps_motion_check`: slow
  spoofing).

## Topics
In: `/day/image_raw`, `/day/frame_meta`, `/navera/estimate/gps`, `/day/camera/start`.
Out: `/navera/estimate/day` (the contract), `/day/position_estimate`, `/day/day_status`,
`/day/frame_done`, `/day/localizer_ready`, `/navera/vision/odometry` (while GPS is trusted).

`/day/day_status` (JSON) also carries the search, for display: `search_center` (the last retained
position), `search_radius_m`, `n_candidates` (tiles inside the circle), `top5` (lat, lon, score,
tile) and `threshold`; while GPS is good, `source: gps_active` with the `anchor`.

## Data
`DAY_DATASET_DIR` → `dataset.csv` (tile file names; coordinates are derived from the XYZ tile
name, centre of the tile) + `images/`. The descriptor cache `descriptors_cache.npz` is built
on first start (~3 min for 1120 tiles). DINOv2 weights come from `TORCH_HOME`.

### Preparing a mission area — `prepare_area.py`

Vision can only localise over tiles that were prepared. Before flying a new area:

    ros2 run day_pkg prepare_area.py --mbtiles map.mbtiles --out /data/areas/mission1 \
        --route 35.8256,10.6385 35.8560,10.6010 [--buffer-m 1000]
    ros2 run day_pkg prepare_area.py --mbtiles map.mbtiles --route ... --check   # coverage only

It extracts the z17 tiles of a corridor of `--buffer-m` around the route from the MBTiles map,
computes their DINOv2 descriptors (batched on the GPU) and writes a complete dataset directory
(`images/`, `dataset.csv`, `descriptors_cache.npz`, `area.json` with the tiles the map lacks);
point `DAY_DATASET_DIR` at it. Built in `<out>.partial` and moved into place only when complete.
With `--fetch-url <XYZ template> --cache <file.mbtiles>`, tiles the onboard map lacks are
downloaded into the cache (8 parallel requests), and the base map's corridor tiles are copied
there too, so the cache alone covers the corridor (mission areas anywhere; measured: 195 tiles
in Paris downloaded and prepared in 22 s). Storing online imagery offline in a product needs
the imagery provider's licence.
`--extra-zoom 18` stores the corridor's z18 tiles too (`area.json` `zooms`; low flights, see
"Map zoom" above). `--dem copernicus` stores the corridor's terrain in `terrain/` (Copernicus DEM
GLO-30, else GLO-90; free licence, attribution in `area.json` `dem`): live_camera's height above
ground over relief (`navera_common/terrain.py`).
Measured on the Jetson: 249 tiles (4.8 km route, ±1 km) in 16 s; descriptors identical to the
per-tile cache build (cosine ≥ 0.9996). Progress is printed as JSON lines.

## Run
`ros2 launch simulation_web day_pipeline.launch.py` (camera + localizer) or `day_sim.launch.py`
(+ web bridge).

## Local matching parameters
| Parameter | Default | Meaning |
|---|---|---|
| `matcher` | `local` | `local` or `retrieval` (former method) |
| `camera_hfov_deg` | NaN (`NAVERA_DAY_HFOV_DEG`) | day camera horizontal field of view; unknown = retrieval |
| `pose_tilt_guard_deg` | 4 | with `camera_hfov_deg` the position is the point under the camera from the matched pose; used only when the pose's tilt agrees with the frame's attitude tilt (0 once straightened) within this, else the frame centre (status `pose_guard`); ≤ 0 = off. UAV-VisLoc, 8 real flights: fixes > 100 m 70 → 2 (VL-1) |
| `local_min_inliers` | 8 | geometric inliers required (the 2026-10-01 benchmark below was measured with 6) |
| `local_retry_features` | 4000 | SIFT: a frame that fills its 1500-feature budget and finds too few inliers is described again with this many (heavy rain; 0 = off) |
| `gyro_heading` | true | gyro heading carry between fixes for frames without attitude (above) |
| `gyro_imu_topic` | "" | sensor_msgs/Imu with the gyro (angular_velocity; orientation for the vertical when given); "" = `NAVERA_SENSOR_SOURCE`'s |
| `gyro_heading_bias_dps` / `gyro_heading_noise_dps_rthz` | 0.1 / 0.02 | gyro bias left after calibration, rate noise density: the carried heading's growing σ |
| `gyro_heading_reset_sigma_deg` / `gyro_heading_max_sigma_deg` | 2 / 10 | σ of a vision heading; beyond the max (~100 s after the last good fix) no heading |
| `gyro_heading_min_inliers` | 20 | inliers of a fix whose rotation restarts the carried heading |
| `strong_gate_k_sigma` | 3 | a fix with ≥ `strong_inliers` further than this × the two sigmas from the carried position waits for a second agreeing fix (`day_pkg/fix_consistency.py`; was 6, F16) |
| `reacquire_confirm` | false | while the carried position is lost (σ > 50 m), a fix further from it than 3 × its own σ also waits for confirmation (costs availability: off) |
| `blend_fixes` | true | a fix is averaged with the carried position by their sigmas when the carry has a heading (attitude or gyro) and the fix is not a re-acquisition (F20, F23, D17) |
| `frame_max_blur_px` / `frame_exposure_s` / `frame_sharp_rel` | 0 / 1/60 / 0 | `day_pkg/frame_gate.py`: frames smeared beyond this by the gyro rate at the exposure, or less sharp than this × the flight's median, are not matched (0 = off; F20) |
| `local_heading_search` / `local_heading_search_after` | false / 3 | heading search always / automatically when no heading is known or after this many frames in a row without a match (D18; 0 = never) |
| `gyro_course_reset` | true | while GPS is trusted, reset the gyro heading from the GPS course (2 s chord, steady course) |
| `gyro_course_min_speed_mps` / `gyro_course_crab_sigma_deg` | 5 / 5 | slower: no course; σ of the camera's offset from the course when it comes from the meta's `mount_yaw_deg` (nose first) instead of vision |
| `map_zoom_min_ratio` | 2 | an area with several zooms (`area.json` `zooms`): the finest zoom at least this many times coarser than the frame (`day_pkg/map_levels.py`), else the coarsest |
| `local_scale_tol` | 0.15 | accepted deviation of the fitted scale from the altitude's |
| `local_sigma_m` | 30 | stated accuracy (1 σ) of a local match |
| `local_max_radius_m` | 600 | largest search radius of one matcher window (re-acquisition windows off) |
| `reacquire_windows` | true | a search circle wider than one window is covered with small windows (`day_pkg/reacquire.py`, F32): the carried position's first, then a scan going on frame to frame |
| `reacquire_window_frac` | 0.65 | window radius = this × the frame's half diagonal on the ground (at least `local_min_radius_m`) |
| `reacquire_windows_per_frame` | 4 | windows tried per frame (~0.25 s each on the Jetson, learned matcher) |
| `reacquire_max_radius_m` | 1500 | largest circle covered (3 σ of the carried position); farther is not searched |
| `reacquire_min_inliers` | 25 | a match in a window other than the carried position's needs this many |

## Camera delay (`navera_common.latency_cal`, `navera_common.delay_monitor`)
A frame is dated `arrival - delay`; a wrong delay puts every fix speed × error along the track.
The GPS may be lost right after take-off and stay lost for hours, so the delay must come from
before the flight. Sources, in order:

1. **Bench-measured, per camera (main source).** `navera_tools/bench/camera_latency.py --calib
   <calibration.yaml>` writes `latency_s` into the camera's calibration file (or set
   `NAVERA_CAMERA_LATENCY_S`). live_camera subtracts it and puts it in every frame's meta
   (`capture_latency_s`); the day node takes it as its set delay (`camera_latency_s`), stated with
   `camera_latency_sigma_s` (0.1 s) — speed × 0.1 s added to every stated fix.
2. **Kept from an earlier flight.** Without a set delay, the delay measured against the GPS on a
   flight is written to the NAVERA state dir (`camera_delay_<calibration file name>.json`, or
   `latency_store_key`) and starts the next flight with its sigma (at least
   `latency_store_min_sigma_s`); a measurement that contradicts it by > 2 σ drops it.
3. **Measured in this flight**, when the GPS phase allows (below).
4. **Never measured:** the delay is unknown: nothing is applied and every stated fix includes
   speed × `unknown_delay_sigma_s` (1 s) for the whole flight — honest, but at 10 m/s that is 10 m
   of stated σ, and the fix is ~2× worse at the stated time than at the exposure (Isaac Sim:
   13 m vs 6.5 m median).

In flight, while the GPS is trusted, each GPS-check match is compared with the GPS track at `arrival - D`
While the GPS is trusted, each GPS-check match is compared with the GPS track at `arrival - D`
for every D in the search range; D and a constant east/north offset (map shift, mounting) are fitted
together, so D is observable only from heading/speed changes (a straight line at one speed: never
applied). Samples need ≥ `latency_min_speed_mps` and no turn faster than `latency_max_turn_dps`. The
estimate is frozen when the GPS is lost or untrusted, the last `latency_rollback_s` of samples are then
dropped (a slow spoof is trusted until refused). It is published in the status JSON (`latency`:
estimate, sigma, applied, applied_sigma, prior, delay, samples, reason) whether or not it is applied.
With no set delay the estimate is applied in stages: once it has `latency_partial_min_samples`, a σ ≤
`latency_partial_max_sigma_s`, is off the bounds and agrees with the previous estimates, the applied
delay is its inverse-variance combination with the prior (the stored delay, else 0 ± 1 s) and
the stated fixes include speed × that combination's σ; fully when stable (σ ≤ `latency_max_sigma_s`).

A delay measured in the GPS phase needs heading/speed changes: on the copter circuit (10 m/s, one
135° turn) σ reaches ~0.3–0.5 s only after the turn, and the samples of the last 20 s before the GPS
loss are dropped (spoof rollback: replays of a 0.5–3 m/s spoof without it applied up to 1.3 s wrong).
**Runbook:** to calibrate in flight, fly at cruise speed with at least two turns of ≥ 90° more than
`latency_rollback_s` (20 s) before the GPS may be lost; otherwise measure the delay on the bench.

Isaac Sim closed loop 2026-10-22 (SIMULATION; true delay 1.3 s; copter 10 m/s 250 m; fix error after the GPS
cut at the stated time, median / p90; outputs beyond 3 σ; wrong fixes > 50 m):

| run | delay used | stamp error | stated σ (median) | > 3 σ | wrong |
|---|---|---|---|---|---|
| c3_base (before) | none (unknown) | 12.8 / 20.7 m | — | 1 / 317 | 0 |
| f31_base | none: staged 1.39–1.54 ± 0.4 s in the last 20 s, rolled back at the cut | 14.7 / 20.9 m | 15 m | 0 / 367 | 0 |
| f31_base_setdelay | bench value 1.3 s (`capture_latency_s`) | **7.4 / 11.9 m** | 6.7 m | 0 / 396 | 0 |
| f31_base_shortgps | none, GPS cut 15 s after the climb (no sample) | 13.1 / 22.9 m | 31 m | 0 / 590 | 0 |
| c2_plane30 (before) | none (1.34 ± 0.43 s never applied) | 50 / 76 m | | 2 / 174 | 8 |
| f31_plane30 | staged 1.25 ± 0.42 s from 10 samples on | **18 / 67 m** (exposure 16 / 67) | | 9 / 227 | 27 (matching, at the exposure) |
| f31r_plane30_nostaged (A/B, staging off) | none (1.45 ± 0.41 s not applied) | 48 / 75 m (exposure 14 / 39) | | 2 / 212 | 12 |

The plane's extra wrong fixes (27 vs 8–12, all > 50 m already at the exposure, scattered directions,
no map bias applied) are matching errors, not the delay; one staged run is not enough to tell them
from run-to-run variance — a repeat is still to do.

The delay can change in flight (a USB/GStreamer queue, a starved grab thread, an IP camera's network):
live_camera watches arrival − the source's own stamp (V4L2 buffer timestamp, GStreamer PTS) against
the first 60 s (`delay_monitor` in the frame meta); a significant change widens the stated accuracy by
speed × the change and is logged (not corrected). A change inside the camera before it stamps the
frame (its encoder) cannot be seen, and an input without source stamps (`ros`) is not watched.

| Parameter | Default | Meaning |
|---|---|---|
| `auto_latency` | true | apply the estimate (false: estimate and publish only) |
| `camera_latency_s` | 0.0 | the delay the camera already subtracted from its stamps (its `capture_latency_s`); the estimate replaces it only when more than `latency_change_sigmas` σ away |
| `latency_min_s` / `latency_max_s` | 0 / 3 | search range of the total delay (s) |
| `latency_min_samples` | 20 | samples before an estimate can be applied (one per `gps_check_period_s`: ≥ 40 s of trusted GPS in motion) |
| `latency_max_sigma_s` | 0.1 | applied only below this σ (statistical + systematic: residual spread / velocity spread) |
| `latency_change_sigmas` | 3 | a set delay within this many σ of the estimate is kept |
| `latency_min_speed_mps` / `latency_max_turn_dps` | 5 / 8 | motion gates of a sample |
| `latency_rollback_s` | 20 | samples dropped at a GPS **refusal** (`NavStatus.gps_refused`); a plain loss keeps them (F39) |
| `camera_latency_sigma_s` | 0.1 | σ of a set (bench-measured) delay in the stated accuracy |
| `latency_partial_max_sigma_s` / `latency_partial_min_samples` | 0.5 / 10 | staged apply of an unknown delay |
| `latency_store` / `latency_store_key` | true / "" | keep the measured delay per camera (key: the calibration file name) |
| `latency_store_max_age_days` / `latency_store_min_sigma_s` | 60 / 0.1 | a stored delay's age limit, and its σ floor |

## Stated accuracy: in-flight sigma calibration, kept per camera (`day_pkg/fix_sigma.py`)
While GPS is trusted, every GPS-check match measures this flight's real vision error
(`SigmaCalibration`); after `sigma_cal_min_samples` (15) the stated σ is scaled to it, else it is at
least `sigma_floor_no_cal_m` (30 m). The samples of the last `calib_rollback_s` (60 s) are forgotten
when the GPS is **refused** (a slow spoof is trusted until refused); a GPS simply **lost** keeps
them (F39: in the Isaac endurance flight the GPS was lost 12 s after reaching altitude and the 24
samples of the climb were all thrown away: 30 m stated for ~14 m errors).

The calibration is kept for the next flight with the same camera (F39), like the camera delay:
| Parameter | Default | |
|---|---|---|
| `sigma_cal_store` / `sigma_cal_store_key` | true / "" | keep it per camera (key: `latency_store_key`, else the calibration file's name) in `NAVERA_STATE_DIR` (`sigma_cal_<key>.json`) |
| `sigma_cal_store_max_age_days` | 30 | an older one is ignored |
| `sigma_cal_store_inflation` / `sigma_cal_store_floor_m` | 1.3 / 10 | a kept calibration is used ×1.3 (terrain, light and height change between flights) and never below 10 m |

Written every 60 s from the samples older than `calib_rollback_s` (the newer ones a refusal could
still roll back) and at the GPS loss. It is used only while this flight has fewer than 15 samples of
its own, and dropped as soon as 2 of those are beyond 3 of its σ (another camera setting, terrain or
height): back to the 30 m floor. The status JSON shows it (`sigma_cal.prior`, `prior_dropped`).

Bench replay (`navera_tools/bench/replay_latency.py`, screen-bench logs 2026-10-20, 30 s of good GPS +
the drift phase until refused): at 60 m/s the GPS phase alone gives 0.97–0.99 s for the Hikvision
(set 0.4 or 1.5 s: after-loss vision error 62 → 6.8 m and 49 → 6.1 m median) and 1.59–1.71 s for the
Insta360 360 (hand value 1.71 s kept: within 3 σ); at 20 m/s (38° of heading change) σ is 0.37–0.71 s,
nothing applied. No run got worse. Bench only (a screen, a circle flight): to confirm in flight.

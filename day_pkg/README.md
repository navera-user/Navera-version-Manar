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
  ≥ `conf_threshold`.
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
- Whole-map search (no prior) is disabled by default (`allow_global_search`): its score does
  not separate good from bad matches.

## Topics
In: `/day/image_raw`, `/day/frame_meta`, `/navera/estimate/gps`, `/day/camera/start`.
Out: `/navera/estimate/day` (the contract), `/day/position_estimate`, `/day/day_status`,
`/day/frame_done`, `/day/localizer_ready`.

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
| `local_scale_tol` | 0.15 | accepted deviation of the fitted scale from the altitude's |
| `local_sigma_m` | 30 | stated accuracy (1 σ) of a local match |
| `local_max_radius_m` | 1500 | largest search radius while widening after failed frames |

## Camera delay, estimated online (`navera_common.latency_cal`)
A frame is dated `arrival - delay`; a wrong delay puts every fix speed × error along the track.
While the GPS is trusted, each GPS-check match is compared with the GPS track at `arrival - D`
for every D in the search range; D and a constant east/north offset (map shift, mounting) are fitted
together, so D is observable only from heading/speed changes (a straight line at one speed: never
applied). Samples need ≥ `latency_min_speed_mps` and no turn faster than `latency_max_turn_dps`. The
estimate is frozen when the GPS is lost or untrusted, the last `latency_rollback_s` of samples are then
dropped (a slow spoof is trusted until refused). It is published in the status JSON (`latency`:
estimate, sigma, applied, delay, samples, reason) whether or not it is applied.

| Parameter | Default | Meaning |
|---|---|---|
| `auto_latency` | true | apply the estimate (false: estimate and publish only) |
| `camera_latency_s` | 0.0 | the delay the camera already subtracted from its stamps (its `capture_latency_s`); the estimate replaces it only when more than `latency_change_sigmas` σ away |
| `latency_min_s` / `latency_max_s` | 0 / 3 | search range of the total delay (s) |
| `latency_min_samples` | 20 | samples before an estimate can be applied (one per `gps_check_period_s`: ≥ 40 s of trusted GPS in motion) |
| `latency_max_sigma_s` | 0.1 | applied only below this σ (statistical + systematic: residual spread / velocity spread) |
| `latency_change_sigmas` | 3 | a set delay within this many σ of the estimate is kept |
| `latency_min_speed_mps` / `latency_max_turn_dps` | 5 / 8 | motion gates of a sample |
| `latency_rollback_s` | 20 | samples dropped at a GPS loss/refusal |

Bench replay (`navera_tools/bench/replay_latency.py`, screen-bench logs 2026-10-20, 30 s of good GPS +
the drift phase until refused): at 60 m/s the GPS phase alone gives 0.97–0.99 s for the Hikvision
(set 0.4 or 1.5 s: after-loss vision error 62 → 6.8 m and 49 → 6.1 m median) and 1.59–1.71 s for the
Insta360 360 (hand value 1.71 s kept: within 3 σ); at 20 m/s (38° of heading change) σ is 0.37–0.71 s,
nothing applied. No run got worse. Bench only (a screen, a circle flight): to confirm in flight.

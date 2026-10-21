# night_pkg — night (thermal) localization

`night_subscriber` aligns the thermal frame with the satellite map around the prior using
the STHN homography network (`night_localizer.py`, one-stage weights from HuggingFace
`xjh19972/STHN`).

> Validated on synthetic data only (8–13 m median, 250–600 m, any heading); **not validated
> on real thermal imagery** — see [docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md).

## How it works
1. A 1536 px satellite patch (zoom 17, ≈1 m/px) is cut **centred on the prior** (last GPS fix
   or last accepted STHN fix).
2. The thermal frame is brought to STHN's training geometry (`normalize_query`): resampled to
   the map resolution from the altitude (`frame_meta.altitude_m`) and the camera's horizontal
   field of view (`camera_hfov_deg`), turned north-up with the heading (`frame_meta.heading_deg`,
   else the IMU `/navera/sensors/imu`), cropped to the 512 px reference. No altitude, no field of
   view, or less than 85 % of the reference covered → no position, with the reason.
3. STHN (`set_input(satellite, thermal)`, corr_level 4, resize 256 — fixed by the weights'
   `config.json`) predicts where the thermal frame's corners lie in the patch.
4. The centre of that quadrilateral is converted back to lat/lon (exact Web Mercator).
5. A geometric consistency score (0–1, not a probability) rejects impossible quadrilaterals,
   and a **motion gate** rejects a fix farther from the last one than the vehicle can travel
   (`max_speed_mps` × elapsed + `gate_margin_m`): the score does not detect a wrong match.
6. **Wrong-fix checks** (2026-10-17): STHN returns a confident quad near the search centre even
   for a frame with no information (sea, salt flat, cloud, noise, heading > 10° off). Each fix
   is re-run from a search centre `recheck_offset_m` (150 m) away and kept only if both agree
   within `recheck_max_m` (25 m; the mean is published), and the map warped into the frame
   must correlate with it (`min_match_ncc`, 0.05). Synthetic stress test: wrong accepts
   228 → 1 of 1272 frames (`navera_tools/bench/night_conditions.py`, docs/VALIDATION_STATUS.md).
   Costs a second inference per accepted frame. The black wedges of a straightened (tilted)
   frame are not ground: a frame showing < 55 % ground in the reference is refused.
7. **2026-10-19** (`docs/test_reports/night_2026-10-19.md`): the frame's ground is stretched
   to the full 8 bits before STHN (a linear-AGC frame with a fire in view: 8/30 → 30/30);
   each confirmed fix states `sigma_m` = hypot(8 m + 1 % of the height above 400 m, 0.8 × the
   two-centre disagreement) — 99 % of synthetic fixes within 3 σ, published as covariance only
   with `state_sim_calibrated_sigma`; the track (`night_tracker.py`) no longer locks onto one
   wrong fix (B16): a jump > `max_single_jump_m` (150) is never taken alone and `reacquire_n`
   (3) agreeing refused fixes re-anchor the track (`reacquire_confirmed_n`, 5, against a
   confirmed one).

The weights must match the network exactly: loading refuses any missing weight.

## Node
| Executable | Node name | Role |
|---|---|---|
| `night_subscriber.py` | `night_subscriber` | thermal frame → STHN → night position (`night_localizer.py`, track: `night_tracker.py`) |

## Topics
| Direction | Topic (default; parameter) | Type | QoS |
|---|---|---|---|
| in | `/thermal/image_raw` (`image_topic`) | `sensor_msgs/Image` (bgr8 or mono16) | RELIABLE, depth 10 |
| in | `/thermal/frame_meta` (`meta_topic`) | `std_msgs/String` (JSON) | RELIABLE, depth 10 |
| in | `/navera/position` (`gps_topic`) | `navera_msgs/PositionEstimate` — the prior while GPS is the source in use | depth 10 |
| in | `/navera/nav_status` | `navera_msgs/NavStatus` | depth 10 |
| in | `/navera/sensors/imu` (`imu_topic`) | `sensor_msgs/Imu` (heading when frame_meta has none) | sensor QoS (BEST_EFFORT) |
| in | `/thermal/camera/start` (`start_topic`) | `std_msgs/Bool` | RELIABLE, TRANSIENT_LOCAL, depth 1 |
| out | `/navera/estimate/night` | `navera_msgs/PositionEstimate` (the estimator's contract) | depth 10 |
| out | `/night/position_estimate` (`fix_topic`) | `sensor_msgs/NavSatFix` | depth 10 |
| out | `/night/night_status` (`status_topic`) | `std_msgs/String` (JSON) | depth 10 |
| out | `/thermal/frame_done` (`done_topic`) | `std_msgs/Int32` (ack, back-pressure) | RELIABLE, depth 1 |
| out | `/night/localizer_ready` (`ready_topic`) | `std_msgs/Bool` (handshake) | RELIABLE, TRANSIENT_LOCAL, depth 1 |

## Parameters
| Parameter | Default | Notes |
|---|---|---|
| `sthn_dir` | `$NAVERA_STHN_DIR`, else `/home/navera/isaac_ros_common/night_pkg/STHN` | |
| `weights` | `$NAVERA_STHN_WEIGHTS`, else `/home/navera/isaac_ros_common/night_pkg/STHN/weights/one_stage/model.safetensors` | |
| `mbtiles` | `$NAVERA_MBTILES`, else the legacy Sousse MBTiles path | |
| `zoom` | `17` | |
| `conf_threshold` | `0.30` | geometric consistency |
| `state_sim_calibrated_sigma` | `false` | publish `sigma_m` as covariance |
| `map_offset_lat_deg`, `map_offset_lon_deg` | `0.0` | map calibration, 0 unless measured |
| `gps_prior_timeout_s` | `2.0` | |
| `shadow_mode` | `false` | test flights: run beside a valid GPS (launch: `$NAVERA_SHADOW_MODE`) |
| `max_dead_reckon_s` | `30.0` | |
| `mixed_precision` | `"false"` | string (torch backend only) |
| `sthn_backend` | `"auto"` | `auto`: TensorRT fp32 engine when built (`navera_tools/trt/build_engines.py`) and `NAVERA_TRT` is not `0`, else the GPU graph (closed-form homographies, no CPU solves); `torch` = STHN's own forward; `graph`; `trt` |
| **`camera_hfov_deg`** | `nan` | **required** (launch: `$NAVERA_THERMAL_HFOV_DEG`); NaN = no night position |
| `max_altitude_rel_sigma` | `0.15` | |
| `imu_heading_timeout_s` | `1.0` | |
| `max_speed_mps` | `30.0` | motion gate (launch: from `$NAVERA_MAX_SPEED_KMH`) |
| `gate_margin_m` | `30.0` | |
| `max_single_jump_m` | `150.0` | ≤ 0 = no limit |
| `reacquire_n`, `reacquire_confirmed_n` | `3`, `5` | |
| `min_match_ncc` | `0.05` | ≤ −1 disables |
| `recheck_offset_m`, `recheck_max_m` | `150.0`, `25.0` | ≤ −1 disables |
| `heading_retry_deg` | `"-10,10,-20,20"` | `""` = off |
| `height_retry` | `"0.1,-0.1,0.2"` | `""` = off |

Retry checks: `heading_retry_deg` (default `"-10,10,-20,20"`, `""` turns it
off: a heading 10–30° off is tried again turned by each offset, only on frames that failed the map
check; synthetic 30 frames: 10° off 19 → 29/30, 20° off 0 → 29/30, 30° off 0 → 19/30, nominal
unchanged, no new wrong fix; ~1.7 s per failed frame instead of ~0.5 s) and `height_retry` (default `"0.1,-0.1,0.2"`: then the
height scaled by each; a footprint too small for the stated height is only tried higher; synthetic:
height −10 % 13 → 28/30, −20 % 0 → 29/30, field of view −10 % 6 → 30/30, 350 m 5 → 24/30; frames
with no information still 0/30 but ~2.4 s each). `night_status` also carries the search square
(`search_center`, `search_size_m`), the matched footprint (`footprint_quad`) and the query
geometry.

## How to run
```bash
ros2 launch night_pkg night_subscriber.launch.py          # the node alone
ros2 launch simulation_web night_pipeline.launch.py       # camera + node (what the box runs)
ros2 launch simulation_web night_sim.launch.py            # + web bridge on :8181
```
`night_subscriber.launch.py` arguments: `sthn_dir`, `weights`, `mbtiles` (env defaults above),
`zoom` (`17`), `conf_threshold` (`0.30`), `image_topic`, `meta_topic`, `fix_topic`,
`status_topic` (defaults above), `camera_hfov_deg` (`$NAVERA_THERMAL_HFOV_DEG`, else `nan`).
On the box: `navera-pipeline-night.service` (`deploy/systemd/navera_boot_pipeline_night.sh`).

## Limits
- Minimum altitude: the frame must cover ≥ 85 % of the 512 px (~500 m) reference — about
  350 m with an 84° camera (lower with a wider lens).
- The heading from the IMU is magnetic (IMU-3). Synthetic: 5° off is tolerated, 10° off loses a
  third of the fixes and 20° off all of them without the heading retry (on by default since 2026-10-19).
- Height error: −10 % refuses half the frames at 400 m (footprint), −20 % all; +20 % keeps about
  half. The search area is ±745 m around the prior: a prior farther off gives no fix.
- GPU: ~225 ms/frame. On JetPack 6 the Jetson PyTorch build cannot load CUDA linear algebra;
  the small homography solves are then routed to the CPU automatically (same results).
- The replay set's frames cover only ~190–300 m of ground (mostly sea): they are refused.

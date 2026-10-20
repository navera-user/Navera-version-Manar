# simulation_web — web bridge, operator view, launch files

## Nodes
| Executable (`ros2 run simulation_web …`) | Node name | Role |
|---|---|---|
| `navera_web_bridge.py` | `navera_web_bridge` | HTTP server on :8181 — operator view (`/operator`), mission preparation (`/mission`), replay/debug dashboard (`/`), map tiles from the MBTiles file, mission start. Day and night pipelines. |
| `navera_stellar_bridge.py` | `navera_stellar_bridge` | The same dashboard (`/`) for the celestial pipeline (no `/operator`, no `/mission`). |

Only one bridge runs at a time (both bind the same port). Endpoints and security rules:
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §6. The shared HTTP layer (token, JSON limits,
tile bounds, static files) is `simulation_web/web_common.py`; the `/mission` logic is
`simulation_web/mission_prep.py`; the pages are in `simulation_web/resources/`.

### Topics — `navera_web_bridge`
| Direction | Topic (default) | Type | QoS |
|---|---|---|---|
| in | `status_topic` = `/day/day_status` | `std_msgs/String` (JSON) | depth 10 |
| in | `fix_topic` = `/day/position_estimate` | `sensor_msgs/NavSatFix` | depth 10 |
| in | `ready_topic` = `/day/localizer_ready` | `std_msgs/Bool` | RELIABLE, TRANSIENT_LOCAL, depth 1 |
| in | `/day/frame_meta`, `/thermal/frame_meta` | `std_msgs/String` (JSON) | depth 10 |
| in | `position_topic` = `/navera/position` | `navera_msgs/PositionEstimate` | depth 10 |
| in | `nav_status_topic` = `/navera/nav_status` | `navera_msgs/NavStatus` | depth 10 |
| in | `/navera/vehicle/status` | `std_msgs/String` (JSON, from vehicle_link) | depth 10 |
| in | `/navera/sim/truth` | `sensor_msgs/NavSatFix` (simulation only) | depth 10 |
| out | `start_topic` = `/day/camera/start` | `std_msgs/Bool` | RELIABLE, TRANSIENT_LOCAL, depth 1 |
| out | `/navera/operator/start_position` | `navera_msgs/PositionEstimate` | RELIABLE, TRANSIENT_LOCAL, depth 1 |

### Topics — `navera_stellar_bridge`
| Direction | Topic (default) | Type | QoS |
|---|---|---|---|
| in | `status_topic` = `/cn/cn_status` | `std_msgs/String` (JSON) | depth 10 |
| in | `fix_topic` = `/cn/position_estimate` | `sensor_msgs/NavSatFix` | depth 10 |
| out | `start_topic` = `/celestial/camera/start` | `std_msgs/Bool` | RELIABLE, TRANSIENT_LOCAL, depth 1 |

### HTTP endpoints (port `web_port`, default 8181)
`navera_web_bridge`: `GET /` (`navera.html`), `/operator`, `/mission`, `/tiles/{z}/{x}/{y}.png`,
`/gps_status.json`, `/api/operator_position`, `/flight_log.csv`, `/api/cache_status`,
`/api/precollect_progress`, `/api/mission/state`, `/health`; `POST /api/set_mission`,
`/api/mission/{settings,apply,plan,generate,cancel,activate,save_mission,delete_mission}`
(all POSTs need the control token); any other `GET` serves a static file from `resources/`.

`navera_stellar_bridge`: `GET /`, `/tiles/{z}/{x}/{y}.png`, `/gps_status.json`,
`/api/cache_status`, `/api/precollect_progress`, `/api/node`, `/health`; `POST /api/set_mission`
(token); other `GET` → static file.

## Mission preparation on the box (`/mission`)
The page an operator uses on the vehicle, in three steps:
1. **Vehicle** — type, maximum speed, thermal camera field of view, IMU mounting,
   declination. Saved to `/var/lib/navera/settings.env` (validated keys only, atomic
   write), which every NAVERA unit loads after `/etc/navera/navera.env`; **Apply**
   try-restarts the running NAVERA units.
2. **Route** — the autopilot's mission file (Mission Planner `.waypoints`, QGroundControl
   `.plan`) or two clicks on the map; split into ≤ 10 km legs so the map follows the
   flown path.
3. **Satellite map** — generated with `prepare_area.py` into `$NAVERA_AREAS_DIR` (onboard
   MBTiles, plus downloads when `NAVERA_TILE_URL` is set), then **Activate** points
   `DAY_DATASET_DIR` at it and restarts the day pipeline.

Every change needs the control code (`NAVERA_WEB_TOKEN`); without it the page is read-only.
The only root action the web service may take is restarting NAVERA's units, through
`deploy/sudoers/navera-web` (exact commands). Logic and tests: `mission_prep.py`,
`test/test_mission_prep.py`.

## Launch files
| File | Starts |
|---|---|
| `day_pipeline.launch.py` / `night_pipeline.launch.py` / `cn_pipeline.launch.py` | camera + localizer (no bridge) |
| `bridge.launch.py` | one web bridge (topics as arguments) |
| `day_sim.launch.py` / `night_sim.launch.py` / `cn_sim.launch.py` | pipeline + bridge, single command |

Every node in these launch files ends its launch if it exits (`on_exit=Shutdown`) so the
systemd service restarts the whole pipeline.

### Launch arguments (defaults; `$VAR` = environment variable read by the launch file)
- `bridge.launch.py`: `bridge_executable` (`navera_web_bridge.py`), `bridge_name`
  (`navera_web_bridge`), `status_topic` (`/day/day_status`), `ready_topic`
  (`/day/localizer_ready`), `fix_topic` (`/day/position_estimate`), `start_topic`
  (`/day/camera/start`), `mbtiles_path` (`$NAVERA_MBTILES`, else the legacy Sousse MBTiles
  path), `web_host` (`0.0.0.0`), `web_port` (`8181`).
- `day_pipeline.launch.py`: `conf_threshold` (`0.75`), `antijump_enabled` (`true`),
  `max_consecutive_rejects` (`3`), `max_dead_reckon_s` (`30.0`), `shadow_mode` (from
  `$NAVERA_SHADOW_MODE` via `navera_common.vehicle`), `allow_global_search` (`false`),
  `camera_hfov_deg` (`$NAVERA_DAY_HFOV_DEG`, else `nan`), `matcher` (`$NAVERA_DAY_MATCHER`,
  else `auto`), `default_gps_valid` (`true`), `csv_path` (`$NAVERA_DAY_CSV`, else
  camera_pkg `data/day/flight_demo.csv`), `images_dir` (`$NAVERA_DAY_IMAGES_DIR`, else
  camera_pkg `data/day`). `$NAVERA_CAMERA=live` uses camera_pkg `live.launch.py` instead of
  the replay camera; the vehicle maximum speed comes from `$NAVERA_MAX_SPEED_KMH`.
- `night_pipeline.launch.py`: `mbtiles_path` (`$NAVERA_MBTILES`), `conf_threshold` (`0.30`),
  `max_dead_reckon_s` (`30.0`), `shadow_mode`, `csv_path` (`$NAVERA_THERMAL_CSV`, else
  camera_pkg `data/thermal/flight_ready.csv`), `images_dir` (`$NAVERA_THERMAL_IMAGES_DIR`),
  `default_gps_valid` (`true`), `cuda_visible_devices` (`0`), `cuda_alloc_conf`
  (`expandable_segments:True`), `mixed_precision` (`false`), `camera_hfov_deg`
  (`$NAVERA_THERMAL_HFOV_DEG`, else `nan`), `sthn_dir` (`$NAVERA_STHN_DIR`), `weights`
  (`$NAVERA_STHN_WEIGHTS`). `$NAVERA_CAMERA=live` as for day.
- `cn_pipeline.launch.py`: `min_log_odds` (`20.7`), `camera_fov_deg`
  (`$NAVERA_STAR_CAMERA_HFOV_DEG` when live, else `nan`), `solver_mode` (`geoloc`), `tilt`
  (`75.46`), `azimuth` (`283.18`), `utc_time` (`2026-03-10 20:20:00`), `prior_lat` (`35.83`),
  `prior_lon` (`10.64`) — the sample-sky values; with `$NAVERA_STAR_CAMERA_INPUT` set (live)
  they become `nan` / empty. `camera_mount_elevation_deg`
  (`$NAVERA_STAR_CAMERA_ELEVATION_DEG`, else `90.0`), `camera_mount_azimuth_deg`
  (`$NAVERA_STAR_CAMERA_AZIMUTH_DEG`, else `0.0`), `magnetic_declination_deg`
  (`$NAVERA_MAGNETIC_DECLINATION_DEG`, else `0.0`), `attitude_sigma_deg`
  (`$NAVERA_ATTITUDE_SIGMA_DEG`, else `nan`).
- `day_sim` / `night_sim` / `cn_sim`: `web_port` (`8181`), `mbtiles_path`, plus the matching
  pipeline's arguments above (the subset they re-declare).

## Parameters (bridges)
| Parameter | Default | Bridge |
|---|---|---|
| `status_topic` | `/day/day_status` (stellar: `/cn/cn_status`) | both |
| `fix_topic` | `/day/position_estimate` (stellar: `/cn/position_estimate`) | both |
| `start_topic` | `/day/camera/start` (stellar: `/celestial/camera/start`) | both |
| `mbtiles_path` | `""` (the launch files pass `$NAVERA_MBTILES`) | both |
| `web_host` | `0.0.0.0` | both |
| `web_port` | `8181` | both |
| `control_token` | `$NAVERA_WEB_TOKEN` (empty = read-only) | both |
| `tls_cert`, `tls_key` | `$NAVERA_TLS_CERT`, `$NAVERA_TLS_KEY` (empty = plain HTTP) | both |
| `status_stale_s` | `10.0` | web |
| `ready_topic` | `/day/localizer_ready` | web |
| `position_topic` | `/navera/position` | web |
| `nav_status_topic` | `/navera/nav_status` | web |
| `nav_status_timeout_s` | `2.0` | web |
| `position_timeout_s` | `60.0` | web |

## How to run
```bash
ros2 launch simulation_web day_sim.launch.py        # pipeline + bridge (or night_sim / cn_sim)
ros2 run simulation_web navera_web_bridge.py        # the bridge alone
curl http://localhost:8181/gps_status.json
```
On the box: `navera-web.service` (`deploy/systemd/navera_boot_web.sh`: `bridge.launch.py`
with the topics of `$NAVERA_PIPELINE` = day | night | cn) and `navera-pipeline-day`,
`navera-pipeline-night`, `navera-pipeline-cn` (`*_pipeline.launch.py`).

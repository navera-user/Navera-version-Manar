# cn_pkg — celestial localization

`cn_subscriber` plate-solves a star image with astrometry.net and turns the camera's pointing
direction into a ground position (`celestial_math.py`).

> Run end to end on simulated star fields: 5.5–6.5 km with a perfect attitude, **24–119 km
> with a BNO085-class IMU** — a coarse fix bounded by the attitude (~111 km per degree). See
> [docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md).

## How it works
1. `drone_sky_prep.py` (subprocess): optional siril preprocessing, then `solve-field` → field
   centre RA/Dec (J2000) and the log-odds of the star match.
2. RA/Dec are converted to the equinox of date (astropy TETE); Greenwich apparent sidereal
   time from the UTC time.
3. With the camera attitude (tilt above the horizon, azimuth from true north), both solutions
   of the observer latitude are computed; the one consistent with the prior position
   (`prior_lat`, `prior_lon`) is kept. If the prior cannot separate them: no position.

## 360 all-sky mode (`solver_mode:=allsky360`)
For the Insta360's full dual-fisheye frame (3840x1920): no astrometry.net, no heading, no prior.
The bright spots of both fisheye circles become rays in the camera frame, are identified
lost-in-space against the bright-star catalogue (pairs + TRIAD + Wahba), and the zenith among
the stars ('up' through the solution) is the position. Code shared with the field tools
(`navera_tools/field/allsky.py`, `sky360.py` are aliases of `cn_pkg/allsky.py`, `cn_pkg/sky360.py`):
- **Quality gate** `allsky.accept`: >= 7 stars and rms <= 0.2 deg and chance probability
  p <= 1e-6, or p <= 1e-4 with rms <= 0.12, or p <= 1e-2 with rms <= 0.10; lenses agree within 1 deg.
- **'up'** (`allsky_up_source`): `camera` = frame_meta `up_imu` (the camera's accelerometer; refused
  when frame_meta `accel_g` is off 1 g by more than `allsky.ACCEL_NORM_TOL`), `vehicle` = the IMU
  orientation at the exposure through the full camera-to-body rotation `allsky_R_cam_body`
  (9 values, row-major, camera vector = R @ body FLU vector; default: camera standing on a level
  vehicle), `auto` = camera when the frame carries it.
- **Lens model:** `allsky_lens_file` (default `~/.navera_sim/insta360_usb_lens.json`, `NAVERA_INSTA360_LENS`);
  the focal length is searched (`allsky_f_scale_search`) on the first fix, then kept.
- **Tilt of 'up'** (mount + accelerometer residual, 1 deg = 111 km): learned on the first
  `allsky_cal_samples` fixes taken with a fresh GPS fix (`allsky_cal_gps_max_age_s`) while still,
  then frozen; later fixes are corrected (`allsky_mount.TiltCalibration`, the field server's fit).
- **Stated sigma** (`PositionEstimate` covariance): 'up' attitude (`attitude_sigma_deg`, default 0.3 deg;
  the learned tilt's residual once calibrated) and the star fit in quadrature, + 5 deg when frame_meta
  says `stopped: false`, + the IMU timing at the rotation rate (vehicle source).
- **Offline:** the catalogue is `cn_pkg/data/bsc5_mag4.5.csv` (Yale BSC5, 904 stars), never downloaded;
  time via the bundled IERS table (`celestial_math.configure_offline_iers`).

Simulation only (navera_tools/sim/allsky_cn_parity.py): the node path gives the same fixes as the
field path on the stress set; no real-sky validation of the node yet.

## Install

    sudo apt install astrometry.net astrometry-data-tycho2-10-19

`NAVERA_SOLVE_FIELD` / `NAVERA_ASTROMETRY_CFG` point at another solver or index location.
The solve is anchored at the image centre with a 4th-order fit (`--crpix-center
--tweak-order 4`) and skips the Python line-removal steps (they break on NumPy ≥ 1.24).

## Inputs that must be real
- **Time:** `frame_meta.utc_time`, else parameter `utc_time`, else the DS3231 RTC
  (`/navera/sensors/rtc_time`, when valid), else the system clock.
- **Attitude:** `tilt`, `azimuth` from frame_meta; else from the IMU **at the frame's
  exposure** (`/navera/sensors/imu`, nearest sample to the image stamp) with the camera mounting
  (`camera_mount_elevation_deg` 90 = pointing up, `camera_mount_azimuth_deg`) and the
  `magnetic_declination_deg`; else the `tilt`/`azimuth` parameters; unknown → no position.
- **Prior:** `prior_lat`/`prior_lon`, else the last valid GPS fix.
- **Stated accuracy:** `attitude_sigma_deg` × ~111 km (NaN = unknown covariance).

## Node
| Executable | Node name | Role |
|---|---|---|
| `cn_subscriber.py` | `cn_subscriber` | star frame → plate solve (or 360 all-sky identification) → celestial position |

Modules: `nodes/cn_subscriber.py` (the node), `nodes/solver.py` (runs `drone_sky_prep.py` /
`solve-field` in a killable process group), `nodes/drone_sky_prep.py` (the astrometry CLI),
`nodes/celestial_math.py` (pure geometry, no ROS), `star_detect.py` (star detection and rating);
the 360 mode's `allsky.py`, `allsky_mount.py`, `allsky_locator.py`, `sky360.py` (see above).

## Topics
| Direction | Topic (default; parameter) | Type | QoS |
|---|---|---|---|
| in | `/celestial/image_raw` (`image_topic`) | `sensor_msgs/Image` | RELIABLE, depth 10 |
| in | `/celestial/frame_meta` (`meta_topic`) | `std_msgs/String` (JSON) | RELIABLE, depth 10 |
| in | `/navera/sensors/imu` (`imu_topic`) | `sensor_msgs/Imu` | sensor QoS (BEST_EFFORT) |
| in | `/navera/estimate/gps` (`gps_topic`) | `navera_msgs/PositionEstimate` (prior when none is set) | depth 10 |
| in | `/navera/sensors/rtc_time` (`rtc_topic`) | `sensor_msgs/TimeReference` | depth 10 |
| out | `/navera/estimate/cn` | `navera_msgs/PositionEstimate` (the estimator's contract) | depth 10 |
| out | `/cn/position_estimate` (`fix_topic`) | `sensor_msgs/NavSatFix` | depth 10 |
| out | `/cn/cn_status` (`status_topic`) | `std_msgs/String` (JSON) | depth 10 |
| out | `/celestial/frame_done` | `std_msgs/Int32` (the live star camera may send the next frame) | depth 1 |

## Parameters
| Parameter | Default | Notes |
|---|---|---|
| `min_log_odds` | `20.7` | astrometry match threshold |
| `camera_fov_deg` | `nan` | NaN = wide 5–90° search (pipeline launch: `$NAVERA_STAR_CAMERA_HFOV_DEG` when live) |
| `solver_mode` | `geoloc` | `wcs` gives sky coordinates only, never a position; `allsky360` = 360 mode |
| `tilt`, `azimuth` | `nan` | attitude fallback (deg) |
| `utc_time` | `""` | fallback exposure time |
| `prior_lat`, `prior_lon` | `nan` | else the last valid GPS fix |
| `camera_mount_elevation_deg` | `90.0` | launch: `$NAVERA_STAR_CAMERA_ELEVATION_DEG` |
| `camera_mount_azimuth_deg` | `0.0` | launch: `$NAVERA_STAR_CAMERA_AZIMUTH_DEG` |
| `magnetic_declination_deg` | `0.0` | launch: `$NAVERA_MAGNETIC_DECLINATION_DEG` |
| `imu_timeout_s` | `1.0` | |
| `attitude_sigma_deg` | `nan` | stated accuracy ≈ value × 111 km; launch: `$NAVERA_ATTITUDE_SIGMA_DEG` |
| `max_rotation_dps` | `3.0` | frames taken while rotating faster are not solved |
| `imu_max_gap_s` | `0.1` | |
| `allsky_up_source` | `auto` | `camera` / `vehicle` / `auto` |
| `allsky_R_cam_body` | camera standing on a level vehicle (9 values) | |
| `allsky_lens_file` | `""` (= `$NAVERA_INSTA360_LENS` / `~/.navera_sim/insta360_usb_lens.json`) | |
| `allsky_catalogue` | `""` (= bundled `data/bsc5_mag4.5.csv`) | |
| `allsky_f_scale_search` | `[0.96, 1.0, 1.04]` | |
| `allsky_cal_min_samples`, `allsky_cal_samples` | `4`, `12` | |
| `allsky_cal_gps_max_age_s` | `2.0` | |
| `allsky_cal_still_dps` | `0.5` | |

`solve-field` is found via `NAVERA_SOLVE_FIELD`, then `PATH`.

## How to run
```bash
ros2 launch cn_pkg cn_subscriber.launch.py                # the node alone
ros2 launch simulation_web cn_pipeline.launch.py          # star camera + node (what the box runs)
ros2 launch simulation_web cn_sim.launch.py               # + web bridge on :8181
```
`cn_subscriber.launch.py` arguments: `min_log_odds` (`20.7`), `camera_fov_deg` (`nan`),
`image_topic`, `meta_topic`, `fix_topic`, `status_topic` (defaults above), `solver_mode`
(`geoloc`), `allsky_up_source` (`auto`). On the box: `navera-pipeline-cn.service`
(`deploy/systemd/navera_boot_pipeline_cn.sh`).

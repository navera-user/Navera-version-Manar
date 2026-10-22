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
3. **Compass-free (B11), when the camera's full mounting is known** (`camera_R_cam_body`, or
   `camera_mount_roll_deg` with the elevation / azimuth): the plate solve gives the camera's
   whole rotation among the stars (`celestial_math.camera_rotation_from_wcs`, from the WCS
   file); 'up' in the camera comes from the IMU's roll and pitch only (`up_in_camera`), and the
   zenith among the stars is the position (`zenith_fix`): one answer, no compass, no magnetic
   declination, no prior. Synthetic plate solution: a compass error of 1 / 5 / 10 deg moved the
   one-direction fix 51 / 256 / 516 km, the zenith fix 0.24 km whatever the heading. A wrong
   roll of the mount costs ~(vehicle tilt x roll error): 0 on a level vehicle, ~48 km for
   5 deg x 5 deg. The tilt of 'up' is learned on fixes with a fresh GPS reference as in the
   360 mode (robust `TiltCalibration`).
4. **Otherwise (mount roll unknown)** — the one-direction method: with the camera attitude
   (tilt above the horizon, azimuth from the **compass**, true north), both solutions of the
   observer latitude are computed; the one consistent with the prior position (`prior_lat`,
   `prior_lon`) is kept. If the prior cannot separate them: no position. A heading error is
   stretched by cos(lat) / (cos(dec) |cos H|) and the two roots merge near H = ±90 deg (no fix):
   the status says `fix_method: boresight (... camera mount roll unknown, set camera_R_cam_body)`.

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
- **Tilt of 'up'** (mount + accelerometer residual, 1 deg = 111 km): learned on fixes taken with a
  fresh GPS fix (`allsky_cal_gps_max_age_s`) while still, until `allsky_cal_samples` of them agree
  (or twice that many were taken), then frozen; later fixes are corrected (`allsky_mount.TiltCalibration`,
  the field server's fit). The fit is robust (D11): a sample more than 3.5 robust sigma (0.3-1.0 deg)
  from the others is left out and does not count, and a fit without a clear majority (>= 3 agreeing,
  more than half) or with a tilt > 5 deg is not applied.
- **Stillness** (`standstill.py`, D8/D12, for whoever sets frame_meta `stopped`): the exposure window
  (0.2 s means steady, rotation < 0.5 deg/s) AND a 10 s look back at the gyro-propagated vertical:
  'up' must not have moved without the camera turning, unless |a| shows the vehicle braked to this
  stop. Glass-road simulation: 'stopped' frames with 'up' > 0.3 deg off 106 -> 1 (4 seeds 394 -> 2), no stop
  lost on 13 profiles; trusted fixes through the field server p90 265 -> 9.3 km, max 825 -> 22 km.
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
- **Time:** a `frame_meta.utc_time` stated by a replay / the simulator, else parameter
  `utc_time`, else the exposure on a **trusted** clock (`navera_common/trusted_time.py`, hazard
  H-08): the DS3231 (`rtc_time` + `rtc_status` valid, not lost_power), a GNSS time received within
  `gnss_time_max_age_s` (300 s, `/navera/sensors/gnss_time` from gps_node) or NTP, with no
  wall-clock step since and none in the last 60 s. Otherwise **no solve**: the estimate is invalid
  with the reason `no trusted time: ...`. live_camera's `utc_time` (system clock,
  `utc_source: system_clock`) is never trusted by itself.
- **Attitude:** `tilt`, `azimuth` from frame_meta; else from the IMU **at the frame's
  exposure** (`/navera/sensors/imu`, nearest sample to the image stamp) with the camera mounting
  (`camera_mount_elevation_deg` 90 = pointing up, `camera_mount_azimuth_deg`) and the
  `magnetic_declination_deg`; else the `tilt`/`azimuth` parameters; unknown → no position.
  With the full mounting (`camera_R_cam_body` / `camera_mount_roll_deg`), only the IMU's 'up' is
  used (frame_meta `up_cam` overrides it): the heading and the declination play no part.
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
| in | `/navera/sensors/rtc_status` (`rtc_status_topic`) | `std_msgs/String` (JSON) | depth 10 |
| in | `/navera/sensors/gnss_time` (`gnss_time_topic`) | `sensor_msgs/TimeReference` | depth 10 |
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
| `camera_R_cam_body` | 9 x NaN (unknown) | the narrow camera's full mounting: optical-frame vector = R @ body FLU vector, row-major (optical frame: x image right, y image down, z along the axis); known → compass-free fix (B11) |
| `camera_mount_roll_deg` | `nan` | or the image's roll about its axis with the elevation / azimuth above (0 = image top towards the body's up; for a camera looking straight up: towards the front); measure it, never assume it |
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

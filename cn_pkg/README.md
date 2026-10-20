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

## Key parameters
`min_log_odds` (20.7), `camera_fov_deg` (NaN = wide 5–90° search), `prior_lat`, `prior_lon`,
`solver_mode` (`geoloc`; `wcs` gives sky coordinates only, never a position).
`solve-field` is found via `NAVERA_SOLVE_FIELD`, then `PATH`.

## Topics
In: `/celestial/image_raw`, `/celestial/frame_meta`, `/navera/sensors/rtc_time`.
Out: `/navera/estimate/cn`, `/cn/position_estimate`, `/cn/cn_status`.

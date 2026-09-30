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

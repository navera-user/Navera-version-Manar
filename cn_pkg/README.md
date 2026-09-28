# cn_pkg — celestial localization

`cn_subscriber` plate-solves a star image with astrometry.net and turns the camera's pointing
direction into a ground position (`celestial_math.py`).

> Geometry verified by simulation; **not run end to end** (needs astrometry.net and IMU
> attitude) — see [docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md).

## How it works
1. `drone_sky_prep.py` (subprocess): optional siril preprocessing, then `solve-field` → field
   centre RA/Dec (J2000) and the log-odds of the star match.
2. RA/Dec are converted to the equinox of date (astropy TETE); Greenwich apparent sidereal
   time from the UTC time.
3. With the camera attitude (tilt above the horizon, azimuth from true north), both solutions
   of the observer latitude are computed; the one consistent with the prior position
   (`prior_lat`, `prior_lon`) is kept. If the prior cannot separate them: no position.

## Inputs that must be real
- **Time:** `frame_meta.utc_time`, else parameter `utc_time`, else the DS3231 RTC
  (`/navera/sensors/rtc_time`, when valid), else the system clock.
- **Attitude:** `tilt`, `azimuth` (frame_meta or parameters). Unknown (NaN, the default) →
  no position. They are meant to come from the IMU (not wired yet).

## Key parameters
`min_log_odds` (20.7), `camera_fov_deg` (NaN = wide 5–90° search), `prior_lat`, `prior_lon`,
`solver_mode` (`geoloc`; `wcs` gives sky coordinates only, never a position).
`solve-field` is found via `NAVERA_SOLVE_FIELD`, then `PATH`.

## Topics
In: `/celestial/image_raw`, `/celestial/frame_meta`, `/navera/sensors/rtc_time`.
Out: `/navera/estimate/cn`, `/cn/position_estimate`, `/cn/cn_status`.

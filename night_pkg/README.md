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

The weights must match the network exactly: loading refuses any missing weight.

## Topics
In: `/thermal/image_raw` (bgr8 or mono16), `/thermal/frame_meta`, `/navera/estimate/gps`,
`/thermal/camera/start`. Out: `/navera/estimate/night`, `/night/position_estimate`,
`/night/night_status`, `/thermal/frame_done`, `/night/localizer_ready`.

## Key parameters
`sthn_dir`, `weights`, `mbtiles` (defaults from `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS`,
`NAVERA_MBTILES`), `conf_threshold` (consistency), `max_dead_reckon_s`,
`map_offset_lat_deg` / `map_offset_lon_deg` (map calibration, 0 unless measured),
`mixed_precision`, **`camera_hfov_deg` (required; `NAVERA_THERMAL_HFOV_DEG`)**,
`max_speed_mps` (30), `gate_margin_m` (30). `night_status` also carries the search square
(`search_center`, `search_size_m`), the matched footprint (`footprint_quad`) and the query
geometry.

## Limits
- Minimum altitude: the frame must cover ≥ 85 % of the 512 px (~500 m) reference — about
  350 m with an 84° camera (lower with a wider lens).
- The heading from the IMU is magnetic (IMU-3); a 1.5° heading error was tolerated in tests.
- GPU: ~225 ms/frame. On JetPack 6 the Jetson PyTorch build cannot load CUDA linear algebra;
  the small homography solves are then routed to the CPU automatically (same results).
- The replay set's frames cover only ~190–300 m of ground (mostly sea): they are refused.

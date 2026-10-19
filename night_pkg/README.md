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

## Topics
In: `/thermal/image_raw` (bgr8 or mono16), `/thermal/frame_meta`, `/navera/estimate/gps`,
`/thermal/camera/start`. Out: `/navera/estimate/night`, `/night/position_estimate`,
`/night/night_status`, `/thermal/frame_done`, `/night/localizer_ready`.

## Key parameters
`sthn_dir`, `weights`, `mbtiles` (defaults from `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS`,
`NAVERA_MBTILES`), `conf_threshold` (consistency), `max_dead_reckon_s`,
`map_offset_lat_deg` / `map_offset_lon_deg` (map calibration, 0 unless measured),
`mixed_precision`, **`camera_hfov_deg` (required; `NAVERA_THERMAL_HFOV_DEG`)**,
`max_speed_mps` (30), `gate_margin_m` (30), `recheck_offset_m` (150), `recheck_max_m` (25),
`min_match_ncc` (0.05) — ≤ −1 disables a check — and `heading_retry_deg` (default `"-10,10,-20,20"`, `""` turns it
off: a heading 10–30° off is tried again turned by each offset, only on frames that failed the map
check; synthetic 30 frames: 10° off 19 → 29/30, 20° off 0 → 29/30, 30° off 0 → 19/30, nominal
unchanged, no new wrong fix; ~1.7 s per failed frame instead of ~0.5 s) and `height_retry` (default `"0.1,-0.1,0.2"`: then the
height scaled by each; a footprint too small for the stated height is only tried higher; synthetic:
height −10 % 13 → 28/30, −20 % 0 → 29/30, field of view −10 % 6 → 30/30, 350 m 5 → 24/30; frames
with no information still 0/30 but ~2.4 s each). `night_status` also carries the search square
(`search_center`, `search_size_m`), the matched footprint (`footprint_quad`) and the query
geometry.

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

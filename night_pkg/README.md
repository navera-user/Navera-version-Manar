# night_pkg — night (thermal) localization

`night_subscriber` aligns the thermal frame with the satellite map around the prior using
the STHN homography network (`night_localizer.py`, one-stage weights from HuggingFace
`xjh19972/STHN`).

> Validated on synthetic data only (3–17 m on 100–150 m shifts); **not validated on real
> thermal imagery** — see [docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md).

## How it works
1. A 1536 px satellite patch (zoom 17, ≈1 m/px) is cut **centred on the prior** (last GPS fix
   or last accepted STHN fix).
2. STHN (`set_input(satellite, thermal)`, corr_level 4, resize 256 — fixed by the weights'
   `config.json`) predicts where the thermal frame's corners lie in the patch.
3. The centre of that quadrilateral is converted back to lat/lon (exact Web Mercator).
4. A geometric consistency score (0–1, not a probability) rejects impossible quadrilaterals.

The weights must match the network exactly: loading refuses any missing weight.

## Topics
In: `/thermal/image_raw` (bgr8 or mono16), `/thermal/frame_meta`, `/navera/estimate/gps`,
`/thermal/camera/start`. Out: `/navera/estimate/night`, `/night/position_estimate`,
`/night/night_status`, `/thermal/frame_done`, `/night/localizer_ready`.

## Key parameters
`sthn_dir`, `weights`, `mbtiles` (defaults from `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS`,
`NAVERA_MBTILES`), `conf_threshold` (consistency), `max_dead_reckon_s`,
`map_offset_lat_deg` / `map_offset_lon_deg` (map calibration, 0 unless measured),
`mixed_precision`.

## Limits
- The thermal footprint is not yet rescaled from altitude/FOV to the satellite scale.
- On this JetPack the Jetson PyTorch build needs a newer cusolver for GPU inference; CPU works
  (~1.6 s/frame).

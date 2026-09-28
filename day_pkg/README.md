# day_pkg — day visual localization

`day_subscriber` estimates the position by matching the camera frame against satellite
tiles with DINOv2 (cosine similarity on GeM-pooled descriptors, `day_localizer.py`).

> Measured accuracy is **not sufficient to replace GPS** (median 442 m on labelled frames):
> see [docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md).

## Behaviour
- While live GPS is valid, no inference: the last GPS fix is the prior.
- Without GPS, the search is limited to a 600 m circle around the prior (last GPS fix or last
  accepted match); a match must score ≥ `conf_threshold`.
- No match: dead-reckoning from measured heading/speed only, for at most `max_dead_reckon_s`;
  otherwise an explicit "no position". After `max_consecutive_rejects` the prior is dropped.
- Whole-map search (no prior) is disabled by default (`allow_global_search`): its score does
  not separate good from bad matches.

## Topics
In: `/day/image_raw`, `/day/frame_meta`, `/navera/estimate/gps`, `/day/camera/start`.
Out: `/navera/estimate/day` (the contract), `/day/position_estimate`, `/day/day_status`,
`/day/frame_done`, `/day/localizer_ready`.

## Data
`DAY_DATASET_DIR` → `dataset.csv` (tile file names; coordinates are derived from the XYZ tile
name, centre of the tile) + `images/`. The descriptor cache `descriptors_cache.npz` is built
on first start (~3 min for 1120 tiles). DINOv2 weights come from `TORCH_HOME`.

## Run
`ros2 launch simulation_web day_pipeline.launch.py` (camera + localizer) or `day_sim.launch.py`
(+ web bridge).

# Replay data (labels only in git; the images live with the deployed data, e.g. NAVERA_DAY_IMAGES_DIR)

## What the frames are

- `day/` and `thermal/` show the SAME 30 places of one flight around Sousse at 400 m. The `thermal`
  frames are the day photos turned grey and darkened: a **day-derived stand-in, not thermal imagery**
  (sun shadows are visible). Night-vision results measured on them say nothing about real LWIR.
- `thermal/frame_k` is the same picture as `vision_pkg/.../dataset/frames_gps/frame_k` for k = 1-15
  (normalised cross-correlation 0.87-1.0, next best <= 0.67) and as `day/frame_(k+8)` for every k
  (cyclic: thermal 23-30 = day 1-8; NCC 0.85-0.93).

## Labels (checked 2026-10-20)

Every frame was located on the satellite map (day_pkg LocalMatcher, 1120-tile dataset, 700 m search
around the label, 400 m altitude): 25 of 30 matched, and the 21 labelled ones among them sit
**1-5 m** from the `thermal/flight_ready.csv` label; the map rotation agrees with the track heading
within ~1 deg.

- `thermal/flight_ready.csv`: positions were already right; the heading was 0 for every row and is
  now the track heading (71, 322, 291, 313, 195, 146 deg by leg).
- `day/flight_log.csv`: the labels were in frame order but the pictures are 8 frames later in the
  flight, so every day label was the position of another picture (1.8-5.9 km off). Each day frame
  now carries the label of its own place (`day/frame_j` = track row j-8, cyclic).
- Rows without lat/lon are the simulated GPS-loss frames (the empty rows move with their picture).
  Their positions found on the map, for scoring: `truth_from_map.csv` (all 30 frames; frame 20 is a
  weak 6-inlier match, frames 6 and 22 did not match; map_rotation_deg = heading of the image top).

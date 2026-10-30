# Mission 27 data

Synthetic data made for the course (no real flight). Positions and errors are in metres, east and north (ENU).

| File | What |
|---|---|
| `static_fixes.csv` | 600 fixes of a receiver standing still on a surveyed pillar on a harbour quay, one every 10 s: `t_s`, and the error `e_m`, `n_m` of each fix from the surveyed point |
| `judge.json` | lab Steps 5–6: a predicted position after a GPS outage, its covariance, the covariance GPS states, and six candidate fixes A–F |
| `fusion.csv` | lab Step 7: a 400 s drive, one row per second: the true position, the GPS fix and the covariance it states (`gps_a` = σE², `gps_b` = cov(E, N), `gps_c` = σN², m²), the day-vision fix and the σ it states, and `vis_wrong` (1 = a wrong map match; use it only to score a gate, never to decide) |

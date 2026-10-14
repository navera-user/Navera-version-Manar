# Mission 28 — Kalman filter data

SIMULATED data, made for the course (not a recording, not NAVERA's output). Local metres; times in seconds.

| File | What |
|---|---|
| `heights.csv` | t_s, height_m, sigma_m, source, true_height_m: heights above the ground from three sources (`baro`, `gps-ground`, `vision`) at irregular times, each with the σ its source states. A height of 0.0 means "no reading". `true_height_m` is the truth: use it to grade a filter, never inside one |
| `reference_heights.csv` | t_s, height_m, sigma_m: the course's reference height filter (NAVERA Lite `Height1D`, default settings) after each row of `heights.csv` |
| `track.csv` | t_s, true_e, true_n, true_ve, true_vn, z_e, z_n, sigma_m: a drone flying along a coast, one second per row. `true_*` is the truth (m, m/s); `z_e`, `z_n` are the position fixes it received (empty: no fix at that second); `sigma_m` the σ per axis the fixes state |

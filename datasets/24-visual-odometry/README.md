# Mission 24 — visual odometry data

Synthetic downward camera frames drawn from OpenStreetMap data of Sousse, Tunisia (NAVERA's test area) with the
course's map renderer. Map data © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).

| File | What |
|---|---|
| `flight/frame_NNN.jpg` | 90 frames (320 × 240), one per second, of one flight. Heading-up: the top of each frame points to the drone's heading |
| `flight.csv` | frame, file, t_s, heading_deg (IMU), baro_alt_m (barometer): what the drone measured |
| `truth.csv` | frame, east_m, north_m: the true position, metres from frame 0. Use it to grade your odometry, never to compute it |
| `map_fixes.csv` | frame, east_m, north_m, sigma_m: positions from map matching (mission 23), where it worked |
| `info.json` | camera and flight facts |
| `pairs/a_NN.jpg`, `pairs/b_NN.jpg`, `pairs.csv` | 40 frame pairs for comparing odometers: group, turn_deg (heading change from a to b), true_dx_px, true_dy_px (where the ground point at a's centre appears in b, minus the centre) |

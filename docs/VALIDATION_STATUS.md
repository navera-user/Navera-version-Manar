# NAVERA — Validation status and known limitations

**Release 0.2 — field validation pending.** Last updated 2026-09-30.

This document states what has been measured, how, and what still has to be validated in
the field. Every number below comes from a run on the Jetson Orin Nano (bench, replay and
synthetic data). None of them comes from a real flight. Anything not listed here has not
been measured. Open engineering items are tracked in
[ENGINEERING_BACKLOG.md](ENGINEERING_BACKLOG.md).

## Summary

| Capability | Status | Evidence |
|---|---|---|
| GPS pass-through, fix arbitration, operator display | Working, bench-tested | Scripted tests, virtual serial port, simulated sensors |
| Automatic restart after a crash | Mechanism verified; not yet reboot-tested on a deployed unit | Node exit → launch exit, verified |
| Day vision (DINOv2 tile retrieval) | **Not accurate enough to replace GPS** | Median 442 m on labelled replay frames |
| Night vision (STHN homography) | Frames scaled and turned north-up from altitude, camera field of view and heading; motion gate; **not validated on real thermal** | 8–13 m median on synthetic frames (250–600 m, any heading); simulated night mission 6 m median |
| Celestial (astrometry.net) | Run end to end on simulated star fields; **coarse: bounded by the IMU attitude (~111 km per degree)** | 5.5–6.5 km with a perfect attitude; 24–119 km with a BNO085-class IMU |
| IMU dead-reckoning | **Not implemented** (IMU is liveness only) | — |

## Position output contract

Every position NAVERA publishes carries its source, whether it was measured or
dead-reckoned, and whether its uncertainty is known:

- **FIX**: a fresh measured position with a known uncertainty. Today only GPS reaches it.
- **DEGRADED**: a position is available, but its uncertainty is unknown or it is dead-reckoned.
  All vision and celestial positions are reported as DEGRADED.
- **NO_FIX**: no source is usable. No old position is re-sent as current.
- **OFFLINE**: on the operator view, the arbiter itself is not answering.

## Measurements

### Day vision (`day_pkg`, DINOv2 + tile retrieval against z17 satellite tiles)

Data: 33 labelled replay frames around Sousse (`vision_pkg/.../frames_gps`), 1120 tiles.

| Method | Median error | Within 300 m |
|---|---|---|
| DINOv2, search limited to 600 m around the previous true position | 442 m | 41 % |
| Random tile in the same circle (baseline) | 536 m | 17 % |
| Repeating the previous position (baseline) | 480 m | 31 % |
| DINOv2, whole map, no prior | 1 696 m | 12 % |
| Best tile available (resolution limit) | 107 m | 94 % |

In a simulated GPS loss (GPS for 3 frames, then 30 frames of vision), the error grew to
**4–5 km**. The similarity score stays high on wrong matches, so it cannot flag them.

Whole-map search, score discrimination (33 labelled frames, 4 within 300 m): scores of the
good matches (0.942–0.974) lie inside the range of the bad ones (0.823–0.972). The best
possible score threshold classifies 94 % correctly, against 88 % for "always reject". The
top-1/top-2 and top-1/top-5 gaps do no better than "always reject". **Whole-map search is
therefore disabled by default** (`allow_global_search: false`). Day vision reports no
position until it has a prior (the last GPS fix, or its own tracked matches).

**Conclusion:** the current day method must not be relied on as a GPS replacement. A
different matching approach (local feature matching against the satellite image around a
prior) is required and is the main open development item.

> The replay frames in `camera_pkg/data/day` do not show the places their CSV labels
> say. Earlier accuracy figures computed on them are not valid.

### Night vision (`night_pkg`, STHN one-stage)

- Before 2026-09-28 the model ran with **random weights**: the checkpoint keys never
  matched. Inputs, output reading and configuration were also wrong. It is now rebuilt
  exactly as trained (`weights/one_stage/config.json`), and it refuses to start if the
  weights do not load.
- Synthetic test: greyscale satellite crops stand in for thermal frames, at 2 locations.
  Known shifts of 100–150 m are recovered within **3–17 m**. One 320 m shift failed
  (238 m error), yet its consistency score was 0.93, so it was not flagged.
- GPU: ~225 ms per frame (fp32) vs ~1.5 s on CPU, identical positions (≤ 0.02 m). The Jetson
  PyTorch build cannot load CUDA linear algebra on JetPack 6, so the small homography
  solves run on the CPU automatically. fp16 brought no speed, memory or accuracy gain.
- **Scale (LOC-16, fixed 2026-09-30).** STHN expects the thermal image to cover 512 px of the
  satellite map at map resolution, north-up. Each frame is now resampled from the altitude
  (frame_meta) and the camera's horizontal field of view (`camera_hfov_deg`, required), turned
  north-up with the heading (frame_meta, else the IMU) and cropped to that footprint. Synthetic
  frames (grey renders of the map, 84° camera, prior 100–250 m off, 12 per case):

  | Altitude | Unscaled (before) | Scaled (now) |
  |---|---|---|
  | 250 m | 149–263 m median | 11–13 m median, p90 ≤ 32 m |
  | 400 m | 11–215 m | 8–11 m |
  | 600 m | 98–218 m | 8–11 m |

- **Minimum ground coverage and motion gate.** Tracking along a route at 300 m with a
  diagonal heading (the rotated frame covering 77 % of the reference) ran away to 2.4 km
  while the consistency stayed ~0.9. Frames covering < 85 % of the reference are refused
  ("fly higher": ≥ ~350 m with an 84° camera), and a fix implying a speed above
  `max_speed_mps` (30) is rejected. At 400 m: worst 13 m over 5 headings × 30 frames.
- **Mission simulator, drone at 400 m, night, GPS jammed:** 290 matches, median 6 m, p90
  11 m, max 37 m; with its positions given to the autopilot the drone kept flying its
  mission. Optimistic: the thermal images are grey renders of the same map.
- **The replay set cannot be used for night vision.** Its frames cover only ~190–300 m of
  ground, mostly sea (measured by correlation with the map at 0.12–0.2 m/px); the former
  4.7 km "drift" came from feeding them at the wrong scale. The node now refuses them
  ("footprint too small").

**Not validated:** real thermal imagery (which differs from grey satellite images), real
camera calibration, and any confidence calibration: the consistency score does not detect a
wrong match, the motion gate does.

### Celestial (`cn_pkg`)

- The latitude formula took a single root. Any camera facing the southern half of the sky
  produced positions hundreds to thousands of km off. It now computes both solutions and
  picks the one matching a prior position. If the prior can't tell them apart, no
  position is reported.
- Star coordinates are now corrected for precession to the date of observation. The
  error was about 0.4° in right ascension in 2026, i.e. tens of km.
- The node no longer uses a fixed test date or camera angles. Without a measured camera
  attitude (from the IMU), it reports no position.
- Round trip over 20 000 random camera pointings: 0 wrong positions, 1–2 % reported ambiguous.

- **End to end, 2026-09-30** (astrometry.net 0.89, Tycho-2 index 10–19), on star fields drawn
  from the Yale Bright Star Catalogue for a known position, time and attitude (60° camera):
  - the solver's fit was anchored near an image edge and came out ~1° off at the centre
    (111 km); `--resort` made it 46′. Now anchored at the centre, 4th-order fit: 2.9′;
  - astrometry.net's Python helpers use `np.bool` (gone in NumPy 1.26): nothing was solved;
    those steps are skipped;
  - attitude now from the IMU **at the frame's exposure** (it was read at processing time:
    degrees of error on a moving drone).

  | Camera attitude | Position error |
  |---|---|
  | perfect, camera up / at 75° | 5.5 km / 6.5 km (solve 3–13 s) |
  | tilt error 0.5° | 53 km |
  | tilt 0.5° + heading 2° | 91 km |
  | simulated BNO085-class IMU (0.3° / 1.5°), drone in flight | 24–119 km, ~50 km typical |

  Each degree of attitude error costs ~111 km: **celestial is a coarse fix** (region,
  GPS sanity), stated with `attitude_sigma_deg`, never a position to fly a mission on. A
  levelled (gimballed) star camera and a better attitude source are what improve it.

- **First real sky photo, 2026-10-01** (`ImageTest.jpeg`, 1200×1600, found on the data disk in an
  earlier project; no date, place or attitude recorded): with NAVERA's solver settings the image
  centre is identified in 20 s, **1.7′ from an independent earlier solution** (Siril/astrometry).
  This checks star identification on a real photograph; it cannot check a position (no time,
  place or attitude). It also exposed that the secondary `wcs` solver mode failed on real photos
  (`np.bool` in astrometry.net's line removal) — fixed.

**Not validated:** a real sky image with known time, place and attitude (position accuracy),
clouds and light pollution, a real IMU.

### Robustness (bench)

| Test | Result |
|---|---|
| GPS: line without checksum / bad checksum | Ignored |
| GPS: receiver in its own dead-reckoning (GGA quality 6) | Reported invalid |
| GPS: serial port unplugged | Node exits (code 1), launch exits, systemd restarts it every 10 s |
| Estimator: one measurement | Published once (it was re-published at 5 Hz) |
| Estimator: timestamp 60 s in the future | Refused ("clock problem") |
| Estimator: GPS flapping every 0.5 s | One source switch in 8 s, no zig-zag |
| Estimator: GPS jumps 5 km in 1 s (spoofing / glitch) | Refused ("possible spoofing"), re-accepted once plausible again |
| Estimator: GPS silent 4 s (jammed), then back 2 km away while vision (stated accuracy) disagrees ("jam, then spoof") | Refused; true GPS accepted as soon as it agrees with vision |
| Estimator: GPS pulled away gradually (40 m/s bench, 4 m/s simulator) while vision (stated accuracy) stays on the truth | Refused once it has disagreed beyond 5 σ + 50 m for 3 s (simulator: at ~160–200 m); status says "GPS refused: … drifting away" |
| Estimator: GPS jumps 2 km and stays there, vision with a stated accuracy sees the true position | Refused for as long as it lasts (150 s tested); the true GPS re-accepted 2 s after it returns. Before the fix the spoof was accepted after offset / max speed (33 s) and then the true GPS was locked out |
| Web: control without token / cross-site request / bad input | Refused (401 / 415 / 400) |

### Autopilot in the loop (ArduPilot SITL — simulation)

`navera_tools/run_sim.sh`: ArduPilot SITL (Copter 4.5, Rover, motorboat) whose only position
input is NAVERA's output; NAVERA's GPS driver reads a simulated receiver over a
pseudo-terminal. The world and the vision errors are simulated, so these are **behaviour**
results, not accuracy results.

| Scenario | Result |
|---|---|
| Drone, GPS OK, 120 m, 10–15 m/s | NAVERA error 1–4 m; autopilot position error 1–3 m |
| Drone, GPS jammed in flight, vision at the target accuracy (15 m σ, simulated) | Mission continues on NAVERA's vision fix; autopilot error 2–18 m for 2.5 min, no failsafe |
| Boat, 2 km GPS spoof for 150 s | Refused within 1 s; boat continues on vision (3–21 m) |
| Drone, GPS jammed 30 s then spoofed 2 km for 30 s | Spoof refused throughout; true GPS re-accepted 3 s after it returns |
| Drone, GPS spoofed by a slow drift (4 m/s) | Refused at ~160–200 m offset; the autopilot followed the drift to ~200 m, then recovered on vision without failsafe |
| Robot, GPS jammed, vision at today's measured accuracy (DEGRADED, withheld) | Autopilot loses its position → its own failsafe (HOLD); resumes when GPS returns |
| GPS jammed + camera failed | NAVERA: NO FIX → autopilot failsafe (Copter LAND, Rover HOLD) |

**With the real day vision** (`day_subscriber`, DINOv2) on simulated camera images, drone at
150 m (≈270 m footprint), 7.5 km route prepared with `prepare_area.py` (356 tiles), GPS jammed
in flight: vision searched a 600 m circle around the last GPS fix (18–21 candidate tiles) and
matched every frame; NAVERA's error 27–187 m, median match error 96 m. With its positions given
to the autopilot (stated accuracy 300 m), the drone continued the mission (autopilot error
27–209 m, one glitch warning, no failsafe); with NAVERA's default (not given), the autopilot
landed. **These accuracies are optimistic:** the camera images are cut from the same satellite
map vision matches against. The best-match score stayed at 0.95–0.98 for good and bad matches
alike, as on real data.

Integration defects found and fixed this way: no velocity sent (ArduPilot assumed zero or
stale velocity → EKF failsafe during take-off); vision fixes labelled 2D (ignored by
ArduPilot); the same fix repeated at 5 Hz; the spoofing gate above; positions forwarded on a
5 Hz timer while arriving at 5 Hz, which dropped or doubled messages — ArduPilot reported
"GPS not healthy" and refused to arm (the estimator and the output now act on arrival). The ArduPilot settings
this requires are in navera_output/README.md.

**QA campaign (2026-09-30)** — scripted missions with every fault, command and invalid input
(backlog §7). Two critical product defects found and fixed: (1) with the real vision, a GPS
spoof left NAVERA without any position and the drone landed — vision idled behind the spoofed
GPS and took the first spoofed fix as its search centre; it now takes its GPS reference from
the arbiter's vetted output and starts as soon as GPS is refused (re-test: 3/3 spoofs taken
over by vision, median 59–129 m, mission continued); (2) a celestial fix (±55 km) forwarded to
the autopilot moved its position by 125 km — positions coarser than `max_forward_sigma_m`
(1 km) are no longer forwarded.

### Long route (simulator, 2026-10-01)

Paris → Tunisia, 1768 km, mapped as ≤ 10 km great-circle legs: 79 775 tiles generated in
105 min (78 904 downloaded), 980 MB on disk. Day vision loads the model and the 80 000-tile
area in 30 s; per frame it compares the 21 tiles of its 600 m circle, as on a small area
(ranking 3–4 ms instead of 289 ms before the grid index); ~1.1 GB more memory in use (1.6 GB
left available on the 8 GB Jetson with the simulator running).

Flown with the real day vision from km 1755 (13 km before the end, uniform terrain near
Gabès), GPS jammed: 185 matches, **median 351 m, p90 853 m**, 44 frames rejected by the motion
gate (jumps of 360–570 m). With vision forwarded at ±300 m, ArduCopter's EKF failed safe
(LAND) after 45 s. Over textured ground (Sousse, same day) the median was 111 m and the
drone flew on. **Day vision is unreliable over uniform terrain** (desert, sea) — consistent
with the project report. Same 13 km, same protocol (GPS jammed 4 min):

| Flight | Rejected frames | Samples with no position | Autopilot failsafe |
|---|---|---|---|
| 80 000-tile area, ±300 m | 44 | — | 45 s |
| 536-tile area of the same place, ±300 m | 58 | 13 / 48 | 61 s |
| 80 000-tile area, ±500 m | 40 | 18 / 48 | 91 s |

The small area fails the same way: **the terrain is the cause, not the size of the map**. An
honest ±500 m delays the failsafe but cannot prevent it: about a third of the time day vision
has no acceptable match (jumps rejected by the motion gate) and nothing bridges the gaps —
no inertial dead-reckoning yet (FEAT-2). Cures: LOC-14 (local features around the prior) and
FEAT-2. (A first ±500 m run was discarded: an orphan estimator from the simulator was
competing with the real one — fixed in 6bff3d6.)

## Hardware results recorded in the project report (2026-06-02)

The final project report (`rapport_vFinal_Navera.pdf`, 83 pages, found deleted on the data disk)
holds the only results from the real sensors. No sensor recording (log, bag) was kept.

| Sensor | What the report records | Used here |
|---|---|---|
| GPS u-blox Neo-M8N, `/dev/ttyTHS1`, 9600 baud | a valid fix, `$GNRMC,141621.00,A,3544.04006,N,01034.55091,E,…`: 35.734 N, 10.576 E, M'saken — the test site | the receiver's multi-constellation `GN` sentences, with that position, go through `gps_node` over a serial line in `test_gps_serial.py`: accepted, position exact (2026-10-01) |
| Clock DS3231 | specifications only (±2 ppm); the reboot test of 2026-07-14 (−0.148 s vs NTP) is in the git history | — |
| IMU **GY-87** (MPU6050 0x68, QMC5883L 0x0D, BMP180 0x77) on I²C bus 7 | wiring and addresses only, no measurement | replaced by the **BNO085** (bus 1, 0x4A), the IMU on the box: driver rewritten and **verified live on the Jetson on 2026-07-13** — orientation, rates and accelerations at 50 Hz, the gyro responding to motion (commit b51aa5f; no values kept). Not yet checked: its heading reference with a known heading (IMU-3), its noise (covariances are datasheet values) |
| Camera Insta360 ONE R (nadir, fisheye corrected) | the 30-frame `sousse_flight` replay set (25 with GPS, 5 without) | the frames do not show the places their labels say (see Day vision) |
| Celestial, the sky photo `ImageTest.jpeg` | RA 106.1123°, Dec 37.6187°, solve 13 s | NAVERA's solver today: centre RA 106.109°, Dec 37.606° — **0.8′ from the report**, 1.7′ from Siril |
| Night (STHN) on the Jetson | 370 ms/frame (302–419), first 1030 ms, 0 CUDA crash on 5 frames — RGB frames, not thermal | consistent with the ~225 ms measured since on the GPU |

## Known limitations

1. **Accuracy is not established on real data.** No real flight has been recorded with
   camera, GPS and IMU together. This is the first thing to do with a vehicle.
2. **Day vision is not accurate enough** (see above).
3. **The IMU is not used for navigation** (liveness only). Dead-reckoning needs a heading
   and speed source.
4. **One pipeline at a time.** Day and night cannot both be loaded within 8 GB.
5. **Map coverage is Sousse only** (z13–z19 MBTiles). Other areas need their own map and
   tile cache. The imagery licence must allow offline commercial use.
6. **Vehicle output validated in simulation only** (ArduPilot SITL, above); not yet on a real
   autopilot, and not on PX4. ArduPilot needs `EK3_SRC1_VELXY = 0` / `EK3_SRC1_VELZ = 0` and
   one real GPS fix at power-on (navera_output/README.md).
7. **GPS spoofing:** a sudden jump beyond the vehicle's maximum speed (`max_speed_mps`, set
   per vehicle) is refused, and stays refused until an independent source with a **stated**
   accuracy (vision / celestial with a known covariance) confirms it. A GPS returning after an
   outage must agree with that source too ("jam, then spoof"), and a trusted GPS that drifts
   away from it for 3 s is refused (gradual spoofing, detected beyond 5 σ + 50 m). **All three
   protections need that independent source.** With vision of unknown accuracy — today's day
   and night vision — the gate falls back to reachability from the last good fix: a sudden
   jump is caught, but a patient or gradual spoofer is not.
8. **Security model:** DDS is limited to the box itself (`ROS_LOCALHOST_ONLY`). The web
   control API needs a token. The web interface itself is plain HTTP (no TLS).

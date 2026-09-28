# NAVERA — Validation status and known limitations

**Release 0.2 — field validation pending.** Last updated 2026-09-28.

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
| Night vision (STHN homography) | Maths verified at the trained scale; **drifts on off-scale frames**; not validated on real thermal | 3–17 m on synthetic shifts; 4.7 km median on replayed frames |
| Celestial (astrometry.net) | Geometry verified; **not run end to end** | 0 wrong positions in 20 000 simulated pointings |
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
- **Replayed "night" frames (30 frames, 1536×730, darkened satellite images — not thermal,
  scale unknown, ~480 m apart), GPS for 3 frames then lost:** tracking **drifts** —
  median error 4.7 km, max 9.7 km over 22 scored frames, the estimate advancing ~100 m per
  frame while the vehicle moves ~480 m. The consistency score stayed at 0.90–0.94
  throughout: **it cannot detect a drifting track.** Cause: the query is not rescaled to the
  satellite scale STHN was trained on (backlog LOC-16).

**Not validated:** real thermal imagery, real altitudes and headings, and any
confidence calibration. Night positions must not be trusted until the frame scale is
normalised from altitude and field of view (LOC-16) and the result is measured on real
thermal data.

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

**Not validated:** real sky images. astrometry.net is not installed on the development
unit, and the IMU attitude is not wired in yet.

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

Integration defects found and fixed this way: no velocity sent (ArduPilot assumed zero or
stale velocity → EKF failsafe during take-off); vision fixes labelled 2D (ignored by
ArduPilot); the same fix repeated at 5 Hz; the spoofing gate above. The ArduPilot settings
this requires are in navera_output/README.md.
| Web: control without token / cross-site request / bad input | Refused (401 / 415 / 400) |

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

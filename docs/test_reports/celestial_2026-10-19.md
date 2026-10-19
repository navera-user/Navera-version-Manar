# Celestial 360 (standing Insta360) — car field-test readiness, 2026-10-19

Branch `test/celestial-car` (from `feat/field-sky-test` 8a0a1d1). **Everything below is SIMULATION
(synthetic IMU, synthetic sky) unless marked otherwise.** Measured on the Jetson Orin Nano itself, but
while other jobs were running (load average 7–13 on 6 cores): times are pessimistic.

Tools written for this (all re-runnable):

| tool | what it does |
|---|---|
| `navera_tools/sim/car360_drive.py` | 500 Hz car (braking 0.1–0.3 g, curves 0.05–0.3 g, gentle 0.02–0.05 g speed changes, suspension pitch/roll 2.5/5 deg/g at 1.3 Hz, road vibration 10–30 Hz, body bounce 1–2 Hz, bumps, idle engine at the stops) feeding the **real** `insta360_usb.stopped()/gravity()` and the **real** `server.Field` on a simulated clock, with the 1.5 s stamp lag and 1.7 s arrival delay; stops of 20 s every ~150 s + a 25 s start stop. `--detector-only` scores every key frame (2/s). |
| `navera_tools/sim/celestial360_conditions.py --set car` | 67 cells × 6 seeds of `allsky.locate` at a stop with the measured 0.07° accelerometer residual, stated-sigma coverage, wrong accepts, 7 junk cells. |
| `navera_tools/bench/celestial_screen.py` + `campaign_celestial_real.sh` + `summarise_celestial_screen.py` | the **real-camera** screen campaign (lead runs it), see §7. |

## 1. Car motion end to end (test 1)

### 1a. Stillness flag vs truth, every key frame (`--detector-only`, 1068 frames/profile, 163 settled at rest)

Before = 8a0a1d1, after = fdc973e (0.2 s means, gyro gate on 0.1 s means, IMU coverage ≥ 90 %).
"usable" = stopped AND gravity accepted, i.e. a fix the server would trust.

| profile | usable at-rest frames before → after | moving frames called stopped (after) | of those 'up' > 0.3° off | stopped 'up' error p50/p90/max (after) |
|---|---|---|---|---|
| normal (idle 0.02 g @ 27 Hz) | 141 → 146 | 0 / 901 | 0 | 0.070 / 0.078 / 0.087° |
| rough road + idle 0.05 g | **30 → 146** | 0 | 0 | 0.071 / 0.084 / 0.097° |
| idle 0.05 g @ 27 Hz | **28 → 146** | 0 | 0 | 0.071 / 0.080 / 0.091° |
| idle 0.03 g @ 15 Hz | 138 → 146 | 0 | 0 | 0.070 / 0.079 / 0.086° |
| mount jitter 0.02° @ 10–30 Hz | **0 → 145** | 0 | 0 | 0.069 / 0.093 / 0.125° |
| smooth road | 145 → 147 | 2 | 0 | 0.071 / 0.079 / 0.089° |
| no gentle speed changes | – → 146 | 0 | 0 | 0.071 / 0.080 / 0.090° |
| slope 8° | 141 → 146 | 0 | 0 | 0.070 / 0.077 / 0.087° |
| IMU silent 6 s while driving | 141 → 146 | 0 | 0 | 0.070 / 0.078 / 0.087° |
| IMU silent 3.6 s through the last braking | – → 144 | 0 | 0 | 0.070 / 0.078 / 0.087° |
| stamp lag really 1.8 s / 1.2 s | 142/140 → 146/144 | 0 | 0 | 0.070 / 0.078 / 0.088° |
| **"glass" road (body motion 0.01°, road 0.003 g)** | 148 → 147 | **333 / 901** | **106** (up to 7.4°) | 0.074 / 2.39 / 7.43° |

- Braking/curve frames are never marked stopped on any realistic road model; the start/end of a stop
  are handled: the first ~1.5 s after the wheels stop (suspension rocking) and the last 0.5 s are not
  "stopped" (16–19 of 163 at-rest frames).
- IMU silence: before, 400 rows (0.8 s of the 2.5 s window) were enough to call "stopped"; now the
  window must be 90 % covered. The `imu_age` watchdog path (`no camera sensor data`) gives no fix.
- **Open risk (glass road):** an accelerometer+gyro cannot tell constant gentle acceleration from rest.
  Only on a very smooth road with almost no body motion (0.01° rms) is it fooled; our normal/smooth
  models are not. The real car's vibration is NOT measured. Mitigation shipped for the test: the
  phone's GPS speed is logged with every frame and `stopped_but_phone_moving` marks such fixes
  (referee only, never used to decide).

### 1b. Through the server (`car360_drive.py --profile normal`, 4 stops, real solves)

| | before (20 s cadence) | after (72688c8: also every 4 s while stopped) |
|---|---|---|
| trusted (stopped) fixes per stop | 1, 1, 1, 1 | **2, 4, 4, 4** |
| trusted fix error p50/p90/max | 7.8 / 8.6 / 8.8 km (n=4) | 7.6 / 8.6 / 8.8 km (n=14) |
| trusted within 3σ (σ ≈ 33 km) | 4/4 | 14/14 |
| trusted fix taken while actually moving | 0 | 0 |
| moving fixes (flagged), error p50/p90/max | 25.7 / 469 / 623 km (n=13) | 19.2 / 482 / 826 km (n=15) |
| moving within 3σ (σ ≈ 557 km) | 13/13 | 15/15 |

The ~8 km of a trusted fix is the injected 0.07° accelerometer residual (the measured value), i.e. the
error budget is the IMU, not the stars.

### 1c. Honest sigma of moving fixes (055ef27)

6872 moving key frames that passed every gate (13 profiles): 'up' up to **10.6°** off, because the 1–2 Hz
body bounce moves the 1 s vertical mean by 0.01–0.02 g and hides up to ~0.2 g of braking from the
|a| = 1 g test. With `MOVING_ATTITUDE_SIGMA_DEG` 3.0, 26/6872 fell outside 3σ; 4.0 → 0; set to **5.0**
(σ ≈ 557 km; margin for the ~14° the gate can let through). Moving fixes are for logging only.

## 2–6. Sky, distractors, calibration, gate (`celestial360_conditions --set car`, 6 seeds/cell)

All at a stop with the 0.07° accelerometer residual; σ = the server's (0.3° ⊕ fit) ≈ 33 km.
WRONG = > 50 km. 359/360 real-sky frames solved; **junk frames: 0/42 accepted (wrong-accept rate 0)**.

| group | cells | solved | median / p90 km | within 3σ | note |
|---|---|---|---|---|---|
| star limit 2.0 / 2.5 / 3 / 3.5 / 4 / 5 | 6 | 36/36 | 7.9–8.4 / 8.0–9.1 | 36/36 | mag ≤ 2 still 16 matched stars |
| H.264 key frame qp24 (~640 kB), qp28 (~150 kB), qp32 (~12 kB) at mag 2.5–3.5 | 5 | 30/30 | 7.8–7.9 / 8.0–8.2 | 30/30 | |
| dim stars (−2.5/−3.5 mag, mag-3 at SNR ~5) + H.264 qp24/28/32 | 5 | 30/30 | 7.9–8.2 / 8.0–8.8 | 30/30 | qp32 + dim: 46 matched |
| gain (read noise 8), exposure −1 mag | 2 | 12/12 | 7.8 / 8.1 | 12/12 | |
| moon full high / low / quarter / crescent / below horizon / + flare | 6 | 36/36 | 7.8–8.0 / 7.9–8.1 | 36/36 | |
| city glow 20/60, twilight | 3 | 18/18 | 7.7–7.8 / 8.0–8.1 | 18/18 | |
| clouds 20/50/80 %, cirrus 1/2 mag | 5 | 30/30 | 7.8–8.3 / 7.9–8.7 | 30/30 | clouds 80 %: 18 matched |
| obstruction 10/25/40°, camera inside the car (roof below 45°) | 4 | 24/24 | 7.8–7.9 / 7.8–8.0 | 24/24 | inside: 24 matched |
| planes, satellites, drones, birds, insects, hot pixels, lamps, urban+moon+clouds+planes | 8 | 48/48 | 7.7–8.0 / 7.8–8.3 | 48/48 | |
| tilt 15 / 25 / 35 / 45° (camera or slope) | 4 | 24/24 | 7.6–7.9 / 7.8–8.0 | 24/24 | |
| latitude 0 / 20 / 50 / 65 / −35 | 5 | 30/30 | 7.7–7.9 / 7.8–8.1 | 30/30 | |
| right lens f −5.5 % / −3 % / +3 % | 3 | 18/18 | 7.8 / 12.0 / 11.2 ; p90 9.0 / 18.8 / 30.9 | 18/18 | right lens loses ~half its matches |
| right lens k1 +0.02 | 1 | 6/6 | 15.5 / 22.5 | 6/6 | |
| right lens centre 10 px (+ f −5.5 %) | 2 | 11/12 | 7.7 / 10.3 | 11/11 | 1 refused (rms 0.28°) |
| clock +10 / +30 / +60 s | 3 | 18/18 | 6.9 / 9.6 / 19.4 ; p90 10.8 / 17.7 / 28.6 | 18/18 | 0.46 km/s × cos(lat) |
| **lens-to-IMU mount 0.5 / 1 / 2°** | 3 | 18/18 | p90 **63 / 119 / 230 km** | **6/6, 0/6, 0/6** | **no star check sees it; 15 'wrong'** |
| JUNK: noise, lit overcast, 60/120 random points, clutter+insects+drones, inside-car LEDs, H.264+60 points | 7 | **0/42** | – | – | wrong-accept 0 |

False-reject rate of the gate on real-sky frames: 1/390 (right-lens centre 10 px, rms 0.28°).
All lenses in these runs are the calibration files as of 10:33 today (left 2026-10-17, right 2026-10-19).

**Calibration is now the dominant risk, not the sky:** a lens-to-IMU tilt of 1° costs ~111 km on every
trusted fix and is invisible to every gate (the stars fit the camera's rotation perfectly; only 'up' is
wrong). See §5.

## 5. Mount-angle recovery (`reprocess360 --fit`)

Drive with the true lenses tilted 1.0° against the IMU (`car360_drive.py --profile mount1 --cycles 3`):
16 stopped fixes all 112.5–113.6 km off (0/16 within 3σ — the stated σ cannot know), 4 per stop.
`reprocess360 <folder> --fit 5`:

| | before (8a0a1d1) | after (5361b10) |
|---|---|---|
| frames used for the fit | first 5 solved, moving ones included | first 5 **stopped** |
| reported mount angle | 124.7° (free turn about 'up') | **1.015°** (tilt only) |
| calibrated error, later frames (median / p90 / max) | 3.7 / 177 / 766 km (moving mixed in) | **0.7 / 1.3 / 1.7 km** (11 stopped) |
| no mount error (profile normal) | – | fits 0.071° (= the injected accelerometer residual), 7.5 → 0.7 km |

So 5 stopped fixes (≈ 2 stops) are enough to measure the mount — **in simulation, with a constant
accelerometer residual**; the real residual may drift with temperature and handling.

## 7. Real-screen campaign (for the lead; not run by me — camera and screen are in use)

`celestial_screen.py` now has 19 drawable conditions with an amount (`name[:amount]`, `+` combines,
`worst`), applies `allsky.accept()` exactly as `locate` does (p_chance + retry on the 25 brightest) and
logs `accepted / gate_why / correct / wrong_accept` per case. Drawing verified offline (162 screens saved
as PNG and inspected). Ideal-camera baseline (`--offline`, the drawn screen solved directly): 162 cases,
134 right, 26 wrong identifications, **0 wrong accepts**, 8 false rejects (mag-3 fields with distractors).
Note: the bench uses its own peak finder (not `detect_spots`), so cloud edges / rain / insects flood it
with up to 60 spots — expect low acceptance there, not wrong accepts.

Run (dark room, after `lens_calib_screen.py --save`, ~15 min):

    navera_tools/bench/campaign_celestial_real.sh ~/navera-field/screen_2026-10-19

Wind is scored with a tolerance of 1° + 1.5 × amplitude (the shake really moves the drawn field).

## 8. Throughput on the Jetson (load average 7–9 from other jobs)

| case | `allsky.locate` | live spot detection (every loop second) |
|---|---|---|
| mag ≤ 3 | 2.1 s (max 2.7) | 0.7 s |
| mag ≤ 5 | 4.1 s | 0.7 s |
| urban clutter | 1.6 s | 0.6 s |
| junk, 120 points (worst) | 5.3 s | 0.6 s |
| first solve (5 focal scales) | 6.6 s (max 7.9) | 0.6 s |

In the drive run the mean solve was 3.0–3.2 s (max 9–17 s under load): the 4 s stop cadence keeps up
(3–4 trusted fixes per 20 s stop). The H.264 decoder's CPU share was not in these runs.

## Operator checklist (field night)

Run `python3 -m navera_tools.field.watch` every few minutes. It now prints a `360:` block.

**Before driving**
- `camera device: … USB 360 mode (2e1a) present`. If absent: camera not in Android USB mode.
- Page step 2: "Camera steady" green. Step 3: stars green.
- After the first stop: event `lens_focal_found` with `f_scale` within 0.97–1.03 (both lenses are now
  calibrated; far from 1.0 means a lens file problem — note it).

**While driving — believe only `USE` fixes**
- `USE (stopped) error vs phone`: expect ~10 km median (sim: 8 km with the measured IMU). A constant
  50–250 km on every USE fix = the lens-to-IMU mount angle → keep driving, it is fixed afterwards by
  `reprocess360 --fit`.
- `IGNORE (moving)`: any error up to ~1500 km is normal; never quote these.
- Each 20 s stop should add 2–4 USE fixes. 0 at a stop: look at `not solved because` (sky, too few
  stars, `camera moving or turning` = the engine/mount vibrates the camera too much → note it).
- `WARNING: … called stopped while the phone moved` → those fixes are wrong-flagged; write a note
  (road type, speed). One or two: ignore them. Many: the stillness test is fooled on this road.
- `WARNING: … no camera IMU data` → the IMU stream is silent; the server reconnects after 10 s. If it
  persists > 1 min, restart the server.
- `solve time` median > 6 s → Jetson overloaded/hot.

**Flags meaning "ignore this fix"**: `stopped=false` (IGNORE moving), `stopped_but_phone_moving=true`,
`solved=false` (any `why`), sigma_km > 100. **Never a reason to ignore**: a large error on a moving fix.

**After**: `python3 -m navera_tools.field.analyze <folder>` (trusted vs flagged apart), then
`python3 -m navera_tools.field.reprocess360 <folder> --fit 5` (mount angle from stopped frames only).

## Open problems

| # | where | evidence | impact | suggested fix |
|---|---|---|---|---|
| 1 | lens-to-IMU mount angle (`sky360.R_LEFT/R_RIGHT` assumed exact) | matrix: 1° → p90 119 km, 0/6 within 3σ; no gate sees it | every trusted fix biased; stated σ 33 km is optimistic until measured | measure on the first clear night with `reprocess360 --fit` (stopped frames, §5) and store it in the lens file; until then quote σ ≥ 0.3° ⊕ mount |
| 2 | `insta360_usb.stopped()` | glass-road profile: 333/901 moving frames "stopped", 106 with 'up' 0.3–7.4° off | wrong trusted fixes up to ~800 km on a very smooth road with gentle acceleration | field test: the phone referee flag (done). Product: compare the accelerometer with a gyro-stabilised long-term mean (mean specific force since the last stop = gravity + v/T), or a below-horizon frame-difference standstill test |
| 3 | real vibration levels | all vibration/idle amplitudes are assumed | decides how many stops yield fixes | log the IMU during the drive (raw rows) and replay through `car360_drive`'s detector |
| 4 | left lens file vs brief | `~/.navera_sim/insta360_usb_lens.json` left f 563.23 / k1 0.052, the brief says 577.09 / 0.038 (the right lens is 576.68 / 0.039) | if the left values are stale, a 2.4 % f error = ~10–30 km (right-lens cells) | lead to confirm which left calibration is current |
| 5 | single `f_scale` for both lenses | right-lens ±3 % f: 11–12 km median, p90 19–31 km | moderate | per-lens focal refinement from matched stars (`locate`) |
| 6 | bench peak finder | offline: clouds/rain/insects give 60 spurious spots | lower acceptance on the screen than in the field | use `detect_spots`-style blob filtering on the pinhole view |
| 7 | throughput measured under load, without the decoder | §8 | first solve 6.6–8 s | re-measure with the live stream on a quiet Jetson |

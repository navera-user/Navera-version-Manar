# Real-sky celestial test: runbook (30-60 min drive, one chance)

Operator: opens the app, START, drives, END. Claude watches over the internet (phone hotspot) and
runs expert agents on the data while the car drives. Everything the camera sends is recorded raw
(`<test>/raw/`, ~380 MB/min), so anything missed live is redone afterwards with `replay360`.

## Goal and pass criteria

| Measure | Target | Why |
|---|---|---|
| Trusted (stopped) fixes | >= 20 | enough to calibrate and to judge |
| Tilt-corrected error, stops after the calibration | median <= 5 km | simulation 1.2 km, screen 1-6 km |
| Trusted fixes > 50 km | 0 | a wrong trusted position is the worst outcome |
| Raw recording | 0 drops, whole drive | everything can be replayed |

## Choose the night

A bright moon washes out the faint stars the camera's video barely shows, and the sun must be 15 deg below the
horizon. Drive only when it is dark AND the moon is down:

    python3 -m navera_tools.field.sky_window --start 2026-10-31 --nights 7    # offline; Tunis by default

On 2026-10-20 it printed, local time: 31 Oct 18:40-22:25, 1 Nov 18:35-23:35, 2 Nov 18:35-00:45, 3 Nov
18:35-01:55, 4 Nov 18:35-03:00 (24-27 Oct: none, full moon on the 25th). Check the cloud forecast for the
same hours; scattered cloud is handled, overcast gives no fix.

## The day before

1. Rehearsal: 10 min, any clear night, camera on a balcony or a parked car (START, wait, END).
   Checks the real star count, the exposure, the solve and the app on the operator's phone.
2. The Jetson joined the operator's hotspot once (it then rejoins alone); the car powers the Jetson.
3. Claude: `e2e_check --selftest`, `--live`, disk >= 100 GB free, lens and IMU calibration files present,
   `tailscale funnel status` shows 8443, camera USB mode Android.
4. Battery clock (F27, optional for this test, needed for the product offline): if the DS3231 module is wired
   (below), set it once while the Jetson has internet: `python3 -m navera_tools.field.rtc_clock --set-from-system`
   (refused unless NTP-synchronised), then `python3 -m navera_tools.field.rtc_clock` must print `'ok': True`
   and an offset within 1 s. The service must be restarted to start reading it (`sudo systemctl restart
   navera-field`, the user). The page's checks then show "Battery clock (DS3231)".

### DS3231 wiring (Jetson Orin Nano 40-pin header, I2C bus 1 — shared with the BNO085 at 0x4A)

| DS3231 pin | Jetson header pin | Signal |
|---|---|---|
| VCC | 1 | 3.3 V (not 5 V: the module's pull-ups then hold SDA/SCL at 3.3 V, safe for the Jetson) |
| GND | 6 (or 9) | ground |
| SDA | 27 | I2C1_SDA (bus 1) |
| SCL | 28 | I2C1_SCL (bus 1) |
| SQW, 32K | not connected | |

A CR2032 in the module's holder keeps the time with the Jetson off. Common ZS-042 boards charge the cell through a
resistor and diode meant for a rechargeable LIR2032: with a plain CR2032, remove that resistor (or the diode).
Check: `i2cdetect -y -r 1` shows `68` (and `57`, the module's EEPROM). No root is needed to read it (the user is in
the `i2c` group). The star time order is then: phone clock > DS3231 > NTP; every frame records `time_source` and
`rtc_minus_phone_s` (the battery clock's real error against the phone).

## The drive (operator instructions add one thing: stay parked 3 min after START and before END)

| Time | Car | Claude |
|---|---|---|
| T-15 | Jetson on in the car, camera on the roof | STATUS.txt: camera, IMU age < 1 s, raw ready, phone GPS |
| T0 | START, parked 3 min | first frames: star count, sky, background; first solve (focal search), first fixes |
| T+3 | drive, stop 20 s every 2-3 min | each minute: STATUS.txt + `watch.py`; ALERTS.log |
| T+10 | | live lab round 1 (below), the 12 calibration samples should be in (event `tilt_calibrated`) |
| T+25 | | live lab round 2: re-score, apply a winner if any |
| T+40 | | round 3 (if the drive is 60 min) |
| end | parked 3 min, END | final static fixes; supervisor runs reprocess360 |

## What Claude watches, and what to do

| Symptom | Likely cause | Action |
|---|---|---|
| IMU age > 2 s | camera IMU feed silent (F14) | the driver restarts it after 1.5 s; the server reconnects after 10 s; if it persists, restart the service (the test resumes in the same folder) |
| no frames > 60 s | camera stream stopped / USB | check `camera_error`; restart the service |
| stars < 12 in a clear sky | video exposure / detector threshold | live lab: detection variants on the stops; `livectl set` the winner |
| no fix at stops, many spots | junk (lights, reflections) | live lab: `allsky.MAX_RMS_DEG`, max spots, min altitude variants |
| fixes refused "chance" | too few matched stars | `allsky.MIN_MATCHED` stays; check focal (`f_scale`) |
| stopped fixes with the phone moving | stillness fooled (D12) | they are flagged and ignored. Since 2026-10-22 the server adds the long-window test (cn_pkg/standstill.py: 'up' must not have moved without the camera turning in the last 10 s, \|a\| at rest); `stillness.why` says which test refused. Live knobs: `standstill.LONG_S`, `standstill.DIR_TOL_DEG`, `Stillness.LONG_CHECK=0` (driver test only) |
| stops give no stopped frame for ~10 s | a very gentle roll to the stop (no braking): the long window refuses it on purpose | ask the driver to brake normally; nothing to change |
| constant 50-250 km on every trusted fix | lens-to-IMU mount angle (D11) | expected before the calibration; after `tilt_calibrated` the corrected error must drop |
| event `tilt_fit_refused` | the calibration samples disagree (no clear majority) | nothing: outliers are left out and do not count; it keeps learning until 12 agree (or 24 taken). `residuals_deg` in the event shows the bad samples |
| corrected error grows with time | calibration bad (moving sample) or temperature | live lab: recalibrate on later stops; compare |
| solve time > 6 s | Jetson hot / busy | nothing else runs on the Jetson during the test |
| phone GPS age > 10 s | screen off / app closed | the app shows a red message; the samples are buffered |

## What the drive must measure (F19) and where it is logged

Simulation assumed these; the night measures them. Every 360 frame record (`frames.jsonl`) carries them, and
`analyze.py` (report.md "Drive measurements") sums them up; the raw recording keeps the full 500 Hz IMU for
anything else.

| Measure | Field in each frame record | Why |
|---|---|---|
| Vibration at rest (idle) and driving: accelerometer above ~5 Hz, 0.2 s means' spread, gyro rms | `imu_vib` (`acc_hp_rms_g`, `acc_lf_std_g`, `gyro_rms_dps`, `mag_mean_g`) | the car simulation's idle 0.02 g / road 0.03 g / bounce 0.02 g are guesses; they set the stillness thresholds |
| Stopped flag against the phone's speed: false stops, lost stops; the driver's test vs the long-window test | `stopped`, `stillness` (`driver_stopped`, `why`, `up_change_deg`, `excess_g`, `expected_g`), `phone_speed_mps`, `stopped_but_phone_moving` | D12 was measured on a simulated glass road only |
| Trusted fixes per stop (20 s stops) | from `stopped`, `solved` and the phone speed | the simulation gave ~3; it decides how long the driver must stop |
| Solve time on a quiet Jetson, with its load and temperature | `solve_s`, `host` (`load1`, `temp_c`, `mem_avail_mb`) | 6.6-8 s first solve was measured under load; quiet = `load1` < 2 |
| Image standstill measure (logged only, not used) | `ground_change`, `ground_dt_s` | whether lit ground features can tell a gentle cruise from a stop at night |
| Time source and the battery clock's error | `time_source`, `rtc_minus_phone_s` | F27 |
| Camera stream health | `cam_health` (`reconnects`, `imu_restarts`, `imu_age_s`) | F14: how often the IMU feed needs a restart in the car |
| Mount tilt learned | events `tilt_calibrated` / `tilt_fit_refused` (`residuals_deg`, `rejected`) | D11 |

Live lab rounds load the Jetson: run them while the car drives, not during a stop, so that some stops give a
quiet-Jetson solve time (`host.load1` < 2 tells them apart in the report).

## Live lab rounds (agents, while the car drives)

`live_lab.py <test> --variant ...` copies what is recorded so far and replays it with each variant
against the phone's GPS (read-only on the live test). One agent per question:

1. Stars: detection threshold / max spots / min altitude variants on the stop frames: more correct
   matches, no wrong.
2. Geometry: tilt calibration from different stop subsets (first 12, every other stop, last 12):
   stable within 0.05 deg? per-lens focal from the matched stars.
3. Timing: frame stamp lag (1500 ms measured on the screen) re-fitted on real stops (the error must not
   depend on how the car stopped).
4. Stillness: the stopped flag against the phone speed: missed stops, fooled moving frames.

A variant is applied live (`livectl set`) only if it wins on the real data with 0 wrong fixes.
Every change is logged (event `live_param`) and the raw recording keeps the original stream.

## After END

Six agents in parallel on the raw recording: stars, geometry (mount, lens), timing, stillness,
accuracy (every stop, raw and corrected, against the phone), full replay with every improvement.
Results: report, problems doc updated, numbers in `docs/VALIDATION_STATUS.md` (real sky, measured).

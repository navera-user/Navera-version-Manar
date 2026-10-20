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
| stopped fixes with the phone moving | stillness fooled (D12) | they are flagged and ignored; tighten the stillness window if frequent |
| constant 50-250 km on every trusted fix | lens-to-IMU mount angle (D11) | expected before the calibration; after `tilt_calibrated` the corrected error must drop |
| corrected error grows with time | calibration bad (moving sample) or temperature | live lab: recalibrate on later stops; compare |
| solve time > 6 s | Jetson hot / busy | nothing else runs on the Jetson during the test |
| phone GPS age > 10 s | screen off / app closed | the app shows a red message; the samples are buffered |

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

# NAVERA field sky test

A phone, the Jetson and the camera are enough. The phone is the dashboard and the truth
(its GPS); the Jetson runs the real celestial solver and saves everything.

## For the person doing the test: START, drive, END

1. Install the app once: open the link in Chrome (Android: menu, "Add to Home screen") or Safari (iPhone: Share,
   "Add to Home Screen"). The "NAVERA Sky" icon opens the test from then on, even before the Jetson answers
   ("Waiting for NAVERA...").
2. Press START (the phone asks once for location and motion). Recording starts whatever the sky: camera,
   steadiness, stars and positions are only shown as status lines; a red banner appears only when the
   operator must act ("Turn on location", "Keep this app open").
3. Drive; stop 20 s every 2-3 minutes. Press END (confirm): "Test saved: <name>. Thank you."

The owner's Results are behind the small "Owner: results" link at the bottom of the page.

Two ways to connect (both printed at start in `~/navera-field/LINK.txt`):

* **Phone hotspot with mobile data** (best): the Tailscale link (`NAVERA_FIELD_PUBLIC_URL`, trusted certificate,
  the app works offline, Claude can watch live).
* **Same Wi-Fi, no internet**: `https://<jetson>.local:<lan port>/field?k=...` or the Wi-Fi IP, with the Jetson's
  own certificate (the phone warns once). Behind Tailscale (`NAVERA_FIELD_PLAIN=1`) this LAN listener is on
  `NAVERA_FIELD_LAN_PORT` (8445), otherwise on `NAVERA_FIELD_PORT`. The offline app shell (service worker)
  only works on the trusted link.

## Watching and checking

* `supervisor.py` (started by `run_field.sh`): every 20 s `~/navera-field/STATUS.txt` (one screen) and
  `ALERTS.log` (each problem when it appears, with what to do; when it clears). Read-only. After a 360 test
  ends: `reprocess360 --fit 12` once, output in `~/navera-field/<test>_reprocess360.txt`.
* `python3 -m navera_tools.field.e2e_check --selftest`: a whole test over HTTPS on a synthetic 360 sky (free
  port, never the real camera, no DISPLAY), cron-ready; `--live https://127.0.0.1:8445` reads the running
  server's health only. Verdicts in `~/navera-field/E2E.log`.
* `NAVERA_FIELD_CAMERA=none` runs the server without any camera (page checks).

## For the owner

* Results tab of the same page: verdict, error, problems with fixes, frame by frame, zip download.
* Files: `~/navera-field/<date_time>/` (`NAVERA_FIELD_DIR`). `phone.jsonl` (truth), `frames.jsonl`
  (every frame: stars, sky, solver answer, error), `events.jsonl` (steps, notes), `frames/*.jpg`,
  `report.json`, `report.md`. Written every second; a power cut loses at most the last second.
* Re-read a test with new rules: `python3 -m navera_tools.field.analyze <folder>`.
* Remote: the Jetson has Tailscale; `https://<tailscale-ip>:8443/field` works from anywhere on the tailnet.
* Before the first night: `python3 -m navera_tools.field.selftest` (known sky photo through the whole chain).

## 360 mode (the default when the Insta360 is in USB mode "Android")

The server picks it by itself (`NAVERA_FIELD_CAMERA=auto|360|strip`). Set the camera's USB mode to
**Android** in its menu; the udev rule `/etc/udev/rules.d/99-insta360.rules` (MODE 0666 for vendor
2e1a) lets the server open it.

* `insta360_usb.py`: the full 3840x1920 dual fisheye and the camera's own accelerometer/gyro (500 Hz)
  over USB, no SDK (the protocol of Insta360's app). Key frames only: 2 frames/s, 1.5 s behind the
  scene (measured on the screen, corrected in the time used).
* Gravity comes from the camera itself (6-position calibration in `~/.navera_sim/insta360_usb_imu.json`):
  no phone tilt, no heading, any camera attitude. The camera only has to be still for a second.
* `allsky.py`: bright stars in both circles above the horizon, identified like a star tracker,
  the zenith through the camera's orientation → latitude, longitude. Works with stars to magnitude 2.5
  (simulated). The lens focal length is found on the first identified frame and kept.
* Every full frame is saved with 'up', |a| and the rotation rate: `python3 -m navera_tools.field.reprocess360
  <folder> --fit 5` scores the test, measures the sensor-to-lens angle on the first 5 frames with the phone's
  GPS and applies it to the rest (simulated 0.4 degree misalignment: 36 km → 0.5 km); `--resolve` solves the
  saved images again.
* Before a night: `python3 -m navera_tools.field.selftest360` (synthetic standing-camera sky through the whole server).
* Not measured yet: how many stars the video exposure keeps on a real night, the sensor-to-lens angle
  (stated ±0.3 degrees = 33 km until the first frames measure it), lens distortion beyond the focal length.

## Raw recording and replay (360 mode)

From START to END the server writes every packet the camera sends (all video frames, the 500 Hz IMU, the rest)
to `<test>/raw/raw360_NNNN.bin` (1 GB files; a writer thread, so the camera is never slowed by the disk; lost
packets are counted and the supervisor alerts). The whole test can then be run again offline through the real
server code with any setting changed:

    python3 -m navera_tools.field.replay360 <test folder> --info                      # duration, MB/min, frames
    python3 -m navera_tools.field.replay360 <test folder> [--set server.STOPPED_SOLVE_GAP_S=1] [--every-frame]
    python3 -m navera_tools.field.replay360 <test folder> --export-frames DIR --stops-only   # lossless PNG + index.csv

Keep at least 10 GB free per hour of drive (STATUS.txt shows the size).

## Autolab: expert rounds during the drive (360 mode)

`run_field.sh` also starts `autolab.py`. Once a 360 test records it needs nobody (no Claude session, no
internet): at T+10, T+25 and T+40 min it replays the last 5 min of the raw recording (`live_lab`, read-only on
the live test, one replay at a time at nice 19, waiting while the load is above 4 or solves are slow) with the
settings in use and two preset variants (`autolab.VARIANTS`: star detection threshold, spots given to the
identification, stars needed, stillness test, residual gate; never the tilt calibration). A variant is applied
live (`live_params.json`, by "autolab") only with MORE trusted fixes, median not worse (+0.5 km), p90 not worse,
no fix > 50 km and no more fixes outside 3 sigma; one change per round; a change that later scores worse than
the defaults is reverted; at END a report-only round runs and any change is removed. Each round: an `autolab`
event, `<test>/autolab_round_N.md`, a line in `AUTOLAB.txt` (shown in STATUS.txt) and `ALERTS.log`.
Off: `NAVERA_AUTOLAB=0` or `touch ~/navera-field/autolab_off`.

## What it measures, and what it does not

* Measures the celestial METHOD with this camera: star detection, plate solving, the position, against the phone's GPS (about 5 m).
* It does not run the ROS box (estimator, outputs). It calls the same solver code on the same kind of frame.
* The camera points at the zenith: the position then needs no heading. Each degree the camera is off
  vertical moves the answer 111 km unless the tilt is corrected; the phone's tilt corrects it (0.5 degrees assumed, unmeasured).
* One second of clock error is 0.46 km. The star time follows the product's order (`navera_common/trusted_time.py`):
  NAVERA's GPS anchor (`NAVERA_FIELD_GPS`, off by default) > the autopilot's SYSTEM_TIME (`NAVERA_FIELD_MAVLINK`, off
  by default; must agree with the anchor within 1 s) > the DS3231 (`NAVERA_FIELD_RTC`, read when wired) > the phone's
  clock > NTP; none: no solve. The page's "Star time" line shows the source and its 1-sigma (`time_feeds.py`,
  `docs/field/celestial_test_runbook.md`).
* All limits (12 stars, 1 degree level, 0.5 s clock) are first guesses until a real night calibrates them.

## What counts as a star

`cn_pkg/cn_pkg/star_detect.py`. A spot is a star only if it is a small round compact point, on flat dark
sky (its ring looks like sensor noise), not crowded, not on a line of spots, and seen again in the next frames
where the star pattern says it should be. Everything else is named: hot pixel, trail (aircraft, satellite),
Moon/planet/lamp, glare, structure (text, edges, objects), crowded, fixed on the sensor (dirt), moves against the stars.
A frame that is mostly structure is "blocked": no star in it is counted.
Measured on a real sky photo: keeps 82 % of the stars the solver matched to the catalogue, and a room with a
screen full of text gives 0 stars.

## Start at boot (once, from the owner account)

    sudo cp navera_tools/field/navera-field.service /etc/systemd/system/
    sudo systemctl enable --now navera-field
    tailscale funnel --https=8443 --bg http://127.0.0.1:8444     # makes the operator link work from any phone

The link (with its secret key) is then in `~/navera-field/LINK.txt`. Delete `~/navera-field/access_key.txt` and restart for a new one.

## If the network drops

The Jetson keeps recording on its own disk. The phone page keeps its GPS/tilt readings while offline (up to 2 hours), shows "Connection lost - keep driving", and sends them with their original times when the link is back (`/api/phone_batch`), so the truth has no hole. Frames taken while the Jetson itself has no internet are saved as usual.

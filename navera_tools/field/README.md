# NAVERA field sky test

A phone, the Jetson and the camera are enough. The phone is the dashboard and the truth
(its GPS); the Jetson runs the real celestial solver and saves everything.

## For the person doing the test (5 steps, the page walks you through them)

1. On the Jetson: `navera_tools/field/run_field.sh` (or it starts by itself at boot, see below).
   It prints an address like `https://192.168.43.5:8443/field`.
2. Phone on its own hotspot, Jetson connected to it. Open that address on the phone.
   The phone warns about the certificate once: Advanced, continue.
3. Follow the page: connect, mount (camera straight up, phone flat beside it), check the sky, drive, finish.
4. Nothing to save by hand. The test is saved on the Jetson as you go.

## For the owner

* Results tab of the same page: verdict, error, problems with fixes, frame by frame, zip download.
* Files: `~/navera-field/<date_time>/` (`NAVERA_FIELD_DIR`). `phone.jsonl` (truth), `frames.jsonl`
  (every frame: stars, sky, solver answer, error), `events.jsonl` (steps, notes), `frames/*.jpg`,
  `report.json`, `report.md`. Written every second; a power cut loses at most the last second.
* Re-read a test with new rules: `python3 -m navera_tools.field.analyze <folder>`.
* Remote: the Jetson has Tailscale; `https://<tailscale-ip>:8443/field` works from anywhere on the tailnet.
* Before the first night: `python3 -m navera_tools.field.selftest` (known sky photo through the whole chain).

## What it measures, and what it does not

* Measures the celestial METHOD with this camera: star detection, plate solving, the position, against the phone's GPS (about 5 m).
* It does not run the ROS box (estimator, outputs). It calls the same solver code on the same kind of frame.
* The camera points at the zenith: the position then needs no heading. Each degree the camera is off
  vertical moves the answer 111 km unless the tilt is corrected; the phone's tilt corrects it (0.5 degrees assumed, unmeasured).
* One second of clock error is 0.46 km.
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

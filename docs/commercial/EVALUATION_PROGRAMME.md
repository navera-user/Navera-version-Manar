# NAVERA evaluation programme — for pilot customers

The first customers test NAVERA on their own vehicles, with IRIS's support, before full
commercial release. This document describes the kit, the process, the acceptance test and the
report.

## 1. What the customer receives
| Item | Notes |
|---|---|
| NAVERA box (Jetson Orin Nano, installed with release 0.5.x) | serial number + `VERSION` file |
| Camera (Insta360 One R kit) or support for the customer's camera | with lens calibration file |
| Cables: USB-serial 3.3 V, JST-GH to the autopilot, power | per vehicle |
| Mission map package for the customer's test area | prepared by IRIS before delivery |
| User manual (`USER_MANUAL.md` / PDF) and this document | |
| Remote support (agreed hours), one installation session | |

## 2. Process
1. **Kick-off:** vehicle type, autopilot (ArduPilot/PX4), camera, test area, goals.
2. **Preparation by IRIS:** map package of the area, camera calibration, settings file.
3. **Installation** (with IRIS): mount, wiring, autopilot parameters (manual §5), `check_box`.
4. **Shadow flights** (GPS used, NAVERA only compared): 3+ flights. NAVERA records its positions
   next to GPS → measured accuracy on this vehicle.
5. **GPS-denied flights** (NAVERA guides, safety pilot ready, inside the mapped area): GPS
   blocked in the autopilot by parameter (no real jamming), increasing durations.
6. **Report:** IRIS analyses the logs, the customer fills in the evaluation report.

## 3. Acceptance test (at delivery, on the ground, ~30 min)
| # | Check | Pass when |
|---|---|---|
| 1 | Power on, wait 2 min | operator web page reachable |
| 2 | `python3 navera_tools/check_box.py` | no FAIL |
| 3 | Autopilot detected | web page / report shows the autopilot and its type |
| 4 | GPS detected | GPS source shown, fix with satellites |
| 5 | Camera | live image, attitude present |
| 6 | Map package | `mission_bundle.py check` PASS for the test area |
| 7 | NAVERA as GPS | autopilot shows NAVERA's GPS with a 3D fix |
| 8 | Unplug the camera 5 s, plug back | camera restarts by itself, status back to OK |
| 9 | Reboot the box | everything comes back without intervention (`check_boot.sh`) |

## 4. Evaluation report (customer fills in)
- Vehicle, autopilot + version, camera, mounting, area, dates, weather.
- Shadow flights: duration, height, speed; NAVERA error vs GPS (IRIS computes from logs).
- GPS-denied flights: duration, did the mission complete, behaviour at GPS loss and return,
  any unexpected behaviour (time + description).
- Installation effort (hours), clarity of the manual (1–5), support (1–5).
- What is missing for your use?

## 5. Rules for the GPS-denied flights
- Only over the area covered by the map, in daylight (or with the thermal kit at night).
- A safety pilot able to take manual control at any time.
- Copter: `EK3_GLITCH_RAD 100` (manual §5). Autopilot failsafes configured.
- `NAVERA_FORWARD_DEGRADED=true` in `/etc/navera/navera.env` (otherwise the autopilot lands at
  GPS loss — the safe default for shadow flights).
- Start with short denied periods (1–2 min), then extend.

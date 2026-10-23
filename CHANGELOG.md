# NAVERA — release notes

Measured numbers come from simulation (Isaac Sim + ArduPilot/PX4 SITL), bench, or recorded
data from other vehicles; **no NAVERA flight yet**. Details: `docs/VALIDATION_STATUS.md`,
requirements: `docs/certification/REQUIREMENTS.md`, known problems: the shared problems list.

## 0.5.0 — 2026-10-23 (since 0.4.0, 2026-09-28)

### Navigation
- Day vision: local feature matching (DISK + LightGlue, TensorRT engines), pose-attitude guard,
  track-consistency check, blending with the gyro-carried heading, automatic heading search,
  in-flight sigma calibration (stored per camera), camera delay measured on the bench or in
  flight (stored per camera), camera mount offset learned only when separable from the delay.
- Re-acquisition after gaps: small search windows over the dead-reckoning uncertainty, visual
  odometry during gaps, dead reckoning up to 120 s / 900 m stated accuracy.
- Night vision (STHN): accuracy fitted on real aerial thermal data and stated by default,
  retry gate, first-try consistency gate, heading at the exposure.
- Celestial: compass-free solution from the plate solve, standstill check, robust mount learning,
  trusted time from GPS at take-off (DS3231 optional).

### Vehicles and sensors
- GPS sources detected automatically: NMEA or u-blox UBX on serial/USB, DroneCAN (passive),
  network GPS, the autopilot's GPS 1 or GPS 2 over MAVLink (serial, UDP, TCP), ROS; hot-plug.
- Autopilots: ArduPilot (GPS_INPUT with velocity and honest accuracy); PX4 via HIL_GPS (SITL
  v1.15.4). Copter requires `EK3_GLITCH_RAD 100`.
- IRIS kit: Insta360 One R as camera and IMU (attitude filter, boot service).
- Output: vision-FIX gaps bridged up to 10 s; mission-area guard and geofence tool.

### Product
- Crash resilience: services restart in 1 s with backoff; the output keeps the autopilot fed;
  a restarted day node resumes its track.
- Swap and memory classes, journal cap, frozen-camera and camera-stall detection, clean
  installs (no repository data), release archive (`deploy/make_release.sh`).
- User manual (`docs/USER_MANUAL.md`), 85 requirements each linked to tests, 1,073 tests.

### Validation (simulation / recorded data)
- Isaac Sim 2-hour GPS-denied copter flight with a mid-flight crash: mission completed,
  6–7 m median error throughout, 0 wrong fixes, 0 outputs beyond 3 sigma.
- Real Jetson in the loop (installed as deployed): 25 min denied, 97 % matched, 5.4 m, 8.4 W.
- Public real flights (UAV-VisLoc, AerialVL), real aerial thermal (Bordeaux), real sky (ESO).

### Known limits
- No real NAVERA flight; ground hidden (fog, low cloud, sea); maps older than ~5 years;
  1200 m while accelerating; a crash exactly at a turn; 60 s blackouts complete 2 of 4 times.
- Vision positions go to the autopilot only with `NAVERA_FORWARD_DEGRADED=true`.

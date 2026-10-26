# NAVERA — release notes

Measured numbers come from simulation (Isaac Sim + ArduPilot/PX4 SITL), bench, or recorded
data from other vehicles; **no NAVERA flight yet**. Details: `docs/VALIDATION_STATUS.md`,
requirements: `docs/certification/REQUIREMENTS.md`, known problems: the shared problems list.

## 0.6.0 — 2026-10-26 (simulation/bench-validated; no real flight yet)
- **Plug-and-play cameras** (`navera_common/cameras.py`): navera-discover and hot-plug find USB /
  UVC, CSI, network (ONVIF WS-Discovery, IPv4 + IPv6 link-local, login from
  `NAVERA_IP_CAMERA_USER` / `_PASSWORD`, never written to discovered.env; known gimbal camera
  addresses) and ROS cameras; tell colour / thermal and ground / sky; give each its job: day
  (`NAVERA_CAMERA_*`), thermal for night (`NAVERA_THERMAL_CAMERA_*`), star (`NAVERA_STAR_CAMERA_*`).
  RTSP pipelines written with hardware decoding; size, V4L2 format and a starting field of view
  filled in; look-alikes reported with CHECK. Wired interfaces only by default (`wifi` to add).
- Live camera: a stream's own size (`SIZE=auto`), 16-bit / grey thermal pictures, the V4L2 format.
- **Lens calibrated in flight against the map** (`day_pkg/lens_selfcal.py`), no checkerboard: while
  the GPS is trusted, from the GPS-check matches, with a height not taken from the image; a fitted
  lens is on trial (old / new alternating frame by frame) and kept for the camera only if its GPS
  checks are no worse; the views are kept for the next flight. Isaac Sim (70 deg guess on a 92 deg
  fisheye, delay set): 12.8 m without → 10.6, 10.2, 8.0, 7.2 m over 5 flights (true lens 4.8–5.4 m);
  the lens converges to an 89 deg fisheye. The bench calibration file still wins and stays
  recommended before delivery.
- Star camera: its field width measured from the first solved sky and kept.
- discovered.env values with spaces are double-quoted (read alike by systemd, a shell, read_env);
  provision_box sets `NAVERA_CAMERA=live`; check_box shows the lens state of each camera.
- Requirements NAV-FUN-31 (cameras) and NAV-FUN-32 (lens in flight); manual §6.0–6.6.

## 0.5.2 — 2026-10-25 (simulation/bench-validated; no real flight yet)
- Power cuts: every file NAVERA keeps is written atomically and durably (temp + fsync +
  rename, `navera_common/atomic_io.py`); every reader takes a damaged file as "nothing saved"
  (fixed: a damaged saved ground crashed the altitude, a non-UTF-8 `settings.env` the web page);
  damaged `settings.env` / `discovered.env` are moved aside at boot; `deploy/setup_fs.sh`
  (`fsck.repair=yes`); `stage_check.sh --corrupt-state`. Not yet tested by pulling the power
  on a real box.
- `install.sh --product`: SSH keys-only or off, no desktop, developer sudo rules removed, web
  token, `NAVERA_WEB_HOST`, iptables firewall, unused services off. Signed releases
  (`make_release.sh` + `verify_release.sh`). `deploy/README.md` §13.
- `deploy/provision_box.sh`: one box's identity, camera calibration + delay, map package
  settings, check_box and a provisioning record.
- Isaac Sim: wide 12 km scene `kalaa_wide` and jet condition `plane60_wide` (60 m/s): completes
  twice, 0 wrong, 15–16 m.
- Fast vehicles: the output is carried along the velocity at the last fix (curve fit), not the
  20 s chord; plane60_wide EKF error 37–46 → 25 m median, base no regression.
- EKF fusing NAVERA's vision velocity measured worse on plane and copter: keep
  `EK3_SRC1_VELXY 0` (docs only).
- Insta360 kit attitude bench on the real camera: stamps 0–30 ms, tilt 0.15° median still.
- Docs: sale-prep guide for this development Jetson, commercial docs (datasheet, evaluation
  programme, hardware kit, bench tests), Isaac Sim guide + `index_runs.py`.
- 24-hour soak on the Jetson: no memory growth in NAVERA nodes (day node ~2.1–2.2 GB flat),
  259 036 frames, 0 dropped, 100 % valid outputs, 4.4 m median; 0 log errors.
- Test tools: isaac_link camera delivery backlog bounded (OOM after 2.6 h in the first soak);
  frames published via array.array (533 → 3.6 ms per frame; frames had been dropped).
- 1,135 tests.

## 0.5.1 — 2026-10-23
- Day vision: multi-hypothesis track (D17). A far-off fix starts an alternative instead of moving
  the track; it takes over only after 3+ agreeing fixes and a clear likelihood lead, and the stated
  sigma covers it meanwhile. Replay with injected wrong matches: two-in-a-row believed 49 → 11
  (missions), 33 → 7 (flights); output max 1541 → 727 m. Applies while the carried sigma is
  30–250 m (beyond that, two agreeing fixes still re-acquire, to keep availability).
- 1200 m while accelerating: Isaac Sim flight on 0.5.0 code completed (95.5 % matched, 22 m
  median, 0 wrong, 0 beyond 3 sigma).
- 1,097 tests.

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
  a restarted day node resumes its track, turned with the IMU yaw and the autopilot velocity
  (crash at a turn: 745 → 40 m); 60 s camera blackouts complete 4 of 4.
- Memory: day node peak 4.3 → 2.4 GB (GPU cache trimmed), flat over a 1-hour soak.
- Swap and memory classes, journal cap, frozen-camera and camera-stall detection, clean
  installs (no repository data), release archive (`deploy/make_release.sh`).
- User manual (`docs/USER_MANUAL.md`), 85 requirements each linked to tests, 1,073 tests.

### Validation (simulation / recorded data)
- Isaac Sim 2-hour GPS-denied copter flight with a mid-flight crash: mission completed,
  6–7 m median error throughout, 0 wrong fixes, 0 outputs beyond 3 sigma.
- Real Jetson in the loop (installed as deployed): 25 min denied, 97 % matched, 5.4 m, 8.4 W.
- Public real flights (UAV-VisLoc, AerialVL), real aerial thermal (Bordeaux), real sky (ESO).

### Known limits
- No real NAVERA flight; ground hidden (fog, low cloud, sea); maps older than ~5 years.
- (0.5.1 closed the 1200 m and most of the D17 items listed for 0.5.0.)
- Vision positions go to the autopilot only with `NAVERA_FORWARD_DEGRADED=true`.

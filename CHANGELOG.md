# NAVERA — release notes

Measured numbers come from simulation (Isaac Sim + ArduPilot/PX4 SITL), bench, or recorded
data from other vehicles; **no NAVERA flight yet**. Details: `docs/VALIDATION_STATUS.md`,
requirements: `docs/certification/REQUIREMENTS.md`, known problems: the shared problems list.

## 0.8.1 — 2026-10-30 (simulation/bench-validated; no real flight yet)
- **UBX output:** between vision measurements the last position decision is repeated at
  `rate_hz` (its stated accuracy, measurement time kept; a bridged position with its grown
  accuracy), so a flight controller does not drop the receiver as silent. Never past the
  measurement-age, position-timeout and bridge limits. NMEA, MAVLink and ROS outputs unchanged.
  Tested in SITL only.
- **Operator view:** the forwarding chip shows the settings the output service is actually
  running (published on `/navera/output/config`), with the saved setting beside it and a
  "restart pending" mark when they differ.
- **Setup Wi-Fi:** phones' online checks are answered as a captive network until the setup page
  is shown, then as online for 10 minutes, so the phone stays on the setup Wi-Fi; the setup
  Wi-Fi is kept while a phone was seen on it in the last 5 minutes.
- **Late camera frames:** a frame later than the usual camera delay is re-dated from the
  camera's own time stamp when it has one; otherwise the day fix states the extra error (ground
  speed x lateness), or gives no fix beyond 60 m. Unit-tested on synthetic stalls; no new
  simulator run.
- **Celestial (all-sky):** the chance-match probability counts the focal lengths actually tried
  and the retry attempt (stricter gate); stored real-sky results re-gated: no fix count changes.
- **Logs download:** a "Download logs" button on the mission page gives a bounded archive of
  the last 24 h of NAVERA logs and settings, with passwords, codes and keys removed.

## 0.8.0 — 2026-10-30 (simulation/bench-validated; no real flight yet)
- **u-blox (UBX) GPS output** for flight controllers that take a u-blox GPS
  (`NAVERA_NMEA_PROTOCOL=ubx`): NAV-PVT and the related position messages, with the stated
  accuracy, so the flight controller can weigh vision positions; a stateful responder answers the
  flight controller's u-blox auto-configuration (PX4, INAV, Betaflight, ArduPilot: ACKs, port and
  baud changes, polls). Needs at least 38400 baud (refused below). Tested against flight-controller
  software in the loop (SITL) only. Manual §5.5.
- **Box access:** the box joins the client's Wi-Fi when it can, else raises its own setup Wi-Fi
  with a captive setup page (choose the client's network, type its password). Each box has its
  own setup Wi-Fi name (`NAVERA-XXXX`), random password and hostname (`navera-xxxx`), printed on
  its access card (QR code). Firewall rules for the hotspot (setup page from the hotspot's subnet
  only). Control without the code only from the box's own hotspot by default; other trusted
  networks only when added. Control requests from pages of other web sites are refused.
- **Autopilot forwarding on/off and its accuracy on the mission page**; the operator view draws
  the estimated-error circle and shows whether forwarding is on; in product mode "/" opens the
  operator view. Apply restarts the output service too, and is refused (as are forwarding changes)
  while the vehicle may be flying: armed, moving, navigating without GPS, or armed state unknown
  while NAVERA is the flight controller's serial GPS.
- **Fast plane in turns (Isaac Sim, 60 m/s jet):** a learned camera delay is applied above the
  speed cap when it is surely not zero; vision fixes and dead-reckoning carries are dated
  consistently (no odometry step used twice). A dating term for the GPS spoofing check exists but
  ships off. Remaining spikes from frame-arrival jitter are documented as open.
- **Celestial:** the bright planets join the all-sky (360) solver's catalogue, the same quality
  gate deciding (unit and simulation tested; no real clear sky yet). Prior-aided star
  identification is available to the solver but not used by the flight pipeline yet; a
  "too cloudy / blocked" reason in the field tools; Sun/Moon line-of-position, sky cleaning, a star-segmentation network and long-exposure
  still capture as offline/field tools only (not wired into the product pipeline).
- Wi-Fi manager hardened (a hung network tool no longer stops it; the hotspot is checked to be up;
  a working saved network is kept until a new one has joined).

## 0.7.2 — 2026-10-29 (second readiness review; no real flight yet)
- Product firewall: the camera-search answers (from UDP 3702 / 3956) are accepted only on the box's
  ephemeral ports 32768–60999 (a source port alone was a way past the firewall); a GigE Vision
  camera's video needs `NAVERA_FW_ALLOW_UDP` / `NAVERA_FW_ALLOW_FROM` (documented).
- Docs: ~5 m with the true lens is a simulation figure; PX4 via HIL_GPS in the hardware table;
  map coverage limitation; release 0.7.2.

## 0.7.1 — 2026-10-29 (delivery fixes from an independent readiness review; no real flight yet)
- **Product firewall lets plug-and-play cameras in** (`NAVERA_FW_CAMERAS=1`, default): UDP 5600
  (pushed RTP: SIYI-type gimbals, MAVLink-announced streams) and 8554 (GoPro MPEG-TS), and the
  answers to the camera searches (from UDP 3702 ONVIF, 3956 GigE Vision). Before, product mode let
  in only RTSP over TCP.
- Client documents brought to 0.7.0: manual status block (PX4 via HIL_GPS in SITL, cameras, lens),
  map coverage (Sousse + part of eastern Tunisia), VALIDATION_STATUS header and summary rows
  (release checks, plug-and-play cameras, lens in flight).
- The release archive leaves out internal files (CLAUDE.md, AUDIT.md, archive/, .vscode,
  the internal box-preparation procedure).

## 0.7.0 — 2026-10-29 (simulation/bench-validated, one real camera on the bench; no real flight yet)
- **More drone cameras found by themselves** (`navera_common/cameras.py`): RTSP cameras without
  ONVIF on the wired subnet (Viewpro, Topotek…: RTSP port + the usual stream paths); streams the
  vehicle announces over MAVLink (camera protocol, `VIDEO_STREAM_INFORMATION`: RTSP, RTP/UDP,
  MPEG-TS over UDP / TCP, with its name, size, field of view and thermal flag); a GoPro on USB
  (webcam mode started at each start: `NAVERA_*_START_URL`); GigE Vision / USB3 Vision industrial
  cameras through Aravis (`NAVERA_*_INPUT=aravis`, `camera_pkg/aravis_capture.py`: colour, Bayer,
  grey 8–16 bit) — without Aravis they are reported with the install command.
- **First real-camera test** (Hikvision DS-2TD2617B-3/PA bi-spectrum on Ethernet, ONVIF off as
  shipped): five bugs found and fixed — frame sampling never worked (np.save to a pipe), the RTSP
  digest login must stay on its connection (and retry once: logins arriving together), IPv6
  link-local cameras scanned and one camera counted once (MAC), channels told apart by their stream
  (a camera answering any path), a grey thermal picture with a coloured overlay is grey. Result:
  day = visible 2688×1520, thermal = 1280×720, password in no written file, both streams 20/20
  frames from the written settings.
- install.sh adds `gstreamer1.0-plugins-bad` (MPEG-TS, H.264 parsing) and Aravis.
- Verified on the Orin Nano: unit tests (fake RTSP / MAVLink camera / GoPro HTTP / Aravis); the
  RTP/UDP (1280×720), MPEG-TS over UDP (1920×1080, the GoPro's) and over TCP (1280×720) pipelines
  decoded in hardware from a live test stream; Aravis' simulated GenICam camera read in Mono8,
  BayerRG8, RGB8 and Mono16. Not tested: any of these with a real camera.

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

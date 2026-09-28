# NAVERA — Engineering backlog

Every finding from the 2026-09-28 full code review (5 areas, every file), plus the product
features still to build. An item is **done** only when it is fixed, tested and committed;
the commit is listed. Severity: **C** critical (wrong position or unsafe), **H** high
(likely failure in real use), **M** medium, **L** low.

Status: ✅ done · 🔧 in progress · ⬜ open

## 1. Localization correctness

| ID | Sev | Item | Status |
|---|---|---|---|
| LOC-1 | C | Day: tile NW corner published as position (175 m bias) | ✅ e725928 |
| LOC-2 | C | Day: descriptor cache could not be rebuilt (lat/lon column names) | ✅ e725928 |
| LOC-3 | C | Day: spatial search ignored conf_threshold; wrong anchor locked forever | ✅ 18084e2 |
| LOC-4 | C | Day: rejected match / (0,0) published and used as anchor | ✅ 18084e2 |
| LOC-5 | C | Day/night: dead-reckoning ≥120 m/frame with invented speed/heading | ✅ 2d4e5d1, 18084e2, ce66efc |
| LOC-6 | C | Night: STHN ran with random weights (checkpoint prefix, strict=False) | ✅ ce66efc |
| LOC-7 | C | Night: inputs swapped, double normalisation, output layout/units wrong, wrong config | ✅ ce66efc |
| LOC-8 | C | Night: satellite patch centred on tile, not on prior (≤110 m) | ✅ ce66efc |
| LOC-9 | C | Night: NaN from the model poisoned the whole mission | ✅ ce66efc |
| LOC-10 | C | Celestial: fixed test date/attitude; single asin root; no precession | ✅ 7c553fc |
| LOC-11 | C | Camera invents speed 5 m/s, heading 0, altitude 400 m; live mode crashes | ✅ 2d4e5d1 |
| LOC-12 | H | Day/night: first anchor only from replayed CSV — no prior in real operation (wire last valid GPS) | ✅ a2fd365 |
| LOC-13 | H | Day: global search accepts anything (scores 0.92–0.97 even when km off) — confidence not discriminative | ✅ eaeeceb |
| LOC-14 | H | Day: accuracy ~440 m median — matching method redesign (local features vs satellite around prior) | ⬜ |
| LOC-15 | H | Image/meta paired as "latest of each" — pair by frame_id (day, night, cn) | ✅ 5b9d760 |
| LOC-16 | H | Night: query not normalised for scale (altitude/FOV) or heading — confirmed blocker: 4.7 km drift on replay frames | ⬜ |
| LOC-17 | M | sensor_stamp = publication time; use image exposure stamp | ✅ 5b9d760 |
| LOC-18 | M | Day: no coverage check (outside the tile set a Sousse tile is still returned) — closed by disabling whole-map search: outside coverage the circle has no tile → no position | ✅ eaeeceb |
| LOC-19 | M | Day: unused NetVLAD/ResNet50 loaded and run at boot (VRAM, internet download) | ✅ d055bc0 |
| LOC-20 | M | Anchor not reset when the mission restarts (camera rewind) | ✅ cc4fe58 |
| LOC-21 | M | MODE_REPLAYED estimates published with valid=True; unknown src defaults to MEASURED | ✅ 1201291 |
| LOC-22 | M | Vision/DR fixes published on NavSatFix as STATUS_FIX / SERVICE_GPS | ✅ 1201291 |
| LOC-23 | M | Night: Sousse-specific Bing/ESRI bias applied everywhere | ✅ b26f5be |
| LOC-24 | M | Night: mono16 thermal converted to bgr8 without scaling | ✅ b26f5be |
| LOC-25 | M | Night: MagicMock stand-ins installed globally in sys.modules | ✅ b26f5be |
| LOC-26 | M | Celestial: solver timeout leaves solve-field/siril orphans; siril has no timeout; /tmp log leak | ✅ da40a41 |
| LOC-27 | M | Celestial: solve-field path hardcoded (/usr/local/astrometry); FOV scale 50–90° hardcoded | ✅ da40a41 |
| LOC-28 | M | Celestial: confidence gate is a constant (0.95) | ✅ da40a41 |
| LOC-29 | L | Non-dict frame_meta crashes the day node | ✅ 5b9d760 |
| LOC-30 | L | Integer launch overrides (e.g. conf_threshold:=1) crash float parameters | ✅ c53b9fc |
| LOC-31 | L | No CUDA warm-up before localizer_ready (first frame may exceed ack timeout) | ✅ d055bc0 |

## 2. Estimator and sensors

| ID | Sev | Item | Status |
|---|---|---|---|
| EST-1 | C | Same measurement re-published at 5 Hz as new MEASURED fixes | ✅ 2a68e08 |
| EST-2 | C | Future timestamp kept a dead source "fresh" | ✅ 2a68e08 |
| EST-3 | H | GPS/vision flapping zig-zag (no hold-off) | ✅ 2a68e08 |
| EST-4 | H | GPS always wins, even when spoofed — kinematic jump gate | ✅ fef6d26 |
| EST-8 | H | Gradual GPS spoof detection (needs an independent position: accurate vision or INS) | ⬜ |
| EST-5 | M | No sanity check on winner (NaN/range/covariance) | ✅ 2a68e08 |
| EST-6 | M | FIX has no threshold on uncertainty size (HDOP 20 = green) | ✅ 0a1cc05 |
| EST-7 | M | Freshness judged on publication stamp, not measurement stamp | ✅ 0a1cc05 |
| GPS-1 | H | NMEA checksum not verified | ✅ 92bce23 |
| GPS-2 | H | GGA quality 6/7/8 accepted as fix | ✅ 92bce23 |
| GPS-3 | H | Serial failure left a zombie process (no restart) | ✅ 92bce23 |
| GPS-4 | M | Altitude MSL instead of ellipsoid; missing altitude = 0 | ✅ 92bce23 |
| GPS-5 | M | Invented HDOP when missing; gps_vel units/frame | ✅ 92bce23 |
| IMU-1 | H | Possible stale data published forever (library caches last report) | ✅ 8050227 |
| IMU-2 | M | Reconnect attempted every tick (50 Hz) on the shared I²C bus | ✅ 8050227 |
| IMU-3 | M | Heading magnetic, not true; no mounting transform | ⬜ |
| RTC-1 | M | Transient I²C error during connect can crash the node | ✅ 8050227 |
| RTC-2 | M | valid:true regardless of drift vs system clock (local-time RTC = 1 h error) | ✅ 8050227 |

## 3. Web and security

| ID | Sev | Item | Status |
|---|---|---|---|
| WEB-1 | C | Unauthenticated mission control + CORS "*" (both bridges) | ✅ 542630c, dad2e83 |
| WEB-2 | C | Operator view kept a lost position on screen; no staleness detection | ✅ 542630c |
| WEB-3 | H | Dashboard needs internet (CDN Leaflet, Google Fonts) | ✅ 542630c |
| WEB-4 | H | Tile zoom DoS (2**z on client input) | ✅ 542630c, dad2e83 |
| WEB-5 | H | Stellar bridge single-threaded | ✅ dad2e83 |
| WEB-6 | H | "/" dashboard shows replayed CSV truth as "GPS" and DR as "match found" | ✅ 3fac266 |
| WEB-7 | H | "/" dashboard: fake accuracy circle (200/score), "mission done" after 3 s of same frame, readiness stub always "ready" | ✅ 3fac266 |
| WEB-8 | M | "/" dashboard: XSS via innerHTML of status fields | ✅ 3fac266 |
| WEB-9 | M | "/" dashboard: unbounded arrays/DOM over long flights; overlapping polls | ✅ 3fac266 |
| WEB-10 | M | "/" dashboard: pre-flight settings (thresholds, limits) are never sent anywhere | ✅ 3fac266 |
| WEB-11 | M | Bridge /gps_status.json never expires a "predicted" position | ✅ 3fac266 |
| WEB-12 | M | DDS open to the network; simulators can hijack the estimator | ✅ c3aae6e, 8774666 |
| WEB-13 | L | Web interface is plain HTTP (no TLS) — optional HTTPS, off by default (decision: enable per site) | ✅ a29051c |
| WEB-14 | L | Orphan front-ends: root index.html, server.js, navera_IMPROVED.html, navera_stellar.html (empty), scripts/server.py | ✅ 3a832e3 |

## 4. Deployment and packaging

| ID | Sev | Item | Status |
|---|---|---|---|
| DEP-1 | C | Crashed nodes never restarted (launch exits 0) | ✅ c3aae6e |
| DEP-2 | H | GPS service lacked dialout group | ✅ c3aae6e |
| DEP-3 | H | Data-path settings never reached the services | ✅ c3aae6e |
| DEP-4 | H | Estimator service missing from deploy README | ✅ c3aae6e |
| DEP-5 | H | Full `colcon build` failed offline (vendored isaac packages) | ✅ d233e09 |
| DEP-6 | M | Undeclared package dependencies | ✅ d233e09 |
| DEP-7 | M | No night / celestial boot services | ✅ 252fa15 |
| DEP-8 | M | No mount ordering for an external data disk; offline boot needs pre-filled model caches | ✅ 252fa15 |
| DEP-9 | M | `After=network-online.target` delays boot on a vehicle with no network | ✅ 252fa15 |
| DEP-10 | M | Docker files and start_navera.sh stale vs host deployment | ✅ 093c32d |
| DEP-11 | M | Licences: root LICENSE is NVIDIA's; package.xml says Apache-2.0 / navera@example.com; satellite imagery licence — code proprietary + THIRD_PARTY_NOTICES done; **ESRI imagery licence still required** | ◐ c8356b3 |
| DEP-12 | L | package.xml buildtool ament_cmake_python on ament_python packages; dead CMakeLists.txt | ✅ 3a832e3 |
| DEP-13 | L | Log growth (~/.ros/log never rotated) | ✅ 252fa15 |
| DEP-14 | L | Reboot validation of the new restart mechanism on a deployed unit | ⬜ |

## 5. Quality

| ID | Sev | Item | Status |
|---|---|---|---|
| QA-1 | H | No automated tests; no one-command test run | ✅ 9ad7c7e |
| QA-2 | M | Per-package READMEs missing (camera, day, cn, gps, imu, simulation_web, estimator, common) | ✅ 093c32d |
| QA-3 | L | print() instead of ROS logger in day_localizer; dead code; orphan scripts in packages | ✅ 3a832e3 |
| QA-5 | L | Intermittent test-suite failure seen twice on the first run right after a rebuild (every step printed PASS); runner now names the failing step | ✅ 3a832e3 |
| QA-4 | L | Stale docs: ROS_TOPICS_AND_COMMUNICATION.md, NAVERA_FULL_DOCUMENTATION.md, VISUAL_LOCALIZATION_SUMMARY.md, night READMEs | ✅ 093c32d |

## 6. Product features

| ID | Item | Status |
|---|---|---|
| FEAT-1 | Vehicle outputs: NMEA GPS emulation (serial) + MAVLink GPS_INPUT | ✅ 44d7e11 |
| FEAT-1b | Validate the outputs against an autopilot — ArduPilot SITL passed (MAVLink + NMEA); real vehicle pending | ✅ f2f2c6b |
| FEAT-2 | IMU dead-reckoning (heading/speed) and celestial attitude | ⬜ |
| FEAT-3 | GPU inference for STHN on JetPack 6 — done (CPU route for small solves); TensorRT not done | ✅ 20634c3 |
| FEAT-4 | Real-data recording tool (camera + GPS + IMU synchronised) and evaluation harness in repo | ✅ 6652916 |

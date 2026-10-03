# Acceptance findings — 2026-10-03 (three independent testers)

Integrator (I-), mission operator (O-), safety/QA (Q-). Status: [ ] open, [x] fixed + verified.

## Block 1 — wrong positions and false accuracy
- [ ] Q-F1 zero / tiny covariance accepted as perfect accuracy (estimator, ros_gps_node, policy)
- [ ] Q-F3 undefined covariance_type treated as bounded (FIX)
- [ ] Q-F4 non-PSD covariance accepted and republished
- [ ] I-D1 NMEA cannot carry accuracy (ArduPilot fuses it as ~0.5 m): degraded must not go out on NMEA
- [ ] O-F2 position not carried to the present: error = speed x latency, stated sigma ignores it
- [ ] O-F1 plane + fixed camera: wrong vision matches stated +-30 m
- [ ] I-D2 ArduPilot caps stated accuracy at 100 m (doc + warning)

## Block 2 — auto-discovery
- [ ] I-F1 GPS2 fed by NAVERA's own GPS_INPUT taken as the vehicle's GPS (loop)
- [ ] I-F2 discovery overrides written ROS_DOMAIN_ID / ROS_LOCALHOST_ONLY; LOCKED parsing
- [ ] I-F5 cold GPS2 missed; fallback to /dev/ttyTHS1 that may be the autopilot link
- [ ] I-F6 camera chosen alphabetically; overrides a written NAVERA_CAMERA_DEVICE; star camera taken
- [ ] I-F7 check_box / check_boot / NAVERA shell ignore discovered.env
- [ ] I-F8 NMEA without fix (modem, no antenna, autopilot NMEA out) taken as the box GPS
- [ ] I-D6 port_in_use cannot see root processes
- [ ] I-D8 two autopilots: first alphabetically, no warning; sysid fixed 1
- [ ] I-F10 MAVLink output cannot be turned off; "off" crashes the node

## Block 3 — spoofing, gaps, autopilot behaviour
- [ ] O-F3 slow spoof shown as GPS FIX with no warning until refused
- [ ] O-F9 / R4 switch to vision after a drift makes the autopilot fail safe
- [ ] Q-F2 late / out-of-order GPS fix flagged as spoofing
- [ ] O-F8 3 s staleness without hysteresis: NO FIX flicker -> LAND
- [ ] O-F7 vehicle stays in failsafe after GPS returns (sim behaviour vs doc)
- [ ] O-F10 in-flight lock blind without vehicle link
- [ ] Q-S1 dedup on header.stamp only (stale-as-current risk)

## Block 4 — integration
- [ ] I-F3 BEST_EFFORT sensor topics never received (camera, estimator, night, cn)
- [ ] I-F4 single TELEM port: docs contradict; output to a relay nobody owns, silent
- [ ] I-D3 PX4 guidance
- [ ] I-F11 /navera/fix frame_id, vision as STATUS_FIX with NaN alt, no separate ROS forwarding switch
- [ ] I-F12 forward_degraded "enabled"/"on" silently false; sigma > max_forward accepted
- [ ] I-F13 check_box misses static config errors (ports reused, URL without baud, empty mbtiles...)
- [ ] I-D9 GPS2 altitude MSL published as ellipsoidal
- [ ] I-D7 imu/rtc units enabled on every vehicle, imu ignores sensor source
- [ ] I-D11 no way to start without GPS (operator initial position)
- [ ] I-D12 ROS IMU contract (true north, QoS, rate) + late ROS vehicle join
- [ ] I-D10 EK3_SRC velocity doc

## Block 5 — simulator, UX, docs, tools
- [ ] O-F4 night: simulated thermal FOV 56.7 vs 84 assumed; altitude advice
- [ ] O-F5 sim "camera failed" ignored with real vision
- [ ] O-F6 sim default forwarded sigma 450/500 m (old DINOv2 figure)
- [ ] O-UX /operator: accuracy figure, day/night, tilt warning; failsafe banner wrong; terrain warning at plan; generate refusal text; code lockout; sim port 8190 open on LAN
- [ ] I-F9 template gst pipeline breaks the shell (quote)
- [ ] I-F14 install.sh --help / check_boot.sh --help
- [ ] I-D5 /data/navera parents root-owned; data disk mounting
- [ ] I-D4 maps outside Sousse / boats
- [ ] I-D13 doc inconsistencies (French, unit count, URL, restart lists, shadow recipe, calibrate path, hfov key, pip list, French comments, internal docs linked)
- [ ] VALIDATION_STATUS outdated (dead-reckoning exists, night 400 m)

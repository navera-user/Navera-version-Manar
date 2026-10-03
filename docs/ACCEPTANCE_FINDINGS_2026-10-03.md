# Acceptance findings — 2026-10-03 (three independent testers)

Integrator (I-), mission operator (O-), safety/QA (Q-). [x] fixed and verified (how in
brackets), [~] mitigated / partly, [ ] open. Commits on branch fix/acceptance.

## Block 1 — wrong positions and false accuracy
- [x] Q-F1 zero / tiny covariance accepted as perfect accuracy (estimator test)
- [x] Q-F3 undefined covariance_type treated as bounded (estimator test)
- [x] Q-F4 non-PSD covariance accepted and republished (estimator test)
- [x] I-D1 NMEA cannot carry accuracy: degraded positions not sent over NMEA unless
      NAVERA_NMEA_FORWARD_DEGRADED (unit test)
- [x] O-F2 position not carried to the present: carried along the measured ground velocity,
      accuracy grown by the lag (unit test; simulator plane+gimbal autopilot error
      46/136 m -> 18/79 m median/max)
- [~] O-F1 plane + fixed camera: straightening verified correct at 300 m / 18 deg roll
      (benchmark 33/33 within 2.9 m); the simulated plane oscillates +-26 deg in roll even
      with GPS (simulator issue, below); frames taken while turning > 30 deg/s now refused
- [x] I-D2 ArduPilot caps accuracy at 100 m: check_box WARN, docs

## Block 2 — auto-discovery
- [x] I-F1 NAVERA's own GPS_INPUT read back as GPS2 (SITL: GPS_TYPE2=14 refused)
- [x] I-F2 written ROS_DOMAIN_ID / ROS_LOCALHOST_ONLY never changed; ROS_DOMAIN_ID=auto
- [x] I-F5 cold GPS2 decided from GPS_TYPE2; no default port opened (GPS_SOURCE=none)
- [x] I-F6 star camera excluded, written device kept, several -> warning
- [x] I-F7 check_box / check_boot / documented shell load discovered.env
- [x] I-F8 NMEA without satellite data not a receiver; fix preferred; warning
- [x] I-D6 kernel console / serial-getty ports never probed
- [x] I-D8 several autopilots: wired port, warning; NAVERA_MAVLINK_SYSID
- [x] I-F10 NAVERA_MAVLINK_URL=off; port/URL parameters forced to text
- [x] I-F9 template gst pipeline quoted

## Block 3 — spoofing, gaps, autopilot behaviour
- [x] O-F3 slow spoof: GPS IN DOUBT (DEGRADED, accuracy = gap) from 2 fixes beyond 3 sigma
      (estimator test; simulator: DEGRADED at ~104 m, refused at 138 m, held)
- [~] O-F9 switch to vision after a drift: the doubt widens the GPS accuracy before the
      switch; still bounded by vision's stated 30 m (3 sigma = 90 m) until vision is measured
- [x] Q-F2 late GPS fix dropped, not "spoofing" (estimator test)
- [x] O-F8 vision usable 5 s, carried to the present (estimator config, output 5 s)
- [x] O-F7 failsafe: doc corrected (an autopilot does not resume by itself), sim message
- [x] O-F10 in-flight lock from NAVERA's own motion (unit test)
- [x] Q-S1 de-duplication on stamps and content

## Block 4 — integration
- [x] I-F3 BEST_EFFORT sensor topics received (integrator's script: 4/4 unusable -> 3/3)
- [x] I-F4 relay without vehicle link: loud error; check_box FAIL; docs
- [ ] I-D3 PX4: documentation only (no PX4 SITL run) — see docs/PX4_INTEGRATION.md
- [x] I-F11 /navera/fix frame id, service 0 for non-GPS, ROS forwarding switch
- [x] I-F12 forward_degraded true/false only; sigma above the ceiling refused
- [x] I-F13 check_box static checks (integrator's bad configuration flagged)
- [x] I-D9 GPS2 ellipsoid altitude and h_acc
- [x] I-D7 imu / rtc services idle without their chips
- [x] I-D11 operator start position without GPS (/mission, verified end to end)
- [x] I-D12 ROS IMU contract documented
- [x] I-D10 EK3_SRC velocity documented

## Block 5 — simulator, UX, docs, tools
- [x] O-F4 night altitude advice from the thermal camera's real field of view (~480 m)
- [x] O-F5 sim "camera failed" stops the camera process
- [x] O-F6 sim default forwarded sigma 30 m
- [x] O-UX operator accuracy / source / carried position / camera warnings; failsafe banner;
      terrain warning at planning; generate refusal text; code lockout; replace confirm
- [ ] O-UX simulator control port 8190 open on the LAN without authentication (development
      tool; documented — the user drives it from another computer)
- [x] I-F14 install.sh / check_boot.sh --help
- [x] I-D5 /data/navera owned by navera; data disk mounting documented
- [x] I-D4 maps outside Sousse / boats documented
- [x] I-D13 doc inconsistencies
- [x] VALIDATION_STATUS: dead-reckoning, night field of view, failsafe behaviour
- [ ] Simulator: ArduPlane "plane-jet" oscillates +-26 deg in roll at 40 m/s on this machine
      (with GPS working too) — fixed-camera plane results in the simulator are not
      representative until it is understood

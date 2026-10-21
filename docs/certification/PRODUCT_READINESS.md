# NAVERA — Product readiness (one page)

Status 2026-10-21, code `acd37fd`. **NAVERA has not flown.** Every number below is from the
cited evidence; TRL uses the usual 1–9 scale (4 = validated in the lab, 5 = in a relevant
environment, 6 = system prototype demonstrated in a relevant environment, 7 = in the operational
environment). Levels: SIM simulator / SITL · BENCH real NAVERA hardware on a bench · PUB public
real data · HW hardware in role · FLT flight.

| Subsystem | TRL | Strongest evidence | Key number | What moves it up |
|---|---|---|---|---|
| Arbiter (`navera_estimator`): priority, FIX/DEGRADED/NO_FIX, spoof gates | **5** | SIM (ArduPilot SITL in the loop), UT | 2 km spoof refused < 1 s; 4 m/s drift refused ~140 m; 0 false refusals on 108 real-camera runs + 7.2 h real drone data | flight with a real receiver and spoof/jam trials |
| Vehicle output (MAVLink `GPS_INPUT`, NMEA) | **5** | SIM (ArduCopter 4.5.7 SITL) | EKF height = baro within 0.1 m under vision (F7) | a real ArduPilot autopilot on the bench, then in flight; PX4 path (none today) |
| Vehicle link (autopilot → NAVERA) | **5** | SIM | attitude / height / rangefinder agree with SITL | real autopilot |
| GPS driver (serial NMEA / ROS GPS) | **5** | UT + HW (receiver fix recorded in the project report) | checksum, quality 6/7/8 refused, port loss → restart | live receiver on the box through today's driver |
| Day vision (DISK + LightGlue / SIFT, local matching, pose guard) | **5** algorithm · **4** with NAVERA's camera | PUB (8 real drone flights), BENCH (Insta360 on a screen) | real flights: median 16 m, p90 34 m, 1 / 2599 > 100 m; 0.993–0.999 within 3σ. Screen: 3.6–7.3 m median | a recorded flight with NAVERA's camera, GPS and IMU (shadow mode) |
| Day dead-reckoning between matches | **4** | SIM | land median 10 m / max 33 m; 90 s over sea ≤ 146 m | real IMU + camera; inertial navigation (not implemented) |
| Night vision (STHN, thermal) | **3–4** | SIM (synthetic renders) | 8–13 m median synthetic; real camera bench: no fix (F24) | real LWIR recording (Hikvision camera now on the Jetson) |
| Celestial (all-sky / plate solve) | **4** | BENCH (real camera, screen sky), PUB-like (one real sky photo) | 23/27 right at 0.4–9 km on the screen; 24–119 km with a BNO085-class IMU (SIM) | real night sky with known time/place/attitude |
| Inertial navigation (FEAT-2) | **2** | — | not implemented (IMU = attitude / heading change / liveness) | implementation |
| IMU driver (BNO085) | **5** | HW (live on the Jetson, 50 Hz) | heading reference not checked (IMU-3) | known-heading test, noise measurement |
| Real-time clock (DS3231) | **6** module · **open** on the field box | HW (power-cycle reboot, −0.148 s vs NTP) | F27: the field Jetson booted 16 h off (no DS3231 fitted) | RTC mandatory in the build; trusted-time gate in product celestial |
| Discovery (auto configuration) | **5** | SIM (SITL), UT | own output never read back as a GPS | real autopilot + sensors |
| Operator web / mission preparation (offline maps, token, armed lock) | **5** | UT, BENCH | 1768 km route prepared offline (79 775 tiles, 980 MB) | sudoers restart on an installed box (R-8) |
| Deployment (systemd units, install, restart) | **5–6** | HW (reboot 2026-07-15, older mechanism), staged validation 2026-10-21 (this branch) | staged: every unit up, killed nodes restarted by systemd ([DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md)) | reboot test of today's units on a deployed box (DEP-14) |
| **System as a whole** | **4–5** | SIM end to end; components on BENCH / PUB | — | first instrumented flight in shadow mode, then GPS-denied with a safety pilot |

**Certification readiness** (details: [STANDARDS_MAPPING.md](STANDARDS_MAPPING.md)): 63 system
requirements, 55 traced to automated tests, 8 without ([TRACEABILITY.md](TRACEABILITY.md));
hazard log with 16 hazards, 4 at High residual risk ([SAFETY_ANALYSIS.md](SAFETY_ANALYSIS.md)):
slow spoof without an independent source, autopilot misconfiguration, frozen camera image,
unvalidated night vision. No DO-178C plans, no structural coverage, Python/ROS/ML in the
position path — a DAL C target needs a partitioned arbiter + output path.

**Readiness for a first flight campaign** (shadow mode: NAVERA records and computes, GPS flies
the vehicle): **yes**, with the stage-checked install, `check_box.py` pre-flight, an RTC fitted,
and `NAVERA_FORWARD_DEGRADED=false`. **For GPS-denied flight on NAVERA's positions**: only with a
safety pilot, over textured land, after the open items O-1 (frozen image), O-25 (autopilot
parameter check) and the reboot validation are closed.

# NAVERA — product datasheet (release 0.5.1)

**GPS-denied navigation for drones, boats and ground robots.** NAVERA gives the vehicle its
position when GPS is jammed, faked or lost — for minutes or for the whole flight — by comparing
its camera with satellite imagery stored on board. Fully offline in flight.

## How it works
1. Before the mission, the satellite map of the area is loaded on the box (offline package).
2. The vehicle takes off with GPS. NAVERA checks the GPS continuously against its camera.
3. When GPS is jammed or faked, NAVERA takes over: camera + map → position, sent to the
   autopilot as a GPS. Between camera fixes, the position is carried with the vehicle's motion.
4. NAVERA always states how accurate its position is; the autopilot weighs it accordingly.

## Performance (simulation and recorded data — first real flights pending)
| | Result |
|---|---|
| Position error without GPS (copter, 250 m, camera delay calibrated) | **6–7 m median**, ~10 m p90 |
| Long GPS-denied flight (simulation, 2 h, with a software crash) | mission completed, error constant over 2 h |
| Wrong positions (> 50 m) in normal conditions | **0** in 31 simulated conditions (weather, light, obstacles, terrain) |
| Real recorded drone flights (public datasets) | 3–19 m median depending on map age and terrain |
| Night (thermal camera, 640 px, 700–1000 m) | 10–12 m median, 0 wrong, on real aerial thermal data |
| GPS spoofing detection | a slow 3 m/s drag refused after 60–72 m |
| Height range validated in simulation | 150 m – 1200 m |
| Speeds validated in simulation | copter 8–15 m/s, fixed-wing 30 m/s |

**Limits:** needs visible ground with texture (not thick fog, low cloud, open sea); map imagery
should be recent (< 5 years); night needs a thermal camera.

## Hardware
| | |
|---|---|
| Computer | NVIDIA Jetson Orin Nano 8 GB (Super), JetPack 6.2 |
| Power | ~8.5 W average, 12 W peak (module); input per carrier board |
| Temperature | 72 °C junction under continuous load at room temperature, no throttling |
| Camera (IRIS kit) | Insta360 One R (camera + built-in IMU) — or customer USB / CSI / network camera |
| Optional | thermal camera (night), DS3231 clock |
| Storage | NVMe SSD (maps, logs) |

## Interfaces (detected automatically at power-on and when plugged in)
- **Autopilot:** ArduPilot (MAVLink GPS_INPUT), PX4 (MAVLink HIL_GPS) — serial, UDP or TCP.
- **GPS in:** NMEA or u-blox (serial/USB, or listening on the autopilot's GPS wire), DroneCAN
  (CAN bus), network GPS, the autopilot's own GPS, ROS 2.
- **GPS out:** MAVLink, NMEA serial, ROS 2 (`/navera/fix`).
- **Robots:** ROS 2 Humble, joins the vehicle's ROS network automatically.
- **Operator:** web page (status, map, mission preparation).

## Software
- Day vision (camera vs satellite map), night vision (thermal), star navigation (experimental).
- GPS spoofing / jamming detection; honest accuracy on every position.
- Survives a software crash in flight (restart in ~1 s, autopilot kept fed).
- Offline mission package with integrity check; release archives with checksums.
- 1,097 automated tests; 85 requirements, each linked to tests.

*IRIS Systems — Integrated Robotics and Intelligent Systems.*

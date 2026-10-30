# NAVERA hardware kit — parts list, enclosure requirements, pre-shipping checklist

## 1. IRIS kit parts list
| Part | Model | Qty | Notes |
|---|---|---|---|
| Computer | NVIDIA Jetson Orin Nano 8 GB Super (module + carrier) | 1 | JetPack 6.2 |
| Storage | NVMe SSD ≥ 256 GB | 1 | maps, logs |
| Camera + IMU | Insta360 One R (360 mod) | 1 | USB; lying, left lens down, top to the nose |
| Clock (optional) | DS3231 + CR2032 | 1 | I²C pins 1/6/27/28; time also comes from GPS at take-off |
| Power | DC-DC converter, drone battery → carrier input, ≥ 25 W | 1 | wide input range for the battery |
| Autopilot link | USB-serial 3.3 V (FTDI/CP2102) + JST-GH cable | 1 | TELEM port, 921600 baud |
| Thermal camera (night, optional) | FLIR Boson 640, 50° | 1 | |
| Mounting | vibration-damped plate, lens hood | 1 | |

## 1b. Accessories to buy (add-ons)
Prices are rough 2026 retail estimates, not quotes. "Needed" = for the feature named.

| Add-on | Example model | Needed for | Est. price | Notes |
|---|---|---|---|---|
| 4G USB modem ("HiLink", shows up as a network card) + data SIM | Huawei E3372h-320 or similar | the public link (dashboard from anywhere) when there is no Ethernet | 40–60 € + SIM | the box's Wi-Fi is busy as the hotspot; HiLink models need no driver |
| Ethernet cable / router port | Cat6 | the public link at a base or lab | 5 € | simplest internet for the box |
| Wi-Fi antennas (2×, U.FL / RP-SMA) | dual-band 5 dBi | hotspot range in the field | 10–20 € | the carrier's stock antennas reach only a few metres in a closed case |
| USB-serial 3.3 V + JST-GH cable | FTDI FT232R / CP2102 | autopilot link (MAVLink, NMEA or u-blox UBX output) | 10–20 € | one per vehicle type (JST-GH 6-pin for Pixhawk TELEM/GPS) |
| GPS receiver for take-off | u-blox M10 module | NAVERA starts with GPS | 20–40 € | NMEA or UBX on USB/serial |
| Clock module + battery | DS3231 + CR2032 | star time without GPS after power loss | 5–10 € | |
| Night-sky camera (celestial) | IMX462 or IMX585 board camera, raw output, with an f/1.2–2 fisheye | stars in city light and haze, much fainter than the Insta360's video | 50–300 € | not yet integrated: see VALIDATION_STATUS "first real night" |
| Lens hood / baffle for the sky camera | matte black tube | street lamps and stray light | 5–15 € | biggest free gain measured on the 2026-10-29 night |
| 700 nm long-pass filter (optional) | 25–37 mm screw-in | LED city glow and haze for the night-sky camera | 20–40 € | no help against cloud |
| Thermal camera (night vision) | FLIR Boson 640 / Hikvision DS-2TD2617B | night map matching | 300–3000 € | |
| Powered USB 3 hub | 4-port, 5 V 3 A | several USB cameras + modem | 20–30 € | the carrier's ports trip with a camera + modem |
| Battery DC-DC converter | 6–36 V in → carrier input, ≥ 25 W, XT60 | power from the vehicle battery | 15–30 € | |
| NVMe SSD (maps) | ≥ 512 GB | larger mission maps | 40–70 € | |
| Printed access card / label | from navera_tools/access_card.py | the Wi-Fi QR code on the box | — | same code for every box (fixed Wi-Fi name and password) |

## 2. Enclosure requirements
- **Heat:** the module reaches ~72 °C under continuous load at room temperature with the stock
  fan; margin is only ~2 °C at 50 °C ambient → the enclosure needs airflow (inlet + outlet) and
  must not enclose the fan; consider a larger heatsink for hot climates.
- **Power:** ~8.5 W average, 12 W peak for the module; size the DC-DC for 25 W with the camera.
- **Vibration:** soft mounts (silicone dampers) between the frame and the enclosure; the camera
  on its own damped mount; no cable pulling on connectors (strain relief).
- **Water/dust:** splash-proof for drones (IP54 target), vents with membranes.
- **Access:** USB-C / Ethernet for maintenance, LED or buzzer for status, the NVMe reachable.
- **Weight:** keep the enclosure light; report total weight in the datasheet once built.
- **Antennas / RF:** keep Wi-Fi/GPS antennas away from the Jetson and the USB 3 cables.

## 3. Pre-shipping checklist (each box)
- [ ] Release installed from the archive: `tar xzf navera-X.tar.gz && cd navera-X && sha256sum -c RELEASE_MANIFEST.sha256 --quiet && sudo deploy/install.sh`
- [ ] Box set up with `sudo deploy/provision_box.sh --serial NAV-XXXX --customer "..." --lens FILE --camera-delay S --map-bundle DIR --env-extra extra.env`
      (extra.env e.g. `NAVERA_FORWARD_DEGRADED=true`, `NAVERA_DEGRADED_SIGMA_M=15`); keep the record `/var/lib/navera/provision/<serial>.json`
- [ ] Camera calibrated (`navera_tools/calibrate_camera.py`) and camera delay measured (manual §6.3)
- [ ] Map package of the customer area built and checked (`mission_bundle.py check`)
- [ ] `deploy/setup_swap.sh --check` OK; `deploy/check_boot.sh` after a reboot: all services active
- [ ] Acceptance test (evaluation programme §3) passed on the bench
- [ ] 1-hour burn-in on the bench (memory flat, temperature < 80 °C)
- [ ] Serial number, `VERSION`, calibration files and test results recorded

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

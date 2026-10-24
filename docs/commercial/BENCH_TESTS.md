# Bench tests with real hardware — step by step (no flight)

For when the bench hardware arrives (flight controller with ArduPilot, u-blox M10 GPS, cables;
optional DroneCAN GPS + CAN adapter). Each test: what to plug, what to run, what "pass" means.
Run on the Jetson, in `~/Navera`, after `source /opt/ros/humble/setup.bash && source install/setup.bash`.

## 1. Insta360 kit (camera + IMU)
1. Plug the Insta360 by USB, switch it on. `sudo systemctl stop navera-field`.
2. `python3 navera_tools/bench/attitude_check.py --kit --seconds 120 --out ~/attitude_kit.csv`
3. Hold the camera ~40 cm in front of the dot grid on the screen, turn and tilt it slowly.
4. **Pass:** tilt error median < 1°, max < 3°; best stamp offset near 0 ms. Then
   `sudo systemctl start navera-field`.

## 2. GPS on USB / serial (u-blox M10)
1. Plug the GPS (USB-serial adapter: GPS TX → adapter RX, GND, 5 V). Place it near a window.
2. `python3 -m navera_common.discovery` (or reboot the box: `/var/lib/navera/discovery.json`) — the report lists the GPS
   port, baud and protocol (UBX or NMEA).
3. `ros2 topic echo /navera/estimate/gps --once`
4. **Pass:** the GPS is found by itself; valid fix with satellites and accuracy (hAcc).

## 3. Autopilot over MAVLink (flight controller with ArduPilot)
1. Connect the flight controller's TELEM port to the Jetson (USB-serial 3.3 V, TX↔RX, GND).
   Set on the autopilot: `SERIAL1_PROTOCOL 2`, `SERIAL1_BAUD 921`, `GPS1_TYPE 14` (NAVERA as GPS 1).
2. Reboot both. Discovery report shows the autopilot (ArduPilot, its type).
3. With the u-blox on NAVERA (wiring A): the autopilot's ground station (Mission Planner /
   QGroundControl over USB) shows GPS 1 with a 3D fix coming from NAVERA.
4. **Pass:** NAVERA found the autopilot alone; the autopilot has a 3D fix through NAVERA;
   `ros2 topic hz /navera/vehicle/imu` ≥ 40 Hz.

## 4. Listening on the autopilot's GPS wire (Y-cable)
1. GPS wired to the autopilot's GPS port as usual; Y-splitter on the GPS TX line to the Jetson's
   adapter RX (receive only).
2. The autopilot configures the GPS in UBX at 230400: NAVERA must follow by itself.
3. **Pass:** discovery finds UBX on the adapter; `/navera/estimate/gps` valid; nothing sent to the GPS.

## 5. DroneCAN GPS (optional)
1. CAN adapter (CANable 2.0 USB, or SN65HVD230 on the Jetson CAN pins), 120 Ω termination.
2. `sudo ip link set can0 up type can bitrate 1000000 restart-ms 100` (or the USB adapter's interface).
3. **Pass:** discovery lists the DroneCAN GNSS node; `/navera/estimate/gps` valid.

## 6. Plug after boot (hot-plug)
1. Boot the box with no GPS. Then plug the GPS.
2. **Pass:** within ~1 minute the GPS service picks it up by itself (journal: `journalctl -u navera-hotplug`).

## 7. Crash recovery on the bench
1. Everything running, autopilot showing NAVERA's fix. `sudo systemctl kill navera-estimator`.
2. **Pass:** the autopilot's GPS never drops to "no fix" for more than ~3 s; the service is back in ~2 s.

Send the outputs (or photos of the screens) to IRIS engineering for each test.

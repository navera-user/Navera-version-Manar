# gps_pkg — GPS driver

NAVERA's GPS source. It turns a GPS fix into the typed source contract
`navera_msgs/PositionEstimate` on `/navera/estimate/gps` (consumed by `navera_estimator`, where a
valid GPS fix wins over every vision source), and republishes the raw fix for the nodes that read
it (the live camera, the GPS cross-check).

Three executables, one per kind of GPS; the boot service starts exactly one of them
(`NAVERA_GPS_SOURCE`, see "How to run"). How a client connects a GPS, in every supported way:
`docs/manual_gps_section.md`.

## Nodes

### `gps_node.py` (node name `gps_node`) — a receiver's stream: NMEA and / or u-blox UBX

Reads a serial GPS (default `/dev/ttyTHS1`, 9600 baud), or a GPS stream on the network
(`url`): NMEA sentences and u-blox UBX binary, recognised automatically, even mixed on one
stream (`navera_common/gnss.py::StreamDecoder`). Works on a passive tap (Y-cable on the TX wire
of a GPS an autopilot configured): it never writes to the receiver unless
`configure_receiver` is true.

UBX (`NAV-PVT`, u-blox 7 and later; `NAV-DOP` of the same epoch adds the HDOP):
- a fix only with `gnssFixOK` and fix type 2D / 3D / GNSS + dead reckoning; dead reckoning
  only, time only and `invalidLlh` are published as invalid;
- covariance = the receiver's own `hAcc`² / `vAcc`² (`COVARIANCE_TYPE_DIAGONAL_KNOWN`), unknown
  when it states none; altitude = `NAV-PVT` height (ellipsoid); `geo_sep_m` in the details;
- velocity from `velN` / `velE` / `velD`; GNSS time when the UTC is valid and fully resolved;
- while `NAV-PVT` arrives (3 s), the same receiver's NMEA is not published a second time.

NMEA:

- Only sentences with a valid checksum are used.
- GGA fix qualities 1, 2, 4 and 5 (GPS, DGPS, RTK fixed, RTK float) count as a fix; 6 (receiver
  dead-reckoning), 7 (manual) and 8 (simulator) are published as invalid.
- Altitude is height above the WGS84 ellipsoid (MSL + geoid separation), NaN if unknown.
- Covariance: σ = 2 m × HDOP (assumed user range error), `COVARIANCE_TYPE_APPROXIMATED`; UNKNOWN
  when HDOP is missing (never invented). Source `SOURCE_GPS`, mode `MODE_MEASURED`.
- If the port cannot be opened or disappears, the node exits (code 1) and systemd restarts it.
- The service user needs the `dialout` group.

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `serial_port` | string | `/dev/ttyTHS1` | serial device (`/dev/ttyUSB0` for a USB GPS) |
| `baud_rate` | int | `9600` | serial speed |
| `url` | string | `""` | instead of the two above: `serial:/dev/<port>:<baud>`, `tcp:<host>:<port>` (connects; a closed connection exits 1), `udp:<port>` (listens) |
| `configure_receiver` | bool | `false` | allow NAVERA to turn on UBX `NAV-PVT` / `NAV-DOP` (CFG-MSG and CFG-VALSET, receiver RAM only) |

Defaults are also in `config/gps_params.yaml`; the boot service overrides them with
`NAVERA_GPS_PORT` / `NAVERA_GPS_BAUD`.

| Direction | Topic | Type | QoS |
|-----------|-------|------|-----|
| out | `/navera/estimate/gps` | `navera_msgs/PositionEstimate` | depth 10 (reliable) |
| out | `/navera/sensors/gps_fix` | `sensor_msgs/NavSatFix` | depth 10 (reliable) |
| out | `/navera/sensors/gps_vel` | `geometry_msgs/TwistStamped` (ENU: `linear.x` east, `linear.y` north, m/s, from RMC or NAV-PVT) | depth 10 (reliable) |
| out | `/navera/sensors/gnss_time` | `sensor_msgs/TimeReference` (the receiver's UTC) | depth 10 (reliable) |

### `dronecan_gps_node.py` (node name `dronecan_gps`) — a DroneCAN GNSS on a CAN bus

Here3 / Here4, Holybro DroneCAN GNSS and other `uavcan.equipment.gnss.Fix2` (or legacy `Fix`)
receivers, read with pydronecan (`pip install dronecan`) and published like `gps_node`
(`gps_pkg/fix_publish.py`): valid with a 2D / 3D fix, accuracy from the message covariance,
UTC from a UTC or GPS timestamp. Passive: no node id, nothing sent on the bus — it can share
the vehicle's bus with the autopilot. A node that also sends ESC / actuator commands (an
autopilot re-broadcasting its own GPS) is never used; with `node_id` 0 it listens 2 s, then
keeps the first GNSS node heard with a fix (another one only after 5 s of silence). Exits 1
when the bus cannot be opened or fails.

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `can_interface` | string | `can0` | SocketCAN interface, or `slcan:/dev/ttyACM0`, `mcast:0` (virtual bus, tests) |
| `bitrate` | int | `1000000` | SLCAN adapters only (SocketCAN: `ip link`) |
| `node_id` | int | `0` | the GNSS node to use; 0 = the first with a fix |
| `allocate_node_ids` | bool | `false` | opt-in: run a dynamic node-id allocator as `own_node_id` (a GPS alone on NAVERA's CAN); NAVERA then transmits |
| `own_node_id` | int | `125` | NAVERA's node id when allocating |
| `allocation_db` | string | `:memory:` | the allocator's table (the boot service keeps it in `/var/lib/navera`) |

### `ros_gps_node.py` (node name `ros_gps`) — a GPS that is not NAVERA's own receiver

For installations without the box's GPS: the vehicle's ROS GPS (a boat's or robot's
`NavSatFix`), or the autopilot's second GPS (`/navera/vehicle/gps2`) or first GPS
(`/navera/vehicle/gps1`, only while the autopilot says NAVERA does not feed it) read by
`navera_output/vehicle_link_node`. Republishes it exactly like `gps_node`. A fix is valid only with a
fix status and a finite, non-(0,0) position; the input covariance is kept when known.

Never point it at a position NAVERA itself produces (the autopilot's fused position, or a GPS fed
by NAVERA's GPS_INPUT): NAVERA would check its own output against itself.

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `fix_topic` | string | `/navera/vehicle/gps2` | `sensor_msgs/NavSatFix` input |

| Direction | Topic | Type | QoS |
|-----------|-------|------|-----|
| in | `fix_topic` (default `/navera/vehicle/gps2`) | `sensor_msgs/NavSatFix` | sensor data (best effort) |
| out | `/navera/estimate/gps` | `navera_msgs/PositionEstimate` | depth 10 (reliable) |
| out | `/navera/sensors/gps_fix` | `sensor_msgs/NavSatFix` (not republished when it is the input topic) | depth 10 (reliable) |

An unstamped input fix is stamped with its receipt time.

## How to run

```bash
# A receiver on a serial port (NMEA and / or UBX)
ros2 launch gps_pkg gps.launch.py                                   # /dev/ttyTHS1, 9600
ros2 launch gps_pkg gps.launch.py serial_port:=/dev/ttyUSB0 baud_rate:=115200
# ... or on the network
ros2 launch gps_pkg gps.launch.py url:=tcp:192.168.1.50:10110

# A DroneCAN GPS (can0 must be up: sudo ip link set can0 up type can bitrate 1000000)
ros2 run gps_pkg dronecan_gps_node.py --ros-args -p can_interface:=can0

# Any NavSatFix topic as NAVERA's GPS
ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/boat/gps/fix
```

In deployment the systemd unit `navera-gps.service` runs `deploy/systemd/navera_boot_gps.sh`,
which picks the node from `NAVERA_GPS_SOURCE` (`/etc/navera/navera.env`, or decided at boot by
`navera-discover`):

| `NAVERA_GPS_SOURCE` | Runs |
|---------------------|------|
| `serial` (default) | `gps.launch.py serial_port:=$NAVERA_GPS_PORT baud_rate:=$NAVERA_GPS_BAUD` |
| `network` | `gps.launch.py url:=$NAVERA_GPS_URL` |
| `dronecan` | `dronecan_gps_node.py` on `$NAVERA_GPS_CAN_IFACE`, node `$NAVERA_GPS_CAN_NODE` (`NAVERA_GPS_CAN_ALLOCATE=1`: allocator) |
| `vehicle` | `ros_gps_node.py` with `fix_topic:=/navera/vehicle/gps2` (needs `navera-vehicle-link`) |
| `vehicle_gps1` | `ros_gps_node.py` with `fix_topic:=/navera/vehicle/gps1` (navera-vehicle-link reads GPS 1 only while its `GPS_TYPE` is not NAVERA's) |
| `ros` | `ros_gps_node.py` with `fix_topic:=$NAVERA_ROS_GPS_TOPIC` (required) |
| `none` / `auto` | nothing (GPS idle; never opens a default port, which may be the autopilot's link) until navera-hotplug finds a GPS connected later |

`NAVERA_GPS_CONFIGURE=1` passes `configure_receiver:=true` (serial / network).

Tests: `gps_pkg/test/` (`test_ros_gps.py`, `test_dronecan_gps.py`, plus the flake8/pep257
linters); `navera_common/test/test_gnss.py` (UBX / Fix2 decoding); integration
`navera_tools/tests/test_gps_serial.py` (NMEA, pseudo-terminal) and `test_gps_sources.py` (UBX
tap, TCP, UDP, DroneCAN virtual bus).

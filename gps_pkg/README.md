# gps_pkg — GPS driver

NAVERA's GPS source. It turns a GPS fix into the typed source contract
`navera_msgs/PositionEstimate` on `/navera/estimate/gps` (consumed by `navera_estimator`, where a
valid GPS fix wins over every vision source), and republishes the raw fix for the nodes that read
it (the live camera, the GPS cross-check).

Two executables, one per kind of GPS; the boot service starts exactly one of them
(`NAVERA_GPS_SOURCE`, see "How to run").

## Nodes

### `gps_node.py` (node name `gps_node`) — the box's own receiver, NMEA over serial

Reads NMEA sentences from a serial GPS (default `/dev/ttyTHS1`, 9600 baud).

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

Defaults are also in `config/gps_params.yaml`; the boot service overrides them with
`NAVERA_GPS_PORT` / `NAVERA_GPS_BAUD`.

| Direction | Topic | Type | QoS |
|-----------|-------|------|-----|
| out | `/navera/estimate/gps` | `navera_msgs/PositionEstimate` | depth 10 (reliable) |
| out | `/navera/sensors/gps_fix` | `sensor_msgs/NavSatFix` | depth 10 (reliable) |
| out | `/navera/sensors/gps_vel` | `geometry_msgs/TwistStamped` (ENU: `linear.x` east, `linear.y` north, m/s, from RMC) | depth 10 (reliable) |

### `ros_gps_node.py` (node name `ros_gps`) — a GPS that is not NAVERA's own receiver

For installations without the box's GPS: the vehicle's ROS GPS (a boat's or robot's
`NavSatFix`), or the autopilot's second GPS read by `navera_output/vehicle_link_node`
(`/navera/vehicle/gps2`). Republishes it exactly like `gps_node`. A fix is valid only with a
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
# The box's receiver (NMEA serial)
ros2 launch gps_pkg gps.launch.py                                   # /dev/ttyTHS1, 9600
ros2 launch gps_pkg gps.launch.py serial_port:=/dev/ttyUSB0 baud_rate:=115200

# Any NavSatFix topic as NAVERA's GPS
ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/boat/gps/fix
```

In deployment the systemd unit `navera-gps.service` runs `deploy/systemd/navera_boot_gps.sh`,
which picks the node from `NAVERA_GPS_SOURCE` (`/etc/navera/navera.env`, or decided at boot by
`navera-discover`):

| `NAVERA_GPS_SOURCE` | Runs |
|---------------------|------|
| `serial` (default) | `gps.launch.py serial_port:=$NAVERA_GPS_PORT baud_rate:=$NAVERA_GPS_BAUD` |
| `vehicle` | `ros_gps_node.py` with `fix_topic:=/navera/vehicle/gps2` (needs `navera-vehicle-link`) |
| `ros` | `ros_gps_node.py` with `fix_topic:=$NAVERA_ROS_GPS_TOPIC` (required) |
| `none` / `auto` | nothing (GPS idle; never opens a default port, which may be the autopilot's link) |

Tests: `gps_pkg/test/` (`test_ros_gps.py`, plus the flake8/pep257 linters).

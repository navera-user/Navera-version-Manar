# gps_pkg — GPS driver

`gps_node` reads NMEA sentences from a serial GPS (default `/dev/ttyTHS1`, 9600 baud).

- Only sentences with a valid checksum are used.
- GGA fix qualities 1, 2, 4 and 5 count as a fix; 6 (receiver dead-reckoning), 7 and 8 are
  published as invalid.
- Altitude is height above the WGS84 ellipsoid (MSL + geoid separation), NaN if unknown.
- Covariance: σ = 2 m × HDOP (assumed user range error); UNKNOWN when HDOP is missing.
- If the port cannot be opened or disappears, the node exits (code 1) and systemd restarts it.

## Outputs
`/navera/estimate/gps` (PositionEstimate, the contract), `/navera/sensors/gps_fix`
(NavSatFix), `/navera/sensors/gps_vel` (TwistStamped, ENU east/north m/s from RMC).

## Parameters
`serial_port`, `baud_rate` (boot service: `NAVERA_GPS_PORT`, `NAVERA_GPS_BAUD`). The service
user needs the `dialout` group.

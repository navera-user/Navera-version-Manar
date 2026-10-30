# Mission 13 — report

## Precedence

With no file the drone ran at its code default, 10.0 m/s. With my_gps.yaml it took 18.0 from its own section.
Adding -p speed_mps:=25.0, before or after the file, still gave 18.0: -p writes into the /** row, and
that row sits above /drone/fake_gps, so the drone's own row wins. A second file with the same section name
(fast.yaml) overwrote the row in place and gave 25.0. Rule for a colleague: one place per value, /** first,
override a node's section with a later file of the same name, and always check with ros2 param get.

## Guards

The type and the range act at start and while running (150.0 at start stopped the node, 500.0 was refused).
Read-only refused rate_hz 5.0 at run time but allows a start value. My callback refused 25.0 for a boat
while running, but a boat started with -p speed_mps:=25.0 kept 25.0: the callback never saw start values.
check_settings reads the whole settings file at start and found 4 problems in integrator.yaml.

## One setting per vehicle

With the drone's 30 m/s limit the jump gate allowed 80 m per second, the plane flew 85 m, and after 10 s the
judge was NO_FIX with its real GPS refused as jumps; with 100.0 it was FIX. check_settings said
"max_speed_mps must be >= 100.0 for a plane, got 30.0" before any flight. Setting fix_max_sigma_m to 2.0
turned the same 3 m fixes into DEGRADED "gps: σ 3.0 m > 2.0 m".

# Lab 13 — analysis

## Precedence

`ros2 param get /car/fake_gps rate_hz` gave 2.0 with no file (the code default), 1.0 with the file (the
/** section), 4.0 with `--params-file my_gps.yaml -p rate_hz:=4.0` and 1.0 with
`-p rate_hz:=4.0 --params-file my_gps.yaml`. The rule is simply "the last value applied wins", in the
order the items are written, and inside one file the last matching section wins. In a product I would
keep one YAML file per installation, put the common /** section first, and change values only through
launch arguments that are documented, never by a second hidden file.

## Validation

The descriptors refused `ros2 param set /fake_gps rate_hz 5.0` with "Trying to set a read-only
parameter" and 500 m/s with "out of range Min: 0.0, Max: 60.0". My callback refused 45 m/s for the
car with "speed 45.0 m/s too fast for a car (max 40.0)" and 20 m/s for the boat with "speed 20.0 m/s
too fast for a boat (max 15.0)". A range is a property of one parameter; the maximum speed depends on
another parameter, the vehicle, so only a callback that sees both values can express it.

## NAVERA

With gps_timeout_s: 1.0 in the YAML, the product launch still gave 3.0, because estimator.launch.py
passes a dict with gps_timeout_s from its launch argument after the YAML. `ros2 run` with the YAML
alone gave 1.0, and my launch, which includes the file with gps_timeout_s:=2.0, gave 2.0. After setting
fix_max_sigma_m to 2.0, the arbiter answered "GPS fix, uncertainty 3 m > 2 m": the same 3 m receiver is
now DEGRADED.

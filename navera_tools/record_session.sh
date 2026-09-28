#!/bin/bash
# Record a NAVERA test session (drive, flight, bench) into one ROS 2 bag.
#
#   navera_tools/record_session.sh <output_dir> [day|night|cn]
#
# Records every sensor, every source estimate, the arbiter's decision and the
# chosen camera's frames — everything needed to replay the session and to
# measure each source against GPS (navera_tools/evaluate_session.py).
#
# For a measurement session, start the vision pipeline in shadow mode so it
# runs while GPS is valid, e.g.:
#   ros2 launch simulation_web day_pipeline.launch.py shadow_mode:=true default_gps_valid:=false
#
# Size: camera frames dominate (a 1920x1080 bgr8 frame is ~6 MB): record on the
# data disk. Stop with Ctrl-C.
set -u
out="${1:?usage: record_session.sh <output_dir> [day|night|cn]}"
cam="${2:-day}"
case "$cam" in
  day) ns=day ;; night) ns=thermal ;; cn) ns=celestial ;;
  *) echo "unknown pipeline: $cam" >&2; exit 1 ;;
esac
[ -e "$out" ] && { echo "$out exists; choose a new directory" >&2; exit 1; }

topics=(
  /navera/sensors/gps_fix /navera/sensors/gps_vel /navera/sensors/imu
  /navera/sensors/rtc_time /navera/sensors/rtc_status
  /navera/estimate/gps /navera/estimate/day /navera/estimate/night /navera/estimate/cn
  /navera/position /navera/nav_status
  "/$ns/image_raw" "/$ns/frame_meta" "/$ns/frame_done" "/$ns/camera/start"
)
echo "recording ${#topics[@]} topics to $out (camera: /$ns) — Ctrl-C to stop"
exec ros2 bag record -o "$out" "${topics[@]}"

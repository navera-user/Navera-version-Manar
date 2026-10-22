#!/bin/bash
# Inside the navera-humble container (run_isaac_flight.sh starts it): build NAVERA, start its
# real nodes on their own ROS domain, loopback only, and the Isaac link. SIMULATION only.
#
#   gps_node       NAVERA's GPS driver, reading the link's simulated NMEA receiver (a pty)
#   estimator      the arbiter (/navera/position, /navera/nav_status)
#   live_camera    /isaac/camera/image_raw -> undistorted, straightened /day/image_raw + frame_meta
#   day_subscriber the day pipeline (local feature matching against /data/area)
#   isaac_link     the vehicle's sensors + camera from Isaac Sim, and the record
#   vehicle_output (VEHICLE_OUT set: closed loop) NAVERA's position -> the autopilot as GPS_INPUT
#
# Environment: RUN (run name), DAY_ARGS (extra day_subscriber -p ...), CAM_ARGS (extra live_camera -p ...), GIMBAL (true: stabilised camera), VEHICLE_OUT (pymavlink URL of the autopilot), DEGRADED_SIGMA, MAX_SPEED (m/s), GROUND_ALT (site elevation m), LINK_ARGS
# (extra "-p name:=value" for isaac_link), MATCHER (auto = DISK+LightGlue on the GPU | local = SIFT).
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-77} ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash             # (not under set -u: ROS setup reads unset variables)
set -u
cd /ws
pk="navera_msgs navera_common day_pkg camera_pkg navera_estimator gps_pkg navera_output"
if ! colcon build --symlink-install --packages-up-to $pk > /results/colcon.log 2>&1; then
  echo "colcon build failed: /results/colcon.log" >&2; exit 1
fi
set +u; source /ws/install/setup.bash; set -u
export NAVERA_STATE_DIR=/results/state DAY_DATASET_DIR=/data/area TORCH_HOME=/torch_home
mkdir -p "$NAVERA_STATE_DIR"
L=/results/logs; mkdir -p $L
rm -f /results/gps_port /results/lens.yaml /results/navera_ready /results/finished /results/gps_cut   # a re-used run name
share=$(ros2 pkg prefix navera_estimator)/share/navera_estimator/config/estimator_params.yaml
pids=()
ros2 run navera_estimator estimator_node.py --ros-args --params-file "$share" \
  -p max_speed_mps:=${MAX_SPEED:-45.0} > $L/estimator.log 2>&1 & pids+=($!)
ros2 run day_pkg day_subscriber.py --ros-args -p matcher:=${MATCHER:-auto} \
  -p max_speed_mps:=${MAX_SPEED:-45.0} ${DAY_ARGS:-} > $L/day.log 2>&1 & pids+=($!)
if [ -n "${VEHICLE_OUT:-}" ]; then        # closed loop: NAVERA's position to the autopilot (GPS_INPUT)
  ( until ros2 run navera_output vehicle_output_node.py --ros-args -p mavlink_url:=$VEHICLE_OUT \
      -p forward_degraded:=true -p degraded_sigma_m:=${DEGRADED_SIGMA:-30.0} \
      -p max_speed_mps:=${MAX_SPEED:-45.0}; do sleep 2; done ) >> $L/vehicle_output.log 2>&1 &   # until SITL is up
  pids+=($!)
fi
python3 /ws/src/navera/navera_tools/isaac/isaac_link.py --ros-args -p run_dir:=/isaac/runs/$RUN \
  -p results:=/results -p lens_file:=/data/lens/hik_visible_lens.yaml $LINK_ARGS > $L/link.log 2>&1 &
link=$!
until [ -f /results/lens.yaml ]; do                     # written by isaac_link
  kill -0 $link 2>/dev/null || { echo "isaac_link failed: $L/link.log" >&2; kill ${pids[@]}; exit 1; }; sleep 0.5
done
until [ -f /results/gps_port ]; do sleep 0.2; done      # the link's NMEA receiver
ros2 run gps_pkg gps_node.py --ros-args -p serial_port:=$(cat /results/gps_port) > $L/gps.log 2>&1 & pids+=($!)
ros2 run camera_pkg live_camera.py --ros-args -r __ns:=/day -p input:=ros \
  -p input_topic:=/isaac/camera/image_raw -p width:=${CAM_W:-1344} -p height:=${CAM_H:-760} \
  -p calibration_file:=/results/lens.yaml -p fps:=${CAM_FPS:-3.0} -p wait_for_ready:=true \
  -p ready_topic:=/day/localizer_ready -p ground_altitude_m:=${GROUND_ALT:-nan} \
  -p gimbal:=${GIMBAL:-false} $CAM_ARGS > $L/camera.log 2>&1 &
pids+=($!)
trap 'kill ${pids[@]} $link 2>/dev/null; exit 0' INT TERM
# ready marker for the launcher: day_subscriber has its map and models
( until grep -q "awaiting frames\|DayLocalizer ready\|localizer_ready=True" $L/day.log 2>/dev/null; do sleep 1; done; touch /results/navera_ready ) &
wait $link
sleep 2
kill ${pids[@]} 2>/dev/null

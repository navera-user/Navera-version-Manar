#!/bin/bash
# NAVERA demonstration: a simulated mission with GPS jamming, on the real
# arbiter and operator view. No hardware needed. SIMULATED data only.
#
#   navera_tools/run_demo.sh [measured|target] [extra demo_mission.py args]
#
#   measured  vision error as measured today (~440 m median) — the honest default
#   target    vision at the product accuracy target (15 m sigma) — NOT measured
#
# Open http://<jetson-ip>:8181/operator (red SIMULATION banner while it runs).
# Runs on its own ROS domain, local only; never start it on a box in service
# (it would share port 8181 with the real bridge). Stop with Ctrl-C.
set -u
cd "$(dirname "$0")/.."
profile="${1:-measured}"; shift || true
# shellcheck disable=SC1091
set +u; source /opt/ros/humble/setup.bash && source install/setup.bash; set -u
export ROS_DOMAIN_ID="${NAVERA_DEMO_DOMAIN:-78}" ROS_LOCALHOST_ONLY=1 NAVERA_ALLOW_SIM=1
: "${NAVERA_MBTILES:?set NAVERA_MBTILES to the map (.mbtiles) — e.g. source ~/navera_env.sh}"

pids=()
cleanup() {
  for p in "${pids[@]}"; do kill -TERM -- "-$p" 2>/dev/null; done
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

setsid ros2 run navera_estimator estimator_node.py >/dev/null 2>&1 & pids+=($!)
setsid ros2 run simulation_web navera_web_bridge.py --ros-args \
  -p mbtiles_path:="$NAVERA_MBTILES" >/dev/null 2>&1 & pids+=($!)
sleep 3
echo "operator view: http://$(hostname -I | awk '{print $1}'):8181/operator  (Ctrl-C to stop)"
python3 navera_tools/demo_mission.py --profile "$profile" "$@"

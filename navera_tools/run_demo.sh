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
# One demo at a time: a second start is refused. Runs on its own ROS domain,
# loopback only; never start it on a box in service (the real bridge owns
# port 8181). Stop with Ctrl-C. Logs: ~/.navera_demo/
set -u
cd "$(dirname "$0")/.." || exit 1
profile="${1:-measured}"; shift || true
case "$profile" in measured|target) ;; *) echo "profile must be measured or target" >&2; exit 2 ;; esac
: "${NAVERA_MBTILES:?set NAVERA_MBTILES to the map (.mbtiles) — e.g. source ~/navera_env.sh}"

logs="$HOME/.navera_demo"; mkdir -p "$logs"
exec 9>"$logs/demo.lock"
if ! flock -n 9; then
  echo "a NAVERA demo is already running (PID $(cat "$logs/demo.pid" 2>/dev/null || echo ?))." >&2
  echo "Watch it at http://$(hostname -I | awk '{print $1}'):8181/operator, or stop it (Ctrl-C in its terminal, or kill that PID) first." >&2
  exit 1
fi
if ss -ltn 2>/dev/null | grep -q ':8181 '; then
  echo "port 8181 is in use (the NAVERA web service or another bridge): stop it first." >&2
  exit 1
fi
echo $$ > "$logs/demo.pid"

set +u; source /opt/ros/humble/setup.bash && source install/setup.bash; set -u
export ROS_DOMAIN_ID="${NAVERA_DEMO_DOMAIN:-78}" ROS_LOCALHOST_ONLY=1 NAVERA_ALLOW_SIM=1

pids=()
cleanup() {
  for p in "${pids[@]}"; do kill -INT -- "-$p" 2>/dev/null; done
  wait 2>/dev/null
  rm -f "$logs/demo.pid"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

setsid ros2 run navera_estimator estimator_node.py >"$logs/estimator.log" 2>&1 & pids+=($!)
setsid ros2 run simulation_web navera_web_bridge.py --ros-args \
  -p mbtiles_path:="$NAVERA_MBTILES" >"$logs/bridge.log" 2>&1 & pids+=($!)

for _ in $(seq 30); do
  curl -s -m 1 http://127.0.0.1:8181/health >/dev/null && break
  for p in "${pids[@]}"; do
    kill -0 "$p" 2>/dev/null || { echo "a NAVERA node failed to start:" >&2; tail -5 "$logs"/*.log >&2; exit 1; }
  done
  sleep 0.5
done
curl -s -m 1 http://127.0.0.1:8181/health >/dev/null || { echo "web bridge not answering on 8181" >&2; exit 1; }

echo "operator view: http://$(hostname -I | awk '{print $1}'):8181/operator  (Ctrl-C to stop)"
python3 navera_tools/demo_mission.py --profile "$profile" "$@" 2>&1 | tee "$logs/demo_mission.log"

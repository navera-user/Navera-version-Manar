#!/bin/bash
# One closed-loop GPS-denied mission with NAVERA's REAL day pipeline in the loop: the mission
# simulator (navera_tools/run_sim.sh: ArduCopter SITL fed only by navera_output, the camera
# rendered from the map by sim/vision_link.py, the real day_subscriber matching it) driven
# headless by sitl_fault_campaign.py. SIMULATED data only; never on a box installed on a vehicle.
#
#   navera_tools/tests/sitl_real_pipeline.sh [scenario] [out dir]
#     scenario  default S11_gps_cut_forward_sigma30 (see sitl_fault_campaign.py --list)
#
# Needs: ~/navera_env.sh (ROS + NAVERA_MBTILES + DAY_DATASET_DIR + TORCH_HOME), an ArduPilot SITL
# build (copter, rover: $NAVERA_ARDUPILOT, default ~/ardupilot), the campaign route's map area
# prepared once (the simulator prepares it on the first mission: needs internet for tiles the map
# lacks), a CUDA GPU. The whole simulator holds the GPU lock ($NAVERA_GPU_LOCK) for the run.
# Jetson Orin Nano: ~10 min per scenario (1x real time). Stopped by its recorded process group.
set -u
wt="$(cd "$(dirname "$0")/../.." && pwd)"
sc="${1:-S11_gps_cut_forward_sigma30}"
out="${2:-$HOME/.navera_sim/real_pipeline_$(date +%F)}"
lock="${NAVERA_GPU_LOCK:-/tmp/claude-1000/navera_gpu.lock}"
mkdir -p "$out" "$(dirname "$lock")"
echo "simulator from $wt (waiting for the GPU lock $lock)"
export NAVERA_SIM_TLS_PORT="${NAVERA_SIM_TLS_PORT:-8444}"   # 8443 is often taken (tailscale serve)
setsid flock "$lock" nice -n 19 "$wt/navera_tools/tests/sitl_fault_start_sim.sh" >"$out/sim_stdout.log" 2>&1 &
sim=$!
echo "$sim" >"$out/sim.pid"
stop_sim() {
  kill -INT -- "-$sim" 2>/dev/null; sleep 10; kill -TERM -- "-$sim" 2>/dev/null; sleep 3
  kill -KILL -- "-$sim" 2>/dev/null; true
}
trap stop_sim EXIT
# waits as long as the GPU lock is held by others (other GPU jobs queue on the same lock)
until curl -sf http://127.0.0.1:8190/api/state >/dev/null; do
  kill -0 "$sim" 2>/dev/null || { echo "simulator exited: see $out/sim_stdout.log" >&2; exit 1; }
  sleep 2
done
echo "simulator up at $(date +%T)"
nice -n 19 python3 "$wt/navera_tools/tests/sitl_fault_campaign.py" --out "$out" "$sc"

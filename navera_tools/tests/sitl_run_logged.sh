#!/bin/bash
# Runs fault-campaign scenarios with the ROS logger and the MAVLink logger next to each:
#   navera_tools/tests/sitl_run_logged.sh OUTDIR S2_gps_cut_forward_degraded [more scenarios]
# One file pair per scenario: OUTDIR/<S-id>_ros.jsonl, OUTDIR/<S-id>_mav.jsonl (S-id = name up to the first "_").
# The simulator (sitl_fault_start_sim.sh) must be running. SIMULATED runs only.
out="$1"; shift
here="$(cd "$(dirname "$0")" && pwd)"
source ~/navera_env.sh
mkdir -p "$out"
for sc in "$@"; do
  id="${sc%%_*}"
  ROS_DOMAIN_ID=79 ROS_LOCALHOST_ONLY=1 python3 "$here/sitl_ros_logger.py" "$out/${id}_ros.jsonl" >/dev/null 2>&1 & rp=$!
  python3 "$here/sitl_mav_logger.py" "$out/${id}_mav.jsonl" >/dev/null 2>&1 & mp=$!
  python3 "$here/sitl_fault_campaign.py" --out "$out" "$sc"
  kill -TERM $rp $mp 2>/dev/null
  wait $rp $mp 2>/dev/null
done

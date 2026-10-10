#!/bin/bash
# record_campaign.sh — how the fault-injection campaign of lesson 31 was recorded.
# Run by the TEACHER, on the full simulator (teacher only; students fly Part E in Sim Lite).
# Run from a terminal that holds the simulator (lesson 31 folder, sim_ctl.py there):
#     bash /data/academy/31-simulator/record_campaign.sh [scenario.json ...]
# Default: the three scenarios in /data/academy/31-simulator/scenarios/. Each one is a drone
# mission over Sousse (simulated vision "target" profile), with faults at fixed times after the
# drone starts flying to the destination. One simulator session; it is stopped at the end.
# The first two flights of the campaign (sample_flight.csv, campaign/jam_spoof_measured.csv) were recorded
# with record_sample.sh (GPS jammed 60 s, then spoofed by a 2 km jump for 30 s).
set -u
L=~/lessons/31-simulator
D=/data/academy/31-simulator
for p in 8181 8190 8443 5760 5762; do
  ss -ltn | grep -q ":$p " && { echo "port $p busy: the simulator is in use, not starting it"; exit 1; }
done
mkdir -p ~/.navera_sim
cd ~/navera || exit 1
NAVERA_SIM_DOMAIN=$ROS_DOMAIN_ID navera_tools/run_sim.sh > ~/.navera_sim/run_sim.out 2>&1 &
SIM=$!
cd "$L" || exit 1
for i in $(seq 90); do python3 sim_ctl.py status >/dev/null 2>&1 && break; sleep 2; done
python3 sim_ctl.py status || { kill -TERM $SIM; exit 1; }
mkdir -p campaign
if [ $# -eq 0 ]; then set -- $D/scenarios/*.json; fi
for sc in "$@"; do
  python3 sim_ctl.py campaign "$sc" --out-dir campaign
  sleep 5
done
kill -TERM $SIM; wait $SIM
cp ~/.navera_sim/estimator.log campaign/estimator_campaign.log
echo "done: campaign/"

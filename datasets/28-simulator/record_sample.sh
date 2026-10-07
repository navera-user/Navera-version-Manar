#!/bin/bash
# record_sample.sh — how the sample flight of lessons 28/29 was recorded.
# Run in a student sandbox that holds the simulator (lesson 28 folder, sim_ctl.py there):
#     bash /data/academy/28-simulator/record_sample.sh [target|measured]
# Drone mission over Sousse, simulated vision profile; GPS jammed 60 s, then spoofed (2 km jump)
# 30 s. Writes flight.csv, events.log and a copy of the estimator log in the lesson folder.
set -u
VISION="${1:-target}"
L=~/lessons/28-simulator
cd ~/navera || exit 1
NAVERA_SIM_DOMAIN=$ROS_DOMAIN_ID navera_tools/run_sim.sh > ~/.navera_sim/run_sim.out 2>&1 &
SIM=$!
cd "$L" || exit 1
for i in $(seq 90); do python3 sim_ctl.py status >/dev/null 2>&1 && break; sleep 2; done
python3 sim_ctl.py status || { kill -TERM $SIM; exit 1; }
python3 sim_ctl.py mission --vision "$VISION"
python3 sim_ctl.py record --seconds 600 --out flight.csv --events events.log > record.out 2>&1 &
REC=$!
for i in $(seq 150); do python3 sim_ctl.py status | grep -q "^phase enroute" && break; sleep 2; done
python3 sim_ctl.py status
sleep 30; python3 sim_ctl.py fault gps jammed
sleep 60; python3 sim_ctl.py fault gps ok
sleep 40; python3 sim_ctl.py fault gps spoof_jump
sleep 30; python3 sim_ctl.py fault gps ok
sleep 30; python3 sim_ctl.py status
kill -TERM $REC; wait $REC   # (a background job ignores Ctrl+C; rows are flushed every second)
python3 sim_ctl.py stop
kill -TERM $SIM; wait $SIM
cp ~/.navera_sim/estimator.log estimator_copy.log
echo "done: flight.csv events.log estimator_copy.log"

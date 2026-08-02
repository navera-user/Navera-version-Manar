#!/bin/bash
# NAVERA - scenario "perte GPS en vol" (banc de test)
# GPS simule actif -> mission camera (rejeu 30 frames) -> SIGSTOP du simulateur
# pendant les frames sans GPS (18-20, 24) -> DINOv2 doit fournir la position -> retour GPS.
set -u
EV=~/scenario_events.txt; LOG=~/scenario_log.txt
rm -f "$EV" "$LOG"
SIM_PID=$(cat ~/sensor_sim.pid)
( while true; do echo "$(date +%s) $(curl -s -m 2 http://localhost:8181/api/operator_position)" >> "$LOG"; sleep 1; done ) &
MON=$!
echo "$(date +%s) T0_MONITOR" >> "$EV"
sleep 2
curl -s -X POST -H "Content-Type: application/json" -d '{}' http://localhost:8181/api/set_mission >/dev/null
echo "$(date +%s) MISSION_START_camera_rewind_go" >> "$EV"
sleep 28
kill -STOP "$SIM_PID" && echo "$(date +%s) GPS_LOST_sensor_sim_SIGSTOP" >> "$EV"
sleep 28
kill -CONT "$SIM_PID" && echo "$(date +%s) GPS_BACK_sensor_sim_SIGCONT" >> "$EV"
sleep 14
kill "$MON" 2>/dev/null
echo "$(date +%s) END" >> "$EV"

#!/bin/bash
# The lab's terminal steps, exactly as a student types them (run from ~/lessons/02-terminal).
set -e
mkdir -p mission/photos mission/logs mission/docs
mv inbox/*.jpg mission/photos/
mv inbox/*.log mission/logs/
mv inbox/notes_for_pilot.txt mission/docs/notes.txt
ls inbox/*.tmp
rm inbox/*.tmp
rmdir inbox
cp ~/navera/gps_pkg/gps_pkg/config/gps_params.yaml mission/docs/
ls ~/navera > packages.txt
grep SOURCE_ ~/navera/navera_msgs/msg/PositionEstimate.msg > sources.txt
echo "Checked by the ground engineer." >> mission/docs/notes.txt
# the answers, found with the terminal (answers.py of the solution already holds them):
find ~/navera/day_pkg -name "*.py" | wc -l
find ~/navera -name "PositionEstimate.msg"
wc -l ~/navera/navera_msgs/msg/PositionEstimate.msg
grep -rl PositionEstimate ~/navera/day_pkg
find ~/navera -name nmea.py
cat mission/logs/*.log | grep "GPS LOST" | wc -l

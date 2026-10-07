#!/bin/bash
# The lab's terminal steps, as a student types them (run from ~/lessons/02-terminal).
set -e
mkdir -p mission/photos mission/logs mission/docs mission/bin
mv inbox/*.jpg mission/photos/
mv inbox/*.log mission/logs/
mv inbox/notes_for_pilot.txt mission/docs/notes.txt
mv inbox/preflight.sh mission/bin/
ls inbox/*.tmp
rm inbox/*.tmp
rmdir inbox
chmod +x mission/bin/preflight.sh
./mission/bin/preflight.sh
cp ~/navera/gps_pkg/gps_pkg/config/gps_params.yaml mission/docs/
env | grep '^ROS_' | sort > ros_env.txt
ls ~/navera/README.md ~/navera/NO_SUCH_FILE.md > ls_out.txt 2> ls_err.txt || true
./fake_node.sh &
sleep 1
pid=$(cat fake_node.pid)
kill "$pid"
sleep 1.5
chmod +x mission/bin/log_report.sh
for f in mission/logs/*.log; do
    ./mission/bin/log_report.sh "$f" > "mission/docs/report_$(basename "$f" .log).txt"
done
sed -i "s/^E1 = -1/E1 = $ROS_DOMAIN_ID/" answers.py

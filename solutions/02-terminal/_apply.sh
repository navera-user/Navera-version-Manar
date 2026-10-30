#!/bin/bash
# The lab's terminal steps, as a student types them (run from ~/lessons/02-terminal by try_lesson.py).
set -e
./box.sh start
mkdir -p mission/photos mission/logs mission/docs mission/bin mission/deploy
mv inbox/*.jpg mission/photos/
mv inbox/*.log mission/logs/
mv inbox/notes_for_pilot.txt mission/docs/notes.txt
mv inbox/preflight.sh mission/bin/
ls inbox/*.tmp
rm inbox/*.tmp
rmdir inbox
chmod u+x mission/bin/preflight.sh
./mission/bin/preflight.sh || echo "(preflight reported a problem)"
env | grep '^ROS_' | sort > ros_env.txt
ls navera_lite.yaml no_such_file.yaml > ls_out.txt 2> ls_err.txt || true
# Step 6: the orphan is the arbiter whose parent is PID 1
for pid in $(pgrep -f "box/bin/navera_lite_arbiter"); do
    if [ "$(ps -o ppid= -p "$pid" | tr -d ' ')" = 1 ]; then orphan=$pid; fi
done
kill "$orphan"
sleep 4                 # a student needs several seconds before the next kill
# observe the supervisor: stop the supervised arbiter, it comes back with a new PID
for pid in $(pgrep -f "box/bin/navera_lite_arbiter"); do kill "$pid"; done
sleep 3
cam=$(pgrep -f "box/bin/camera")
kill "$cam"
sleep 3
kill -9 "$cam"
sleep 2
./box.sh stop
chmod u+x mission/bin/log_report.sh
for f in mission/logs/*.log; do
    ./mission/bin/log_report.sh "$f" > "mission/docs/report_$(basename "$f" .log).txt"
done
sed -i "s/^E1 = -1/E1 = $ROS_DOMAIN_ID/; s/^P3 = 0/P3 = $(stat -c %a mission/bin/preflight.sh)/" answers.py

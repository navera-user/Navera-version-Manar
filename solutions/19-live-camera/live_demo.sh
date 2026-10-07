#!/bin/bash
# Lesson 19 — run NAVERA's REAL live camera node on the recorded frames, in one command:
#   1. replay_camera.py  plays the "camera" (recorded frames) and a fake IMU
#   2. live_camera.py    NAVERA's own node, from your copy ~/navera (camera_pkg)
#   3. watch_live.py     receives what NAVERA publishes and saves it in out/
# Usage:  bash live_demo.sh                 (camera level)
#         bash live_demo.sh --pitch 15      (arguments go to replay_camera.py)
CALIB=/data/academy/19-live-camera/insta360_top.yaml
set -m        # each background program in its own group: Ctrl+C reaches it, we can stop it
stop() { kill -INT -- -$REPLAY -$LIVE 2>/dev/null; wait 2>/dev/null; }
trap 'stop; exit 130' INT

python3 replay_camera.py "$@" &
REPLAY=$!

# NAVERA's live camera, fed by a ROS image topic instead of the USB camera:
ros2 run camera_pkg live_camera.py --ros-args -r __ns:=/day \
    -p input:=ros -p input_topic:=/vehicle/camera/image_raw \
    -p width:=1920 -p height:=1080 -p crop:=top \
    -p calibration_file:=$CALIB -p wait_for_ready:=false -p fps:=1.0 &
LIVE=$!

python3 watch_live.py --frames 3
RESULT=$?

stop
exit $RESULT

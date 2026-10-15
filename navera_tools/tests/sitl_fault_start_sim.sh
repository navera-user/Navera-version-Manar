#!/bin/bash
# Starts the mission simulator with THIS worktree's python packages first on PYTHONPATH
# (executables and share files still resolve through the install tree of ~/Navera, so check
# with sitl_fault_campaign.py that the code under test is the worktree's: see the
# "code under test" line the node logs). SIMULATED runs only.
wt="$(cd "$(dirname "$0")/../.." && pwd)"
source ~/navera_env.sh
pp=""
for p in camera_pkg cn_pkg day_pkg gps_pkg imu_pkg isaac_common_py isaac_ros_common isaac_ros_launch_utils \
         isaac_ros_rosbag_utils isaac_ros_test isaac_ros_test_cmake navera_common navera_estimator navera_output \
         night_pkg rtc_pkg simulation_web vision_pkg; do pp="$pp$wt/$p:"; done
export PYTHONPATH="$pp$PYTHONPATH"
cd "$wt"
exec navera_tools/run_sim.sh

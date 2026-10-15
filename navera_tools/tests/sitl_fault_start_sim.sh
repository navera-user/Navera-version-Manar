#!/bin/bash
# start the simulator from the worktree (product code of branch fix/coast-throughput), cwd = worktree
source ~/navera_env.sh
export PYTHONPATH="/home/shadow-team/navera-wt/camera_pkg:/home/shadow-team/navera-wt/cn_pkg:/home/shadow-team/navera-wt/day_pkg:/home/shadow-team/navera-wt/gps_pkg:/home/shadow-team/navera-wt/imu_pkg:/home/shadow-team/navera-wt/isaac_common_py:/home/shadow-team/navera-wt/isaac_ros_common:/home/shadow-team/navera-wt/isaac_ros_launch_utils:/home/shadow-team/navera-wt/isaac_ros_rosbag_utils:/home/shadow-team/navera-wt/isaac_ros_test:/home/shadow-team/navera-wt/isaac_ros_test_cmake:/home/shadow-team/navera-wt/navera_common:/home/shadow-team/navera-wt/navera_estimator:/home/shadow-team/navera-wt/navera_output:/home/shadow-team/navera-wt/night_pkg:/home/shadow-team/navera-wt/rtc_pkg:/home/shadow-team/navera-wt/simulation_web:/home/shadow-team/navera-wt/vision_pkg:$PYTHONPATH"
cd ~/navera-wt
exec navera_tools/run_sim.sh

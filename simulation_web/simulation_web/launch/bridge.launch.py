#!/usr/bin/env python3
"""
bridge.launch.py — the ROS→web bridge, alone, independent of any pipeline.

The bridge is the only process that binds the HTTP port (8181 by default), so
running exactly one of it is what allows the localization pipelines to coexist:
before this split, day_sim / night_sim / cn_sim each started their own bridge on
8181 and the second one to start died on bind.

The bridge is not a passive viewer — it also serves the mission control plane
(POST /api/set_mission, publishing `start_topic`). Which pipeline it drives is
therefore a parameter, not a hardcoded choice. Ownership of mission start will
move to the arbiter (navera_estimator) once that exists.

Every topic is an argument, so one launch file serves day, night and celestial:

  ros2 launch simulation_web bridge.launch.py            # day (defaults)
  ros2 launch simulation_web bridge.launch.py \
       status_topic:=/night/night_status \
       fix_topic:=/night/position_estimate \
       start_topic:=/thermal/camera/start
  ros2 launch simulation_web bridge.launch.py \
       bridge_executable:=navera_stellar_bridge.py bridge_name:=navera_stellar_bridge \
       status_topic:=/cn/cn_status fix_topic:=/cn/position_estimate \
       start_topic:=/celestial/camera/start
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_mbtiles = os.environ.get('NAVERA_MBTILES', '/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles')

    return LaunchDescription([
        # Which bridge binary. navera_web_bridge serves day/night and renders the
        # arbiter's decision on /operator; navera_stellar_bridge serves celestial
        # and has no /operator. Merging the two is a task of its own — see the
        # package README.
        DeclareLaunchArgument('bridge_executable', default_value='navera_web_bridge.py'),
        DeclareLaunchArgument('bridge_name',       default_value='navera_web_bridge'),

        # Which pipeline the bridge listens to, and which camera it starts.
        # The arbiter topics (/navera/position, /navera/nav_status) are NOT
        # arguments: there is one arbiter, so they never vary per pipeline.
        DeclareLaunchArgument('status_topic',  default_value='/day/day_status'),
        DeclareLaunchArgument('fix_topic',     default_value='/day/position_estimate'),
        DeclareLaunchArgument('start_topic',   default_value='/day/camera/start'),

        DeclareLaunchArgument('mbtiles_path', default_value=default_mbtiles),
        DeclareLaunchArgument('web_host',     default_value='0.0.0.0'),
        DeclareLaunchArgument('web_port',     default_value='8181'),

        Node(
            package='simulation_web',
            executable=LaunchConfiguration('bridge_executable'),
            name=LaunchConfiguration('bridge_name'),
            output='screen',
            # Any node exiting ends the launch, so the systemd unit
            # (Restart=always) restarts the whole pipeline.
            on_exit=Shutdown(reason='node exited'),
            parameters=[{
                'status_topic':  LaunchConfiguration('status_topic'),
                'fix_topic':     LaunchConfiguration('fix_topic'),
                'start_topic':   LaunchConfiguration('start_topic'),
                'mbtiles_path':  LaunchConfiguration('mbtiles_path'),
                'web_host':      LaunchConfiguration('web_host'),
                'web_port':      LaunchConfiguration('web_port'),
            }],
        ),
    ])

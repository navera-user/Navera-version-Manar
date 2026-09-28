#!/usr/bin/env python3
"""
estimator.launch.py — start the NAVERA position arbiter (GPS > day > night > celestial).

Examples:
  ros2 launch navera_estimator estimator.launch.py
  ros2 launch navera_estimator estimator.launch.py gps_timeout_s:=2.0
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('navera_estimator')
    cfg = os.path.join(pkg_share, 'config', 'estimator_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('publish_rate_hz', default_value='5.0'),
        DeclareLaunchArgument('gps_timeout_s',   default_value='3.0'),
        DeclareLaunchArgument('imu_timeout_s',   default_value='1.0'),

        Node(
            package='navera_estimator',
            executable='estimator_node.py',
            name='estimator_node',
            output='screen',
            # Any node exiting ends the launch, so the systemd unit
            # (Restart=always) restarts the whole pipeline.
            on_exit=Shutdown(reason='node exited'),
            parameters=[
                cfg,
                {
                    'publish_rate_hz': LaunchConfiguration('publish_rate_hz'),
                    'gps_timeout_s':   LaunchConfiguration('gps_timeout_s'),
                    'imu_timeout_s':   LaunchConfiguration('imu_timeout_s'),
                },
            ],
        ),
    ])
